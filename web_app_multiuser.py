#!/usr/bin/env python3
"""
Multi-user SaaS TTS Shorts Generator
"""

import os
import shutil
import threading
import time
import uuid
import json
from pathlib import Path
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_from_directory, render_template, redirect, url_for, after_this_request, send_file, abort, session, flash
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
app.config['GAM_REWARDED_AD_UNIT_PATH'] = os.getenv('GAM_REWARDED_AD_UNIT_PATH', '').strip()
app.config['STRIPE_SECRET_KEY'] = os.getenv('STRIPE_SECRET_KEY', '').strip()
app.config['STRIPE_WEBHOOK_SECRET'] = os.getenv('STRIPE_WEBHOOK_SECRET', '').strip()
app.config['PRESET_VIDEO1_PATH'] = os.getenv('PRESET_VIDEO1_PATH', '').strip()
app.config['PRESET_VIDEO2_PATH'] = os.getenv('PRESET_VIDEO2_PATH', '').strip()
app.config['PRESET_SOAP_CUTTING_PATH'] = os.getenv('PRESET_SOAP_CUTTING_PATH', '').strip()

# Convenience default for local/dev: if user dropped a preset into static/video/preset_parkour.mp4
# and PRESET_VIDEO1_PATH isn't set, use it automatically.
if not app.config['PRESET_VIDEO1_PATH']:
    try:
        _default_preset = Path("static") / "video" / "preset_parkour.mp4"
        if _default_preset.exists() and _default_preset.is_file():
            app.config['PRESET_VIDEO1_PATH'] = str(_default_preset)
    except Exception:
        pass

if not app.config['PRESET_SOAP_CUTTING_PATH']:
    try:
        _default_preset = Path("static") / "video" / "soap.mp4"
        if _default_preset.exists() and _default_preset.is_file():
            app.config['PRESET_SOAP_CUTTING_PATH'] = str(_default_preset)
    except Exception:
        pass
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
            conn.exec_driver_sql('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS subscription_tier VARCHAR(50) DEFAULT \'free\';')
            conn.exec_driver_sql('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS bonus_credits INTEGER DEFAULT 0;')
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
        add_col("subscription_tier TEXT DEFAULT 'free'", 'subscription_tier')
        add_col('bonus_credits INTEGER DEFAULT 0', 'bonus_credits')

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

def _get_preset_video_path(config_key: str) -> Path | None:
    raw = (app.config.get(config_key) or "").strip()
    if not raw:
        return None
    try:
        p = Path(raw)
        if not p.is_absolute():
            p = (Path.cwd() / p).resolve()
        if not p.exists() or not p.is_file():
            return None
        return p
    except Exception:
        return None

def _is_youtube_eligible() -> bool:
    try:
        if not current_user.is_authenticated:
            return False
    except Exception:
        return False

    tier = (getattr(current_user, "subscription_tier", None) or "").strip().lower()
    if tier == "pro":
        return True
    if bool(getattr(current_user, "is_admin", False)):
        return True
    return False

def _youtube_settings_path(user_id: int) -> Path:
    return get_user_directory(user_id, "youtube") / "settings.json"

def _read_youtube_settings(user_id: int) -> dict:
    p = _youtube_settings_path(user_id)
    try:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {}

def _get_youtube_auto_upload(user_id: int) -> bool:
    s = _read_youtube_settings(user_id)
    try:
        return bool(s.get("auto_upload", False))
    except Exception:
        return False

def _set_youtube_auto_upload(user_id: int, enabled: bool) -> None:
    p = _youtube_settings_path(user_id)
    data = _read_youtube_settings(user_id)
    data["auto_upload"] = bool(enabled)
    data["updated_at"] = datetime.utcnow().isoformat()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")

