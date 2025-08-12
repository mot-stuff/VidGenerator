"""
YouTube API integration for automated video uploads with rate limiting and queuing.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import threading
import queue
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload
    YOUTUBE_API_AVAILABLE = True
except ImportError:
    YOUTUBE_API_AVAILABLE = False
    logger.warning("YouTube API dependencies not installed. Install with: pip install google-auth google-auth-oauthlib google-api-python-client")


# YouTube API scopes
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']


@dataclass
class VideoMetadata:
    """Metadata for a video to be uploaded."""
    file_path: Path
    title: str
    description: str
    tags: List[str]
    category_id: str = "24"  # Entertainment category
    privacy_status: str = "public"  # public, private, unlisted
    thumbnail_path: Optional[Path] = None
    scheduled_time: Optional[datetime] = None
    created_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()


@dataclass
class UploadResult:
    """Result of a video upload attempt."""
    success: bool
    video_id: Optional[str] = None
    video_url: Optional[str] = None
    error: Optional[str] = None
    retry_after: Optional[int] = None


class YouTubeUploadManager:
    """Manages YouTube video uploads with rate limiting and queuing."""
    
    def __init__(self, credentials_path: Path = Path("data/youtube_credentials.json"), 
                 token_path: Path = Path("data/youtube_token.json"),
                 upload_queue_path: Path = Path("data/upload_queue.json"),
                 uploaded_videos_path: Path = Path("data/uploaded_videos.json")):
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.upload_queue_path = upload_queue_path
        self.uploaded_videos_path = uploaded_videos_path
        
        self.service = None
        self.upload_queue: queue.Queue = queue.Queue()
        self.uploaded_videos: List[Dict] = []
        self.upload_history: List[Dict] = []
        
        # Rate limiting: 10 uploads per 24 hours
        self.max_uploads_per_day = 10
        self.rate_limit_window = 24 * 60 * 60  # 24 hours in seconds
        
        # Threading for background uploads
        self._upload_thread = None
        self._stop_upload_thread = False
        self._upload_lock = threading.Lock()
        
        # Load existing data
        self._load_upload_queue()
        self._load_uploaded_videos()
        self._load_upload_history()
        
    def setup_youtube_api(self) -> bool:
        """Set up YouTube API authentication."""
        if not YOUTUBE_API_AVAILABLE:
            logger.error("YouTube API dependencies not available")
            return False
            
        try:
            creds = None
            
            # Load existing token
            if self.token_path.exists():
                creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
            
            # If no valid credentials, start OAuth flow
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    if not self.credentials_path.exists():
                        logger.error(f"YouTube credentials file not found: {self.credentials_path}")
                        return False
                    
                    flow = InstalledAppFlow.from_client_secrets_file(
                        str(self.credentials_path), SCOPES)
                    creds = flow.run_local_server(port=0)
                
                # Save credentials for next run
                with open(self.token_path, 'w') as token_file:
                    token_file.write(creds.to_json())
            
            # Build YouTube service
            self.service = build('youtube', 'v3', credentials=creds)
            logger.info("YouTube API authentication successful")
            return True
            
        except Exception as e:
            logger.error(f"Failed to setup YouTube API: {e}")
            return False
    
    def can_upload_now(self) -> tuple[bool, int]:
        """Check if we can upload now based on rate limits."""
        current_time = time.time()
        
        # Filter uploads within the last 24 hours
        recent_uploads = [
            upload for upload in self.upload_history
            if current_time - upload['timestamp'] < self.rate_limit_window
        ]
        
        uploads_today = len(recent_uploads)
        remaining_uploads = self.max_uploads_per_day - uploads_today
        
        if remaining_uploads > 0:
            return True, remaining_uploads
        
        # Find when the oldest upload will expire
        if recent_uploads:
            oldest_upload_time = min(upload['timestamp'] for upload in recent_uploads)
            reset_time = oldest_upload_time + self.rate_limit_window
            wait_seconds = int(reset_time - current_time)
            return False, wait_seconds
        
        return True, self.max_uploads_per_day
    
    def add_video_to_queue(self, video_metadata: VideoMetadata) -> bool:
        """Add a video to the upload queue."""
        try:
            # Validate video file exists
            if not video_metadata.file_path.exists():
                logger.error(f"Video file not found: {video_metadata.file_path}")
                return False
            
            # Convert metadata to dict with JSON-serializable types
            metadata_dict = asdict(video_metadata)
            
            # Convert Path objects to strings
            metadata_dict['file_path'] = str(metadata_dict['file_path'])
            if metadata_dict.get('thumbnail_path'):
                metadata_dict['thumbnail_path'] = str(metadata_dict['thumbnail_path'])
            
            # Convert datetime objects to ISO format strings
            if metadata_dict.get('created_at'):
                if isinstance(metadata_dict['created_at'], datetime):
                    metadata_dict['created_at'] = metadata_dict['created_at'].isoformat()
            if metadata_dict.get('scheduled_time'):
                if isinstance(metadata_dict['scheduled_time'], datetime):
                    metadata_dict['scheduled_time'] = metadata_dict['scheduled_time'].isoformat()
            
            # Add to queue
            queue_item = {
                'metadata': metadata_dict,
                'added_at': datetime.now().isoformat(),
                'attempts': 0,
                'max_attempts': 3
            }
            
            self.upload_queue.put(queue_item)
            self._save_upload_queue()
            
            logger.info(f"Added video to upload queue: {video_metadata.title}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add video to queue: {e}")
            return False
    
    def upload_video(self, video_metadata: VideoMetadata) -> UploadResult:
        """Upload a single video to YouTube."""
        if not self.service:
            return UploadResult(success=False, error="YouTube API not initialized")
        
        try:
            # Check rate limits
            can_upload, remaining_or_wait = self.can_upload_now()
            if not can_upload:
                return UploadResult(
                    success=False, 
                    error=f"Rate limit exceeded. Try again in {remaining_or_wait} seconds",
                    retry_after=remaining_or_wait
                )
            
            # Prepare video metadata for YouTube API
            body = {
                'snippet': {
                    'title': video_metadata.title,
                    'description': video_metadata.description,
                    'tags': video_metadata.tags,
                    'categoryId': video_metadata.category_id
                },
                'status': {
                    'privacyStatus': video_metadata.privacy_status,
                    'selfDeclaredMadeForKids': False
                }
            }
            
            # Add scheduled publishing time if specified
            if video_metadata.scheduled_time:
                body['status']['publishAt'] = video_metadata.scheduled_time.isoformat() + 'Z'
            
            # Create media upload
            media = MediaFileUpload(
                str(video_metadata.file_path),
                chunksize=-1,  # Upload in single request
                resumable=True,
                mimetype='video/mp4'
            )
            
            # Upload video
            logger.info(f"Starting upload: {video_metadata.title}")
            request = self.service.videos().insert(
                part=','.join(body.keys()),
                body=body,
                media_body=media
            )
            
            response = None
            error = None
            retry_count = 0
            max_retries = 3
            
            while response is None and retry_count < max_retries:
                try:
                    status, response = request.next_chunk()
                    if status:
                        logger.info(f"Upload progress: {int(status.progress() * 100)}%")
                except HttpError as e:
                    if e.resp.status in [500, 502, 503, 504]:
                        # Retriable error
                        error = f"Retriable error: {e}"
                        retry_count += 1
                        time.sleep(2 ** retry_count)  # Exponential backoff
                    else:
                        # Non-retriable error
                        error = f"Non-retriable error: {e}"
                        break
                except Exception as e:
                    error = f"Unexpected error: {e}"
                    break
            
            if response and 'id' in response:
                video_id = response['id']
                video_url = f"https://www.youtube.com/watch?v={video_id}"
                
                # Record successful upload
                self._record_upload(video_id, video_metadata)
                
                logger.info(f"Upload successful: {video_url}")
                return UploadResult(
                    success=True,
                    video_id=video_id,
                    video_url=video_url
                )
            else:
                return UploadResult(success=False, error=error or "Unknown upload error")
                
        except Exception as e:
            logger.error(f"Upload failed: {e}")
            return UploadResult(success=False, error=str(e))
    
    def start_background_uploader(self):
        """Start background thread for processing upload queue."""
        if self._upload_thread and self._upload_thread.is_alive():
            return
        
        self._stop_upload_thread = False
        self._upload_thread = threading.Thread(target=self._background_upload_worker, daemon=True)
        self._upload_thread.start()
        logger.info("Background upload worker started")
    
    def stop_background_uploader(self):
        """Stop background upload thread."""
        self._stop_upload_thread = True
        if self._upload_thread and self._upload_thread.is_alive():
            self._upload_thread.join(timeout=5)
        logger.info("Background upload worker stopped")
    
    def _background_upload_worker(self):
        """Background worker that processes the upload queue."""
        while not self._stop_upload_thread:
            try:
                # Check if we can upload
                can_upload, remaining_or_wait = self.can_upload_now()
                if not can_upload:
                    logger.info(f"Rate limit reached. Waiting {remaining_or_wait} seconds")
                    time.sleep(min(remaining_or_wait, 3600))  # Wait max 1 hour at a time
                    continue
                
                # Get next item from queue (non-blocking)
                try:
                    queue_item = self.upload_queue.get(timeout=60)  # Wait up to 1 minute
                except queue.Empty:
                    continue
                
                # Process upload
                with self._upload_lock:
                    metadata_dict = queue_item['metadata'].copy()  # Make a copy to avoid modifying original
                    
                    # Recreate VideoMetadata object with proper type conversion
                    metadata_dict['file_path'] = Path(metadata_dict['file_path'])
                    if metadata_dict.get('thumbnail_path'):
                        metadata_dict['thumbnail_path'] = Path(metadata_dict['thumbnail_path'])
                    
                    # Handle datetime conversion safely
                    if metadata_dict.get('scheduled_time'):
                        if isinstance(metadata_dict['scheduled_time'], str):
                            metadata_dict['scheduled_time'] = datetime.fromisoformat(metadata_dict['scheduled_time'])
                    
                    if metadata_dict.get('created_at'):
                        if isinstance(metadata_dict['created_at'], str):
                            metadata_dict['created_at'] = datetime.fromisoformat(metadata_dict['created_at'])
                        elif metadata_dict['created_at'] is None:
                            metadata_dict['created_at'] = datetime.now()
                    
                    video_metadata = VideoMetadata(**metadata_dict)
                    
                    # Skip if file no longer exists
                    if not video_metadata.file_path.exists():
                        logger.warning(f"Skipping upload - file not found: {video_metadata.file_path}")
                        continue
                    
                    # Attempt upload
                    result = self.upload_video(video_metadata)
                    
                    if result.success:
                        logger.info(f"Successfully uploaded: {video_metadata.title}")
                        # Clean up video file after successful upload
                        self._cleanup_uploaded_video(video_metadata.file_path)
                    else:
                        # Handle failed upload
                        queue_item['attempts'] += 1
                        if queue_item['attempts'] < queue_item['max_attempts']:
                            # Re-queue for retry
                            logger.warning(f"Upload failed, will retry: {result.error}")
                            self.upload_queue.put(queue_item)
                        else:
                            logger.error(f"Upload failed after max attempts: {result.error}")
                    
                    self._save_upload_queue()
                    
                    # Small delay between uploads
                    time.sleep(5)
                    
            except Exception as e:
                logger.error(f"Background upload worker error: {e}")
                time.sleep(30)  # Wait before retrying
    
    def _record_upload(self, video_id: str, metadata: VideoMetadata):
        """Record a successful upload."""
        upload_record = {
            'video_id': video_id,
            'title': metadata.title,
            'file_path': str(metadata.file_path),
            'uploaded_at': datetime.now().isoformat(),
            'timestamp': time.time()
        }
        
        self.upload_history.append(upload_record)
        self.uploaded_videos.append(upload_record)
        
        self._save_uploaded_videos()
        self._save_upload_history()
    
    def _cleanup_uploaded_video(self, file_path: Path):
        """Delete video file after successful upload."""
        try:
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Cleaned up uploaded video: {file_path}")
        except Exception as e:
            logger.error(f"Failed to cleanup video file: {e}")
    
    def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue status and rate limit info."""
        can_upload, remaining_or_wait = self.can_upload_now()
        
        return {
            'queue_size': self.upload_queue.qsize(),
            'can_upload_now': can_upload,
            'uploads_remaining_today': remaining_or_wait if can_upload else 0,
            'next_upload_available_in': remaining_or_wait if not can_upload else 0,
            'uploads_today': len([
                u for u in self.upload_history 
                if time.time() - u['timestamp'] < self.rate_limit_window
            ]),
            'total_uploads': len(self.uploaded_videos)
        }
    
    def reset_youtube_integration(self, clear_history: bool = False, clear_queue: bool = False) -> bool:
        """Reset YouTube integration to allow switching accounts or starting fresh.
        
        Args:
            clear_history: Whether to clear upload history (keeps rate limiting data by default)
            clear_queue: Whether to clear pending upload queue
            
        Returns:
            bool: True if reset was successful
        """
        try:
            logger.info("Resetting YouTube integration...")
            
            # Stop background uploader
            self.stop_background_uploader()
            
            # Clear service connection
            self.service = None
            
            # Remove authentication token to force re-authentication
            if self.token_path.exists():
                self.token_path.unlink()
                logger.info("Removed authentication token")
            
            # Clear upload queue if requested
            if clear_queue:
                # Clear in-memory queue
                while not self.upload_queue.empty():
                    try:
                        self.upload_queue.get_nowait()
                    except queue.Empty:
                        break
                
                # Remove queue file
                if self.upload_queue_path.exists():
                    self.upload_queue_path.unlink()
                    logger.info("Cleared upload queue")
            
            # Clear upload history if requested
            if clear_history:
                self.uploaded_videos = []
                self.upload_history = []
                
                if self.uploaded_videos_path.exists():
                    self.uploaded_videos_path.unlink()
                    logger.info("Cleared upload history")
            
            logger.info("YouTube integration reset complete")
            return True
            
        except Exception as e:
            logger.error(f"Failed to reset YouTube integration: {e}")
            return False
    
    def get_authenticated_account_info(self) -> Optional[Dict[str, str]]:
        """Get information about the currently authenticated Google account."""
        if not self.service:
            return None
        
        try:
            # Get channel information to identify the account
            request = self.service.channels().list(part="snippet", mine=True)
            response = request.execute()
            
            if 'items' in response and len(response['items']) > 0:
                channel = response['items'][0]['snippet']
                return {
                    'channel_title': channel.get('title', 'Unknown'),
                    'channel_id': response['items'][0].get('id', 'Unknown'),
                    'description': channel.get('description', '')[:100] + '...' if channel.get('description') else ''
                }
        except Exception as e:
            logger.error(f"Failed to get account info: {e}")
        
        return None
    
    def _load_upload_queue(self):
        """Load upload queue from disk."""
        if self.upload_queue_path.exists():
            try:
                with open(self.upload_queue_path, 'r') as f:
                    queue_data = json.load(f)
                    
                loaded_count = 0
                for item in queue_data:
                    try:
                        # Validate that required fields exist
                        if 'metadata' in item and 'added_at' in item:
                            self.upload_queue.put(item)
                            loaded_count += 1
                        else:
                            logger.warning(f"Skipping invalid queue item: {item}")
                    except Exception as e:
                        logger.warning(f"Skipping corrupted queue item: {e}")
                        
                if loaded_count > 0:
                    logger.info(f"Loaded {loaded_count} items from upload queue")
                    
            except Exception as e:
                logger.error(f"Failed to load upload queue: {e}")
                # If queue is corrupted, start fresh
                try:
                    self.upload_queue_path.unlink()
                    logger.info("Removed corrupted queue file")
                except Exception:
                    pass
    
    def _save_upload_queue(self):
        """Save upload queue to disk."""
        try:
            queue_items = []
            
            # Extract all items from queue
            temp_queue = queue.Queue()
            while not self.upload_queue.empty():
                try:
                    item = self.upload_queue.get_nowait()
                    queue_items.append(item)
                    temp_queue.put(item)
                except queue.Empty:
                    break
            
            # Put items back in queue
            while not temp_queue.empty():
                try:
                    item = temp_queue.get_nowait()
                    self.upload_queue.put(item)
                except queue.Empty:
                    break
            
            # Ensure all data is JSON serializable
            serializable_items = []
            for item in queue_items:
                serializable_item = {}
                for key, value in item.items():
                    if isinstance(value, Path):
                        serializable_item[key] = str(value)
                    elif isinstance(value, datetime):
                        serializable_item[key] = value.isoformat()
                    elif isinstance(value, dict):
                        # Handle nested metadata dict
                        serializable_metadata = {}
                        for meta_key, meta_value in value.items():
                            if isinstance(meta_value, Path):
                                serializable_metadata[meta_key] = str(meta_value)
                            elif isinstance(meta_value, datetime):
                                serializable_metadata[meta_key] = meta_value.isoformat()
                            else:
                                serializable_metadata[meta_key] = meta_value
                        serializable_item[key] = serializable_metadata
                    else:
                        serializable_item[key] = value
                serializable_items.append(serializable_item)
            
            # Save to file
            with open(self.upload_queue_path, 'w') as f:
                json.dump(serializable_items, f, indent=2, default=str)
                
        except Exception as e:
            logger.error(f"Failed to save upload queue: {e}")
    
    def _load_uploaded_videos(self):
        """Load uploaded videos history from disk."""
        if self.uploaded_videos_path.exists():
            try:
                with open(self.uploaded_videos_path, 'r') as f:
                    self.uploaded_videos = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load uploaded videos: {e}")
    
    def _save_uploaded_videos(self):
        """Save uploaded videos history to disk."""
        try:
            with open(self.uploaded_videos_path, 'w') as f:
                json.dump(self.uploaded_videos, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save uploaded videos: {e}")
    
    def _load_upload_history(self):
        """Load upload history for rate limiting."""
        # Use uploaded_videos as upload history
        self.upload_history = self.uploaded_videos.copy()
    
    def _save_upload_history(self):
        """Save upload history (same as uploaded videos)."""
        self._save_uploaded_videos()


# Helper functions for easy integration
def create_video_metadata_from_file(file_path: Path, title: str = None, 
                                   description: str = None, tags: List[str] = None) -> VideoMetadata:
    """Create VideoMetadata from a video file with sensible defaults."""
    if title is None:
        title = f"Daily Minecraft TIPS AND TRICKS/TRIVIA {datetime.now().strftime('%Y-%m-%d')}"
    
    if description is None:
        description = f"""{datetime.now().strftime('%Y-%m-%d')} - Your daily dose of Minecraft tips and tricks/trivia. Generated with AI and uploaded per YT regulations."""

    if tags is None:
        tags = [
            "minecraft", "kids", "tutorial", "automated", "redstone", 
            "content creator", "minecraft tips", "artificial intelligence",
            "dream", "mr beast", "minecraft tips and tricks", "minecraft trivia"
        ]
    
    return VideoMetadata(
        file_path=file_path,
        title=title,
        description=description,
        tags=tags,
        privacy_status="public"
    )
