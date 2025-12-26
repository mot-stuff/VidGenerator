#!/usr/bin/env python3
"""
Multi-user SaaS TTS Shorts Generator
"""

import os
import shutil
import threading
import time
import uuid
from pathlib import Path
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_from_directory, render_template, redirect, url_for, after_this_request, send_file
from flask_login import LoginManager, login_required, current_user
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from models import db, User, VideoJob, IPBan
from auth import auth
from app.tts.tiktok import synthesize_tiktok_tts, TIKTOK_VOICES
from app.captions import (
    allocate_caption_spans,
    allocate_karaoke_word_spans,
    whisper_word_timestamps,
    words_to_karaoke_spans,
)
from app.video import compose_video_with_tts
from app.youtube_uploader import YouTubeUploadManager, create_video_metadata_from_file

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///tts_saas.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# No file size limits on VPS
# app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # Removed for VPS

# Fix for PostgreSQL connection strings (Railway/Heroku)
if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql://')

# Initialize extensions
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'

# Register blueprints
app.register_blueprint(auth)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def get_user_directory(user_id: int, subdir: str = "") -> Path:
    """Get user-specific directory"""
    base_dir = Path("user_data") / str(user_id)
    if subdir:
        base_dir = base_dir / subdir
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir

def get_user_youtube_manager(user_id: int) -> YouTubeUploadManager:
    """Get user-specific YouTube manager"""
    user_dir = get_user_directory(user_id, "youtube")
    return YouTubeUploadManager(
        credentials_path=user_dir / "youtube_credentials.json",
        token_path=user_dir / "youtube_token.json",
        upload_queue_path=user_dir / "upload_queue.json",
        uploaded_videos_path=user_dir / "uploaded_videos.json"
    )

def _ensure_user_columns() -> None:
    """Ensure new User columns exist on existing DBs (no migration tool in this repo)."""
    uri = app.config.get('SQLALCHEMY_DATABASE_URI', '') or ''
    is_sqlite = uri.startswith('sqlite:')

    with db.engine.begin() as conn:
        if not is_sqlite:
            conn.exec_driver_sql('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE;')
            conn.exec_driver_sql('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS daily_quota INTEGER DEFAULT 3;')
            conn.exec_driver_sql('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS daily_videos_used INTEGER DEFAULT 0;')
            conn.exec_driver_sql('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS daily_last_reset_date DATE DEFAULT CURRENT_DATE;')
            conn.exec_driver_sql('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS last_login_ip VARCHAR(64);')
            return

        existing: set[str] = set()
        try:
            res = conn.exec_driver_sql('PRAGMA table_info(user);')
            for row in res.fetchall():
                existing.add(row[1])
        except Exception:
            return

        def add_col(col_sql: str, col_name: str) -> None:
            if col_name in existing:
                return
            try:
                conn.exec_driver_sql(f'ALTER TABLE user ADD COLUMN {col_sql};')
            except Exception:
                pass

        add_col('is_admin BOOLEAN DEFAULT 0', 'is_admin')
        add_col('daily_quota INTEGER DEFAULT 3', 'daily_quota')
        add_col('daily_videos_used INTEGER DEFAULT 0', 'daily_videos_used')
        add_col('daily_last_reset_date DATE', 'daily_last_reset_date')
        add_col('last_login_ip TEXT', 'last_login_ip')

def _get_client_ip() -> str:
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip.strip()
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    return (request.remote_addr or "unknown").strip()

def _is_ip_banned(ip: str) -> bool:
    if not ip or ip == "unknown":
        return False
    ban = IPBan.query.filter_by(ip=ip).first()
    if not ban:
        return False
    if ban.banned_until is None:
        return True
    try:
        return ban.banned_until > datetime.utcnow()
    except Exception:
        return True

@app.before_request
def _block_banned_ips():
    # Allow static assets through; admin sessions can still operate.
    if request.endpoint == "static":
        return None
    if current_user.is_authenticated and getattr(current_user, "is_admin", False):
        return None
    ip = _get_client_ip()
    if _is_ip_banned(ip):
        return "Access denied.", 403