def _resolve_preset_video(preset_id: str | None, slot: str) -> Path | None:
    pid = (preset_id or "").strip().lower()
    if not pid:
        pid = "minecraft_parkour"

    if pid == "soap_cutting":
        return _get_preset_video_path("PRESET_SOAP_CUTTING_PATH")

    if pid != "minecraft_parkour":
        return None

    if slot == "video2":
        p2 = _get_preset_video_path("PRESET_VIDEO2_PATH")
        if p2 is not None:
            return p2
        return _get_preset_video_path("PRESET_VIDEO1_PATH")

    return _get_preset_video_path("PRESET_VIDEO1_PATH")

def _cleanup_expired_user_artifacts(user_id: int, ttl_s: int = 120) -> None:
    now_ts = time.time()
    yt_keep = False
    try:
        yt_keep = _get_youtube_auto_upload(user_id)
    except Exception:
        yt_keep = False
    ttl_outputs = 24 * 3600 if yt_keep else ttl_s
    ttl_jobs = 24 * 3600 if yt_keep else ttl_s

    try:
        has_active = (
            VideoJob.query.filter_by(user_id=user_id)
            .filter(VideoJob.status.in_(('processing', 'pending')))
            .count()
            > 0
        )
    except Exception:
        has_active = False

    # Delete old files (outputs/temp always; uploads only when idle)
    for subdir in ("outputs", "temp", "uploads"):
        p = Path("user_data") / str(user_id) / subdir
        if not p.exists():
            continue
        if subdir == "uploads" and has_active:
            continue
        if subdir == "outputs":
            ttl = ttl_outputs
        elif subdir == "uploads":
            ttl = max(ttl_s, 6 * 3600)
        else:
            ttl = ttl_s
        for f in p.iterdir():
            try:
                if not f.is_file():
                    continue
                if (now_ts - f.stat().st_mtime) > ttl:
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

            if age_s is not None and age_s > ttl_jobs:
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


@app.route('/shop')
@login_required
def shop():
    return redirect(url_for('dashboard'))


@app.route('/support')
@login_required
def support():
    return render_template('support.html')


@app.route('/api/stripe/webhook', methods=['POST'])
def stripe_webhook():
    webhook_secret = (app.config.get('STRIPE_WEBHOOK_SECRET') or '').strip()
    if not webhook_secret:
        abort(404)

    sig_header = request.headers.get('Stripe-Signature', '')
    payload = request.get_data(as_text=True)

    try:
        import stripe
    except Exception:
        return jsonify({'error': 'Stripe SDK not installed'}), 500

    try:
        event = stripe.Webhook.construct_event(payload=payload, sig_header=sig_header, secret=webhook_secret)
    except Exception:
        return jsonify({'error': 'Invalid signature'}), 400

    event_type = (event.get('type') or '').strip()
    if event_type == 'checkout.session.completed':
        session = (event.get('data') or {}).get('object') or {}
        email = None
        try:
            email = (session.get('customer_details') or {}).get('email') or session.get('customer_email')
        except Exception:
            email = None
        email = (email or '').strip().lower() or None

        if email:
            u = User.query.filter_by(email=email).first()
            if u:
                u.subscription_tier = 'pro'
                try:
                    db.session.commit()
                except Exception:
                    try:
                        db.session.rollback()
                    except Exception:
                        pass

    return jsonify({'received': True})

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
    subscription_tier = (request.form.get('subscription_tier') or '').strip().lower()

    if daily_quota:
        try:
            u.daily_quota = max(0, int(daily_quota))
        except Exception:
            pass

    if is_admin in ('0', '1'):
        u.is_admin = is_admin == '1'

    if subscription_tier in ('free', 'pro'):
        u.subscription_tier = subscription_tier

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
            'bonus_credits': int(getattr(current_user, 'bonus_credits', 0) or 0),
        }
    })


