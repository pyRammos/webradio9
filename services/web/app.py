from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file, Response
import sys
import os
import json
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from pathlib import Path
from werkzeug.utils import secure_filename
import uuid
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from shared.config import config
from shared.logging import setup_logger
from shared.models import get_db, Station, Recording, Podcast, PodcastEpisode, RecordingPart
from shared.events import event_bus

app = Flask(__name__)
app.secret_key = config.get('auth', 'secret_key')
logger = setup_logger('web')

# Setup event handlers for podcast episode creation
def setup_podcast_event_handlers():
    """Setup event handlers for automatic podcast episode creation"""
    try:
        event_bus.connect()
        
        def handle_recording_completed(message):
            """Create podcast episode when recording completes"""
            try:
                recording_id = message['recording_id']
                status = message['status']
                
                if status != 'COMPLETE':
                    return  # Only create episodes for successful recordings
                
                db = next(get_db())
                recording = db.query(Recording).filter(Recording.id == recording_id).first()
                
                if not recording or not recording.podcast_id:
                    return  # No podcast assigned
                
                # Check if episode already exists
                existing_episode = db.query(PodcastEpisode).filter(
                    PodcastEpisode.recording_id == recording_id
                ).first()
                
                if existing_episode:
                    return  # Episode already exists
                
                # Get podcast
                podcast = db.query(Podcast).filter(Podcast.id == recording.podcast_id).first()
                if not podcast:
                    return
                
                # Get next episode number
                last_episode = db.query(PodcastEpisode).filter(
                    PodcastEpisode.podcast_id == recording.podcast_id
                ).order_by(PodcastEpisode.episode_number.desc()).first()
                
                episode_number = (last_episode.episode_number + 1) if last_episode else 1
                
                # Create episode
                episode = PodcastEpisode(
                    podcast_id=recording.podcast_id,
                    recording_id=recording_id,
                    title=f"{recording.name} - {recording.start_time.strftime('%Y-%m-%d')}",
                    description=f"Recorded from {recording.station.name} on {recording.start_time.strftime('%B %d, %Y')}",
                    episode_number=episode_number,
                    pub_date=recording.start_time
                )
                
                db.add(episode)
                db.commit()
                
                logger.info(f"Created podcast episode {episode_number} for recording {recording.name}")
                
            except Exception as e:
                logger.error(f"Failed to create podcast episode: {e}")
        
        # Subscribe to recording completion events
        event_bus.subscribe('recording.completed', handle_recording_completed)
        
        # Start consuming in a separate thread
        import threading
        def consume_events():
            try:
                event_bus.start_consuming()
            except Exception as e:
                logger.error(f"Event consumption failed: {e}")
        
        event_thread = threading.Thread(target=consume_events, daemon=True)
        event_thread.start()
        
    except Exception as e:
        logger.error(f"Failed to setup podcast event handlers: {e}")

# Initialize podcast event handlers
setup_podcast_event_handlers()

