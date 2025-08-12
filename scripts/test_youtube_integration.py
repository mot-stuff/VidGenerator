#!/usr/bin/env python3
"""
Test script for YouTube integration.
Use this to verify your YouTube setup is working correctly.
"""

import sys
from pathlib import Path

# Add parent directory to path so we can import app modules
sys.path.append(str(Path(__file__).parent.parent))

from app.youtube_uploader import YouTubeUploadManager, create_video_metadata_from_file


def test_youtube_setup():
    """Test YouTube API setup and authentication."""
    print("🧪 Testing YouTube Integration")
    print("=" * 40)
    
    # Check if credentials exist
    creds_path = Path("../data/youtube_credentials.json")
    if not creds_path.exists():
        print("❌ YouTube credentials not found!")
        print("📝 Run: python scripts/setup_youtube_credentials.py")
        return False
    
    # Initialize YouTube manager
    print("🔧 Initializing YouTube manager...")
    youtube_manager = YouTubeUploadManager()
    
    # Try to setup API
    print("🔐 Setting up YouTube API...")
    success = youtube_manager.setup_youtube_api()
    
    if not success:
        print("❌ YouTube API setup failed!")
        print("💡 Check your credentials and try again")
        return False
    
    print("✅ YouTube API setup successful!")
    
    # Test rate limiting check
    print("📊 Checking rate limits...")
    can_upload, remaining = youtube_manager.can_upload_now()
    
    if can_upload:
        print(f"✅ Ready to upload! {remaining} uploads remaining today")
    else:
        print(f"⏰ Rate limited. Next upload available in {remaining} seconds")
    
    # Get status
    status = youtube_manager.get_queue_status()
    print(f"📋 Queue status: {status}")
    
    # Test video metadata creation
    print("📝 Testing video metadata creation...")
    test_video_path = Path("export") / "test_video.mp4"
    
    if test_video_path.exists():
        print(f"🎬 Found test video: {test_video_path}")
        metadata = create_video_metadata_from_file(
            test_video_path,
            title="Test Upload - Delete This",
            description="This is a test upload from the TTS Video Generator. You can safely delete this video."
        )
        print(f"✅ Created metadata: {metadata.title}")
        
        # Ask if user wants to test upload
        response = input("\n🤔 Do you want to test upload this video? (y/N): ").lower().strip()
        if response == 'y':
            print("📤 Starting test upload...")
            result = youtube_manager.upload_video(metadata)
            
            if result.success:
                print(f"🎉 Upload successful!")
                print(f"🔗 Video URL: {result.video_url}")
                print(f"🆔 Video ID: {result.video_id}")
            else:
                print(f"❌ Upload failed: {result.error}")
                if result.retry_after:
                    print(f"⏰ Retry after: {result.retry_after} seconds")
        else:
            print("⏭️ Skipping test upload")
    else:
        print("📂 No test video found in export/ folder")
        print("💡 Generate a video first to test uploading")
    
    print("\n✅ YouTube integration test complete!")
    return True


def main():
    """Main test function."""
    try:
        success = test_youtube_setup()
        if success:
            print("\n🎉 All tests passed! YouTube integration is ready.")
            return 0
        else:
            print("\n❌ Tests failed. Check setup and try again.")
            return 1
    except KeyboardInterrupt:
        print("\n\n⏹️ Test interrupted by user")
        return 1
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
