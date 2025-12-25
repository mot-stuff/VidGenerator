#!/usr/bin/env python3
"""
Simple standalone web-based TTS Shorts Generator
Run this script and open http://localhost:5000 in your browser
"""

from __future__ import annotations

import os
import threading
import time
import webbrowser
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, render_template

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
# No upload limit for local use

# Global state
selected_videos = {"video1": None, "video2": None}
split_screen_enabled = False
youtube_manager = YouTubeUploadManager()
youtube_enabled = False
auto_upload_enabled = False
processing_status = "Ready to generate videos"
output_dir = Path("export")
temp_dir = Path("temp")

# Ensure directories exist
output_dir.mkdir(parents=True, exist_ok=True)
temp_dir.mkdir(parents=True, exist_ok=True)

# HTML template is now in templates/index.html

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def get_status():
    return jsonify({
        'status': processing_status,
        'youtube_enabled': youtube_enabled,
        'auto_upload_enabled': auto_upload_enabled,
        'selected_videos': selected_videos,
        'split_screen_enabled': split_screen_enabled
    })

@app.route('/api/upload_video', methods=['POST'])
def upload_video():
    global selected_videos
    
    print(f"Upload request received. Files: {list(request.files.keys())}")
    print(f"Form data: {dict(request.form)}")
    
    if 'video' not in request.files:
        print("No video file in request")
        return jsonify({'error': 'No video file'}), 400
    
    file = request.files['video']
    video_type = request.form.get('type', 'video1')
    
    print(f"Processing upload for type: {video_type}, filename: {file.filename}")
    
    if file.filename == '':
        print("Empty filename")
        return jsonify({'error': 'No file selected'}), 400
    
    if file and file.filename.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
        filename = f"{video_type}_{int(time.time())}_{file.filename}"
        filepath = temp_dir / filename
        print(f"Saving file to: {filepath}")
        file.save(filepath)
        selected_videos[video_type] = str(filepath)
        print(f"Upload successful. Selected videos: {selected_videos}")
        return jsonify({'success': True, 'filename': file.filename, 'path': str(filepath)})
    
    print(f"Invalid file type: {file.filename}")
    return jsonify({'error': 'Invalid file type'}), 400

@app.route('/api/upload_csv', methods=['POST'])
def upload_csv():
    if 'csv' not in request.files:
        return jsonify({'error': 'No CSV file'}), 400
    
    file = request.files['csv']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    try:
        import csv
        import io
        
        # Read file content
        file_content = file.read().decode('utf-8')
        texts = []
        
        # Try to detect if it's CSV or plain text
        if ',' in file_content or '"' in file_content:
            # Treat as CSV - use first column
            csv_reader = csv.reader(io.StringIO(file_content))
            for row in csv_reader:
                if row and row[0].strip():  # Skip empty rows
                    texts.append(row[0].strip())
        else:
            # Treat as plain text file, one line per entry
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

@app.route('/api/toggle_split_screen', methods=['POST'])
def toggle_split_screen():
    global split_screen_enabled
    split_screen_enabled = request.json.get('enabled', False)
    return jsonify({'success': True, 'enabled': split_screen_enabled})

