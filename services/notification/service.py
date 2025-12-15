import sys
import os
import requests
import threading
from flask import Flask, jsonify
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from shared.config import config
from shared.logging import setup_logger
from shared.events import event_bus
from shared.models import get_db, Recording

logger = setup_logger('notification')

class NotificationService:
    def __init__(self):
        self.event_bus_ready = False
        self.setup_event_handlers()
        self.start_health_server()
    
    def start_health_server(self):
        """Start Flask health check server on port 5005"""
        app = Flask(__name__)
        
        @app.route('/health')
        def health():
            return jsonify({
                'status': 'ready' if self.event_bus_ready else 'starting',
                'event_bus_connected': self.event_bus_ready
            })
        
        # Start in background thread
        def run_health_server():
            app.run(host='0.0.0.0', port=5005, debug=False)
        
        health_thread = threading.Thread(target=run_health_server, daemon=True)
        health_thread.start()
    
    def setup_event_handlers(self):
        try:
            event_bus.subscribe('recording.completed', self.handle_recording_completed)
            self.event_bus_ready = True
        except Exception as e:
            logger.error(f"Failed to setup event handlers: {e}")
            self.event_bus_ready = False
    
    def handle_recording_completed(self, message):
        """Send notification when recording completes"""
        try:
            recording_id = message['recording_id']
            status = message['status']
            file_size = message.get('file_size', 0)
            duration = message.get('duration', 0)
            
            db = next(get_db())
            recording = db.query(Recording).filter(Recording.id == recording_id).first()
            
            if not recording:
                return
            
            # Build notification message
            title = f"Recording {status.title()}: {recording.name}"
            
            message_parts = [
                f"Status: {status}",
                f"Duration: {self.format_duration(duration)}",
                f"Size: {self.format_file_size(file_size)}"
            ]
            
            # Add failure info
            failures = []
            if recording.save_to_additional_local and recording.local_storage_status == 'FAILED':
                failures.append("Local storage copy failed")
            if recording.save_to_nextcloud and recording.nextcloud_storage_status == 'FAILED':
                failures.append("NextCloud upload failed")
            
            if failures:
                message_parts.extend(failures)
            
            # Add web link
            web_url = f"http://localhost:5000/recordings/{recording_id}"
            message_parts.append(f"Listen: {web_url}")
            
            notification_message = "\n".join(message_parts)
            
            self.send_pushover_notification(title, notification_message)
            
        except Exception as e:
            logger.error(f"Notification failed: {e}")
    
    def send_pushover_notification(self, title, message):
        """Send notification via Pushover"""
        try:
            api_token = config.get('pushover', 'api_token')
            user_key = config.get('pushover', 'user_key')
            
            if not api_token or not user_key:
                logger.warning("Pushover credentials not configured")
                return
            
            data = {
                'token': api_token,
                'user': user_key,
                'title': title,
                'message': message
            }
            
            response = requests.post('https://api.pushover.net/1/messages.json', data=data, timeout=10)
            
            if response.status_code == 200:
                logger.info(f"Notification sent: {title}")
            else:
                logger.error(f"Pushover notification failed: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Pushover notification error: {e}")
    
    def format_duration(self, seconds):
        """Format duration in human readable format"""
        if not seconds:
            return "0s"
        
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        
        if hours:
            return f"{hours}h {minutes}m {secs}s"
        elif minutes:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"
    
    def format_file_size(self, bytes):
        """Format file size in human readable format"""
        if not bytes:
            return "0 B"
        
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes < 1024:
                return f"{bytes:.1f} {unit}"
            bytes /= 1024
        
        return f"{bytes:.1f} TB"
    
    def run(self):
        logger.info("Notification service starting...")
        try:
            event_bus.connect()
            event_bus.start_consuming()
        except Exception as e:
            logger.error(f"notification service failed: {e}")

if __name__ == "__main__":
    service = NotificationService()
    service.run()