@app.route('/')
def index():
    if 'authenticated' not in session:
        return redirect(url_for('login'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Get credentials from config
        admin_username = config.get('auth', 'admin_username')
        admin_password = config.get('auth', 'admin_password')
        
        if username == admin_username and password == admin_password:
            session['authenticated'] = True
            session['username'] = username
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error='Invalid credentials')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('authenticated', None)
    return redirect(url_for('login'))

@app.route('/api/timezone')
def api_timezone():
    return jsonify({
        'timezone': config.get('app', 'timezone', 'Europe/London')
    })

@app.route('/api/stations')
def api_stations():
    if 'authenticated' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    db = next(get_db())
    stations = db.query(Station).all()
    return jsonify([{
        'id': s.id,
        'name': s.name,
        'stream_url': s.stream_url,
        'is_valid': s.is_valid,
        'format': s.format,
        'bitrate': s.bitrate,
        'sample_rate': s.sample_rate,
        'channels': s.channels,
        'metadata': s.metadata if isinstance(s.metadata, dict) else None
    } for s in stations])

@app.route('/api/recordings')
def api_recordings():
    if 'authenticated' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    db = next(get_db())
    recordings = db.query(Recording).order_by(Recording.created_at.desc()).limit(10).all()
    return jsonify([{
        'id': r.id,
        'name': r.name,
        'status': r.status,
        'start_time': r.start_time.isoformat() if r.start_time else None,
        'duration': r.duration,
        'is_recurring': r.is_recurring,
        'recurrence_type': r.recurrence_type
    } for r in recordings])

# Station Management
@app.route('/stations')
def stations():
    if 'authenticated' not in session:
        return redirect(url_for('login'))
    return render_template('stations.html')

@app.route('/api/stations', methods=['POST'])
def create_station():
    if 'authenticated' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        data = request.json
        
        # Connect to event bus when needed
        try:
            event_bus.connect()
        except:
            pass  # Continue even if event bus fails
        
        # Publish station creation event
        event_bus.publish('station.create', {
            'name': data['name'],
            'stream_url': data['stream_url']
        })
        
        logger.info(f"Published station.create event for: {data['name']}")
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Failed to create station: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/stations/<int:station_id>', methods=['DELETE'])
def delete_station(station_id):
    if 'authenticated' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    db = next(get_db())
    station = db.query(Station).filter(Station.id == station_id).first()
    if station:
        db.delete(station)
        db.commit()
    
    return jsonify({'success': True})

# Recording Management
@app.route('/recordings')
def recordings():
    if 'authenticated' not in session:
        return redirect(url_for('login'))
    return render_template('recordings.html')

def calculate_next_recurrence(current_time, recurrence_type):
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

def schedule_next_recurring_instance(base_recording, db):
    """Schedule only the next instance of a recurring recording"""
    # Check if next instance already exists
    existing_next = db.query(Recording).filter(
        Recording.name == base_recording.name,
        Recording.station_id == base_recording.station_id,
        Recording.is_recurring == False,
        Recording.start_time > base_recording.start_time
    ).first()
    
    if existing_next:
        logger.info(f"Next instance already exists for recurring recording: {base_recording.name}")
        return
    
    # Calculate next occurrence using enhanced logic
    try:
        next_time = calculate_next_recurrence(base_recording.start_time, base_recording.recurrence_type)
    except ValueError as e:
        logger.error(str(e))
        return
    
    # Check if we've passed the end date
    if base_recording.recurrence_end and next_time > base_recording.recurrence_end:
        logger.info(f"Recurring recording {base_recording.name} has reached its end date")
        return
    
    # Create next instance
    next_recording = Recording(
        name=base_recording.name,
        station_id=base_recording.station_id,
        podcast_id=base_recording.podcast_id,
        start_time=next_time,
        end_time=next_time + timedelta(seconds=base_recording.duration),
        duration=base_recording.duration,
        format=base_recording.format,
        bitrate=base_recording.bitrate,
        is_recurring=False,  # Individual instance is not recurring
        save_to_additional_local=base_recording.save_to_additional_local,
        save_to_nextcloud=base_recording.save_to_nextcloud
    )
    
    db.add(next_recording)
    db.commit()
    
    logger.info(f"Scheduled next recurring instance: {base_recording.name} at {next_time}")

@app.route('/api/recordings', methods=['POST'])
def create_recording():
    if 'authenticated' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        data = request.json
        db = next(get_db())
        
        # Default start time is now + 2 minutes
        start_time = datetime.fromisoformat(data.get('start_time', 
            (datetime.now() + timedelta(minutes=2)).isoformat()))
        end_time = start_time + timedelta(minutes=int(data['duration']))
        
        # Validate recurrence type matches start day
        if data.get('is_recurring') and data.get('recurrence_type'):
            recurrence_type = data['recurrence_type']
            start_weekday = start_time.weekday()  # 0=Monday, 6=Sunday
            
            if recurrence_type == 'weekdays' and start_weekday >= 5:
                return jsonify({'error': 'Weekdays recordings cannot start on weekends (Sat/Sun)'}), 400
            elif recurrence_type == 'weekends' and start_weekday < 5:
                return jsonify({'error': 'Weekend recordings cannot start on weekdays (Mon-Fri)'}), 400
        
        # Parse recurrence end date if provided
        recurrence_end = None
        if data.get('recurrence_end'):
            recurrence_end = datetime.fromisoformat(data['recurrence_end'])
        
        recording = Recording(
            name=data['name'],
            station_id=data['station_id'],
            podcast_id=data.get('podcast_id') if data.get('podcast_id') else None,
            start_time=start_time,
            end_time=end_time,
            duration=int(data['duration']) * 60,
            format=data.get('format', 'mp3'),
            bitrate=data.get('bitrate'),
            is_recurring=data.get('is_recurring', False),
            recurrence_type=data.get('recurrence_type'),
            recurrence_end=recurrence_end,
            save_to_additional_local=data.get('save_to_additional_local', False),
            save_to_nextcloud=data.get('save_to_nextcloud', False),
            nextcloud_base_dir=data.get('nextcloud_base_dir', '/Recordings')
        )
        
        db.add(recording)
        db.commit()
        
        # Generate next recurring instance if needed
        if recording.is_recurring:
            schedule_next_recurring_instance(recording, db)
        
        # Publish recording schedule event
        schedule_event = {
            'recording_id': recording.id,
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat()
        }
        
        event_bus.publish('recording.schedule', schedule_event)
        logger.info(f"Published recording.schedule event for: {recording.name} (ID: {recording.id})")
        
        return jsonify({'success': True, 'recording_id': recording.id})
        
    except Exception as e:
        logger.error(f"Failed to create recording: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/recording-history')
def recording_history():
    if 'authenticated' not in session:
        return redirect(url_for('login'))
    return render_template('recording_history.html')

@app.route('/logs')
def logs():
    if 'authenticated' not in session:
        return redirect(url_for('login'))
    return render_template('logs.html')

@app.route('/services')
def services():
    if 'authenticated' not in session:
        return redirect(url_for('login'))
    return render_template('services.html')

@app.route('/api/logs')
def api_logs():
    try:
        lines = int(request.args.get('lines', 100))
        log_file = '/home/george/projects/radio1/logs/webradio9.log'
        
        with open(log_file, 'r') as f:
            all_lines = f.readlines()
            recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
            
        return jsonify({
            'lines': [line.rstrip() for line in recent_lines],
            'total_lines': len(all_lines)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/services/restart', methods=['POST'])
def restart_services():
    try:
        data = request.get_json()
        service = data.get('service', 'all')
        
        import subprocess
        import os
        
        if service == 'all':
            # Restart all services by killing run_services.py
            subprocess.run(['pkill', '-f', 'run_services.py'], check=False)
            return jsonify({'success': True, 'message': 'All services restart initiated'})
        else:
            # Restart specific service
            service_map = {
                'web': 'services/web/app.py',
                'scheduler': 'services/scheduler/service.py', 
                'recording': 'services/recording/service.py',
                'station': 'services/station/service.py',
                'storage': 'services/storage/service.py',
                'notification': 'services/notification/service.py',
                'podcast': 'services/podcast/service.py'
            }
            
            if service in service_map:
                subprocess.run(['pkill', '-f', service_map[service]], check=False)
                return jsonify({'success': True, 'message': f'{service} service restart initiated'})
            else:
                return jsonify({'error': 'Invalid service name'}), 400
                
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/recordings/active')
def get_active_recordings():
    # Temporarily disable auth for debugging
    # if 'authenticated' not in session:
    #     return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        db = next(get_db())
        
        # Get all recordings to identify series
        all_recordings = db.query(Recording).join(Station).all()
        
        result = []
        recurring_series = {}
        standalone_recordings = []
        
        # Identify recurring series by finding recordings with the same name
        for recording in all_recordings:
            # Check if there are other recordings with the same name (indicating a series)
            same_name_recordings = db.query(Recording).filter(Recording.name == recording.name).all()
            
            if len(same_name_recordings) > 1:
                # This is part of a recurring series
                if recording.name not in recurring_series:
                    recurring_series[recording.name] = same_name_recordings
            elif recording.status == 'SCHEDULED':
                # This is a standalone scheduled recording
                standalone_recordings.append(recording)
        
        # Add recurring series (show next scheduled time)
        for series_name, recordings_list in recurring_series.items():
            # Find the template (first recurring recording) and next scheduled
            template = None
            next_scheduled = None
            
            for rec in recordings_list:
                if rec.is_recurring and template is None:
                    template = rec
                if rec.status == 'SCHEDULED' and (next_scheduled is None or rec.start_time < next_scheduled.start_time):
                    next_scheduled = rec
            
            if template and next_scheduled:
                result.append({
                    'id': template.id,
                    'name': template.name,
                    'status': 'SCHEDULED',
                    'start_time': next_scheduled.start_time.isoformat(),
                    'duration': template.duration,
                    'is_recurring': True,
                    'recurrence_type': template.recurrence_type,
                    'station_name': template.station.name if template.station else None
                })
        
        # Add standalone recordings
        for recording in standalone_recordings:
            result.append({
                'id': recording.id,
                'name': recording.name,
                'status': recording.status,
                'start_time': recording.start_time.isoformat() if recording.start_time else None,
                'duration': recording.duration,
                'is_recurring': False,
                'recurrence_type': None,
                'station_name': recording.station.name if recording.station else None
            })
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error fetching active recordings: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/recordings/<int:recording_id>', methods=['GET'])
def get_recording(recording_id):
    try:
        db = next(get_db())
        recording = db.query(Recording).filter(Recording.id == recording_id).first()
        
        if not recording:
            return jsonify({'error': 'Recording not found'}), 404
            
        return jsonify({
            'id': recording.id,
            'name': recording.name,
            'status': recording.status,
            'start_time': recording.start_time.isoformat() if recording.start_time else None,
            'duration': recording.duration,  # This is already in seconds
            'is_recurring': recording.is_recurring,
            'recurrence_type': recording.recurrence_type,
            'recurrence_end': recording.recurrence_end.isoformat() if recording.recurrence_end else None,
            'station_id': recording.station_id,
            'format': recording.format,
            'podcast_id': recording.podcast_id,
            'save_to_additional_local': recording.save_to_additional_local,
            'save_to_nextcloud': recording.save_to_nextcloud,
            'nextcloud_base_dir': recording.nextcloud_base_dir
        })
        
    except Exception as e:
        logger.error(f"Error fetching recording {recording_id}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/recordings/<int:recording_id>', methods=['PUT'])
def update_recording(recording_id):
    if 'authenticated' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        data = request.json
        db = next(get_db())
        
        # Get existing recording
        recording = db.query(Recording).filter(Recording.id == recording_id).first()
        if not recording:
            return jsonify({'error': 'Recording not found'}), 404
        
        # Don't allow editing recordings that are currently recording
        if recording.status == 'RECORDING':
            return jsonify({'error': 'Cannot edit recording that is currently in progress'}), 400
        
        # Parse start time
        start_time = datetime.fromisoformat(data['start_time'])
        end_time = start_time + timedelta(minutes=int(data['duration']))
        
        # Validate recurrence type matches start day
        if data.get('is_recurring') and data.get('recurrence_type'):
            recurrence_type = data['recurrence_type']
            start_weekday = start_time.weekday()
            
            if recurrence_type == 'weekdays' and start_weekday >= 5:
                return jsonify({'error': 'Weekdays recordings cannot start on weekends (Sat/Sun)'}), 400
            elif recurrence_type == 'weekends' and start_weekday < 5:
                return jsonify({'error': 'Weekend recordings cannot start on weekdays (Mon-Fri)'}), 400
        
        # Parse recurrence end date if provided
        recurrence_end = None
        if data.get('recurrence_end'):
            recurrence_end = datetime.fromisoformat(data['recurrence_end'])
        
        # Update recording fields
        recording.name = data['name']
        recording.station_id = data['station_id']
        recording.podcast_id = data.get('podcast_id') if data.get('podcast_id') else None
        recording.start_time = start_time
        recording.end_time = end_time
        recording.duration = int(data['duration']) * 60
        recording.format = data.get('format', 'mp3')
        recording.bitrate = data.get('bitrate')
        recording.is_recurring = data.get('is_recurring', False)
        recording.recurrence_type = data.get('recurrence_type')
        recording.recurrence_end = recurrence_end
        recording.save_to_additional_local = data.get('save_to_additional_local', False)
        recording.save_to_nextcloud = data.get('save_to_nextcloud', False)
        
        db.commit()
        
        logger.info(f"Updated recording: {recording.name} (ID: {recording.id})")
        return jsonify({'success': True, 'recording_id': recording.id})
        
    except Exception as e:
        logger.error(f"Failed to update recording {recording_id}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/validate-storage', methods=['POST'])
def validate_storage():
    if 'authenticated' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        data = request.json
        storage_type = data.get('type')
        
        if storage_type == 'local':
            # Check if additional local storage directory exists and is writable
            additional_local_path = config.get('storage', 'additional_local_folder', fallback=None)
            if not additional_local_path:
                return jsonify({'valid': False, 'error': 'Additional local path not configured'})
            
            local_path = Path(additional_local_path)
            if not local_path.exists():
                return jsonify({'valid': False, 'error': f'Directory does not exist: {additional_local_path}'})
            
            if not local_path.is_dir():
                return jsonify({'valid': False, 'error': f'Path is not a directory: {additional_local_path}'})
            
            # Test write permissions
            test_file = local_path / '.webradio9_test'
            try:
                test_file.write_text('test')
                test_file.unlink()
                return jsonify({'valid': True})
            except Exception as e:
                return jsonify({'valid': False, 'error': f'Directory not writable: {str(e)}'})
        
        elif storage_type == 'nextcloud':
            # Check NextCloud configuration and connectivity
            nextcloud_url = config.get('storage', 'nextcloud_url', fallback=None)
            nextcloud_username = config.get('storage', 'nextcloud_username', fallback=None)
            nextcloud_password = config.get('storage', 'nextcloud_password', fallback=None)
            base_dir = data.get('base_dir', '/Recordings')
            
            if not all([nextcloud_url, nextcloud_username, nextcloud_password]):
                return jsonify({'valid': False, 'error': 'NextCloud credentials not configured'})
            
            # Test NextCloud connection (simplified check)
            import requests
            try:
                # Test basic auth to NextCloud
                auth_url = f"{nextcloud_url.rstrip('/')}/remote.php/dav/files/{nextcloud_username}/"
                response = requests.get(auth_url, auth=(nextcloud_username, nextcloud_password), timeout=10)
                
                if response.status_code == 200:
                    return jsonify({'valid': True})
                elif response.status_code == 401:
                    return jsonify({'valid': False, 'error': 'NextCloud authentication failed'})
                else:
                    return jsonify({'valid': False, 'error': f'NextCloud connection failed (HTTP {response.status_code})'})
            
            except requests.exceptions.Timeout:
                return jsonify({'valid': False, 'error': 'NextCloud connection timeout'})
            except requests.exceptions.ConnectionError:
                return jsonify({'valid': False, 'error': 'Cannot connect to NextCloud server'})
            except Exception as e:
                return jsonify({'valid': False, 'error': f'NextCloud validation error: {str(e)}'})
        
        else:
            return jsonify({'valid': False, 'error': 'Unknown storage type'})
    
    except Exception as e:
        logger.error(f"Storage validation error: {e}")
        return jsonify({'valid': False, 'error': 'Validation failed'})

@app.route('/api/recordings/<int:recording_id>', methods=['DELETE'])
def delete_recording(recording_id):
    if 'authenticated' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        db = next(get_db())
        recording = db.query(Recording).filter(Recording.id == recording_id).first()
        
        if not recording:
            return jsonify({'error': 'Recording not found'}), 404
        
        # Cancel if scheduled
        if recording.status == 'SCHEDULED':
            try:
                event_bus.publish('recording.cancel', {'recording_id': recording_id})
                logger.info(f"Published recording.cancel event for: {recording.name} (ID: {recording_id})")
            except Exception as e:
                logger.warning(f"Failed to publish cancel event: {e}")
        
        # Delete related records first (to avoid foreign key constraints)
        
        # Delete podcast episodes that reference this recording
        from shared.models import PodcastEpisode
        episodes = db.query(PodcastEpisode).filter(PodcastEpisode.recording_id == recording_id).all()
        for episode in episodes:
            db.delete(episode)
        
        # Delete recording parts
        from shared.models import RecordingPart
        parts = db.query(RecordingPart).filter(RecordingPart.recording_id == recording_id).all()
        for part in parts:
            db.delete(part)
        
        # Delete file if exists
        if recording.file_path:
            file_path = Path(recording.file_path)
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Deleted file: {file_path}")
        
        # Finally delete the recording
        recording_name = recording.name
        db.delete(recording)
        db.commit()
        
        logger.info(f"Deleted recording: {recording_name} (ID: {recording_id})")
        return jsonify({'success': True})
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete recording {recording_id}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/recordings/<int:recording_id>/download')
def download_recording(recording_id):
    db = next(get_db())
    recording = db.query(Recording).filter(Recording.id == recording_id).first()
    
    if not recording or not recording.file_path:
        return "Recording not found", 404
    
    file_path = Path(recording.file_path)
    if not file_path.exists():
        return "File not found", 404
    
    return send_file(file_path, as_attachment=True)

# Podcast Management
@app.route('/podcasts')
def podcasts():
    if 'authenticated' not in session:
        return redirect(url_for('login'))
    return render_template('podcasts.html')

@app.route('/api/podcasts', methods=['GET'])
def api_podcasts():
    if 'authenticated' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    db = next(get_db())
    podcasts = db.query(Podcast).all()
    return jsonify([{
        'id': p.id,
        'uuid': p.uuid,
        'title': p.title,
        'description': p.description,
        'author': p.author,
        'email': p.email,
        'category': p.category,
        'language': p.language,
        'image_url': p.image_url,
        'created_at': p.created_at.isoformat() if p.created_at else None,
        'episode_count': len(p.episodes)
    } for p in podcasts])

@app.route('/api/podcasts', methods=['POST'])
def create_podcast():
    if 'authenticated' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        db = next(get_db())
        
        # Handle form data (with potential file upload)
        if request.content_type and 'multipart/form-data' in request.content_type:
            title = request.form.get('title')
            description = request.form.get('description')
            author = request.form.get('author')
            email = request.form.get('email')
            category = request.form.get('category', 'Technology')
            
            # Handle image upload
            image_url = None
            if 'image' in request.files:
                image_file = request.files['image']
                if image_file and image_file.filename:
                    # Secure filename and save
                    filename = secure_filename(image_file.filename)
                    # Add UUID to prevent conflicts
                    name, ext = os.path.splitext(filename)
                    unique_filename = f"{name}_{uuid.uuid4().hex[:8]}{ext}"
                    
                    image_path = Path(__file__).parent / 'static' / 'images' / 'podcasts' / unique_filename
                    image_file.save(str(image_path))
                    
                    # Store relative URL
                    image_url = f"/static/images/podcasts/{unique_filename}"
        else:
            # Handle JSON data (backward compatibility)
            data = request.json
            title = data['title']
            description = data.get('description')
            author = data.get('author')
            email = data.get('email')
            category = data.get('category', 'Technology')
            image_url = None
        
        podcast = Podcast(
            title=title,
            description=description,
            author=author,
            email=email,
            category=category,
            image_url=image_url
        )
        
        db.add(podcast)
        db.commit()
        
        return jsonify({'success': True, 'podcast_id': podcast.id})
        
    except Exception as e:
        logger.error(f"Failed to create podcast: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/podcasts/<int:podcast_id>', methods=['PUT'])
def update_podcast(podcast_id):
    if 'authenticated' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        db = next(get_db())
        
        # Get existing podcast
        podcast = db.query(Podcast).filter(Podcast.id == podcast_id).first()
        if not podcast:
            return jsonify({'error': 'Podcast not found'}), 404
        
        # Handle both form data and JSON
        if request.content_type and 'multipart/form-data' in request.content_type:
            # Form data with potential file upload
            title = request.form.get('title')
            description = request.form.get('description', '')
            author = request.form.get('author', '')
            email = request.form.get('email', '')
            category = request.form.get('category', 'Technology')
            
            # Handle image upload
            image_url = podcast.image_url  # Keep existing image by default
            image_file = request.files.get('image')
            if image_file and image_file.filename:
                # Save new image
                filename = secure_filename(image_file.filename)
                name, ext = os.path.splitext(filename)
                unique_filename = f"{name}_{uuid.uuid4().hex[:8]}{ext}"
                
                image_path = Path(__file__).parent / 'static' / 'images' / 'podcasts' / unique_filename
                image_file.save(str(image_path))
                
                # Delete old image if exists
                if podcast.image_url:
                    try:
                        old_image_path = Path(__file__).parent / 'static' / podcast.image_url.lstrip('/')
                        if old_image_path.exists():
                            old_image_path.unlink()
                    except Exception as e:
                        logger.warning(f"Failed to delete old podcast image: {e}")
                
                image_url = f"/static/images/podcasts/{unique_filename}"
        else:
            # JSON data
            data = request.json
            title = data.get('title')
            description = data.get('description', '')
            author = data.get('author', '')
            email = data.get('email', '')
            category = data.get('category', 'Technology')
            image_url = podcast.image_url  # Keep existing image
        
        # Update podcast fields
        podcast.title = title
        podcast.description = description
        podcast.author = author
        podcast.email = email
        podcast.category = category
        if image_url:
            podcast.image_url = image_url
        
        db.commit()
        
        logger.info(f"Updated podcast: {podcast.title} (ID: {podcast_id})")
        return jsonify({'success': True, 'podcast_id': podcast.id})
        
    except Exception as e:
        logger.error(f"Failed to update podcast {podcast_id}: {e}")
        return jsonify({'error': str(e)}), 500

# Public Podcast Routes
# Public Podcast Routes
@app.route('/api/podcasts/<int:podcast_id>', methods=['DELETE'])
def delete_podcast(podcast_id):
    if 'authenticated' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        db = next(get_db())
        podcast = db.query(Podcast).filter(Podcast.id == podcast_id).first()
        
        if not podcast:
            return jsonify({'error': 'Podcast not found'}), 404
        
        # Delete associated episodes first
        episodes = db.query(PodcastEpisode).filter(PodcastEpisode.podcast_id == podcast_id).all()
        for episode in episodes:
            db.delete(episode)
        
        # Delete podcast image if exists
        if podcast.image_url:
            try:
                image_path = Path(__file__).parent / 'static' / podcast.image_url.lstrip('/')
                if image_path.exists():
                    image_path.unlink()
            except Exception as e:
                logger.warning(f"Failed to delete podcast image: {e}")
        
        # Delete podcast
        db.delete(podcast)
        db.commit()
        
        logger.info(f"Deleted podcast: {podcast.title} (ID: {podcast_id})")
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Failed to delete podcast {podcast_id}: {e}")
        return jsonify({'error': str(e)}), 500

# Public Podcast Routes (no authentication required)
@app.route('/podcasts')
def podcasts_public_list():
    """Public list of all podcasts - no authentication required"""
    try:
        db = next(get_db())
        podcasts = db.query(Podcast).all()
        
        # Only show podcasts that have episodes
        podcasts_with_episodes = []
        for podcast in podcasts:
            episode_count = db.query(PodcastEpisode).filter(
                PodcastEpisode.podcast_id == podcast.id
            ).join(Recording).filter(
                Recording.file_path.isnot(None),
                Recording.status == 'COMPLETE'
            ).count()
            
            if episode_count > 0:
                podcasts_with_episodes.append({
                    'podcast': podcast,
                    'episode_count': episode_count
                })
        
        return render_template('podcasts_public_list.html', podcasts=podcasts_with_episodes)
        
    except Exception as e:
        logger.error(f"Public podcasts list failed: {e}")
        return "Error loading podcasts", 500

@app.route('/podcasts/<podcast_uuid>/rss')
def podcast_rss(podcast_uuid):
    """Generate RSS feed for podcast - public access"""
    try:
        db = next(get_db())
        podcast = db.query(Podcast).filter(Podcast.uuid == podcast_uuid).first()
        
        if not podcast:
            return "Podcast not found", 404
        
        # Get episodes with valid recordings
        episodes = db.query(PodcastEpisode).filter(
            PodcastEpisode.podcast_id == podcast.id
        ).join(Recording).filter(
            Recording.file_path.isnot(None),
            Recording.status == 'COMPLETE'
        ).order_by(PodcastEpisode.pub_date.desc()).all()
        
        # Get base URL from request
        base_url = f"{request.scheme}://{request.host}"
        
        # Generate RSS content
        rss_content = generate_podcast_rss(podcast, episodes, base_url)
        
        return Response(rss_content, mimetype='application/rss+xml')
        
    except Exception as e:
        logger.error(f"RSS generation failed for podcast {podcast_uuid}: {e}")
        return "RSS generation failed", 500

@app.route('/podcasts/<podcast_uuid>')
def podcast_public(podcast_uuid):
    """Public podcast page - no authentication required"""
    try:
        db = next(get_db())
        podcast = db.query(Podcast).filter(Podcast.uuid == podcast_uuid).first()
        
        if not podcast:
            return "Podcast not found", 404
        
        # Get episodes with valid recordings
        episodes = db.query(PodcastEpisode).filter(
            PodcastEpisode.podcast_id == podcast.id
        ).join(Recording).filter(
            Recording.file_path.isnot(None),
            Recording.status == 'COMPLETE'
        ).order_by(PodcastEpisode.pub_date.desc()).all()
        
        # Check if files exist on disk
        valid_episodes = []
        for episode in episodes:
            if episode.recording.file_path and os.path.exists(episode.recording.file_path):
                valid_episodes.append(episode)
        
        return render_template('podcast_public.html', podcast=podcast, episodes=valid_episodes)
        
    except Exception as e:
        logger.error(f"Public podcast page failed for {podcast_uuid}: {e}")
        return "Podcast not found", 404

@app.route('/podcasts/<podcast_uuid>/episodes/<int:episode_id>/download')
def podcast_episode_download(podcast_uuid, episode_id):
    """Download podcast episode - public access"""
    try:
        db = next(get_db())
        
        # Verify podcast and episode exist
        podcast = db.query(Podcast).filter(Podcast.uuid == podcast_uuid).first()
        if not podcast:
            return "Podcast not found", 404
            
        episode = db.query(PodcastEpisode).filter(
            PodcastEpisode.id == episode_id,
            PodcastEpisode.podcast_id == podcast.id
        ).first()
        
        if not episode or not episode.recording:
            return "Episode not found", 404
        
        recording = episode.recording
        if not recording.file_path or not os.path.exists(recording.file_path):
            return "File not found", 404
        
        filename = f"{episode.title}.{recording.format or 'mp3'}"
        return send_file(recording.file_path, as_attachment=True, download_name=filename)
        
    except Exception as e:
        logger.error(f"Episode download failed: {e}")
        return "Download failed", 500

@app.route('/podcasts/<podcast_uuid>/episodes/<int:episode_id>/stream')
def podcast_episode_stream(podcast_uuid, episode_id):
    """Stream podcast episode - public access"""
    try:
        db = next(get_db())
        
        # Verify podcast and episode exist
        podcast = db.query(Podcast).filter(Podcast.uuid == podcast_uuid).first()
        if not podcast:
            return "Podcast not found", 404
            
        episode = db.query(PodcastEpisode).filter(
            PodcastEpisode.id == episode_id,
            PodcastEpisode.podcast_id == podcast.id
        ).first()
        
        if not episode or not episode.recording:
            return "Episode not found", 404
        
        recording = episode.recording
        if not recording.file_path or not os.path.exists(recording.file_path):
            return "File not found", 404
        
        # Determine MIME type
        if recording.file_path.endswith('.mp3'):
            mimetype = 'audio/mpeg'
        elif recording.file_path.endswith('.aac'):
            mimetype = 'audio/aac'
        elif recording.file_path.endswith('.m4a'):
            mimetype = 'audio/mp4'
        else:
            mimetype = 'audio/mpeg'
        
        return send_file(recording.file_path, mimetype=mimetype)
        
    except Exception as e:
        logger.error(f"Episode streaming failed: {e}")
        return "Streaming failed", 500

def generate_podcast_rss(podcast, episodes, base_url):
    """Generate RSS XML for podcast"""
    try:
        # Build RSS items
        rss_items = []
        for episode in episodes:
            if not episode.recording.file_path or not os.path.exists(episode.recording.file_path):
                continue
            
            # Episode download URL
            episode_url = f"{base_url}/podcasts/{podcast.uuid}/episodes/{episode.id}/download"
            
            # Get file size
            file_size = episode.recording.file_size or 0
            if not file_size:
                try:
                    file_size = os.path.getsize(episode.recording.file_path)
                except:
                    file_size = 0
            
            # Format duration
            duration_str = ""
            if episode.recording.duration:
                hours = episode.recording.duration // 3600
                minutes = (episode.recording.duration % 3600) // 60
                seconds = episode.recording.duration % 60
                duration_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            
            rss_items.append(f"""
        <item>
            <title>{escape_xml(episode.title)}</title>
            <description>{escape_xml(episode.description or '')}</description>
            <enclosure url="{episode_url}" length="{file_size}" type="audio/mpeg"/>
            <guid>{episode_url}</guid>
            <pubDate>{episode.pub_date.strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate>
            <itunes:duration>{duration_str}</itunes:duration>
            <itunes:episode>{episode.episode_number}</itunes:episode>
        </item>""")
        
        # Build complete RSS
        rss_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
    <channel>
        <title>{escape_xml(podcast.title)}</title>
        <description>{escape_xml(podcast.description or '')}</description>
        <language>{podcast.language}</language>
        <itunes:author>{escape_xml(podcast.author or '')}</itunes:author>
        <itunes:email>{escape_xml(podcast.email or '')}</itunes:email>
        <itunes:category text="{escape_xml(podcast.category or 'Technology')}"/>
        <link>{base_url}/podcasts/{podcast.uuid}</link>
        <itunes:image href="{base_url}{podcast.image_url}" />
        <lastBuildDate>{datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S +0000')}</lastBuildDate>
        {''.join(rss_items)}
    </channel>
</rss>"""
        
        return rss_content
        
    except Exception as e:
        logger.error(f"RSS generation failed: {e}")
        return None

def escape_xml(text):
    """Escape XML special characters"""
    if not text:
        return ""
    return (str(text).replace('&', '&amp;')
                    .replace('<', '&lt;')
                    .replace('>', '&gt;')
                    .replace('"', '&quot;')
                    .replace("'", '&#39;'))

@app.route('/api/recordings/history')
def api_recordings_history():
    try:
        db = next(get_db())
        recordings = db.query(Recording).filter(Recording.status.in_(['COMPLETE', 'FAILED', 'CANCELLED', 'PARTIAL'])).all()
        
        result = []
        for recording in recordings:
            result.append({
                'id': recording.id,
                'name': recording.name,
                'start_time': recording.start_time.isoformat() if recording.start_time else None,
                'status': recording.status.lower() if recording.status else 'unknown',
                'format': recording.format,
                'file_size': recording.file_size,
                'file_path': recording.file_path
            })
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/recordings/bulk-download', methods=['POST'])
def bulk_download():
    try:
        recording_ids = json.loads(request.form.get('recording_ids', '[]'))
        if not recording_ids:
            return jsonify({'error': 'No recordings selected'}), 400
        
        db = next(get_db())
        recordings = db.query(Recording).filter(Recording.id.in_(recording_ids), Recording.status == 'COMPLETE').all()
        
        if len(recordings) == 1:
            # Single file download
            recording = recordings[0]
            if recording.file_path and os.path.exists(recording.file_path):
                return send_file(recording.file_path, as_attachment=True)
        else:
            # Multiple files - create zip
            import zipfile
            import tempfile
            
            temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
            with zipfile.ZipFile(temp_zip.name, 'w') as zip_file:
                for recording in recordings:
                    if recording.file_path and os.path.exists(recording.file_path):
                        filename = f"{recording.name}.{recording.format or 'mp3'}"
                        zip_file.write(recording.file_path, filename)
            
            return send_file(temp_zip.name, as_attachment=True, download_name='recordings.zip')
        
        return jsonify({'error': 'No valid files found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/recordings/bulk-delete', methods=['POST'])
def bulk_delete():
    try:
        data = request.get_json()
        recording_ids = data.get('recording_ids', [])
        
        if not recording_ids:
            return jsonify({'error': 'No recordings selected'}), 400
        
        db = next(get_db())
        recordings = db.query(Recording).filter(Recording.id.in_(recording_ids)).all()
        
        for recording in recordings:
            # Delete podcast episodes that reference this recording
            episodes = db.query(PodcastEpisode).filter(PodcastEpisode.recording_id == recording.id).all()
            for episode in episodes:
                db.delete(episode)
            
            # Delete recording parts
            parts = db.query(RecordingPart).filter(RecordingPart.recording_id == recording.id).all()
            for part in parts:
                db.delete(part)
            
            # Delete file if it exists
            if recording.file_path and os.path.exists(recording.file_path):
                os.remove(recording.file_path)
            
            # Delete recording
            db.delete(recording)
        
        db.commit()
        return jsonify({'success': True, 'deleted': len(recordings)})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/recordings/<int:recording_id>/download')
def api_download_recording(recording_id):
    try:
        db = next(get_db())
        recording = db.query(Recording).filter(Recording.id == recording_id).first()
        
        if not recording:
            return jsonify({'error': 'Recording not found'}), 404
        
        if not recording.file_path or not os.path.exists(recording.file_path):
            return jsonify({'error': 'File not found'}), 404
        
        filename = f"{recording.name}.{recording.format or 'mp3'}"
        return send_file(recording.file_path, as_attachment=True, download_name=filename)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/recordings/<int:recording_id>/stream')
def stream_recording_by_id(recording_id):
    try:
        db = next(get_db())
        recording = db.query(Recording).filter(Recording.id == recording_id).first()
        
        if not recording or not recording.file_path:
            return jsonify({'error': 'Recording or file not found'}), 404
        
        if not os.path.exists(recording.file_path):
            return jsonify({'error': 'File not found on disk'}), 404
        
        # Determine MIME type based on file extension
        if recording.file_path.endswith('.mp3'):
            mimetype = 'audio/mpeg'
        elif recording.file_path.endswith('.aac'):
            mimetype = 'audio/aac'
        elif recording.file_path.endswith('.m4a'):
            mimetype = 'audio/mp4'
        else:
            mimetype = 'audio/mpeg'
        
        return send_file(recording.file_path, mimetype=mimetype)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/system/health')
def system_health():
    try:
        import subprocess
        
        services = [
            {'name': 'Web', 'process': 'app.py', 'health_port': None},
            {'name': 'Station', 'process': 'services/station/service.py', 'health_port': 5003},
            {'name': 'Scheduler', 'process': 'services/scheduler/service.py', 'health_port': 5002},
            {'name': 'Recording', 'process': 'services/recording/service.py', 'health_port': 5001},
            {'name': 'Storage', 'process': 'services/storage/service.py', 'health_port': 5004},
            {'name': 'Notification', 'process': 'services/notification/service.py', 'health_port': 5005},
            {'name': 'Podcast', 'process': 'services/podcast/service.py', 'health_port': 5006}
        ]
        
        result = []
        for service in services:
            try:
                # Check if process is running
                cmd = f"pgrep -f '{service['process']}'"
                proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                process_running = proc.returncode == 0
                
                # Check health endpoint if available
                health_status = 'unknown'
                event_bus_ready = False
                
                if service['health_port'] and process_running:
                    try:
                        import requests
                        response = requests.get(f"http://localhost:{service['health_port']}/health", timeout=2)
                        if response.status_code == 200:
                            health_data = response.json()
                            health_status = health_data.get('status', 'unknown')
                            event_bus_ready = health_data.get('event_bus_connected', False)
                    except:
                        health_status = 'unreachable'
                
                status = 'running' if process_running else 'stopped'
                if process_running and health_status == 'ready':
                    status = 'ready'
                elif process_running and health_status == 'starting':
                    status = 'starting'
                elif process_running and health_status == 'unreachable':
                    status = 'unhealthy'
                
                result.append({
                    'name': service['name'],
                    'status': status,
                    'process_running': process_running,
                    'health_status': health_status,
                    'event_bus_ready': event_bus_ready
                })
            except Exception as e:
                result.append({
                    'name': service['name'],
                    'status': 'unknown',
                    'error': str(e)
                })
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    debug_mode = config.getboolean('app', 'debug', fallback=False)
    host = config.get('app', 'host', fallback='0.0.0.0')
    port = config.getint('app', 'port', fallback=5000)
    
    app.run(debug=debug_mode, host=host, port=port)
