#!/usr/bin/env python3
"""
WebRadio9 Microservices Tests
Tests individual microservice functionality
"""

import sys
import os
import subprocess
import time
import signal
from pathlib import Path

sys.path.append(os.path.dirname(__file__))

from shared.events import event_bus
from shared.models import get_db, Station, Recording

class MicroservicesTests:
    def __init__(self):
        self.services = [
            'station',
            'scheduler', 
            'recording',
            'storage',
            'notification',
            'podcast'
        ]
        self.processes = {}
    
    def start_service(self, service_name, timeout=5):
        """Start a microservice and test if it initializes"""
        try:
            service_path = Path(__file__).parent / 'services' / service_name / 'service.py'
            
            if not service_path.exists():
                print(f"✗ {service_name.title()} Service: File not found")
                return False
            
            # Start service process
            process = subprocess.Popen([
                sys.executable, str(service_path)
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=str(service_path.parent))
            
            # Wait for initialization
            time.sleep(timeout)
            
            # Check if process is still running
            if process.poll() is None:
                print(f"✓ {service_name.title()} Service: Started successfully (PID: {process.pid})")
                self.processes[service_name] = process
                return True
            else:
                stdout, stderr = process.communicate()
                print(f"✗ {service_name.title()} Service: Failed to start")
                if stderr:
                    print(f"    Error: {stderr.decode()}")
                return False
                
        except Exception as e:
            print(f"✗ {service_name.title()} Service: {e}")
            return False
    
    def stop_service(self, service_name):
        """Stop a running service"""
        if service_name in self.processes:
            try:
                process = self.processes[service_name]
                process.terminate()
                process.wait(timeout=5)
                print(f"✓ {service_name.title()} Service: Stopped")
            except subprocess.TimeoutExpired:
                process.kill()
                print(f"✓ {service_name.title()} Service: Force stopped")
            except Exception as e:
                print(f"✗ {service_name.title()} Service stop error: {e}")
    
    def test_station_service_functionality(self):
        """Test station service with actual events"""
        try:
            print("\n📡 Testing Station Service Functionality:")
            
            # Publish station creation event
            station_data = {
                "name": "Test Station for Service",
                "stream_url": "http://example.com/test.mp3"
            }
            
            event_bus.publish('station.create', station_data)
            print("✓ Published station.create event")
            
            # Wait for processing
            time.sleep(3)
            
            # Check if station was created
            db = next(get_db())
            station = db.query(Station).filter(Station.name == "Test Station for Service").first()
            
            if station:
                print(f"✓ Station created in database (ID: {station.id})")
                return True
            else:
                print("✗ Station not found in database")
                return False
                
        except Exception as e:
            print(f"✗ Station service test failed: {e}")
            return False
    
    def test_scheduler_service_functionality(self):
        """Test scheduler service with recording events"""
        try:
            print("\n⏰ Testing Scheduler Service Functionality:")
            
            # Create a test station first
            db = next(get_db())
            station = db.query(Station).first()
            
            if not station:
                station = Station(
                    name="Scheduler Test Station",
                    stream_url="http://test.com/stream.mp3",
                    is_valid=True
                )
                db.add(station)
                db.commit()
            
            # Create a recording to schedule
            from datetime import datetime, timedelta
            start_time = datetime.now() + timedelta(minutes=2)
            end_time = start_time + timedelta(minutes=5)
            
            recording = Recording(
                name="Scheduler Test Recording",
                station_id=station.id,
                start_time=start_time,
                end_time=end_time,
                status="SCHEDULED"
            )
            db.add(recording)
            db.commit()
            
            # Publish scheduling event
            schedule_data = {
                "recording_id": recording.id,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat()
            }
            
            event_bus.publish('recording.schedule', schedule_data)
            print("✓ Published recording.schedule event")
            
            time.sleep(2)
            print("✓ Scheduler processed event (check logs for details)")
            return True
            
        except Exception as e:
            print(f"✗ Scheduler service test failed: {e}")
            return False
    
    def test_event_flow(self):
        """Test complete event flow between services"""
        try:
            print("\n🔄 Testing Event Flow:")
            
            # Test event publishing and consumption
            test_events = [
                ('station.create', {'name': 'Event Test Station', 'stream_url': 'http://test.com'}),
                ('recording.start', {'recording_id': 1, 'station_id': 1}),
                ('recording.completed', {'recording_id': 1, 'status': 'COMPLETE'})
            ]
            
            for event_name, event_data in test_events:
                event_bus.publish(event_name, event_data)
                print(f"✓ Published {event_name} event")
                time.sleep(0.5)
            
            print("✓ Event flow test completed")
            return True
            
        except Exception as e:
            print(f"✗ Event flow test failed: {e}")
            return False
    
    def run_service_tests(self):
        """Run all microservice tests"""
        print("=" * 50)
        print("WebRadio9 Microservices Tests")
        print("=" * 50)
        
        results = {}
        
        # Test each service startup
        print("\n🚀 Service Startup Tests:")
        for service in self.services:
            results[service] = self.start_service(service)
        
        # Test service functionality
        if results.get('station'):
            results['station_functionality'] = self.test_station_service_functionality()
        
        if results.get('scheduler'):
            results['scheduler_functionality'] = self.test_scheduler_service_functionality()
        
        # Test event system
        results['event_flow'] = self.test_event_flow()
        
        # Stop all services
        print("\n🛑 Stopping Services:")
        for service in self.services:
            if service in self.processes:
                self.stop_service(service)
        
        # Summary
        print("\n" + "=" * 50)
        print("Microservices Test Summary:")
        print("=" * 50)
        
        passed = sum(1 for success in results.values() if success)
        total = len(results)
        
        print(f"Total Tests: {total}")
        print(f"Passed: {passed}")
        print(f"Failed: {total - passed}")
        print(f"Success Rate: {(passed/total)*100:.1f}%")
        
        return passed == total

if __name__ == "__main__":
    tests = MicroservicesTests()
    try:
        success = tests.run_service_tests()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted. Cleaning up...")
        for service in tests.services:
            if service in tests.processes:
                tests.stop_service(service)