@app.route('/api/rewarded/start', methods=['POST'])
@login_required
def rewarded_start():
    if bool(getattr(current_user, 'is_admin', False)):
        return jsonify({'error': 'Not eligible'}), 400

    remaining = current_user.remaining_daily_quota() if hasattr(current_user, 'remaining_daily_quota') else 0
    bonus = int(getattr(current_user, 'bonus_credits', 0) or 0)
    if remaining > 0 or bonus > 0:
        return jsonify({'error': 'Quota remaining'}), 400

    from models import RewardTicket
    now = datetime.utcnow()
    today = now.date()

    try:
        redeemed_today = (
            RewardTicket.query.filter(RewardTicket.user_id == current_user.id)
            .filter(RewardTicket.redeemed_at.isnot(None))
            .filter(db.func.date(RewardTicket.redeemed_at) == str(today))
            .count()
        )
    except Exception:
        redeemed_today = 0

    if redeemed_today >= 3:
        return jsonify({'error': 'Rewarded limit reached for today'}), 429

    ticket_id = f"rw_{uuid.uuid4().hex}"
    t = RewardTicket(id=ticket_id, user_id=current_user.id, created_at=now)
    db.session.add(t)
    db.session.commit()
    return jsonify({'success': True, 'ticket_id': ticket_id, 'min_wait_s': 6})


@app.route('/api/rewarded/redeem', methods=['POST'])
@login_required
def rewarded_redeem():
    if bool(getattr(current_user, 'is_admin', False)):
        return jsonify({'error': 'Not eligible'}), 400

    data = request.json or {}
    ticket_id = (data.get('ticket_id') or '').strip()
    if not ticket_id:
        return jsonify({'error': 'Missing ticket_id'}), 400

    from models import RewardTicket
    t = RewardTicket.query.filter_by(id=ticket_id, user_id=current_user.id).first()
    if not t:
        return jsonify({'error': 'Invalid ticket'}), 404
    if t.redeemed_at is not None:
        return jsonify({'error': 'Already redeemed'}), 400

    now = datetime.utcnow()
    try:
        age_s = (now - (t.created_at or now)).total_seconds()
    except Exception:
        age_s = 0
    if age_s < 6:
        return jsonify({'error': 'Too soon'}), 429

    remaining = current_user.remaining_daily_quota() if hasattr(current_user, 'remaining_daily_quota') else 0
    bonus = int(getattr(current_user, 'bonus_credits', 0) or 0)
    if remaining > 0 or bonus > 0:
        return jsonify({'error': 'Quota remaining'}), 400

    try:
        current_user.bonus_credits = int(getattr(current_user, 'bonus_credits', 0) or 0) + 1
        t.redeemed_at = now
        db.session.commit()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify({'error': 'Failed to redeem'}), 500

    return jsonify({'success': True, 'bonus_credits': int(current_user.bonus_credits or 0)})

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


@app.route('/api/validate_uploads', methods=['POST'])
@login_required
def validate_uploads():
    data = request.json or {}
    video1_id = (data.get('video1') or '').strip()
    video2_id = (data.get('video2') or '').strip()

    user_upload_dir = get_user_directory(current_user.id, "uploads")

    def exists(file_id: str) -> bool:
        if not file_id:
            return False
        try:
            return (user_upload_dir / file_id).exists()
        except Exception:
            return False

    return jsonify({
        'success': True,
        'video1_exists': exists(video1_id),
        'video2_exists': exists(video2_id),
    })

