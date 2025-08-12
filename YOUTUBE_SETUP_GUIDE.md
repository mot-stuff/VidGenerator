# YouTube Integration Setup Guide

This guide will help you set up automatic YouTube uploading for your TTS Video Generator.

## Prerequisites

1. A Google account
2. Python environment with the project installed
3. YouTube channel where you want to upload videos

## Step 1: Install YouTube API Dependencies

Run this command to install the required packages:

```bash
pip install google-auth google-auth-oauthlib google-api-python-client
```

Or update your requirements.txt and reinstall:

```bash
pip install -r requirements.txt
```

## Step 2: Set Up Google Cloud Project

1. **Go to Google Cloud Console**
   - Visit: https://console.cloud.google.com/
   - Sign in with your Google account

2. **Create a New Project (or select existing)**
   - Click "Select a project" at the top
   - Click "New Project"
   - Name it something like "TTS-Video-Generator"
   - Click "Create"

3. **Enable YouTube Data API v3**
   - In the Cloud Console, go to "APIs & Services" > "Library"
   - Search for "YouTube Data API v3"
   - Click on it and click "Enable"

4. **Create OAuth 2.0 Credentials**
   - Go to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "OAuth client ID"
   - If prompted, configure the OAuth consent screen:
     - Choose "External" user type
     - Fill in the required fields (App name, User support email, Developer contact)
     - Add your email to test users
     - Save and continue through all steps
   - Choose "Desktop application" as the application type
   - Name it "TTS Video Generator"
   - Click "Create"

5. **Download Credentials**
   - Click the download button (⬇️) next to your newly created credential
   - Save the JSON file as `data/youtube_credentials.json` in your project root directory

## Step 3: Initial Setup

1. **Run the setup script:**
   ```bash
   python scripts/setup_youtube_credentials.py
   ```

2. **If credentials are not set up yet, this will create a template. Replace it with your downloaded JSON file.**

## Step 4: First Authentication

1. **Launch your video generator:**
   ```bash
   python run_gui_ctk.py
   ```

2. **Click the "📤 Setup YT" button** in the bottom status bar

3. **Complete OAuth Flow:**
   - A browser window will open
   - Sign in to your Google account
   - Grant permission to upload videos to YouTube
   - The browser will show a success message
   - Return to your application

4. **Verify Setup:**
   - The YouTube status should change to "🟢 YT: Ready"
   - The button should change to "🔄 Auto Upload"

## Step 5: Enable Auto Upload

1. **Click "🔄 Auto Upload"** to enable automatic uploading
2. **Status should change to "🤖 YT: Auto"**
3. **Generate videos as usual** - they will automatically be queued for YouTube upload

## How It Works

### Rate Limiting
- **Maximum 10 uploads per 24 hours** (YouTube API quota limit)
- Videos are queued when limit is reached
- Automatic uploading resumes when quota resets

### Upload Queue
- Videos are added to a queue when generated (if auto-upload is enabled)
- Background worker processes the queue continuously
- Failed uploads are retried up to 3 times
- Queue persists between application restarts

### File Management
- Videos are automatically deleted from the `export/` folder after successful upload
- Failed uploads remain in the export folder
- You can manually upload videos by disabling auto-upload and using the manual controls

### Video Metadata
Auto-generated videos include:
- **Title:** "AI Generated Short - [Date/Time]"
- **Description:** Professional description with hashtags
- **Tags:** Relevant tags for discovery
- **Privacy:** Public (configurable)
- **Category:** Entertainment

## Customization Options

### Custom Video Titles and Descriptions

You can modify the `create_video_metadata_from_file` function in `app/youtube_uploader.py` to customize:
- Video titles
- Descriptions
- Tags
- Privacy settings
- Scheduled upload times

### Upload Scheduling

```python
from datetime import datetime, timedelta

# Schedule video for later
metadata.scheduled_time = datetime.now() + timedelta(hours=2)
```

### Custom Thumbnails

```python
metadata.thumbnail_path = Path("path/to/thumbnail.jpg")
```

## Monitoring Uploads

### Status Information
- Queue size and pending uploads
- Daily upload limit remaining
- Next upload availability time
- Total successful uploads

### Logs
Check the console output for detailed upload logs including:
- Upload progress
- Success/failure messages
- Rate limit information
- Error details

## Troubleshooting

### Common Issues

1. **"YouTube API dependencies not installed"**
   - Run: `pip install google-auth google-auth-oauthlib google-api-python-client`

2. **"YouTube credentials file not found"**
   - Run `python scripts/setup_youtube_credentials.py`
   - Replace template with actual credentials from Google Cloud Console

3. **"YouTube setup failed - check credentials"**
   - Verify your `data/youtube_credentials.json` is valid
   - Make sure YouTube Data API v3 is enabled
   - Check OAuth consent screen is properly configured

4. **"Rate limit exceeded"**
   - Wait for quota to reset (24 hours from first upload)
   - Videos will automatically upload when quota is available

5. **Authentication issues**
   - Delete `data/youtube_token.json` to force re-authentication
   - Ensure your Google account has access to the YouTube channel

### File Locations

- `data/youtube_credentials.json` - OAuth credentials from Google Cloud
- `data/youtube_token.json` - Generated access token (auto-created)
- `data/upload_queue.json` - Persistent upload queue
- `data/uploaded_videos.json` - History of uploaded videos

## Privacy and Security

- Keep your `data/youtube_credentials.json` file secure and private
- Don't share your credentials with others
- The application only requests upload permissions
- Tokens are stored locally and never transmitted elsewhere

## Advanced Usage

### Manual Queue Management

```python
# Add video manually
metadata = create_video_metadata_from_file(
    Path("my_video.mp4"),
    title="Custom Title",
    description="Custom description",
    tags=["custom", "tags"]
)
youtube_manager.add_video_to_queue(metadata)
```

### Batch Operations

The batch CSV generation automatically queues all generated videos when auto-upload is enabled.

## Switching Google Accounts / Reset Options

### GUI Reset Options
**Right-click the YouTube button** in the app to access reset options:

- **🔄 Switch Google Account**: Disconnect current account and sign in with a different one
- **🗑️ Clear Upload Queue**: Remove pending uploads (keeps videos in export folder)
- **📊 Clear Upload History**: Reset upload history and daily count
- **💥 Full Reset**: Complete reset of account, queue, and history

### Command Line Reset Tool
Use the standalone reset script for advanced management:

```bash
# Interactive menu
python reset_youtube_integration.py

# Command line options
python reset_youtube_integration.py --switch-account
python reset_youtube_integration.py --clear-queue
python reset_youtube_integration.py --clear-history
python reset_youtube_integration.py --full-reset
python reset_youtube_integration.py --status

# Auto-confirm (no prompts)
python reset_youtube_integration.py --switch-account --yes
```

### When to Use Reset Options

- **Switch Account**: When you want to upload to a different YouTube channel
- **Clear Queue**: When you want to stop pending uploads without losing history
- **Clear History**: When you want to reset your daily upload count
- **Full Reset**: When starting completely fresh or troubleshooting issues

## Support

If you encounter issues:
1. Check the console logs for error details
2. Verify your Google Cloud project setup
3. Ensure all API quotas are available
4. Try the reset options above
5. Use `python reset_youtube_integration.py --status` to check current state

Happy uploading! 🚀📹
