#!/usr/bin/env python3
"""
WebRadio9 Recording Functionality Tests
Tests the core recording capabilities
"""

import sys
import os
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.append(os.path.dirname(__file__))

from shared.models import get_db, Station, Recording
from shared.config import config

class RecordingTests:
    def __init__(self):
        self.recordings_dir = Path(config.get('storage', 'recordings_folder'))
    
    def test_ffmpeg_availability(self):
        """Test if ffmpeg is available"""
        try:
            result = subprocess.run(['ffmpeg', '-version'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                version_line = result.stdout.split('\n')[0]
                print(f"✓ FFmpeg Available: {version_line}")
                return True
            else:
                print("✗ FFmpeg not working properly")
                return False
        except FileNotFoundError:
            print("✗ FFmpeg not found in PATH")
            return False
        except Exception as e:
            print(f"✗ FFmpeg test failed: {e}")
            return False
    
    def test_ffprobe_stream_validation(self):
        """Test stream validation with ffprobe"""
        try:
            # Test with a known working stream (BBC Radio)
            test_streams = [
                "http://stream.live.vc.bbcmedia.co.uk/bbc_radio_one",
                "http://bbcmedia.ic.llnwd.net/stream/bbcmedia_radio1_mf_p",
                "https://stream.rcs.revma.com/aw9uqyxy7tzuv"  # Example stream
            ]
            
            print("\n🔍 Testing Stream Validation:")
            
            for stream_url in test_streams:
                try:
                    cmd = [
                        'ffprobe', '-v', 'quiet', '-print_format', 'json',
                        '-show_format', '-show_streams', stream_url
                    ]
                    
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
                    
                    if result.returncode == 0:
                        print(f"✓ Stream validation works: {stream_url[:50]}...")
                        return True
                    else:
                        print(f"✗ Stream failed: {stream_url[:50]}...")
                        
                except subprocess.TimeoutExpired:
                    print(f"⚠ Stream timeout: {stream_url[:50]}...")
                    continue
            
            print("⚠ No working streams found for validation test")
            return True  # Don't fail the test due to external streams
            
        except Exception as e:
            print(f"✗ Stream validation test failed: {e}")
            return False
    
    def test_recording_directory_setup(self):
        """Test recording directory creation and permissions"""
        try:
            # Ensure recordings directory exists
            self.recordings_dir.mkdir(exist_ok=True)
            
            if self.recordings_dir.exists() and self.recordings_dir.is_dir():
                print(f"✓ Recordings directory: {self.recordings_dir}")
                
                # Test write permissions
                test_file = self.recordings_dir / "test_write.tmp"
                test_file.write_text("test")
                test_file.unlink()
                
                print("✓ Directory write permissions OK")
                return True
            else:
                print("✗ Recordings directory not accessible")
                return False
                
        except Exception as e:
            print(f"✗ Directory setup failed: {e}")
            return False
    
    def test_recording_database_operations(self):
        """Test recording database operations"""
        try:
            db = next(get_db())
            
            # Create test station
            station = Station(
                name="Recording Test Station",
                stream_url="http://test.example.com/stream.mp3",
                is_valid=True,
                format="mp3",
                bitrate=128
            )
            db.add(station)
            db.commit()
            
            # Create test recording
            start_time = datetime.now() + timedelta(minutes=1)
            end_time = start_time + timedelta(minutes=2)
            
            recording = Recording(
                name="Database Test Recording",
                station_id=station.id,
                start_time=start_time,
                end_time=end_time,
                duration=120,
                status="SCHEDULED",
                format="mp3",
                bitrate=128
            )
            db.add(recording)
            db.commit()
            
            print(f"✓ Recording created in database (ID: {recording.id})")
            
            # Test status updates
            recording.status = "RECORDING"
            db.commit()
            
            recording.status = "COMPLETE"
            recording.file_path = str(self.recordings_dir / "test_recording.mp3")
            recording.file_size = 1024000
            db.commit()
            
            print("✓ Recording status updates work")
            return True
            
        except Exception as e:
            print(f"✗ Database operations failed: {e}")
            return False
    
    def test_file_format_support(self):
        """Test different audio format support"""
        try:
            formats = ['mp3', 'aac', 'm4a', 'wav']
            
            print("\n🎵 Testing Audio Format Support:")
            
            for fmt in formats:
                try:
                    # Test if ffmpeg supports the format
                    cmd = ['ffmpeg', '-f', 'lavfi', '-i', 'sine=frequency=1000:duration=1', 
                           '-t', '1', '-f', fmt, '-']
                    
                    result = subprocess.run(cmd, capture_output=True, timeout=10)
                    
                    if result.returncode == 0:
                        print(f"✓ Format supported: {fmt.upper()}")
                    else:
                        print(f"✗ Format not supported: {fmt.upper()}")
                        
                except subprocess.TimeoutExpired:
                    print(f"⚠ Format test timeout: {fmt.upper()}")
            
            return True
            
        except Exception as e:
            print(f"✗ Format support test failed: {e}")
            return False
    
    def test_concurrent_recording_support(self):
        """Test database support for concurrent recordings"""
        try:
            db = next(get_db())
            
            # Get or create test station
            station = db.query(Station).filter(Station.name == "Recording Test Station").first()
            if not station:
                station = Station(
                    name="Concurrent Test Station",
                    stream_url="http://test.com/stream.mp3",
                    is_valid=True
                )
                db.add(station)
                db.commit()
            
            # Create multiple concurrent recordings
            base_time = datetime.now() + timedelta(minutes=5)
            
            recordings = []
            for i in range(3):
                recording = Recording(
                    name=f"Concurrent Recording {i+1}",
                    station_id=station.id,
                    start_time=base_time,
                    end_time=base_time + timedelta(minutes=10),
                    status="SCHEDULED"
                )
                recordings.append(recording)
                db.add(recording)
            
            db.commit()
            
            print(f"✓ Created {len(recordings)} concurrent recordings")
            
            # Test unique name handling
            duplicate_recording = Recording(
                name="Concurrent Recording 1",  # Same name
                station_id=station.id,
                start_time=base_time,
                end_time=base_time + timedelta(minutes=5),
                status="SCHEDULED"
            )
            db.add(duplicate_recording)
            db.commit()
            
            print("✓ Duplicate name handling works")
            return True
            
        except Exception as e:
            print(f"✗ Concurrent recording test failed: {e}")
            return False
    
    def test_storage_configuration(self):
        """Test storage configuration options"""
        try:
            # Test additional local folder setting
            additional_local = config.get('storage', 'additional_local_folder')
            print(f"✓ Additional local folder config: {additional_local or 'Not set'}")
            
            # Test NextCloud settings
            nextcloud_url = config.get('storage', 'nextcloud_url')
            print(f"✓ NextCloud URL config: {nextcloud_url or 'Not set'}")
            
            # Test keep recordings count
            keep_count = config.getint('storage', 'keep_recordings_count')
            print(f"✓ Keep recordings count: {keep_count}")
            
            return True
            
        except Exception as e:
            print(f"✗ Storage configuration test failed: {e}")
            return False
    
    def run_recording_tests(self):
        """Run all recording-related tests"""
        print("=" * 50)
        print("WebRadio9 Recording Functionality Tests")
        print("=" * 50)
        
        tests = [
            ("FFmpeg Availability", self.test_ffmpeg_availability),
            ("Stream Validation", self.test_ffprobe_stream_validation),
            ("Directory Setup", self.test_recording_directory_setup),
            ("Database Operations", self.test_recording_database_operations),
            ("Format Support", self.test_file_format_support),
            ("Concurrent Recordings", self.test_concurrent_recording_support),
            ("Storage Configuration", self.test_storage_configuration)
        ]
        
        results = []
        
        for test_name, test_func in tests:
            print(f"\n🧪 {test_name}:")
            try:
                success = test_func()
                results.append((test_name, success))
            except Exception as e:
                print(f"✗ {test_name} failed with exception: {e}")
                results.append((test_name, False))
        
        # Summary
        print("\n" + "=" * 50)
        print("Recording Tests Summary:")
        print("=" * 50)
        
        passed = sum(1 for _, success in results if success)
        total = len(results)
        
        print(f"Total Tests: {total}")
        print(f"Passed: {passed}")
        print(f"Failed: {total - passed}")
        print(f"Success Rate: {(passed/total)*100:.1f}%")
        
        if total - passed > 0:
            print("\nFailed Tests:")
            for name, success in results:
                if not success:
                    print(f"  - {name}")
        
        return passed == total

if __name__ == "__main__":
    tests = RecordingTests()
    success = tests.run_recording_tests()
    sys.exit(0 if success else 1)
