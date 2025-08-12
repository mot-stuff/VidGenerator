#!/usr/bin/env python3
"""
Multi-user SaaS TTS Shorts Generator
"""

import os
import threading
import time
import uuid
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, render_template, redirect, url_for
from flask_login import LoginManager, login_required, current_user
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from models import db, User, VideoJob
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
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max file size

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

@app.route('/api/status')
@login_required
def get_status():
    return jsonify({
        'user': {
            'email': current_user.email,
            'status': 'active'
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
    
    if not text:
        return jsonify({'error': 'Please enter some text'}), 400
    if not video_file_id:
        return jsonify({'error': 'Please upload a video first'}), 400
    if split_screen_enabled and not video2_file_id:
        return jsonify({'error': 'Please upload a second video for split screen mode'}), 400
    
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
    
    def generate_worker():
        job_id = str(uuid.uuid4())
        user_output_dir = get_user_directory(current_user.id, "outputs")
        user_temp_dir = get_user_directory(current_user.id, "temp")
        
        # Create video job record
        job = VideoJob(
            user_id=current_user.id,
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
            except:
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
                crf=8,
                video_bitrate="50M",
                karaoke_word_spans=word_spans,
                add_background_music=True,
                bg_music_volume=0.15,
                bg_music_dir="assets/background_music",
                split_screen_enabled=split_screen_enabled,
                video_path2=str(video2_path) if video2_path else None
            )
            
            # Update job status
            job.status = 'completed'
            job.result_path = str(output_path)
            job.completed_at = time.time()
            
            # Job completed successfully (no quota tracking)
            
            # Clean up temp files
            try:
                tts_path.unlink()
            except:
                pass
                
        except Exception as e:
            job.status = 'failed'
            job.error_message = str(e)
        
        db.session.commit()
    
    threading.Thread(target=generate_worker, daemon=True).start()
    return jsonify({'success': True, 'message': 'Video generation started'})

@app.route('/api/jobs')
@login_required
def get_jobs():
    """Get user's video jobs"""
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
    
    return send_from_directory(result_path.parent, result_path.name, as_attachment=True)

@app.route('/api/generate_batch', methods=['POST'])
@login_required
def generate_batch():
    data = request.json
    texts = data.get('texts', [])
    video_file_id = data.get('video_file_id')
    video2_file_id = data.get('video2_file_id')
    split_screen_enabled = data.get('split_screen_enabled', False)
    
    if not texts:
        return jsonify({'error': 'No texts provided'}), 400
    if not video_file_id:
        return jsonify({'error': 'Please upload a video first'}), 400
    if split_screen_enabled and not video2_file_id:
        return jsonify({'error': 'Please upload a second video for split screen mode'}), 400
    
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
    
    def batch_worker():
        user_output_dir = get_user_directory(current_user.id, "outputs")
        user_temp_dir = get_user_directory(current_user.id, "temp")
        youtube_manager = get_user_youtube_manager(current_user.id)
        
        try:
            total = len(texts)
            for i, text in enumerate(texts, 1):
                job_id = str(uuid.uuid4())
                
                # Create video job record
                job = VideoJob(
                    user_id=current_user.id,
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
                    except:
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
                        crf=8,
                        video_bitrate="50M",
                        karaoke_word_spans=word_spans,
                        add_background_music=True,
                        bg_music_volume=0.15,
                        bg_music_dir="assets/background_music",
                        split_screen_enabled=split_screen_enabled,
                        video_path2=str(video2_path) if video2_path else None
                    )
                    
                    # Update job status
                    job.status = 'completed'
                    job.result_path = str(output_path)
                    job.completed_at = time.time()
                    
                    # Clean up temp files
                    try:
                        tts_path.unlink()
                    except:
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
    
    threading.Thread(target=batch_worker, daemon=True).start()
    return jsonify({'success': True, 'message': 'Batch generation started'})

def init_database():
    """Initialize database safely"""
    try:
        with app.app_context():
            db.create_all()
            
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
    host = '0.0.0.0' if not debug else '127.0.0.1'
    
    print("🚀 Starting Multi-User TTS Shorts Generator...")
    print(f"📱 Opening at http://{'localhost' if debug else 'production'}:{port}")
    print("🛑 Press Ctrl+C to stop")
    app.run(debug=debug, host=host, port=port)

# For production servers (Gunicorn)
init_database()