def _sync_admin_emails() -> None:
    raw = os.getenv('ADMIN_EMAILS', '')
    emails = [e.strip().lower() for e in raw.split(',') if e.strip()]
    if not emails:
        return
    users = User.query.filter(User.email.in_(emails)).all()
    changed = False
    for u in users:
        if not getattr(u, 'is_admin', False):
            u.is_admin = True
            changed = True
    if changed:
        db.session.commit()

def admin_required(fn):
    from functools import wraps

    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not getattr(current_user, 'is_admin', False):
            return redirect(url_for('dashboard'))
        return fn(*args, **kwargs)

    return wrapper

def _cleanup_expired_user_artifacts(user_id: int, ttl_s: int = 120) -> None:
    now_ts = time.time()

    # Delete old files (uploads/outputs/temp) to keep disk usage bounded
    for subdir in ("uploads", "outputs", "temp"):
        p = Path("user_data") / str(user_id) / subdir
        if not p.exists():
            continue
        for f in p.iterdir():
            try:
                if not f.is_file():
                    continue
                if (now_ts - f.stat().st_mtime) > ttl_s:
                    f.unlink()
            except Exception:
                pass

    # Delete old DB job records so they disappear from the UI
    try:
        jobs = VideoJob.query.filter_by(user_id=user_id).all()
        now_dt = datetime.utcnow()

        for job in jobs:
            age_s = None
            try:
                if job.completed_at:
                    # Some older runs stored a float timestamp; handle both.
                    if isinstance(job.completed_at, (int, float)):
                        age_s = now_ts - float(job.completed_at)
                    else:
                        age_s = (now_dt - job.completed_at).total_seconds()
            except Exception:
                age_s = None

            if age_s is None:
                try:
                    age_s = (now_dt - job.created_at).total_seconds()
                except Exception:
                    age_s = None

            if age_s is not None and age_s > ttl_s:
                try:
                    db.session.delete(job)
                except Exception:
                    pass

        db.session.commit()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass

