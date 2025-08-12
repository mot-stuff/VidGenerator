#!/usr/bin/env python3
"""
Desktop TTS Shorts Generator
Runs the web interface in a native desktop window
"""

import threading
import time
import webview
from web_app import app

def start_flask():
    """Start Flask server in background thread"""
    app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)

def main():
    # Start Flask server in background
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()
    
    # Wait a moment for Flask to start
    time.sleep(2)
    
    # Create desktop window
    webview.create_window(
        title='TTS Shorts Generator',
        url='http://127.0.0.1:5000',
        width=750,
        height=650,
        min_size=(600, 500),
        resizable=True,
        fullscreen=False,
        on_top=False
    )
    
    # Start the desktop app
    webview.start(debug=False)

if __name__ == '__main__':
    print("🚀 Starting TTS Shorts Generator Desktop App...")
    main()
