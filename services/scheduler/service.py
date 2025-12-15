import sys
import os
import subprocess
import time
import json
import requests
import threading
from datetime import datetime, timedelta
from pathlib import Path
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.cron import CronTrigger
from flask import Flask, jsonify
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from shared.config import config
from shared.logging import setup_logger
from shared.events import event_bus
from shared.models import get_db, Recording

logger = setup_logger('scheduler')

class SchedulerService:
    def __init__(self):
        self.scheduler = BlockingScheduler()
        self.event_bus_ready = False
        logger.info("DEBUG: Created BlockingScheduler")
        self.setup_event_handlers()
        logger.info("DEBUG: Set up event handlers")
        self.check_active_recordings()
        logger.info("DEBUG: Checked active recordings")
        
        # Start health check server
        self.start_health_server()
    
    def start_health_server(self):
        """Start Flask health check server on port 5002"""
        app = Flask(__name__)
        
        @app.route('/health')
        def health():
            return jsonify({
                'status': 'ready' if self.event_bus_ready else 'starting',
                'event_bus_connected': self.event_bus_ready,
                'scheduled_jobs': len(self.scheduler.get_jobs())
            })
        
        # Start in background thread
        def run_health_server():
            app.run(host='0.0.0.0', port=5002, debug=False)
        
        health_thread = threading.Thread(target=run_health_server, daemon=True)
        health_thread.start()
    
    def check_recording_service_ready(self, max_attempts=10):
        """Check if recording service is ready to receive events"""
        for attempt in range(max_attempts):
            try:
                response = requests.get('http://localhost:5001/health', timeout=2)
                if response.status_code == 200:
                    data = response.json()
                    if data.get('status') == 'ready':
                        return True
                logger.info(f"Recording service not ready, attempt {attempt + 1}/{max_attempts}")
                time.sleep(1)
            except Exception as e:
                logger.warning(f"Health check failed, attempt {attempt + 1}/{max_attempts}: {e}")
                time.sleep(1)
        
        logger.error("Recording service never became ready")
        return False
    
    def setup_event_handlers(self):
        logger.info("DEBUG: Setting up event handlers")
        
        # Create a dedicated queue for scheduler
        try:
            event_bus.connect()  # Connect when setting up
            result = event_bus.channel.queue_declare(queue='scheduler_queue', durable=True)
            event_bus.channel.queue_bind(exchange='webradio9', queue='scheduler_queue', routing_key='recording.schedule')
            event_bus.channel.queue_bind(exchange='webradio9', queue='scheduler_queue', routing_key='recording.cancel')
            logger.info("DEBUG: Created scheduler_queue")
            self.event_bus_ready = True
        except Exception as e:
            logger.error(f"Failed to setup queue: {e}")
            self.event_bus_ready = False
        
        logger.info("DEBUG: Event handlers set up")
    
    def check_active_recordings(self):
        """Check for recordings that should be active now or were interrupted"""
        try:
            db = next(get_db())
            now = datetime.now()
            
            # Find recordings that should be recording now
            active_recordings = db.query(Recording).filter(
                Recording.start_time <= now,
                Recording.end_time > now,
                Recording.status.in_(['SCHEDULED', 'RECORDING'])
            ).all()
            
            # Also find interrupted recordings (status=RECORDING but end_time in recent past)
            recent_cutoff = now - timedelta(minutes=30)  # Look back 30 minutes
            interrupted_recordings = db.query(Recording).filter(
                Recording.status == 'RECORDING',
                Recording.end_time <= now,
                Recording.end_time >= recent_cutoff
            ).all()
            
            # Process active recordings
            for recording in active_recordings:
                if recording.status == 'RECORDING':
                    logger.info(f"Found interrupted recording, restarting: {recording.name}")
                    # Mark as interrupted for proper status tracking
                    recording.was_interrupted = True
                    db.commit()
                else:
                    logger.info(f"Found active recording: {recording.name}")
                self.start_recording(recording.id)
            
            # Process interrupted recordings that ended while services were down
            for recording in interrupted_recordings:
                logger.info(f"Found abandoned recording, marking as PARTIAL: {recording.name}")
                recording.was_interrupted = True
                # Check if any file was created
                if recording.file_path and Path(recording.file_path).exists():
                    recording.status = 'PARTIAL'
                    recording.file_size = Path(recording.file_path).stat().st_size
                    logger.info(f"Marked as PARTIAL with {recording.file_size} bytes")
                else:
                    recording.status = 'FAILED'
                    logger.info(f"Marked as FAILED (no file created)")
                db.commit()
                
        except Exception as e:
            logger.error(f"Error checking active recordings: {e}")
    
    def handle_recording_schedule(self, message):
        """Schedule a new recording"""
        try:
            recording_id = message['recording_id']
            start_time = datetime.fromisoformat(message['start_time'])
            end_time = datetime.fromisoformat(message['end_time'])
            
            logger.info(f"Scheduling recording {recording_id} from {start_time} to {end_time}")
            
            # Check if recording should start immediately
            now = datetime.now()
            if start_time <= now <= end_time:
                logger.info(f"Recording {recording_id} should start immediately")
                self.start_recording(recording_id)
                return
            
            # Schedule start
            if start_time > now:
                self.scheduler.add_job(
                    func=self.start_recording,
                    trigger=DateTrigger(run_date=start_time),
                    args=[recording_id],
                    id=f"start_{recording_id}",
                    replace_existing=True
                )
                logger.info(f"Scheduled start job for recording {recording_id} at {start_time}")
            
            # Schedule end
            if end_time > now:
                self.scheduler.add_job(
                    func=self.stop_recording,
                    trigger=DateTrigger(run_date=end_time),
                    args=[recording_id],
                    id=f"stop_{recording_id}",
                    replace_existing=True
                )
                logger.info(f"Scheduled stop job for recording {recording_id} at {end_time}")
            
        except Exception as e:
            logger.error(f"Failed to schedule recording: {e}")
    
    def handle_recording_cancel(self, message):
        """Cancel a scheduled recording"""
        try:
            recording_id = message['recording_id']
            
            # Remove scheduled jobs
            try:
                self.scheduler.remove_job(f"start_{recording_id}")
                self.scheduler.remove_job(f"stop_{recording_id}")
                logger.info(f"Cancelled recording {recording_id}")
            except:
                pass  # Jobs might not exist
                
        except Exception as e:
            logger.error(f"Failed to cancel recording: {e}")
    
    def start_recording(self, recording_id):
        """Start a recording with health check and retry logic"""
        try:
            logger.info(f"DEBUG: start_recording called for ID {recording_id}")
            
            db = next(get_db())
            logger.info(f"DEBUG: Got database connection")
            
            recording = db.query(Recording).filter(Recording.id == recording_id).first()
            logger.info(f"DEBUG: Queried recording, found: {recording is not None}")
            
            if recording and recording.status in ['SCHEDULED', 'RECORDING']:
                logger.info(f"DEBUG: Recording status is {recording.status}, updating to RECORDING")
                recording.status = 'RECORDING'
                db.commit()
                logger.info(f"DEBUG: Status updated to RECORDING")
                
                # Check if recording service is ready
                logger.info("Checking recording service health...")
                if not self.check_recording_service_ready():
                    logger.error(f"Recording service not ready, marking recording {recording_id} as FAILED")
                    recording.status = 'FAILED'
                    db.commit()
                    return
                
                # Publish event with retry logic
                event_data = {
                    'recording_id': recording_id,
                    'station_id': recording.station_id,
                    'name': recording.name,
                    'format': recording.format,
                    'bitrate': recording.bitrate,
                    'end_time': recording.end_time.isoformat()
                }
                
                # Retry publishing up to 3 times
                for attempt in range(3):
                    try:
                        logger.info(f"DEBUG: Publishing recording.start event (attempt {attempt + 1})")
                        event_bus.publish('recording.start', event_data)
                        logger.info(f"DEBUG: Published recording.start event successfully")
                        break
                    except Exception as e:
                        logger.warning(f"Event publish attempt {attempt + 1} failed: {e}")
                        if attempt == 2:  # Last attempt
                            logger.error(f"Failed to publish event after 3 attempts, marking as FAILED")
                            recording.status = 'FAILED'
                            db.commit()
                            return
                        time.sleep(1)  # Wait before retry
                
                logger.info(f"Started recording: {recording.name}")
            else:
                logger.warning(f"DEBUG: Recording not found or not schedulable. Recording exists: {recording is not None}, Status: {recording.status if recording else 'N/A'}")
                
        except Exception as e:
            logger.error(f"Failed to start recording {recording_id}: {e}")
            logger.error(f"DEBUG: Exception type: {type(e)}")
            import traceback
            logger.error(f"DEBUG: Full traceback: {traceback.format_exc()}")
    
    def stop_recording(self, recording_id):
        """Stop a recording"""
        try:
            event_bus.publish('recording.stop', {
                'recording_id': recording_id
            })
            
            logger.info(f"Stopped recording: {recording_id}")
            
        except Exception as e:
            logger.error(f"Failed to stop recording {recording_id}: {e}")
    
    def calculate_next_recurrence(self, current_time, recurrence_type):
        """Calculate next occurrence based on recurrence type"""
        from dateutil.relativedelta import relativedelta
        
        if recurrence_type == 'daily':
            return current_time + timedelta(days=1)
        
        elif recurrence_type == 'weekdays':
            next_time = current_time + timedelta(days=1)
            # Skip weekends (Saturday=5, Sunday=6)
            while next_time.weekday() >= 5:
                next_time += timedelta(days=1)
            return next_time
        
        elif recurrence_type == 'weekends':
            next_time = current_time + timedelta(days=1)
            # Skip weekdays (Monday=0 to Friday=4)
            while next_time.weekday() < 5:
                next_time += timedelta(days=1)
            return next_time
        
        elif recurrence_type == 'weekly':
            return current_time + timedelta(weeks=1)
        
        elif recurrence_type == 'monthly':
            return current_time + relativedelta(months=1)
        
        else:
            raise ValueError(f"Unknown recurrence type: {recurrence_type}")

    def check_missing_recurring_instances(self):
        """Fallback check for recurring recordings missing their next instance"""
        try:
            db = next(get_db())
            
            # Find all recurring templates
            recurring_templates = db.query(Recording).filter(Recording.is_recurring == True).all()
            
            for template in recurring_templates:
                # Find the latest instance (completed or scheduled) for this recurring series
                latest_instance = db.query(Recording).filter(
                    Recording.name == template.name,
                    Recording.station_id == template.station_id,
                    Recording.is_recurring == False
                ).order_by(Recording.start_time.desc()).first()
                
                # If no instances exist, use the template as base
                base_time = latest_instance.start_time if latest_instance else template.start_time
                
                # Calculate next occurrence using enhanced logic
                try:
                    next_time = self.calculate_next_recurrence(base_time, template.recurrence_type)
                except ValueError as e:
                    logger.error(str(e))
                    continue
                
                # Check if we've passed the end date
                if template.recurrence_end and next_time > template.recurrence_end:
                    continue
                
                # Only create if next occurrence is within next 48 hours
                now = datetime.utcnow()
                check_until = now + timedelta(hours=48)
                if next_time > check_until:
                    continue
                
                # Check if instance already exists for this time
                existing = db.query(Recording).filter(
                    Recording.name == template.name,
                    Recording.station_id == template.station_id,
                    Recording.is_recurring == False,
                    Recording.start_time == next_time
                ).first()
                
                if not existing:
                    # Create missing instance
                    next_recording = Recording(
                        name=template.name,
                        station_id=template.station_id,
                        podcast_id=template.podcast_id,
                        start_time=next_time,
                        end_time=next_time + timedelta(seconds=template.duration),
                        duration=template.duration,
                        format=template.format,
                        bitrate=template.bitrate,
                        is_recurring=False,
                        save_to_additional_local=template.save_to_additional_local,
                        save_to_nextcloud=template.save_to_nextcloud
                    )
                    
                    db.add(next_recording)
                    logger.info(f"Created missing recurring instance: {template.name} at {next_time}")
            
            db.commit()
            
        except Exception as e:
            logger.error(f"Error checking missing recurring instances: {e}")
    
    def run(self):
        logger.info("Scheduler service starting...")
        
        # Use simple polling instead of complex threading + event consumption
        import time
        
        last_recurring_check = 0
        recurring_check_interval = 1800  # 30 minutes in seconds
        
        while True:
            try:
                current_time = time.time()
                
                # Check for new schedule events (non-blocking)
                self.check_for_schedule_events()
                
                # Check for recordings that should start now
                self.check_recordings_to_start()
                
                # Check for missing recurring instances every 30 minutes
                if current_time - last_recurring_check > recurring_check_interval:
                    self.check_missing_recurring_instances()
                    last_recurring_check = current_time
                
                # Sleep for 1 second before next check
                time.sleep(1)
                
            except KeyboardInterrupt:
                logger.info("Scheduler service stopping...")
                self.scheduler.shutdown()
                break
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                time.sleep(5)  # Wait before retrying
    
    def check_for_schedule_events(self):
        """Check for new recording schedule events without blocking"""
        try:
            # Ensure connection
            event_bus.connect()
            
            # Try to get a message without blocking
            method_frame, header_frame, body = event_bus.channel.basic_get(queue='scheduler_queue', auto_ack=True)
            
            if method_frame:
                message = json.loads(body)
                if method_frame.routing_key == 'recording.schedule':
                    self.handle_recording_schedule(message)
                elif method_frame.routing_key == 'recording.cancel':
                    self.handle_recording_cancel(message)
                    
        except Exception as e:
            # No message available or connection issue - ignore
            pass
    
    def check_recordings_to_start(self):
        """Check database for recordings that should start now"""
        try:
            from datetime import datetime
            db = next(get_db())
            now = datetime.now()
            
            # Find recordings that should start now (within 5 seconds)
            recordings_to_start = db.query(Recording).filter(
                Recording.status == 'SCHEDULED',
                Recording.start_time <= now,
                Recording.start_time >= now - timedelta(seconds=5)
            ).all()
            
            for recording in recordings_to_start:
                logger.info(f"Starting overdue recording: {recording.name}")
                self.start_recording(recording.id)
                
        except Exception as e:
            logger.error(f"Error checking recordings to start: {e}")

if __name__ == "__main__":
    service = SchedulerService()
    service.run()
