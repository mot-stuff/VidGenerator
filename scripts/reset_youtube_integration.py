#!/usr/bin/env python3
"""
YouTube Integration Reset Tool

This script provides various options to reset your YouTube integration:
- Switch Google accounts
- Clear upload queue
- Clear upload history  
- Full reset

Run with no arguments to see an interactive menu.
"""

import sys
import argparse
from pathlib import Path
from app.youtube_uploader import YouTubeUploadManager


def confirm_action(message: str) -> bool:
    """Ask user for confirmation."""
    while True:
        response = input(f"{message} (y/N): ").lower().strip()
        if response in ['y', 'yes']:
            return True
        elif response in ['n', 'no', '']:
            return False
        print("Please enter 'y' for yes or 'n' for no.")


def show_current_status(manager: YouTubeUploadManager):
    """Show current YouTube integration status."""
    print("\n📊 Current YouTube Integration Status")
    print("=" * 40)
    
    # Check authentication
    try:
        manager.setup_youtube_api()
        account_info = manager.get_authenticated_account_info()
        if account_info:
            print(f"✅ Authenticated as: {account_info['channel_title']}")
            print(f"📺 Channel ID: {account_info['channel_id']}")
        else:
            print("❌ Not authenticated")
    except Exception:
        print("❌ Authentication failed")
    
    # Show queue status
    try:
        status = manager.get_queue_status()
        print(f"📤 Upload queue: {status['queue_size']} pending videos")
        print(f"📈 Daily uploads: {status['uploads_today']}/10")
        print(f"📊 Total uploads: {status['total_uploads']}")
        
        if not status['can_upload_now']:
            print(f"⏰ Next upload available in: {status['next_upload_available_in']} seconds")
    except Exception as e:
        print(f"❌ Error getting status: {e}")
    
    print()


def interactive_menu():
    """Show interactive menu for reset options."""
    manager = YouTubeUploadManager()
    
    while True:
        print("\n🔧 YouTube Integration Reset Tool")
        print("=" * 40)
        print("1. 📊 Show current status")
        print("2. 🔄 Switch Google account (preserve queue & history)")
        print("3. 🗑️ Clear upload queue")
        print("4. 📊 Clear upload history")
        print("5. 💥 Full reset (account + queue + history)")
        print("6. ❌ Exit")
        
        choice = input("\nSelect an option (1-6): ").strip()
        
        if choice == '1':
            show_current_status(manager)
        
        elif choice == '2':
            print("\n🔄 Switch Google Account")
            print("This will disconnect your current Google account and allow you to sign in with a different one.")
            print("Your upload queue and history will be preserved.")
            
            if confirm_action("Continue"):
                success = manager.reset_youtube_integration(clear_history=False, clear_queue=False)
                if success:
                    print("✅ Account reset successful! You can now authenticate with a different Google account.")
                else:
                    print("❌ Failed to reset account.")
        
        elif choice == '3':
            status = manager.get_queue_status()
            queue_size = status['queue_size']
            
            if queue_size == 0:
                print("✅ Upload queue is already empty.")
            else:
                print(f"\n🗑️ Clear Upload Queue")
                print(f"This will remove {queue_size} pending video(s) from the upload queue.")
                print("Videos will remain in your export folder.")
                
                if confirm_action("Continue"):
                    success = manager.reset_youtube_integration(clear_history=False, clear_queue=True)
                    if success:
                        print("✅ Upload queue cleared successfully!")
                    else:
                        print("❌ Failed to clear upload queue.")
        
        elif choice == '4':
            total_uploads = len(manager.uploaded_videos)
            
            if total_uploads == 0:
                print("✅ Upload history is already empty.")
            else:
                print(f"\n📊 Clear Upload History")
                print(f"This will remove the history of {total_uploads} uploaded video(s).")
                print("⚠️ This will also reset your daily upload count!")
                
                if confirm_action("Continue"):
                    success = manager.reset_youtube_integration(clear_history=True, clear_queue=False)
                    if success:
                        print("✅ Upload history cleared successfully!")
                    else:
                        print("❌ Failed to clear upload history.")
        
        elif choice == '5':
            print(f"\n💥 Full YouTube Reset")
            print("⚠️ WARNING: This will completely reset YouTube integration:")
            print("• Disconnect your Google account")
            print("• Clear all pending uploads")
            print("• Clear upload history")  
            print("• Reset daily upload count")
            print("\nThis action cannot be undone!")
            
            if confirm_action("Continue"):
                success = manager.reset_youtube_integration(clear_history=True, clear_queue=True)
                if success:
                    print("✅ YouTube integration fully reset!")
                else:
                    print("❌ Failed to reset YouTube integration.")
        
        elif choice == '6':
            print("👋 Goodbye!")
            break
        
        else:
            print("❌ Invalid option. Please select 1-6.")


def main():
    """Main function with command line argument support."""
    parser = argparse.ArgumentParser(description="Reset YouTube integration")
    parser.add_argument('--switch-account', action='store_true', 
                       help='Switch Google account (preserve queue & history)')
    parser.add_argument('--clear-queue', action='store_true',
                       help='Clear upload queue')
    parser.add_argument('--clear-history', action='store_true', 
                       help='Clear upload history')
    parser.add_argument('--full-reset', action='store_true',
                       help='Full reset (account + queue + history)')
    parser.add_argument('--status', action='store_true',
                       help='Show current status')
    parser.add_argument('--yes', '-y', action='store_true',
                       help='Automatically answer yes to prompts')
    
    args = parser.parse_args()
    
    # If no arguments provided, show interactive menu
    if not any([args.switch_account, args.clear_queue, args.clear_history, 
                args.full_reset, args.status]):
        interactive_menu()
        return 0
    
    manager = YouTubeUploadManager()
    
    if args.status:
        show_current_status(manager)
        return 0
    
    # Handle command line options
    if args.full_reset:
        if args.yes or confirm_action("Perform full YouTube reset"):
            success = manager.reset_youtube_integration(clear_history=True, clear_queue=True)
            print("✅ Full reset completed!" if success else "❌ Reset failed!")
    
    elif args.switch_account:
        if args.yes or confirm_action("Switch Google account"):
            success = manager.reset_youtube_integration(clear_history=False, clear_queue=False)
            print("✅ Account reset completed!" if success else "❌ Account reset failed!")
    
    elif args.clear_queue:
        if args.yes or confirm_action("Clear upload queue"):
            success = manager.reset_youtube_integration(clear_history=False, clear_queue=True)
            print("✅ Queue cleared!" if success else "❌ Failed to clear queue!")
    
    elif args.clear_history:
        if args.yes or confirm_action("Clear upload history"):
            success = manager.reset_youtube_integration(clear_history=True, clear_queue=False)
            print("✅ History cleared!" if success else "❌ Failed to clear history!")
    
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n⏹️ Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        sys.exit(1)
