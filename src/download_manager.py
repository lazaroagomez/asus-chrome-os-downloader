import os
import httpx
from pathlib import Path
from typing import Optional, Callable, Dict, List
from enum import Enum
import time
import threading
import asyncio


class DownloadStatus(Enum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"
    STOPPED = "stopped"


class DownloadTask:
    """Represents a single download task"""
    
    def __init__(self, url: str, destination: str, filename: str, 
                 metadata: Optional[Dict] = None):
        self.url = url
        self.destination = destination
        self.filename = filename
        self.metadata = metadata or {}
        self.status = DownloadStatus.QUEUED
        self.progress = 0.0
        self.download_speed = 0
        self.eta = 0
        self.error_message = ""
        self.total_size = 0
        self.downloaded_size = 0
        self.paused = False
        self.stopped = False
        self.thread: Optional[threading.Thread] = None
        self.retry_count = 0
    
    @property
    def full_path(self) -> str:
        return os.path.join(self.destination, self.filename)
    
    def exists(self) -> bool:
        """Check if file already exists"""
        return os.path.exists(self.full_path)


class HttpxDownloadManager:
    """Manages downloads using httpx"""
    
    def __init__(self, max_concurrent_downloads: int = 1,
                 max_download_speed: Optional[int] = None,
                 completion_callback: Optional[Callable] = None,
                 max_retries: int = 3):
        """
        Initialize download manager
        
        Args:
            max_concurrent_downloads: Number of simultaneous downloads
            max_download_speed: Speed limit in KB/s (None for unlimited)
            completion_callback: Callback when download completes
            max_retries: Maximum number of retry attempts for failed downloads
        """
        self.max_concurrent_downloads = max_concurrent_downloads
        self.max_download_speed = max_download_speed
        self.completion_callback = completion_callback
        self.max_retries = max_retries
        
        self.tasks: List[DownloadTask] = []
        self.update_callback: Optional[Callable] = None
        self.active_downloads = 0
        self.download_lock = threading.Lock()
    
    def add_download(self, task: DownloadTask) -> bool:
        """Add a download task"""
        # Check if file already exists
        if task.exists():
            task.status = DownloadStatus.COMPLETED
            task.progress = 100.0
            self.tasks.append(task)
            return False
        
        # Create destination directory
        os.makedirs(task.destination, exist_ok=True)
        
        self.tasks.append(task)
        self._start_next_download()
        return True
    
    def _start_next_download(self):
        """Start next queued download if slots available"""
        with self.download_lock:
            if self.active_downloads >= self.max_concurrent_downloads:
                return
            
            # Find next queued task
            for task in self.tasks:
                if task.status == DownloadStatus.QUEUED:
                    self.active_downloads += 1
                    task.status = DownloadStatus.DOWNLOADING
                    task.thread = threading.Thread(
                        target=self._download_file,
                        args=(task,),
                        daemon=True
                    )
                    task.thread.start()
                    break
    
    def _download_file(self, task: DownloadTask):
        """Download a file with resume support"""
        temp_file = task.full_path + ".tmp"
        
        try:
            # Check if partial download exists
            start_byte = 0
            if os.path.exists(temp_file):
                start_byte = os.path.getsize(temp_file)
                task.downloaded_size = start_byte
            
            headers = {}
            if start_byte > 0:
                headers['Range'] = f'bytes={start_byte}-'
            
            # Configure httpx client with timeouts and retries
            with httpx.stream(
                "GET",
                task.url,
                headers=headers,
                timeout=httpx.Timeout(30.0, read=60.0),
                follow_redirects=True
            ) as response:
                
                if response.status_code not in (200, 206):
                    raise Exception(f"HTTP {response.status_code}")
                
                # Get total size
                if 'content-length' in response.headers:
                    content_length = int(response.headers['content-length'])
                    task.total_size = start_byte + content_length
                elif response.status_code == 200:
                    task.total_size = int(response.headers.get('content-length', 0))
                
                # Download in chunks
                chunk_size = 8192
                start_time = time.time()
                last_update = start_time
                
                mode = 'ab' if start_byte > 0 else 'wb'
                with open(temp_file, mode) as f:
                    for chunk in response.iter_bytes(chunk_size=chunk_size):
                        if task.stopped:
                            raise Exception("Download stopped by user")
                        
                        if task.paused:
                            task.status = DownloadStatus.PAUSED
                            while task.paused and not task.stopped:
                                time.sleep(0.1)
                            if task.stopped:
                                raise Exception("Download stopped")
                            task.status = DownloadStatus.DOWNLOADING
                        
                        f.write(chunk)
                        task.downloaded_size += len(chunk)
                        
                        # Update progress
                        current_time = time.time()
                        if task.total_size > 0:
                            task.progress = (task.downloaded_size / task.total_size) * 100
                        
                        # Calculate speed and ETA
                        elapsed = current_time - start_time
                        if elapsed > 0:
                            task.download_speed = int(task.downloaded_size / elapsed)
                            if task.download_speed > 0 and task.total_size > 0:
                                remaining = task.total_size - task.downloaded_size
                                task.eta = int(remaining / task.download_speed)
                        
                        # Update UI periodically
                        if current_time - last_update > 0.5:
                            if self.update_callback:
                                self.update_callback()
                            last_update = current_time
                        
                        # Apply speed limit
                        if self.max_download_speed:
                            time.sleep(len(chunk) / (self.max_download_speed * 1024))
            
            # Download complete, rename temp file
            if os.path.exists(task.full_path):
                os.remove(task.full_path)
            os.rename(temp_file, task.full_path)
            
            task.status = DownloadStatus.COMPLETED
            task.progress = 100.0
            
            # Notify completion
            if self.completion_callback:
                self.completion_callback(task)
        
        except Exception as e:
            task.error_message = str(e)
            
            # Retry logic
            if task.retry_count < self.max_retries:
                task.retry_count += 1
                task.status = DownloadStatus.QUEUED
                # Don't clean up temp file for resume
                if self.update_callback:
                    self.update_callback()
                # Retry after a short delay
                time.sleep(2)
            else:
                task.status = DownloadStatus.ERROR
                # Clean up temp file on final error
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except:
                        pass
        
        finally:
            with self.download_lock:
                self.active_downloads -= 1
            
            if self.update_callback:
                self.update_callback()
            
            # Start next download
            self._start_next_download()
    
    def pause_download(self, task: DownloadTask):
        """Pause a download"""
        if task.status == DownloadStatus.DOWNLOADING:
            task.paused = True
    
    def resume_download(self, task: DownloadTask):
        """Resume a paused download"""
        if task.status == DownloadStatus.PAUSED:
            task.paused = False
    

    

    
    def set_update_callback(self, callback: Callable):
        """Set callback for download updates"""
        self.update_callback = callback
    
    def get_active_downloads_count(self) -> int:
        """Get count of active downloads"""
        return sum(1 for task in self.tasks 
                  if task.status == DownloadStatus.DOWNLOADING)
    
    def cleanup_completed(self):
        """Remove completed tasks from list"""
        self.tasks = [task for task in self.tasks 
                     if task.status != DownloadStatus.COMPLETED]
