"""
Setup script for YouTube API credentials.
Run this script to configure YouTube API access for automated uploading.
"""

import json
from pathlib import Path


def create_credentials_template():
    """Create a template for YouTube API credentials."""
    
    template = {
        "installed": {
            "client_id": "YOUR_CLIENT_ID.apps.googleusercontent.com",
            "project_id": "your-project-id",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_secret": "YOUR_CLIENT_SECRET",
            "redirect_uris": ["http://localhost"]
        }
    }
    
    credentials_path = Path("data/youtube_credentials.json")
    
    if not credentials_path.exists():
        with open(credentials_path, 'w') as f:
            json.dump(template, f, indent=4)
        
        print("📝 Created data/youtube_credentials.json template")
        print("\n🔧 Setup Instructions:")
        print("1. Go to the Google Cloud Console: https://console.cloud.google.com/")
        print("2. Create a new project or select an existing one")
        print("3. Enable the YouTube Data API v3")
        print("4. Create credentials (OAuth 2.0 Client ID) for a Desktop application")
        print("5. Download the JSON file and replace data/youtube_credentials.json with it")
        print("6. Make sure the JSON has the 'installed' key structure")
        print("\n⚠️  Important: Keep your credentials file secure and don't share it!")
        print("\n✅ After setup, run your video generator and the YouTube upload will be available")
        
        return False
    else:
        print("✅ data/youtube_credentials.json already exists")
        
        # Validate the structure
        try:
            with open(credentials_path, 'r') as f:
                creds = json.load(f)
            
            if 'installed' in creds and 'client_id' in creds['installed']:
                if "YOUR_CLIENT_ID" not in creds['installed']['client_id']:
                    print("✅ Credentials appear to be configured correctly")
                    return True
                else:
                    print("⚠️  Please update data/youtube_credentials.json with your actual credentials")
                    return False
            else:
                print("❌ Invalid credentials format. Please check the file structure.")
                return False
                
        except Exception as e:
            print(f"❌ Error reading credentials: {e}")
            return False


if __name__ == "__main__":
    print("🚀 YouTube API Credentials Setup")
    print("=" * 40)
    
    success = create_credentials_template()
    
    if success:
        print("\n🎉 Ready to upload to YouTube!")
    else:
        print("\n📋 Please complete the setup steps above before using YouTube upload.")