# Routes
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('auth.login'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', user=current_user)

@app.route('/admin', methods=['GET'])
@login_required
@admin_required
def admin_dashboard():
    users = User.query.order_by(User.created_at.desc()).limit(500).all()
    bans = IPBan.query.order_by(IPBan.created_at.desc()).limit(500).all()
    return render_template('admin.html', users=users, bans=bans)

@app.route('/admin/user/<int:user_id>/update', methods=['POST'])
@login_required
@admin_required
def admin_update_user(user_id: int):
    u = User.query.get_or_404(user_id)
    daily_quota = (request.form.get('daily_quota') or '').strip()
    is_admin = (request.form.get('is_admin') or '').strip()

    if daily_quota:
        try:
            u.daily_quota = max(0, int(daily_quota))
        except Exception:
            pass

    if is_admin in ('0', '1'):
        u.is_admin = is_admin == '1'

    db.session.commit()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/user/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_user(user_id: int):
    u = User.query.get_or_404(user_id)
    # Prevent self-delete via UI
    if u.id == current_user.id:
        return redirect(url_for('admin_dashboard'))

    try:
        VideoJob.query.filter_by(user_id=u.id).delete(synchronize_session=False)
        db.session.delete(u)
        db.session.commit()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass

    # Best-effort cleanup of user files
    try:
        shutil.rmtree(Path("user_data") / str(user_id), ignore_errors=True)
    except Exception:
        pass

    return redirect(url_for('admin_dashboard'))

@app.route('/admin/user/<int:user_id>/ban_ip', methods=['POST'])
@login_required
@admin_required
def admin_ban_user_ip(user_id: int):
    u = User.query.get_or_404(user_id)
    ip = (getattr(u, "last_login_ip", None) or "").strip()
    if not ip:
        return redirect(url_for('admin_dashboard'))

    days_raw = (request.form.get("days") or "").strip()
    reason = (request.form.get("reason") or "").strip() or None
    banned_until = None
    if days_raw:
        try:
            days = max(0, int(days_raw))
            if days > 0:
                banned_until = datetime.utcnow() + timedelta(days=days)
        except Exception:
            banned_until = None

    ban = IPBan.query.filter_by(ip=ip).first()
    try:
        if ban is None:
            ban = IPBan(ip=ip, reason=reason, banned_until=banned_until)
            db.session.add(ban)
        else:
            ban.reason = reason or ban.reason
            ban.banned_until = banned_until
        db.session.commit()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/ipban/add', methods=['POST'])
@login_required
@admin_required
def admin_ipban_add():
    ip = (request.form.get("ip") or "").strip()
    if not ip:
        return redirect(url_for('admin_dashboard'))

    days_raw = (request.form.get("days") or "").strip()
    reason = (request.form.get("reason") or "").strip() or None
    banned_until = None
    if days_raw:
        try:
            days = max(0, int(days_raw))
            if days > 0:
                banned_until = datetime.utcnow() + timedelta(days=days)
        except Exception:
            banned_until = None

    ban = IPBan.query.filter_by(ip=ip).first()
    try:
        if ban is None:
            ban = IPBan(ip=ip, reason=reason, banned_until=banned_until)
            db.session.add(ban)
        else:
            ban.reason = reason or ban.reason
            ban.banned_until = banned_until
        db.session.commit()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/ipban/<int:ban_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_ipban_delete(ban_id: int):
    ban = IPBan.query.get_or_404(ban_id)
    try:
        db.session.delete(ban)
        db.session.commit()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
    return redirect(url_for('admin_dashboard'))

@app.route('/api/status')
@login_required
def get_status():
    return jsonify({
        'user': {
            'email': current_user.email,
            'status': 'active',
            'is_admin': bool(getattr(current_user, 'is_admin', False)),
            'daily_quota': current_user.get_daily_quota() if hasattr(current_user, 'get_daily_quota') else 3,
            'daily_remaining': current_user.remaining_daily_quota() if hasattr(current_user, 'remaining_daily_quota') else 0,
        }
    })

@app.route('/api/upload_video', methods=['POST'])
@login_required
def upload_video():
    if 'video' not in request.files:
        return jsonify({'error': 'No video file'}), 400
    
    file = request.files['video']
    video_type = request.form.get('type', 'video1')
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if file and file.filename.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
        # Save to user-specific directory
        user_dir = get_user_directory(current_user.id, "uploads")
        filename = f"{video_type}_{int(time.time())}_{file.filename}"
        filepath = user_dir / filename
        file.save(filepath)
        
        return jsonify({
            'success': True, 
            'filename': file.filename, 
            'file_id': filename,
            'path': str(filepath)
        })
    
    return jsonify({'error': 'Invalid file type'}), 400

@app.route('/api/upload_csv', methods=['POST'])
@login_required
def upload_csv():
    if 'csv' not in request.files:
        return jsonify({'error': 'No CSV file'}), 400
    
    file = request.files['csv']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    try:
        import csv
        import io
        
        file_content = file.read().decode('utf-8')
        texts = []
        
        if ',' in file_content or '"' in file_content:
            csv_reader = csv.reader(io.StringIO(file_content))
            for row in csv_reader:
                if row and row[0].strip():
                    texts.append(row[0].strip())
        else:
            for line in file_content.split('\n'):
                line = line.strip()
                if line:
                    texts.append(line)
        
        if texts:
            return jsonify({'success': True, 'texts': texts, 'count': len(texts)})
        else:
            return jsonify({'error': 'No valid text found in file'}), 400
            
    except Exception as e:
        return jsonify({'error': f'Error processing CSV: {e}'}), 400

@app.route('/api/generate_video', methods=['POST'])
@login_required
def generate_video():
    
    data = request.json
    text = data.get('text', '').strip()
    video_file_id = data.get('video_file_id')
    video2_file_id = data.get('video2_file_id')
    split_screen_enabled = data.get('split_screen_enabled', False)
    user_id = current_user.id
    
    if not text:
        return jsonify({'error': 'Please enter some text'}), 400
    if not video_file_id:
        return jsonify({'error': 'Please upload a video first'}), 400
    if split_screen_enabled and not video2_file_id:
        return jsonify({'error': 'Please upload a second video for split screen mode'}), 400

    # Daily quota enforcement (admin bypasses)
    try:
        if not current_user.can_generate_today(1):
            remaining = current_user.remaining_daily_quota()
            return jsonify({'error': f'Daily limit reached. Remaining today: {remaining}'}), 429
        current_user.consume_daily_quota(1)
    except Exception:
        return jsonify({'error': 'Quota check failed'}), 500
    
    # Check if uploaded files exist
    user_upload_dir = get_user_directory(current_user.id, "uploads")
    video_path = user_upload_dir / video_file_id
    if not video_path.exists():
        return jsonify({'error': 'Uploaded video not found'}), 400
    
    video2_path = None
    if split_screen_enabled:
        video2_path = user_upload_dir / video2_file_id
        if not video2_path.exists():
            return jsonify({'error': 'Second uploaded video not found'}), 400
    
    def generate_worker(user_id: int, text: str, video_file_id: str, video2_file_id: str | None, split_screen_enabled: bool):
        job_id = str(uuid.uuid4())
        with app.app_context():
            user_output_dir = get_user_directory(user_id, "outputs")
            user_temp_dir = get_user_directory(user_id, "temp")

            # Check if uploaded files exist (thread-safe; no current_user access)
            user_upload_dir = get_user_directory(user_id, "uploads")
            video_path = user_upload_dir / video_file_id
            video2_path = None
            if split_screen_enabled and video2_file_id:
                video2_path = user_upload_dir / video2_file_id

            # Create video job record
            job = VideoJob(
                user_id=user_id,
                filename=video_file_id,
                text_content=text,
                status='processing'
            )
            db.session.add(job)
            db.session.commit()

            try:
                # Generate TTS
                voice_code = "en_us_002"
                tts_path = synthesize_tiktok_tts(text=text, voice=voice_code, out_dir=user_temp_dir)

                # Generate captions
                spans = allocate_caption_spans(text=text, total_duration_s=None, audio_path=tts_path)
                try:
                    words = whisper_word_timestamps(str(tts_path), language="en", original_text=text)
                    word_spans = words_to_karaoke_spans(words)
                except Exception:
                    word_spans = allocate_karaoke_word_spans(text=text, total_duration_s=None, audio_path=tts_path)

                # Generate output
                output_filename = f"{job_id}_output.mp4"
                output_path = user_output_dir / output_filename

                import random
                from moviepy.editor import VideoFileClip
                with VideoFileClip(str(video_path)) as video_clip:
                    video_duration = video_clip.duration
                random_start = random.uniform(0.0, max(0.0, video_duration - 1.0))

                compose_video_with_tts(
                    video_path=str(video_path),
                    tts_audio_path=tts_path,
                    caption_spans=spans,
                    output_path=output_path,
                    chosen_start_time=random_start,
                    crf=18,
                    video_bitrate=None,
                    karaoke_word_spans=word_spans,
                    add_background_music=True,
                    bg_music_volume=0.15,
                    bg_music_dir="assets/background_music",
                    split_screen_enabled=split_screen_enabled,
                    video_path2=str(video2_path) if video2_path else None,
                    tail_padding_s=3.0,
                )

                # Update job status
                job.status = 'completed'
                job.result_path = str(output_path)
                job.completed_at = datetime.utcnow()

                # Clean up temp files
                try:
                    tts_path.unlink()
                except Exception:
                    pass

                # Delete uploaded source videos to avoid accumulating large files
                try:
                    if video_path.exists():
                        video_path.unlink()
                except Exception:
                    pass
                try:
                    if video2_path and video2_path.exists():
                        video2_path.unlink()
                except Exception:
                    pass

            except Exception as e:
                job.status = 'failed'
                job.error_message = str(e)

            db.session.commit()
            db.session.remove()
    
    threading.Thread(
        target=generate_worker,
        args=(user_id, text, video_file_id, video2_file_id, split_screen_enabled),
        daemon=True
    ).start()
    return jsonify({'success': True, 'message': 'Video generation started'})

@app.route('/api/jobs')
@login_required
def get_jobs():
    """Get user's video jobs"""
    _cleanup_expired_user_artifacts(current_user.id, ttl_s=120)
    jobs = VideoJob.query.filter_by(user_id=current_user.id).order_by(VideoJob.created_at.desc()).limit(20).all()
    return jsonify([{
        'id': job.id,
        'filename': job.filename,
        'status': job.status,
        'created_at': job.created_at.isoformat(),
        'completed_at': job.completed_at.isoformat() if job.completed_at else None,
        'error_message': job.error_message,
        'can_download': job.status == 'completed' and job.result_path
    } for job in jobs])

@app.route('/api/download/<int:job_id>')
@login_required
def download_result(job_id):
    """Download completed video"""
    job = VideoJob.query.filter_by(id=job_id, user_id=current_user.id).first()
    if not job or job.status != 'completed' or not job.result_path:
        return jsonify({'error': 'Video not found or not ready'}), 404
    
    result_path = Path(job.result_path)
    if not result_path.exists():
        return jsonify({'error': 'Video file not found'}), 404

    @after_this_request
    def _cleanup(response):
        try:
            if result_path.exists():
                result_path.unlink()
        except Exception:
            pass
        try:
            # Remove job record so we don't retain history/storage
            db.session.delete(job)
            db.session.commit()
        except Exception:
            pass
        return response

    return send_file(result_path, as_attachment=True, download_name=result_path.name)

@app.route('/api/generate_batch', methods=['POST'])
@login_required
def generate_batch():
    data = request.json
    texts = data.get('texts', [])
    video_file_id = data.get('video_file_id')
    video2_file_id = data.get('video2_file_id')
    split_screen_enabled = data.get('split_screen_enabled', False)
    user_id = current_user.id
    
    if not texts:
        return jsonify({'error': 'No texts provided'}), 400
    if not video_file_id:
        return jsonify({'error': 'Please upload a video first'}), 400
    if split_screen_enabled and not video2_file_id:
        return jsonify({'error': 'Please upload a second video for split screen mode'}), 400

    # Daily quota enforcement (admin bypasses)
    try:
        requested = len(texts)
        if requested <= 0:
            return jsonify({'error': 'No texts provided'}), 400
        if not current_user.can_generate_today(requested):
            remaining = current_user.remaining_daily_quota()
            return jsonify({'error': f'Daily limit reached. Remaining today: {remaining}'}), 429
        current_user.consume_daily_quota(requested)
    except Exception:
        return jsonify({'error': 'Quota check failed'}), 500
    
    # Check if uploaded files exist
    user_upload_dir = get_user_directory(current_user.id, "uploads")
    video_path = user_upload_dir / video_file_id
    if not video_path.exists():
        return jsonify({'error': 'Uploaded video not found'}), 400
    
    video2_path = None
    if split_screen_enabled:
        video2_path = user_upload_dir / video2_file_id
        if not video2_path.exists():
            return jsonify({'error': 'Second uploaded video not found'}), 400
    
    def batch_worker(user_id: int, texts: list[str], video_file_id: str, video2_file_id: str | None, split_screen_enabled: bool):
        with app.app_context():
            user_output_dir = get_user_directory(user_id, "outputs")
            user_temp_dir = get_user_directory(user_id, "temp")
            youtube_manager = get_user_youtube_manager(user_id)
            user_upload_dir = get_user_directory(user_id, "uploads")
            video_path = user_upload_dir / video_file_id
            video2_path = None
            if split_screen_enabled and video2_file_id:
                video2_path = user_upload_dir / video2_file_id
        
            try:
                total = len(texts)
                for i, text in enumerate(texts, 1):
                    job_id = str(uuid.uuid4())
                    
                    # Create video job record
                    job = VideoJob(
                        user_id=user_id,
                        filename=f"batch_{i:03d}_{video_file_id}",
                        text_content=text,
                        status='processing'
                    )
                    db.session.add(job)
                    db.session.commit()
                    
                    try:
                        # Generate TTS
                        voice_code = "en_us_002"
                        tts_path = synthesize_tiktok_tts(text=text, voice=voice_code, out_dir=user_temp_dir)
                        
                        # Generate captions
                        spans = allocate_caption_spans(text=text, total_duration_s=None, audio_path=tts_path)
                        try:
                            words = whisper_word_timestamps(str(tts_path), language="en", original_text=text)
                            word_spans = words_to_karaoke_spans(words)
                        except Exception:
                            word_spans = allocate_karaoke_word_spans(text=text, total_duration_s=None, audio_path=tts_path)
                        
                        # Generate output
                        output_filename = f"batch_{i:03d}_{job_id}_output.mp4"
                        output_path = user_output_dir / output_filename
                        
                        import random
                        from moviepy.editor import VideoFileClip
                        with VideoFileClip(str(video_path)) as video_clip:
                            video_duration = video_clip.duration
                        random_start = random.uniform(0.0, max(0.0, video_duration - 1.0))
                        
                        compose_video_with_tts(
                            video_path=str(video_path),
                            tts_audio_path=tts_path,
                            caption_spans=spans,
                            output_path=output_path,
                            chosen_start_time=random_start,
                            crf=18,
                            video_bitrate=None,
                            karaoke_word_spans=word_spans,
                            add_background_music=True,
                            bg_music_volume=0.15,
                            bg_music_dir="assets/background_music",
                            split_screen_enabled=split_screen_enabled,
                            video_path2=str(video2_path) if video2_path else None,
                            tail_padding_s=3.0,
                        )
                        
                        # Update job status
                        job.status = 'completed'
                        job.result_path = str(output_path)
                        job.completed_at = datetime.utcnow()
                        
                        # Clean up temp files
                        try:
                            tts_path.unlink()
                        except Exception:
                            pass
                            
                    except Exception as e:
                        job.status = 'failed'
                        job.error_message = str(e)
                    
                    db.session.commit()
                    
                    # Small delay between videos
                    if i < total:
                        time.sleep(2)
                        
            except Exception as e:
                print(f"Batch generation error: {e}")
            finally:
                db.session.remove()
    
    threading.Thread(
        target=batch_worker,
        args=(user_id, texts, video_file_id, video2_file_id, split_screen_enabled),
        daemon=True
    ).start()
    return jsonify({'success': True, 'message': 'Batch generation started'})

def init_database():
    """Initialize database safely"""
    try:
        with app.app_context():
            db.create_all()
            _ensure_user_columns()
            _sync_admin_emails()
            
            # Create a test user if none exist
            if not User.query.first():
                test_user = User(email='test@example.com')
                test_user.set_password('password')
                db.session.add(test_user)
                db.session.commit()
                print("✅ Created test user: test@example.com / password")
    except Exception as e:
        print(f"⚠️ Database initialization error: {e}")
        print("Will try to connect on first request...")

if __name__ == '__main__':
    # Initialize database
    init_database()
    
    # Production vs development
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_ENV') != 'production'
    host = '0.0.0.0'  # Always bind to all interfaces for Render
    
    print("🚀 Starting Multi-User TTS Shorts Generator...")
    print(f"📱 Opening at http://{'localhost' if debug else '0.0.0.0'}:{port}")
    print("🛑 Press Ctrl+C to stop")
    app.run(debug=debug, host=host, port=port)

# For production servers (Gunicorn)
init_database()
