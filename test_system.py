#!/usr/bin/env python3
"""
WebRadio9 System Integration Tests
Tests all main requirements and functionality
"""

import sys
import os
import time
import requests
import json
from datetime import datetime, timedelta
from pathlib import Path

sys.path.append(os.path.dirname(__file__))

from shared.models import get_db, Station, Recording, Podcast, PodcastEpisode
from shared.events import event_bus
from shared.config import config

class WebRadio9Tests:
    def __init__(self):
        self.base_url = "http://localhost:5000"
        self.session = requests.Session()
        self.test_results = []
    
    def log_test(self, test_name, success, message=""):
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"{status}: {test_name}")
        if message:
            print(f"    {message}")
        self.test_results.append((test_name, success, message))
    
    def login(self):
        """Test authentication system"""
        try:
            # Test login page
            response = self.session.get(f"{self.base_url}/")
            if response.status_code != 200:
                self.log_test("Web App Accessibility", False, f"Status: {response.status_code}")
                return False
            
            # Test login
            login_data = {"username": "admin", "password": "admin123"}
            response = self.session.post(f"{self.base_url}/login", data=login_data)
            
            if response.status_code == 200 and "Dashboard" in response.text:
                self.log_test("Authentication System", True, "Login successful")
                return True
            else:
                self.log_test("Authentication System", False, "Login failed")
                return False
                
        except Exception as e:
            self.log_test("Authentication System", False, str(e))
            return False
    
    def test_database_models(self):
        """Test database connectivity and models"""
        try:
            db = next(get_db())
            
            # Test Station model
            station_count = db.query(Station).count()
            self.log_test("Database - Station Model", True, f"Found {station_count} stations")
            
            # Test Recording model
            recording_count = db.query(Recording).count()
            self.log_test("Database - Recording Model", True, f"Found {recording_count} recordings")
            
            # Test Podcast model
            podcast_count = db.query(Podcast).count()
            self.log_test("Database - Podcast Model", True, f"Found {podcast_count} podcasts")
            
            return True
            
        except Exception as e:
            self.log_test("Database Models", False, str(e))
            return False
    
    def test_station_management(self):
        """Test station creation and validation"""
        try:
            # Create test station via API
            station_data = {
                "name": "Test Radio Station",
                "stream_url": "http://stream.example.com/test.mp3"
            }
            
            response = self.session.post(
                f"{self.base_url}/api/stations",
                json=station_data,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                self.log_test("Station Creation API", True, "Station created via API")
                
                # Check if station appears in database
                time.sleep(1)
                db = next(get_db())
                station = db.query(Station).filter(Station.name == "Test Radio Station").first()
                
                if station:
                    self.log_test("Station Database Storage", True, f"Station ID: {station.id}")
                    return station.id
                else:
                    self.log_test("Station Database Storage", False, "Station not found in DB")
            else:
                self.log_test("Station Creation API", False, f"Status: {response.status_code}")
            
            return None
            
        except Exception as e:
            self.log_test("Station Management", False, str(e))
            return None
    
    def test_recording_scheduling(self):
        """Test recording scheduling functionality"""
        try:
            # First ensure we have a station
            db = next(get_db())
            station = db.query(Station).first()
            
            if not station:
                # Create a test station directly
                station = Station(
                    name="Test Station for Recording",
                    stream_url="http://test.stream.com/audio.mp3",
                    is_valid=True,
                    format="mp3",
                    bitrate=128
                )
                db.add(station)
                db.commit()
            
            # Schedule a recording
            start_time = (datetime.now() + timedelta(minutes=1)).isoformat()
            recording_data = {
                "name": "Test Recording",
                "station_id": station.id,
                "start_time": start_time,
                "duration": 5,  # 5 minutes
                "format": "mp3",
                "save_to_additional_local": False,
                "save_to_nextcloud": False
            }
            
            response = self.session.post(
                f"{self.base_url}/api/recordings",
                json=recording_data,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                result = response.json()
                self.log_test("Recording Scheduling API", True, f"Recording ID: {result.get('recording_id')}")
                
                # Verify in database
                recording = db.query(Recording).filter(Recording.name == "Test Recording").first()
                if recording and recording.status == "SCHEDULED":
                    self.log_test("Recording Database Entry", True, f"Status: {recording.status}")
                    return recording.id
                else:
                    self.log_test("Recording Database Entry", False, "Recording not properly scheduled")
            else:
                self.log_test("Recording Scheduling API", False, f"Status: {response.status_code}")
            
            return None
            
        except Exception as e:
            self.log_test("Recording Scheduling", False, str(e))
            return None
    
    def test_podcast_management(self):
        """Test podcast creation and management"""
        try:
            # Create a podcast
            podcast_data = {
                "title": "Test Podcast",
                "description": "A test podcast for WebRadio9",
                "author": "Test Author",
                "email": "test@example.com",
                "category": "Technology"
            }
            
            response = self.session.post(
                f"{self.base_url}/api/podcasts",
                json=podcast_data,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                self.log_test("Podcast Creation API", True, "Podcast created successfully")
                
                # Verify in database
                db = next(get_db())
                podcast = db.query(Podcast).filter(Podcast.title == "Test Podcast").first()
                
                if podcast:
                    self.log_test("Podcast Database Storage", True, f"UUID: {podcast.uuid}")
                    
                    # Test RSS feed generation
                    rss_response = self.session.get(f"{self.base_url}/podcasts/{podcast.uuid}/rss")
                    if rss_response.status_code == 200 and "<?xml" in rss_response.text:
                        self.log_test("RSS Feed Generation", True, "Valid RSS XML generated")
                    else:
                        self.log_test("RSS Feed Generation", False, f"RSS Status: {rss_response.status_code}")
                    
                    return podcast.id
                else:
                    self.log_test("Podcast Database Storage", False, "Podcast not found in DB")
            else:
                self.log_test("Podcast Creation API", False, f"Status: {response.status_code}")
            
            return None
            
        except Exception as e:
            self.log_test("Podcast Management", False, str(e))
            return None
    
    def test_event_system(self):
        """Test RabbitMQ event system"""
        try:
            # Test event bus connection
            event_bus.connect()
            self.log_test("Event Bus Connection", True, "RabbitMQ connected")
            
            # Test event publishing
            test_message = {"test": "message", "timestamp": datetime.now().isoformat()}
            event_bus.publish("test.event", test_message)
            self.log_test("Event Publishing", True, "Test event published")
            
            return True
            
        except Exception as e:
            self.log_test("Event System", False, str(e))
            return False
    
    def test_file_operations(self):
        """Test file and directory operations"""
        try:
            # Test recordings directory
            recordings_dir = Path(config.get('storage', 'recordings_folder'))
            if recordings_dir.exists():
                self.log_test("Recordings Directory", True, f"Path: {recordings_dir}")
            else:
                self.log_test("Recordings Directory", False, "Directory not found")
            
            # Test logs directory
            logs_dir = Path(__file__).parent / 'logs'
            if logs_dir.exists():
                log_files = list(logs_dir.glob('*.log'))
                self.log_test("Logging System", True, f"Found {len(log_files)} log files")
            else:
                self.log_test("Logging System", False, "Logs directory not found")
            
            return True
            
        except Exception as e:
            self.log_test("File Operations", False, str(e))
            return False
    
    def test_api_endpoints(self):
        """Test all API endpoints"""
        endpoints = [
            ("/api/stations", "GET"),
            ("/api/recordings", "GET"),
            ("/api/podcasts", "GET")
        ]
        
        for endpoint, method in endpoints:
            try:
                if method == "GET":
                    response = self.session.get(f"{self.base_url}{endpoint}")
                
                if response.status_code == 200:
                    data = response.json()
                    self.log_test(f"API {endpoint}", True, f"Returned {len(data)} items")
                else:
                    self.log_test(f"API {endpoint}", False, f"Status: {response.status_code}")
                    
            except Exception as e:
                self.log_test(f"API {endpoint}", False, str(e))
    
    def test_web_interface(self):
        """Test web interface pages"""
        pages = [
            ("/", "Dashboard"),
            ("/stations", "Stations"),
            ("/recordings", "Recordings"),
            ("/podcasts", "Podcasts")
        ]
        
        for path, page_name in pages:
            try:
                response = self.session.get(f"{self.base_url}{path}")
                if response.status_code == 200 and page_name.lower() in response.text.lower():
                    self.log_test(f"Web UI - {page_name}", True, "Page loads correctly")
                else:
                    self.log_test(f"Web UI - {page_name}", False, f"Status: {response.status_code}")
                    
            except Exception as e:
                self.log_test(f"Web UI - {page_name}", False, str(e))
    
    def run_all_tests(self):
        """Run complete test suite"""
        print("=" * 50)
        print("WebRadio9 System Integration Tests")
        print("=" * 50)
        
        # Core system tests
        print("\n🔧 Core System Tests:")
        self.test_database_models()
        self.test_event_system()
        self.test_file_operations()
        
        # Web application tests
        print("\n🌐 Web Application Tests:")
        if self.login():
            self.test_api_endpoints()
            self.test_web_interface()
        
        # Feature tests
        print("\n📡 Feature Tests:")
        station_id = self.test_station_management()
        recording_id = self.test_recording_scheduling()
        podcast_id = self.test_podcast_management()
        
        # Summary
        print("\n" + "=" * 50)
        print("Test Summary:")
        print("=" * 50)
        
        passed = sum(1 for _, success, _ in self.test_results if success)
        total = len(self.test_results)
        
        print(f"Total Tests: {total}")
        print(f"Passed: {passed}")
        print(f"Failed: {total - passed}")
        print(f"Success Rate: {(passed/total)*100:.1f}%")
        
        if total - passed > 0:
            print("\nFailed Tests:")
            for name, success, message in self.test_results:
                if not success:
                    print(f"  - {name}: {message}")
        
        return passed == total

if __name__ == "__main__":
    tests = WebRadio9Tests()
    success = tests.run_all_tests()
    sys.exit(0 if success else 1)
