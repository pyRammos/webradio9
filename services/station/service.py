import sys
import os
import subprocess
import json
import threading
from flask import Flask, jsonify
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from shared.config import config
from shared.logging import setup_logger
from shared.events import event_bus
from shared.models import get_db, Station

logger = setup_logger('station')

class StationService:
    def __init__(self):
        self.event_bus_ready = False
        self.setup_event_handlers()
        self.start_health_server()
    
    def start_health_server(self):
        """Start Flask health check server on port 5003"""
        app = Flask(__name__)
        
        @app.route('/health')
        def health():
            return jsonify({
                'status': 'ready' if self.event_bus_ready else 'starting',
                'event_bus_connected': self.event_bus_ready
            })
        
        # Start in background thread
        def run_health_server():
            app.run(host='0.0.0.0', port=5003, debug=False)
        
        health_thread = threading.Thread(target=run_health_server, daemon=True)
        health_thread.start()
    
    def setup_event_handlers(self):
        try:
            event_bus.subscribe('station.create', self.handle_station_create)
            event_bus.subscribe('station.validate', self.handle_station_validate)
            self.event_bus_ready = True
        except Exception as e:
            logger.error(f"Failed to setup event handlers: {e}")
            self.event_bus_ready = False
    
    def handle_station_create(self, message):
        """Create a new station and validate its stream"""
        try:
            db = next(get_db())
            station = Station(
                name=message['name'],
                stream_url=message['stream_url']
            )
            db.add(station)
            db.commit()
            
            logger.info(f"Created station: {station.name}")
            
            # Trigger validation
            event_bus.publish('station.validate', {
                'station_id': station.id,
                'stream_url': station.stream_url
            })
            
        except Exception as e:
            logger.error(f"Failed to create station: {e}")
    
    def handle_station_validate(self, message):
        """Validate stream URL using ffprobe"""
        try:
            station_id = message['station_id']
            stream_url = message['stream_url']
            
            # Use ffprobe to validate and get stream info
            cmd = [
                'ffprobe', '-v', 'quiet', '-print_format', 'json',
                '-show_format', '-show_streams', stream_url
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            db = next(get_db())
            station = db.query(Station).filter(Station.id == station_id).first()
            
            if result.returncode == 0:
                # Parse ffprobe output
                probe_data = json.loads(result.stdout)
                audio_stream = next((s for s in probe_data['streams'] if s['codec_type'] == 'audio'), None)
                
                if audio_stream:
                    station.is_valid = True
                    station.format = audio_stream.get('codec_name', 'unknown')
                    station.bitrate = int(audio_stream.get('bit_rate', 0)) // 1000 if audio_stream.get('bit_rate') else None
                    station.sample_rate = int(audio_stream.get('sample_rate', 0)) if audio_stream.get('sample_rate') else None
                    station.channels = audio_stream.get('channels', 0)
                    
                    logger.info(f"Station validated: {station.name} - {station.format} {station.bitrate}kbps")
                    
                    event_bus.publish('station.validated', {
                        'station_id': station_id,
                        'is_valid': True,
                        'format': station.format,
                        'bitrate': station.bitrate
                    })
                else:
                    station.is_valid = False
                    logger.warning(f"No audio stream found for station: {station.name}")
            else:
                station.is_valid = False
                logger.error(f"Stream validation failed for {station.name}: {result.stderr}")
            
            db.commit()
            
        except Exception as e:
            logger.error(f"Station validation error: {e}")
    
    def run(self):
        logger.info("Station service starting...")
        try:
            event_bus.connect()
            event_bus.start_consuming()
        except Exception as e:
            logger.error(f"Station service failed: {e}")

if __name__ == "__main__":
    service = StationService()
    service.run()