@app.route('/api/generate_video', methods=['POST'])
def generate_video():
    global processing_status
    
    data = request.json
    text = data.get('text', '').strip()
    
    if not text:
        return jsonify({'error': 'Please enter some text'}), 400
    if not selected_videos['video1']:
        return jsonify({'error': 'Please select at least one video'}), 400
    if split_screen_enabled and not selected_videos['video2']:
        return jsonify({'error': 'Please select both videos for split screen mode'}), 400
    
    def generate_worker():
        global processing_status
        try:
            processing_status = "Synthesizing TTS..."
            voice_code = "en_us_002"
            tts_path = synthesize_tiktok_tts(text=text, voice=voice_code, out_dir=temp_dir)
            processing_status = "Creating captions..."
            spans = allocate_caption_spans(text=text, total_duration_s=None, audio_path=tts_path)
            try:
                words = whisper_word_timestamps(str(tts_path), language="en", original_text=text)
                word_spans = words_to_karaoke_spans(words)
            except:
                word_spans = allocate_karaoke_word_spans(text=text, total_duration_s=None, audio_path=tts_path)
            processing_status = "Compositing video..." if not split_screen_enabled else "Compositing split-screen video..."
            output_path = output_dir / f"output_{int(time.time())}.mp4"
            import random
            from moviepy.editor import VideoFileClip
            with VideoFileClip(selected_videos['video1']) as video_clip:
                video_duration = video_clip.duration
            random_start = random.uniform(0.0, max(0.0, video_duration - 1.0))
            compose_video_with_tts(
                video_path=selected_videos['video1'], tts_audio_path=tts_path, caption_spans=spans,
                output_path=output_path, chosen_start_time=random_start, crf=18, video_bitrate=None,
                karaoke_word_spans=word_spans, add_background_music=True, bg_music_volume=0.15,
                bg_music_dir="assets/background_music", split_screen_enabled=split_screen_enabled,
                video_path2=selected_videos['video2'] if split_screen_enabled else None,
                tail_padding_s=3.0,
            )
            processing_status = f"✅ Generated: {output_path.name}"
            try: tts_path.unlink()
            except: pass
            if auto_upload_enabled and youtube_enabled:
                metadata = create_video_metadata_from_file(output_path)
                youtube_manager.add_video_to_queue(metadata)
        except Exception as e:
            processing_status = f"❌ Error: {e}"
            try:
                if 'tts_path' in locals(): tts_path.unlink()
            except: pass
    
    threading.Thread(target=generate_worker, daemon=True).start()
    return jsonify({'success': True, 'message': 'Video generation started'})

@app.route('/api/generate_batch', methods=['POST'])
def generate_batch():
    global processing_status
    
    data = request.json
    texts = data.get('texts', [])
    
    if not texts:
        return jsonify({'error': 'No texts provided'}), 400
    if not selected_videos['video1']:
        return jsonify({'error': 'Please select at least one video'}), 400
    if split_screen_enabled and not selected_videos['video2']:
        return jsonify({'error': 'Please select both videos for split screen mode'}), 400
    
    def batch_worker():
        global processing_status
        try:
            total = len(texts)
            generated_count = 0
            failed_count = 0
            
            for i, text in enumerate(texts, 1):
                processing_status = f"🔄 Processing {i}/{total}: {text[:30]}..."
                
                success = False
                for attempt in range(2):  # Try up to 2 times
                    try:
                        if i > 1:  # Add delay between videos
                            time.sleep(2)
                        
                        # Generate TTS
                        voice_code = "en_us_002"
                        tts_path = synthesize_tiktok_tts(text=text, voice=voice_code, out_dir=temp_dir)
                        
                        # Generate captions
                        spans = allocate_caption_spans(text=text, total_duration_s=None, audio_path=tts_path)
                        
                        try:
                            words = whisper_word_timestamps(str(tts_path), language="en", original_text=text)
                            word_spans = words_to_karaoke_spans(words)
                        except:
                            word_spans = allocate_karaoke_word_spans(text=text, total_duration_s=None, audio_path=tts_path)
                        
                        # Generate output filename
                        output_path = output_dir / f"output_batch_{i:03d}_{int(time.time())}.mp4"
                        
                        # Pick random start time
                        import random
                        from moviepy.editor import VideoFileClip
                        with VideoFileClip(selected_videos['video1']) as video_clip:
                            video_duration = video_clip.duration
                        random_start = random.uniform(0.0, max(0.0, video_duration - 1.0))
                        
                        # Compose video
                        compose_video_with_tts(
                            video_path=selected_videos['video1'],
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
                            video_path2=selected_videos['video2'] if split_screen_enabled else None,
                            tail_padding_s=3.0,
                        )
                        
                        generated_count += 1
                        success = True
                        
                        # Clean up TTS file
                        try:
                            tts_path.unlink()
                        except:
                            pass
                        
                        # Add to YouTube queue if enabled
                        if auto_upload_enabled and youtube_enabled:
                            metadata = create_video_metadata_from_file(output_path)
                            youtube_manager.add_video_to_queue(metadata)
                        
                        break
                        
                    except Exception as e:
                        if attempt == 1:  # Last attempt failed
                            failed_count += 1
                            processing_status = f"❌ Failed video {i}, continuing... ({e})"
                            time.sleep(1)
                
                # Force cleanup every few videos
                if i % 3 == 0:
                    import gc
                    gc.collect()
            
            # Final status
            if failed_count == 0:
                processing_status = f"✅ Batch complete: {generated_count}/{total} videos generated"
            else:
                processing_status = f"⚠️ Batch complete: {generated_count}/{total} generated, {failed_count} failed"
                
        except Exception as e:
            processing_status = f"❌ Batch error: {e}"
    
    threading.Thread(target=batch_worker, daemon=True).start()
    return jsonify({'success': True, 'message': 'Batch generation started'})

