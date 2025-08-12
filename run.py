#!/usr/bin/env python3
"""
TTS Shorts Generator - Main Launcher
Simple launcher for the desktop application
"""

if __name__ == "__main__":
    try:
        # Try to run the desktop app
        from desktop_app import main
        main()
    except ImportError:
        print("❌ Missing dependencies. Please install requirements:")
        print("pip install -r requirements.txt")
    except Exception as e:
        print(f"❌ Error starting application: {e}")
        input("Press Enter to exit...")
