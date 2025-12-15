#!/usr/bin/env python3
"""
Test podcast public functionality
"""

import sys
import os
import requests
from pathlib import Path

sys.path.append(os.path.dirname(__file__))

from shared.models import get_db, Podcast, PodcastEpisode, Recording, Station

def test_podcast_public():
    """Test public podcast access"""
    
    # Get a podcast from database
    db = next(get_db())
    podcast = db.query(Podcast).first()
    
    if not podcast:
        print("❌ No podcasts found in database")
        return False
    
    base_url = "http://localhost:5000"
    
    try:
        # Test public podcast page
        response = requests.get(f"{base_url}/podcasts/{podcast.uuid}")
        if response.status_code == 200:
            print(f"✓ Public podcast page accessible: {podcast.title}")
        else:
            print(f"❌ Public podcast page failed: {response.status_code}")
            return False
        
        # Test RSS feed
        response = requests.get(f"{base_url}/podcasts/{podcast.uuid}/rss")
        if response.status_code == 200 and 'xml' in response.headers.get('content-type', ''):
            print(f"✓ RSS feed accessible and valid XML")
        else:
            print(f"❌ RSS feed failed: {response.status_code}")
            return False
        
        # Test episode access if episodes exist
        episodes = db.query(PodcastEpisode).filter(PodcastEpisode.podcast_id == podcast.id).all()
        if episodes:
            episode = episodes[0]
            
            # Test episode download
            response = requests.head(f"{base_url}/podcasts/{podcast.uuid}/episodes/{episode.id}/download")
            if response.status_code == 200:
                print(f"✓ Episode download accessible")
            else:
                print(f"❌ Episode download failed: {response.status_code}")
            
            # Test episode streaming
            response = requests.head(f"{base_url}/podcasts/{podcast.uuid}/episodes/{episode.id}/stream")
            if response.status_code == 200:
                print(f"✓ Episode streaming accessible")
            else:
                print(f"❌ Episode streaming failed: {response.status_code}")
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

if __name__ == "__main__":
    print("Testing podcast public functionality...")
    success = test_podcast_public()
    print(f"\nTest {'PASSED' if success else 'FAILED'}")