@app.route('/api/generate_video', methods=['POST'])
@login_required
def generate_video():
    
    data = request.json
    text = data.get('text', '').strip()
    video_file_id = data.get('video_file_id')
    video2_file_id = data.get('video2_file_id')
    split_screen_enabled = data.get('split_screen_enabled', False)
    use_preset_video1 = bool(data.get('use_preset_video1', False))
    use_preset_video2 = bool(data.get('use_preset_video2', False))
    video1_preset_id = (data.get('video1_preset_id') or '').strip() or None
    video2_preset_id = (data.get('video2_preset_id') or '').strip() or None
    user_id = current_user.id
    
    if not text:
        return jsonify({'error': 'Please enter some text'}), 400
    if not use_preset_video1 and not video_file_id:
        return jsonify({'error': 'Please upload a video first (or choose the preset)'}), 400
    if split_screen_enabled and not use_preset_video2 and not video2_file_id:
        return jsonify({'error': 'Please upload a second video for split screen mode (or choose the preset)'}), 400

    # Daily quota enforcement (admin bypasses)
    try:
        if not current_user.can_generate_today(1):
            remaining = current_user.remaining_daily_quota()
            return jsonify({'error': f'Daily limit reached. Remaining today: {remaining}'}), 429
        current_user.consume_daily_quota(1)
    except Exception:
        return jsonify({'error': 'Quota check failed'}), 500
    
    user_upload_dir = get_user_directory(current_user.id, "uploads")

    preset1 = _resolve_preset_video(video1_preset_id, "video1") if use_preset_video1 else None
    if use_preset_video1 and preset1 is None:
        return jsonify({'error': 'Preset video is not configured on the server'}), 400

    preset2 = _resolve_preset_video(video2_preset_id, "video2") if use_preset_video2 else None
    if split_screen_enabled and use_preset_video2 and preset2 is None:
        return jsonify({'error': 'Preset video is not configured on the server'}), 400

    if use_preset_video1:
        video_path = preset1
    else:
        video_path = user_upload_dir / str(video_file_id)
        if not video_path.exists():
            return jsonify({'error': 'Uploaded video not found'}), 400

    video2_path = None
    if split_screen_enabled:
        if use_preset_video2:
            video2_path = preset2
        else:
            video2_path = user_upload_dir / str(video2_file_id)
            if not video2_path.exists():
                return jsonify({'error': 'Second uploaded video not found'}), 400
    
    def generate_worker(
        user_id: int,
        text: str,
        video_file_id: str | None,
        video2_file_id: str | None,
        split_screen_enabled: bool,
        use_preset_video1: bool,
        use_preset_video2: bool,
        video1_preset_id: str | None,
        video2_preset_id: str | None,
        preset1_path: str | None,
        preset2_path: str | None,
    ):
        job_id = str(uuid.uuid4())
        with app.app_context():
            user_output_dir = get_user_directory(user_id, "outputs")
            user_temp_dir = get_user_directory(user_id, "temp")

            # Check if uploaded files exist (thread-safe; no current_user access)
            user_upload_dir = get_user_directory(user_id, "uploads")
            if use_preset_video1 and preset1_path:
                video_path = Path(preset1_path)
                delete_video1 = False
            else:
                video_path = user_upload_dir / str(video_file_id)
                delete_video1 = True

            video2_path = None
            delete_video2 = True
            if split_screen_enabled:
                if use_preset_video2 and preset2_path:
                    video2_path = Path(preset2_path)
                    delete_video2 = False
                elif video2_file_id is not None:
                    video2_path = user_upload_dir / str(video2_file_id)
                    delete_video2 = True

            # Create video job record
            if use_preset_video1:
                pid = (video1_preset_id or "").strip() or "minecraft_parkour"
                job_filename = f"preset:{pid}"
            else:
                job_filename = str(video_file_id or "upload")
            job = VideoJob(
                user_id=user_id,
                filename=job_filename,
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

                # Optional: enqueue for YouTube upload (Pro only, requires uploaded token)
                try:
                    if _get_youtube_auto_upload(user_id):
                        youtube_manager = get_user_youtube_manager(user_id)
                        if youtube_manager.credentials_path.exists() and youtube_manager.token_path.exists():
                            if youtube_manager.setup_youtube_api():
                                title = f"{text[:60].strip()}{'…' if len(text) > 60 else ''}"
                                metadata = create_video_metadata_from_file(Path(output_path), title=title)
                                youtube_manager.add_video_to_queue(metadata)
                                youtube_manager.start_background_uploader()
                except Exception:
                    pass

                # Clean up temp files
                try:
                    tts_path.unlink()
                except Exception:
                    pass

                # Delete uploaded source videos to avoid accumulating large files
                try:
                    if delete_video1 and video_path.exists():
                        video_path.unlink()
                except Exception:
                    pass
                try:
                    if delete_video2 and video2_path and video2_path.exists():
                        video2_path.unlink()
                except Exception:
                    pass

            except Exception as e:
                job.status = 'failed'
                msg = str(e)
                low = msg.lower()
                if "could not be found" in low or "no such file" in low:
                    job.error_message = "Background video was removed while processing. Please re-upload and try again."
                elif "failed to read the first frame" in low:
                    job.error_message = "Couldn't read your background video (possibly corrupted/unsupported). Try re-encoding or uploading a different MP4."
                else:
                    job.error_message = msg

            db.session.commit()
            db.session.remove()
    
    threading.Thread(
        target=generate_worker,
        args=(
            user_id,
            text,
            video_file_id,
            video2_file_id,
            split_screen_enabled,
            use_preset_video1,
            use_preset_video2,
            video1_preset_id,
            video2_preset_id,
            str(video_path) if use_preset_video1 else None,
            str(video2_path) if (split_screen_enabled and use_preset_video2 and video2_path) else None,
        ),
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
            if not _get_youtube_auto_upload(current_user.id):
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


@app.route('/api/youtube/status')
@login_required
def youtube_status():
    eligible = _is_youtube_eligible()
    tier = (getattr(current_user, "subscription_tier", None) or "").strip().lower()

    user_dir = get_user_directory(current_user.id, "youtube")
    creds_path = user_dir / "youtube_credentials.json"
    token_path = user_dir / "youtube_token.json"
    client_id = None
    client_secret_masked = None
    try:
        if creds_path.exists():
            raw = json.loads(creds_path.read_text(encoding="utf-8"))
            web = raw.get("web") or raw.get("installed") or {}
            client_id = (web.get("client_id") or None)
            cs = (web.get("client_secret") or "")
            if cs:
                client_secret_masked = f"{cs[:4]}…{cs[-4:]}" if len(cs) > 8 else "••••"
    except Exception:
        client_id = None
        client_secret_masked = None

    auto_upload = False
    try:
        auto_upload = _get_youtube_auto_upload(current_user.id)
    except Exception:
        auto_upload = False

    note = None
    if eligible and creds_path.exists() and not token_path.exists():
        note = "Not connected yet"

    return jsonify({
        "success": True,
        "eligible": eligible,
        "tier": tier,
        "has_credentials": creds_path.exists(),
        "has_token": token_path.exists(),
        "auto_upload": bool(auto_upload),
        "note": note,
        "client_id": client_id,
        "client_secret_masked": client_secret_masked,
    })

@app.route('/api/youtube/credentials', methods=['POST'])
@login_required
def youtube_save_credentials():
    if not _is_youtube_eligible():
        return jsonify({"success": False, "error": "Pro plan required"}), 403
    data = request.json or {}
    client_id = (data.get("client_id") or "").strip()
    client_secret = (data.get("client_secret") or "").strip()
    if not client_id or not client_secret:
        return jsonify({"success": False, "error": "Missing client_id/client_secret"}), 400

    user_dir = get_user_directory(current_user.id, "youtube")
    creds_path = user_dir / "youtube_credentials.json"

    redirect_uri = url_for("youtube_oauth_callback", _external=True)
    payload = {
        "web": {
            "client_id": client_id,
            "project_id": "mindsrot",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_secret": client_secret,
            "redirect_uris": [redirect_uri],
        }
    }
    try:
        creds_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        return jsonify({"success": False, "error": "Failed to save credentials"}), 500

    return jsonify({"success": True})


@app.route('/api/youtube/connect', methods=['POST'])
@login_required
def youtube_connect():
    if not _is_youtube_eligible():
        return jsonify({"success": False, "error": "Pro plan required"}), 403

    user_dir = get_user_directory(current_user.id, "youtube")
    creds_path = user_dir / "youtube_credentials.json"
    if not creds_path.exists():
        return jsonify({"success": False, "error": "Save Client ID/Secret first"}), 400

    try:
        from google_auth_oauthlib.flow import Flow
    except Exception:
        return jsonify({"success": False, "error": "YouTube OAuth dependencies not installed"}), 500

    try:
        client_config = json.loads(creds_path.read_text(encoding="utf-8"))
        flow = Flow.from_client_config(client_config, scopes=["https://www.googleapis.com/auth/youtube.upload"])
        flow.redirect_uri = url_for("youtube_oauth_callback", _external=True)
        auth_url, state = flow.authorization_url(access_type="offline", include_granted_scopes="true", prompt="consent")
        session["yt_oauth_state"] = state
        return jsonify({"success": True, "auth_url": auth_url})
    except Exception:
        return jsonify({"success": False, "error": "Failed to start OAuth flow"}), 500


@app.route('/youtube/oauth/callback')
@login_required
def youtube_oauth_callback():
    if not _is_youtube_eligible():
        return redirect(url_for("dashboard"))

    state = (request.args.get("state") or "").strip()
    expected = (session.get("yt_oauth_state") or "").strip()
    if not state or not expected or state != expected:
        flash("YouTube connect failed (invalid state).")
        return redirect(url_for("dashboard"))

    user_dir = get_user_directory(current_user.id, "youtube")
    creds_path = user_dir / "youtube_credentials.json"
    token_path = user_dir / "youtube_token.json"
    if not creds_path.exists():
        flash("YouTube connect failed (missing credentials).")
        return redirect(url_for("dashboard"))

    try:
        from google_auth_oauthlib.flow import Flow
    except Exception:
        flash("YouTube connect failed (missing dependencies).")
        return redirect(url_for("dashboard"))

    try:
        client_config = json.loads(creds_path.read_text(encoding="utf-8"))
        flow = Flow.from_client_config(client_config, scopes=["https://www.googleapis.com/auth/youtube.upload"], state=state)
        flow.redirect_uri = url_for("youtube_oauth_callback", _external=True)
        flow.fetch_token(authorization_response=request.url)
        creds = flow.credentials
        token_path.write_text(creds.to_json(), encoding="utf-8")
        flash("✅ YouTube connected successfully.")
    except Exception:
        flash("YouTube connect failed. Double-check your OAuth client and redirect URI.")

    return redirect(url_for("dashboard"))


@app.route('/api/youtube/auto_upload', methods=['POST'])
@login_required
def youtube_set_auto_upload():
    if not _is_youtube_eligible():
        return jsonify({"success": False, "error": "Pro plan required"}), 403
    data = request.json or {}
    enabled = bool(data.get("enabled", False))
    try:
        _set_youtube_auto_upload(current_user.id, enabled)
    except Exception:
        return jsonify({"success": False, "error": "Failed to update setting"}), 500
    return jsonify({"success": True, "enabled": enabled})

@app.route('/api/generate_batch', methods=['POST'])
@login_required
def generate_batch():
    data = request.json
    texts = data.get('texts', [])
    video_file_id = data.get('video_file_id')
    video2_file_id = data.get('video2_file_id')
    split_screen_enabled = data.get('split_screen_enabled', False)
    use_preset_video1 = bool(data.get('use_preset_video1', False))
    use_preset_video2 = bool(data.get('use_preset_video2', False))
    video1_preset_id = (data.get('video1_preset_id') or '').strip() or None
    video2_preset_id = (data.get('video2_preset_id') or '').strip() or None
    user_id = current_user.id
    
    if not texts:
        return jsonify({'error': 'No texts provided'}), 400
    if not use_preset_video1 and not video_file_id:
        return jsonify({'error': 'Please upload a video first (or choose the preset)'}), 400
    if split_screen_enabled and not use_preset_video2 and not video2_file_id:
        return jsonify({'error': 'Please upload a second video for split screen mode (or choose the preset)'}), 400

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
    
    user_upload_dir = get_user_directory(current_user.id, "uploads")

    preset1 = _resolve_preset_video(video1_preset_id, "video1") if use_preset_video1 else None
    if use_preset_video1 and preset1 is None:
        return jsonify({'error': 'Preset video is not configured on the server'}), 400

    preset2 = _resolve_preset_video(video2_preset_id, "video2") if use_preset_video2 else None
    if split_screen_enabled and use_preset_video2 and preset2 is None:
        return jsonify({'error': 'Preset video is not configured on the server'}), 400

    if use_preset_video1:
        video_path = preset1
    else:
        video_path = user_upload_dir / str(video_file_id)
        if not video_path.exists():
            return jsonify({'error': 'Uploaded video not found'}), 400

    video2_path = None
    if split_screen_enabled:
        if use_preset_video2:
            video2_path = preset2
        else:
            video2_path = user_upload_dir / str(video2_file_id)
            if not video2_path.exists():
                return jsonify({'error': 'Second uploaded video not found'}), 400
    
    def batch_worker(
        user_id: int,
        texts: list[str],
        video_file_id: str | None,
        video2_file_id: str | None,
        split_screen_enabled: bool,
        use_preset_video1: bool,
        use_preset_video2: bool,
        video1_preset_id: str | None,
        video2_preset_id: str | None,
        preset1_path: str | None,
        preset2_path: str | None,
    ):
        with app.app_context():
            user_output_dir = get_user_directory(user_id, "outputs")
            user_temp_dir = get_user_directory(user_id, "temp")
            youtube_manager = get_user_youtube_manager(user_id)
            user_upload_dir = get_user_directory(user_id, "uploads")
            if use_preset_video1 and preset1_path:
                video_path = Path(preset1_path)
                delete_video1 = False
            else:
                video_path = user_upload_dir / str(video_file_id)
                delete_video1 = True

            video2_path = None
            delete_video2 = True
            if split_screen_enabled:
                if use_preset_video2 and preset2_path:
                    video2_path = Path(preset2_path)
                    delete_video2 = False
                elif video2_file_id is not None:
                    video2_path = user_upload_dir / str(video2_file_id)
                    delete_video2 = True
        
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

                        # Optional: enqueue for YouTube upload (Pro only, requires uploaded token)
                        try:
                            if _get_youtube_auto_upload(user_id):
                                if youtube_manager.credentials_path.exists() and youtube_manager.token_path.exists():
                                    if youtube_manager.setup_youtube_api():
                                        title = f"{text[:60].strip()}{'…' if len(text) > 60 else ''}"
                                        metadata = create_video_metadata_from_file(Path(output_path), title=title)
                                        youtube_manager.add_video_to_queue(metadata)
                                        youtube_manager.start_background_uploader()
                        except Exception:
                            pass
                        
                        # Clean up temp files
                        try:
                            tts_path.unlink()
                        except Exception:
                            pass
                            
                    except Exception as e:
                        job.status = 'failed'
                        msg = str(e)
                        low = msg.lower()
                        if "could not be found" in low or "no such file" in low:
                            job.error_message = "Background video was removed while processing. Please re-upload and try again."
                        elif "failed to read the first frame" in low:
                            job.error_message = "Couldn't read your background video (possibly corrupted/unsupported). Try re-encoding or uploading a different MP4."
                        else:
                            job.error_message = msg
                    
                    db.session.commit()
                    
                    # Small delay between videos
                    if i < total:
                        time.sleep(2)
                        
            except Exception as e:
                print(f"Batch generation error: {e}")
            finally:
                try:
                    if delete_video1 and video_path.exists():
                        video_path.unlink()
                except Exception:
                    pass
                try:
                    if delete_video2 and video2_path and video2_path.exists():
                        video2_path.unlink()
                except Exception:
                    pass
                db.session.remove()
    
    threading.Thread(
        target=batch_worker,
        args=(
            user_id,
            texts,
            video_file_id,
            video2_file_id,
            split_screen_enabled,
            use_preset_video1,
            use_preset_video2,
            video1_preset_id,
            video2_preset_id,
            str(video_path) if use_preset_video1 else None,
            str(video2_path) if (split_screen_enabled and use_preset_video2 and video2_path) else None,
        ),
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
