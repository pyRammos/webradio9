import sys
import os
import threading
from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from shared.config import config
from shared.logging import setup_logger
from shared.events import event_bus
from shared.models import get_db, Recording, Podcast, PodcastEpisode

logger = setup_logger('podcast')

class PodcastService:
    def __init__(self):
        self.event_bus_ready = False
        self.setup_event_handlers()
        self.start_health_server()
    
    def start_health_server(self):
        """Start Flask health check server on port 5006"""
        app = Flask(__name__)
        
        @app.route('/health')
        def health():
            return jsonify({
                'status': 'ready' if self.event_bus_ready else 'starting',
                'event_bus_connected': self.event_bus_ready
            })
        
        # Start in background thread
        def run_health_server():
            app.run(host='0.0.0.0', port=5006, debug=False)
        
        health_thread = threading.Thread(target=run_health_server, daemon=True)
        health_thread.start()
    
    def setup_event_handlers(self):
        try:
            event_bus.subscribe('recording.completed', self.handle_recording_completed)
            event_bus.subscribe('podcast.episode.add', self.handle_episode_add)
            self.event_bus_ready = True
        except Exception as e:
            logger.error(f"Failed to setup event handlers: {e}")
            self.event_bus_ready = False
    
    def handle_recording_completed(self, message):
        """Add completed recording to podcast if scheduled"""
        try:
            recording_id = message['recording_id']
            status = message['status']
            
            if status == 'FAILED':
                return
            
            db = next(get_db())
            recording = db.query(Recording).filter(Recording.id == recording_id).first()
            
            # Check if this recording was scheduled for a podcast
            # This would be set during recording scheduling
            # For now, we'll handle this in the web interface
            
        except Exception as e:
            logger.error(f"Podcast episode creation failed: {e}")
    
    def handle_episode_add(self, message):
        """Add episode to podcast"""
        try:
            podcast_id = message['podcast_id']
            recording_id = message['recording_id']
            
            db = next(get_db())
            podcast = db.query(Podcast).filter(Podcast.id == podcast_id).first()
            recording = db.query(Recording).filter(Recording.id == recording_id).first()
            
            if not podcast or not recording:
                return
            
            # Get next episode number
            last_episode = db.query(PodcastEpisode).filter(
                PodcastEpisode.podcast_id == podcast_id
            ).order_by(PodcastEpisode.episode_number.desc()).first()
            
            episode_number = (last_episode.episode_number + 1) if last_episode else 1
            
            # Create episode
            episode = PodcastEpisode(
                podcast_id=podcast_id,
                recording_id=recording_id,
                title=f"{recording.name} - {recording.start_time.strftime('%Y-%m-%d')}",
                description=f"Recorded from {recording.station.name}",
                episode_number=episode_number,
                pub_date=recording.start_time
            )
            
            db.add(episode)
            db.commit()
            
            logger.info(f"Added episode {episode_number} to podcast {podcast.title}")
            
            event_bus.publish('podcast.rss.update', {
                'podcast_id': podcast_id
            })
            
        except Exception as e:
            logger.error(f"Episode addition failed: {e}")
    
    def generate_rss_feed(self, podcast_id, base_url="http://localhost:5000"):
        """Generate RSS feed for podcast"""
        try:
            db = next(get_db())
            podcast = db.query(Podcast).filter(Podcast.id == podcast_id).first()
            
            if not podcast:
                return None
            
            episodes = db.query(PodcastEpisode).filter(
                PodcastEpisode.podcast_id == podcast_id
            ).join(Recording).filter(
                Recording.file_path.isnot(None)
            ).order_by(PodcastEpisode.pub_date.desc()).all()
            
            # Build RSS XML
            rss_items = []
            for episode in episodes:
                if not episode.recording.file_path:
                    continue
                
                file_path = Path(episode.recording.file_path)
                if not file_path.exists():
                    continue
                
                # Build episode URL
                episode_url = f"{base_url}/recordings/{episode.recording.id}/download"
                
                rss_items.append(f"""
                <item>
                    <title>{self.escape_xml(episode.title)}</title>
                    <description>{self.escape_xml(episode.description or '')}</description>
                    <enclosure url="{episode_url}" length="{episode.recording.file_size or 0}" type="audio/mpeg"/>
                    <guid>{episode_url}</guid>
                    <pubDate>{episode.pub_date.strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate>
                </item>""")
            
            rss_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
    <channel>
        <title>{self.escape_xml(podcast.title)}</title>
        <description>{self.escape_xml(podcast.description or '')}</description>
        <language>{podcast.language}</language>
        <itunes:author>{self.escape_xml(podcast.author or '')}</itunes:author>
        <itunes:email>{self.escape_xml(podcast.email or '')}</itunes:email>
        <itunes:category text="{self.escape_xml(podcast.category or 'Technology')}"/>
        <link>{base_url}/podcasts/{podcast.uuid}</link>
        {''.join(rss_items)}
    </channel>
</rss>"""
            
            return rss_content
            
        except Exception as e:
            logger.error(f"RSS generation failed: {e}")
            return None
    
    def escape_xml(self, text):
        """Escape XML special characters"""
        if not text:
            return ""
        return (text.replace('&', '&amp;')
                   .replace('<', '&lt;')
                   .replace('>', '&gt;')
                   .replace('"', '&quot;')
                   .replace("'", '&#39;'))
    
    def run(self):
        logger.info("Podcast service starting...")
        try:
            event_bus.connect()
            event_bus.start_consuming()
        except Exception as e:
            logger.error(f"podcast service failed: {e}")

if __name__ == "__main__":
    service = PodcastService()
    service.run()