@app.route('/api/youtube/toggle', methods=['POST'])
def toggle_youtube():
    global youtube_enabled, auto_upload_enabled, processing_status
    if not youtube_enabled:
        credentials_path = Path("data/youtube_credentials.json")
        if not credentials_path.exists():
            return jsonify({'error': 'Please run setup_youtube_credentials.py first'}), 400
        try:
            success = youtube_manager.setup_youtube_api()
            if success:
                youtube_enabled = True
                youtube_manager.start_background_uploader()
                processing_status = "✅ YouTube upload ready"
                return jsonify({'success': True, 'enabled': True})
            else:
                return jsonify({'error': 'YouTube setup failed - check credentials'}), 400
        except Exception as e:
            return jsonify({'error': f'YouTube error: {e}'}), 400
    else:
        auto_upload_enabled = not auto_upload_enabled
        status = "enabled" if auto_upload_enabled else "disabled"
        processing_status = f"🤖 Auto YouTube upload {status}"
        return jsonify({'success': True, 'auto_upload': auto_upload_enabled})

@app.route('/api/cleanup', methods=['POST'])
def cleanup_temp():
    try:
        current_time = time.time()
        if temp_dir.exists():
            for temp_file in temp_dir.iterdir():
                try:
                    if temp_file.is_file() and temp_file.suffix in ['.mp3', '.mp4', '.wav']:
                        file_age = current_time - temp_file.stat().st_mtime
                        if file_age > 300:
                            temp_file.unlink()
                except: pass
        temp_patterns = ["*TEMP_MPY*.mp4", "*TEMP_MPY*.wav", "*TEMP_MPY*.m4a"]
        for pattern in temp_patterns:
            for temp_file in output_dir.glob(pattern):
                try: temp_file.unlink()
                except: pass
            for temp_file in Path(".").glob(pattern):
                try: temp_file.unlink()
                except: pass
        return jsonify({'success': True, 'message': 'Cleanup completed'})
    except Exception as e:
        return jsonify({'error': f'Cleanup failed: {e}'}), 400

@app.route('/export/<filename>')
def download_file(filename):
    return send_from_directory(output_dir, filename)

@app.route('/api/export_files')
def list_export_files():
    try:
        files = []
        if output_dir.exists():
            for file in output_dir.iterdir():
                if file.is_file() and file.suffix == '.mp4' and not file.name.startswith('temp'):
                    files.append({'name': file.name, 'size': file.stat().st_size, 'created': file.stat().st_mtime})
        files.sort(key=lambda x: x['created'], reverse=True)
        return jsonify({'files': files})
    except Exception as e:
        return jsonify({'error': f'Failed to list files: {e}'}), 400

if __name__ == '__main__':
    def open_browser():
        time.sleep(1)
        webbrowser.open('http://localhost:5000')
    
    threading.Thread(target=open_browser, daemon=True).start()
    print("🚀 Starting TTS Shorts Generator...")
    print("📱 Opening browser at http://localhost:5000")
    print("🛑 Press Ctrl+C to stop")
    app.run(debug=False, host='127.0.0.1', port=5000)
