import sys
import os
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from shared.config import config
from shared.logging import setup_logger
from shared.events import event_bus
from shared.models import get_db, Recording, Station, RecordingPart

logger = setup_logger('recording')

class RecordingService:
    def __init__(self):
        self.active_recordings = {}
        self.event_bus_ready = False
        self.setup_event_handlers()
        
        # Start health check server
        self.start_health_server()
    
    def start_health_server(self):
        """Start Flask health check server on port 5001"""
        app = Flask(__name__)
        
        @app.route('/health')
        def health():
            return jsonify({
                'status': 'ready' if self.event_bus_ready else 'starting',
                'event_bus_connected': self.event_bus_ready,
                'active_recordings': len(self.active_recordings)
            })
        
        # Start in background thread
        def run_health_server():
            app.run(host='0.0.0.0', port=5001, debug=False)
        
        health_thread = threading.Thread(target=run_health_server, daemon=True)
        health_thread.start()
    
    def setup_event_handlers(self):
        try:
            event_bus.connect()  # Connect when setting up
            event_bus.subscribe('recording.start', self.handle_recording_start)
            event_bus.subscribe('recording.stop', self.handle_recording_stop)
            self.event_bus_ready = True
            logger.info("Event bus connected and ready")
        except Exception as e:
            logger.error(f"Failed to setup event handlers: {e}")
            self.event_bus_ready = False
    
    def handle_recording_start(self, message):
        """Start recording a stream"""
        try:
            recording_id = message['recording_id']
            
            # Prevent duplicate processing
            if recording_id in self.active_recordings:
                logger.warning(f"Recording {recording_id} already active, ignoring duplicate start event")
                return
            
            # Double-check database status to prevent race conditions
            db = next(get_db())
            recording = db.query(Recording).filter(Recording.id == recording_id).first()
            if not recording or recording.status not in ['RECORDING']:
                logger.warning(f"Recording {recording_id} not in RECORDING status, ignoring start event")
                return
            
            logger.info(f"DEBUG: handle_recording_start called with message: {message}")
            
            station_id = message['station_id']
            name = message['name']
            format = message['format']
            bitrate = message['bitrate']
            end_time = datetime.fromisoformat(message['end_time'])
            
            logger.info(f"DEBUG: Parsed message - recording_id: {recording_id}, station_id: {station_id}")
            
            # Get station info
            logger.info(f"DEBUG: Got database connection")
            
            station = db.query(Station).filter(Station.id == station_id).first()
            logger.info(f"DEBUG: Queried station, found: {station is not None}")
            
            if not station or not station.is_valid:
                logger.error(f"Invalid station for recording {recording_id}")
                return
            
            logger.info(f"DEBUG: Station is valid, creating output file path")
            
            # Create output file path
            recordings_dir = Path(config.get('storage', 'recordings_folder'))
            recordings_dir.mkdir(exist_ok=True)
            
            timestamp = datetime.now().strftime('%y%m%d-%a')
            output_file = recordings_dir / f"{name}{timestamp}.{format}"
            
            logger.info(f"DEBUG: Output file: {output_file}")
            logger.info(f"DEBUG: About to start recording thread")
            
            # Start recording in separate thread
            thread = threading.Thread(
                target=self.record_stream,
                args=(recording_id, station.stream_url, output_file, end_time, format, bitrate)
            )
            thread.start()
            
            logger.info(f"DEBUG: Recording thread started")
            
            self.active_recordings[recording_id] = {
                'thread': thread,
                'output_file': output_file,
                'parts': []
            }
            
            logger.info(f"Started recording {name} to {output_file}")
            
        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            logger.error(f"DEBUG: Exception type: {type(e)}")
            import traceback
            logger.error(f"DEBUG: Full traceback: {traceback.format_exc()}")
    
    def handle_recording_stop(self, message):
        """Stop an active recording"""
        try:
            recording_id = message['recording_id']
            
            if recording_id in self.active_recordings:
                # Recording will stop naturally when end time is reached
                logger.info(f"Stop signal received for recording {recording_id}")
            
        except Exception as e:
            logger.error(f"Failed to stop recording: {e}")
    
    def record_stream(self, recording_id, stream_url, output_file, end_time, format, bitrate):
        """Record stream using ffmpeg - simplified single process approach"""
        try:
            db = next(get_db())
            recording = db.query(Recording).filter(Recording.id == recording_id).first()
            
            # Calculate total duration
            total_seconds = int((end_time - datetime.now()).total_seconds())
            if total_seconds <= 0:
                logger.warning(f"Recording {recording_id} end time already passed")
                return
            
            logger.info(f"Starting single FFmpeg process for {total_seconds} seconds")
            
            # Build ffmpeg command for entire duration with reconnection options
            cmd = [
                'ffmpeg', '-y',
                '-reconnect', '1',
                '-reconnect_streamed', '1', 
                '-reconnect_on_network_error', '1',
                '-reconnect_delay_max', '300',  # 5 minutes total retry time (10 retries * 30 seconds)
                '-rw_timeout', '30000000',      # 30 second network timeout (in microseconds)
                '-i', stream_url,
                '-c:a', 'copy' if format == recording.station.format else self.get_codec(format),
                '-t', str(total_seconds),
                str(output_file)
            ]
            
            if bitrate and format != recording.station.format:
                cmd.extend(['-b:a', f'{bitrate}k'])
            
            logger.info(f"FFmpeg command: {' '.join(cmd[-4:])}")  # Log last 4 args for debugging
            
            start_time = datetime.now()
            process = subprocess.run(cmd, capture_output=True, text=False)
            actual_end_time = datetime.now()
            
            if process.returncode == 0 and output_file.exists():
                # Set correct status based on whether recording was interrupted
                if recording.was_interrupted:
                    recording.status = 'PARTIAL'
                    logger.info(f"Recording completed with interruptions (PARTIAL): {recording.file_size} bytes")
                else:
                    recording.status = 'COMPLETE'
                    logger.info(f"Recording completed successfully: {recording.file_size} bytes, planned duration: {recording.duration}s")
                
                recording.file_path = str(output_file)
                recording.file_size = output_file.stat().st_size
                # Keep original user-specified duration, don't overwrite with actual time
            else:
                recording.status = 'FAILED'
                error_msg = "FFmpeg failed"
                if process.stderr:
                    try:
                        error_msg = process.stderr.decode('utf-8', errors='ignore')[:200]
                    except:
                        pass
                logger.error(f"Recording failed: {error_msg}")
            
            # Commit status to database BEFORE trying to publish events
            db.commit()
            
            # Try to publish completion event (if this fails, recording status is already saved)
            try:
                event_bus.publish('recording.completed', {
                    'recording_id': recording_id,
                    'status': recording.status,
                    'file_size': recording.file_size,
                    'duration': recording.duration
                })
                logger.info(f"Published completion event for recording {recording_id}")
            except Exception as e:
                logger.error(f"Failed to publish completion event (recording status already saved): {e}")
            
            # Remove from active recordings
            if recording_id in self.active_recordings:
                del self.active_recordings[recording_id]
            
            # Create podcast episode if recording is attached to a podcast and completed successfully
            if recording.podcast_id and recording.status in ['COMPLETE', 'PARTIAL']:
                self.create_podcast_episode(recording)
            
            # Schedule next recurring instance if this was generated from a recurring recording
            self.schedule_next_recurring_if_needed(recording)
            
            # Clean up
            if recording_id in self.active_recordings:
                del self.active_recordings[recording_id]
            
        except Exception as e:
            logger.error(f"Recording failed for {recording_id}: {e}")
            # Mark as failed in database
            try:
                db = next(get_db())
                recording = db.query(Recording).filter(Recording.id == recording_id).first()
                if recording:
                    recording.status = 'FAILED'
                    db.commit()
            except:
                pass
            
            # Merge parts if multiple
            if len(total_parts) > 1:
                self.merge_parts(total_parts, output_file)
                # Multiple parts indicate interruptions
                recording.status = 'PARTIAL'
                logger.info(f"Recording completed with {len(total_parts)} parts (PARTIAL)")
            elif len(total_parts) == 1:
                total_parts[0].rename(output_file)
                # Check if recording was marked as interrupted
                if recording.was_interrupted:
                    recording.status = 'PARTIAL'
                    logger.info(f"Recording completed but was interrupted (PARTIAL)")
                else:
                    recording.status = 'COMPLETE'
                    logger.info(f"Recording completed successfully (COMPLETE)")
            else:
                recording.status = 'FAILED'
                logger.error(f"No parts recorded for {recording_id}")
            
            if output_file.exists():
                recording.file_path = str(output_file)
                recording.file_size = output_file.stat().st_size
                # Keep original user-specified duration, don't overwrite
            
            # Commit status to database BEFORE trying to publish events
            db.commit()
            
            # Try to publish completion event (if this fails, recording status is already saved)
            try:
                event_bus.publish('recording.completed', {
                    'recording_id': recording_id,
                    'status': recording.status,
                    'file_path': str(output_file) if output_file.exists() else None,
                    'file_size': recording.file_size,
                    'duration': recording.duration
                })
                logger.info(f"Published completion event for recording {recording_id}")
            except Exception as e:
                logger.error(f"Failed to publish completion event (recording status already saved): {e}")
            
            # Create podcast episode if recording is attached to a podcast and completed successfully
            if recording.podcast_id and recording.status in ['COMPLETE', 'PARTIAL']:
                self.create_podcast_episode(recording)
            
            # Schedule next recurring instance if this was generated from a recurring recording
            self.schedule_next_recurring_if_needed(recording)
            
            # Clean up
            if recording_id in self.active_recordings:
                del self.active_recordings[recording_id]
            
        except Exception as e:
            logger.error(f"Recording failed for {recording_id}: {e}")
    
    def merge_parts(self, parts, output_file):
        """Merge recording parts using ffmpeg concat"""
        try:
            # Create concat file
            concat_file = output_file.parent / f"{output_file.stem}_concat.txt"
            
            with open(concat_file, 'w') as f:
                for part in parts:
                    f.write(f"file '{part.file_path}'\n")
            
            # Run ffmpeg concat
            cmd = [
                'ffmpeg', '-f', 'concat', '-safe', '0',
                '-i', str(concat_file),
                '-c', 'copy',
                str(output_file)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            # Clean up concat file
            concat_file.unlink()
            
            return result.returncode == 0
            
        except Exception as e:
            logger.error(f"Failed to merge parts: {e}")
            return False
    
    def create_podcast_episode(self, recording):
        """Create a podcast episode from a completed recording"""
        try:
            from shared.models import PodcastEpisode, Podcast
            
            db = next(get_db())
            
            # Get podcast details
            podcast = db.query(Podcast).filter(Podcast.id == recording.podcast_id).first()
            if not podcast:
                logger.error(f"Podcast {recording.podcast_id} not found for recording {recording.id}")
                return
            
            # Check if episode already exists
            existing_episode = db.query(PodcastEpisode).filter(PodcastEpisode.recording_id == recording.id).first()
            if existing_episode:
                logger.info(f"Episode already exists for recording {recording.id}")
                return
            
            # Create episode title and description
            title = recording.name
            
            # Format date as "Saturday, 13th of December 2025"
            day_name = recording.start_time.strftime('%A')
            day = recording.start_time.day
            if 4 <= day <= 20 or 24 <= day <= 30:
                suffix = "th"
            else:
                suffix = ["st", "nd", "rd"][day % 10 - 1]
            month_name = recording.start_time.strftime('%B')
            year = recording.start_time.year
            time_str = recording.start_time.strftime('%H:%M')
            
            description = f"{recording.name}, recorded on {day_name}, {day}{suffix} of {month_name} {year} at {time_str}"
            
            # Create episode
            episode = PodcastEpisode(
                podcast_id=recording.podcast_id,
                recording_id=recording.id,
                title=title,
                description=description,
                pub_date=datetime.utcnow()
            )
            
            db.add(episode)
            db.commit()
            
            logger.info(f"Created podcast episode '{title}' for podcast '{podcast.title}'")
            
        except Exception as e:
            logger.error(f"Failed to create podcast episode for recording {recording.id}: {e}")

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

    def schedule_next_recurring_if_needed(self, completed_recording):
        """Schedule next instance if this recording was part of a recurring series"""
        try:
            db = next(get_db())
            
            # Find the original recurring template by matching name and station
            recurring_template = db.query(Recording).filter(
                Recording.name == completed_recording.name,
                Recording.station_id == completed_recording.station_id,
                Recording.is_recurring == True
            ).first()
            
            if not recurring_template:
                return  # Not part of a recurring series
            
            # Check if next instance already exists
            existing_next = db.query(Recording).filter(
                Recording.name == recurring_template.name,
                Recording.station_id == recurring_template.station_id,
                Recording.is_recurring == False,
                Recording.start_time > completed_recording.start_time
            ).first()
            
            if existing_next:
                logger.info(f"Next recurring instance already exists for: {recurring_template.name}")
                return
            
            # Calculate next occurrence using enhanced logic
            try:
                next_time = self.calculate_next_recurrence(completed_recording.start_time, recurring_template.recurrence_type)
            except ValueError as e:
                logger.error(str(e))
                return
            
            # Check if we've passed the end date
            if recurring_template.recurrence_end and next_time > recurring_template.recurrence_end:
                logger.info(f"Recurring recording {recurring_template.name} has reached its end date")
                return
            
            # Create next instance
            next_recording = Recording(
                name=recurring_template.name,
                station_id=recurring_template.station_id,
                podcast_id=recurring_template.podcast_id,
                start_time=next_time,
                end_time=next_time + timedelta(seconds=recurring_template.duration),
                duration=recurring_template.duration,
                format=recurring_template.format,
                bitrate=recurring_template.bitrate,
                is_recurring=False,
                save_to_additional_local=recurring_template.save_to_additional_local,
                save_to_nextcloud=recurring_template.save_to_nextcloud
            )
            
            db.add(next_recording)
            db.commit()
            
            logger.info(f"Scheduled next recurring instance: {recurring_template.name} at {next_time}")
            
        except Exception as e:
            logger.error(f"Failed to schedule next recurring instance: {e}")

    def merge_parts(self, parts, output_file):
        """Merge recording parts using ffmpeg concat"""
        try:
            # Create concat file
            concat_file = output_file.with_suffix('.txt')
            with open(concat_file, 'w', encoding='utf-8') as f:
                for part in parts:
                    f.write(f"file '{part}'\n")
            
            # Merge using ffmpeg
            cmd = [
                'ffmpeg', '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', str(concat_file),
                '-c', 'copy',
                str(output_file)
            ]
            
            # Run without text decoding to avoid encoding issues
            result = subprocess.run(cmd, capture_output=True, text=False)
            
            if result.returncode == 0:
                # Clean up
                concat_file.unlink()
                for part in parts:
                    part.unlink()
                
                logger.info(f"Merged {len(parts)} parts into {output_file}")
            else:
                logger.error(f"Failed to merge parts: FFmpeg returned {result.returncode}")
            
        except Exception as e:
            logger.error(f"Failed to merge parts: {e}")
    
    def get_codec(self, format):
        """Get ffmpeg codec for format"""
        codecs = {
            'mp3': 'libmp3lame',
            'aac': 'aac',
            'm4a': 'aac',
            'mp4': 'aac'
        }
        return codecs.get(format, 'libmp3lame')
    
    def run(self):
        logger.info("Recording service starting...")
        try:
            event_bus.connect()
            event_bus.start_consuming()
        except Exception as e:
            logger.error(f"Recording service failed: {e}")

if __name__ == "__main__":
    service = RecordingService()
    service.run()
