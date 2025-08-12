# TTS Shorts Generator

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

A modern desktop application that generates professional short-form videos with AI voices. Features a clean web-based interface running in a native desktop window.

> 🚀 **Perfect for content creators, social media managers, and anyone looking to automate video production!**

## ✨ Features

- 🎙️ **AI Text-to-Speech** using TikTok voices
- 🎬 **Split Screen Mode** with dual background videos
- 📱 **9:16 Aspect Ratio** optimized for mobile
- 🌐 **Modern Web UI** in a native desktop window
- ⚡ **Batch Processing** from CSV files
- 🎵 **Background Music** integration
- 🤖 **YouTube Auto-Upload** with queue management
- 🧹 **Auto Cleanup** of temporary files

## 🚀 Quick Start

### Requirements
- Python 3.10+
- FFmpeg installed and on PATH
- Google account for YouTube uploads (optional)

### Installation

#### Option 1: Clone from GitHub (Recommended)
```bash
git clone https://github.com/yourusername/tts-shorts-generator.git
cd tts-shorts-generator
pip install -r requirements.txt
```

#### Option 2: Download ZIP
1. Download the latest release from GitHub
2. Extract the ZIP file
3. Open terminal in the extracted folder
4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

#### Launch the Application
```bash
# Desktop app (recommended)
python run.py

# Web interface only
python web_app.py

# Direct desktop launch
python desktop_app.py
```

### Basic Usage
1. **Choose Videos**: Select MP4 background video(s)
2. **Split Screen**: Optionally enable horizontal split screen with two videos
3. **Enter Text**: Type content or upload CSV for batch processing
4. **Generate**: Create your professional short videos
5. **Download**: Access generated videos from the built-in file manager

### Quick Start with Examples
Want to test it out immediately? Check out the `examples/` directory:
```bash
# Try the sample facts for instant content
# Upload examples/sample_texts.csv in the web interface
# Or copy individual facts from examples/sample_texts.txt
```

## 📤 YouTube Integration

### Setup (First Time Only)
1. Run the credentials setup:
   ```bash
   python scripts/setup_youtube_credentials.py
   ```
2. Follow the **[YouTube Setup Guide](YOUTUBE_SETUP_GUIDE.md)** for detailed instructions
3. Click "📤 Setup YT" in the app to authenticate
4. Enable "🤖 Auto Upload" for automatic publishing

### How It Works
- ✅ **Smart Queue**: Videos automatically queue for upload
- ⏰ **Rate Limiting**: Respects YouTube's 10 uploads/24hrs limit  
- 🔄 **Auto Retry**: Failed uploads are retried up to 3 times
- 🗑️ **Auto Cleanup**: Uploaded videos are deleted from export folder
- 📊 **Progress Tracking**: Real-time status in the GUI

## 🎯 Key Features

### Modern Desktop Interface
- Clean web-based UI in a native window
- No browser chrome or tabs - feels like a real desktop app
- Responsive design that works on any screen size
- Real-time status updates and progress tracking

### Single & Split Screen Videos
- **Single Mode**: Traditional background video with captions
- **Split Screen**: Horizontal split with two different videos
- Smart cropping focuses on the action areas of videos
- Professional quality output optimized for mobile

### Batch Processing
- Upload CSV files with multiple text entries
- Automatic sequential generation with progress tracking
- Error handling and retry logic for failed videos
- Memory management for large batches

## 📁 Output Structure

```
app/                       # Core application modules
├── tts/                  # TikTok TTS integration
├── video.py             # Video processing engine
├── captions.py          # Caption generation
└── youtube_uploader.py  # YouTube integration
assets/background_music/   # Background music files (optional)
data/                      # User data and configuration (git-ignored)
├── youtube_credentials.json
├── youtube_token.json
├── upload_queue.json
└── uploaded_videos.json
examples/                  # Sample files and documentation
├── sample_texts.csv
├── sample_texts.txt
└── README.md
export/                    # Generated videos
scripts/                   # Utility scripts
├── setup_youtube_credentials.py
├── reset_youtube_integration.py
└── test_youtube_integration.py
temp/                      # Temporary files (auto-cleaned)
web_app.py                 # Web interface backend
desktop_app.py             # Desktop window wrapper
run.py                     # Main launcher
```

## ⚙️ Advanced Configuration

### Custom Video Metadata
Edit `app/youtube_uploader.py` to customize:
- Video titles and descriptions
- Tags and categories
- Privacy settings
- Upload scheduling

### Background Music
Place audio files in the `assets/background_music/` folder:
- Supported formats: MP3, WAV, M4A, AAC, OGG, FLAC
- Random selection for each video
- Adjustable volume mixing

## 🔧 Troubleshooting

### Common Issues
- **YouTube API not available**: Install with `pip install google-auth google-auth-oauthlib google-api-python-client`
- **Credentials error**: Run `python scripts/setup_youtube_credentials.py` and follow setup guide
- **Rate limit reached**: Videos will queue and upload when quota resets
- **TTS failures**: Try different voices or wait and retry

### Support Files
- Check `YOUTUBE_SETUP_GUIDE.md` for detailed YouTube setup
- Console logs provide detailed error information
- All queue data persists between app restarts

## 📝 Notes

- Uses unofficial TikTok TTS endpoint (may occasionally change)
- YouTube quota limits: 10 uploads per 24 hours
- Videos are optimized for mobile viewing (9:16 aspect ratio)
- All processing happens locally - your content stays private

## 🎉 Perfect For

- Content creators automating short-form content
- Social media managers scaling video production  
- Businesses creating regular promotional content
- Anyone wanting professional AI-generated videos

---

**Ready to automate your video creation? Get started now!** 🚀 

