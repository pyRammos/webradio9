import sys
import os
import shutil
import requests
import threading
from pathlib import Path
from datetime import datetime
from flask import Flask, jsonify
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from shared.config import config
from shared.logging import setup_logger
from shared.events import event_bus
from shared.models import get_db, Recording

logger = setup_logger('storage')

class StorageService:
    def __init__(self):
        self.event_bus_ready = False
        self.setup_event_handlers()
        self.start_health_server()
    
    def start_health_server(self):
        """Start Flask health check server on port 5004"""
        app = Flask(__name__)
        
        @app.route('/health')
        def health():
            return jsonify({
                'status': 'ready' if self.event_bus_ready else 'starting',
                'event_bus_connected': self.event_bus_ready
            })
        
        # Start in background thread
        def run_health_server():
            app.run(host='0.0.0.0', port=5004, debug=False)
        
        health_thread = threading.Thread(target=run_health_server, daemon=True)
        health_thread.start()
    
    def setup_event_handlers(self):
        try:
            event_bus.subscribe('recording.completed', self.handle_recording_completed)
            event_bus.subscribe('storage.cleanup', self.handle_cleanup)
            self.event_bus_ready = True
        except Exception as e:
            logger.error(f"Failed to setup event handlers: {e}")
            self.event_bus_ready = False
    
    def handle_recording_completed(self, message):
        """Handle completed recording storage"""
        try:
            recording_id = message['recording_id']
            status = message['status']
            
            if status == 'FAILED':
                return
            
            db = next(get_db())
            recording = db.query(Recording).filter(Recording.id == recording_id).first()
            
            if not recording or not recording.file_path:
                return
            
            source_file = Path(recording.file_path)
            
            # Copy to additional local folder
            if recording.save_to_additional_local:
                self.copy_to_additional_local(recording, source_file, db)
            
            # Upload to NextCloud
            if recording.save_to_nextcloud:
                self.upload_to_nextcloud(recording, source_file, db)
            
            # Handle cleanup if keep_recordings_count is set
            keep_count = config.getint('storage', 'keep_recordings_count')
            if keep_count > 0:
                self.cleanup_old_recordings(keep_count, db)
            
        except Exception as e:
            logger.error(f"Storage handling failed: {e}")
    
    def copy_to_additional_local(self, recording, source_file, db):
        """Copy recording to additional local folder"""
        try:
            additional_folder = config.get('storage', 'additional_local_folder')
            if not additional_folder:
                return
            
            # Create hierarchical path
            start_date = recording.start_time
            folder_path = Path(additional_folder) / recording.name / str(start_date.year) / f"{start_date.strftime('%m-%b')}"
            folder_path.mkdir(parents=True, exist_ok=True)
            
            # Create filename with date
            filename = f"{recording.name}{start_date.strftime('%y%m%d-%a')}{source_file.suffix}"
            dest_file = folder_path / filename
            
            shutil.copy2(source_file, dest_file)
            recording.local_storage_status = 'SUCCESS'
            
            logger.info(f"Copied recording to additional local: {dest_file}")
            
        except Exception as e:
            recording.local_storage_status = 'FAILED'
            logger.error(f"Failed to copy to additional local: {e}")
        
        db.commit()
    
    def upload_to_nextcloud(self, recording, source_file, db):
        """Upload recording to NextCloud"""
        try:
            nextcloud_url = config.get('storage', 'nextcloud_url')
            username = config.get('storage', 'nextcloud_username')
            password = config.get('storage', 'nextcloud_password')
            
            if not all([nextcloud_url, username, password]):
                return
            
            # Create hierarchical path
            start_date = recording.start_time
            base_dir = getattr(recording, 'nextcloud_base_dir', '/Recordings')
            remote_path = f"{base_dir.strip('/')}/{recording.name}/{start_date.year}/{start_date.strftime('%m-%b')}"
            filename = f"{recording.name}{start_date.strftime('%y%m%d-%a')}{source_file.suffix}"
            
            # Create directories first
            self.create_nextcloud_directories(nextcloud_url, username, password, remote_path)
            
            # Upload using WebDAV
            upload_url = f"{nextcloud_url.rstrip('/')}/remote.php/dav/files/{username}/{remote_path}/{filename}"
            
            with open(source_file, 'rb') as f:
                response = requests.put(
                    upload_url,
                    data=f,
                    auth=(username, password),
                    timeout=300
                )
            
            if response.status_code in [200, 201, 204]:
                recording.nextcloud_storage_status = 'SUCCESS'
                logger.info(f"Uploaded to NextCloud: {remote_path}/{filename}")
            else:
                recording.nextcloud_storage_status = 'FAILED'
                logger.error(f"NextCloud upload failed: {response.status_code}")
            
        except Exception as e:
            recording.nextcloud_storage_status = 'FAILED'
            logger.error(f"NextCloud upload failed: {e}")
        
        db.commit()
    
    def cleanup_old_recordings(self, keep_count, db):
        """Remove old recordings from flat folder only"""
        try:
            recordings = db.query(Recording).filter(
                Recording.status.in_(['COMPLETE', 'PARTIAL']),
                Recording.file_path.isnot(None)
            ).order_by(Recording.created_at.desc()).all()
            
            if len(recordings) > keep_count:
                to_delete = recordings[keep_count:]
                
                for recording in to_delete:
                    file_path = Path(recording.file_path)
                    if file_path.exists() and file_path.parent.name == 'recordings':  # Only from flat folder
                        file_path.unlink()
                        recording.file_path = None
                        logger.info(f"Deleted old recording: {file_path}")
                
                db.commit()
            
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
    
    def handle_cleanup(self, message):
        """Handle manual cleanup request"""
        try:
            keep_count = message.get('keep_count', 0)
            if keep_count > 0:
                db = next(get_db())
                self.cleanup_old_recordings(keep_count, db)
        except Exception as e:
            logger.error(f"Manual cleanup failed: {e}")
    
    def run(self):
        logger.info("Storage service starting...")
        try:
            event_bus.connect()
            event_bus.start_consuming()
        except Exception as e:
            logger.error(f"storage service failed: {e}")
    
    def create_nextcloud_directories(self, nextcloud_url, username, password, full_path):
        """Create NextCloud directories recursively"""
        try:
            import requests
            
            # Split path into components and create each level
            path_parts = full_path.strip('/').split('/')
            current_path = ''
            
            for part in path_parts:
                current_path += f"/{part}"
                dir_url = f"{nextcloud_url.rstrip('/')}/remote.php/dav/files/{username}{current_path}/"
                
                # Try to create directory (MKCOL)
                response = requests.request('MKCOL', dir_url, auth=(username, password), timeout=30)
                
                # 201 = created, 405 = already exists, both are OK
                if response.status_code not in [201, 405]:
                    logger.warning(f"Failed to create NextCloud directory {current_path}: HTTP {response.status_code}")
            
        except Exception as e:
            logger.error(f"Error creating NextCloud directories: {e}")

if __name__ == "__main__":
    service = StorageService()
    service.run()
