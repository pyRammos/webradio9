#!/usr/bin/env python3
"""
Service runner for WebRadio9 microservices
Starts all services in separate processes
"""

import sys
import os
import subprocess
import signal
import time
from pathlib import Path
import fcntl

# Add project root to path
sys.path.append(os.path.dirname(__file__))

from shared.logging import setup_logger

logger = setup_logger('runner')

class ServiceRunner:
    def __init__(self):
        self.processes = {}
        self.services = [
            'web',
            'station',
            'scheduler', 
            'recording',
            'storage',
            'notification',
            'podcast'
        ]
        self.lock_file = None
        
    def acquire_lock(self):
        """Prevent multiple instances of run_services"""
        try:
            lock_path = Path(__file__).parent / 'run_services.lock'
            self.lock_file = open(lock_path, 'w')
            fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.lock_file.write(str(os.getpid()))
            self.lock_file.flush()
            return True
        except IOError:
            print("❌ Another instance of run_services.py is already running!")
            print("   Stop it first with: pkill -f run_services")
            return False
    
    def release_lock(self):
        """Release the process lock"""
        if self.lock_file:
            try:
                fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_UN)
                self.lock_file.close()
                lock_path = Path(__file__).parent / 'run_services.lock'
                if lock_path.exists():
                    lock_path.unlink()
            except:
                pass
    
    def start_service(self, service_name):
        """Start a single service"""
        try:
            if service_name == 'web':
                service_path = Path(__file__).parent / 'services' / 'web' / 'app.py'
            else:
                service_path = Path(__file__).parent / 'services' / service_name / 'service.py'
            
            if not service_path.exists():
                logger.error(f"Service file not found: {service_path}")
                return None
            
            # Set up environment and working directory
            env = os.environ.copy()
            project_root = str(Path(__file__).parent)
            
            # Use subprocess with proper session handling
            process = subprocess.Popen([
                sys.executable, str(service_path)
            ], 
            cwd=project_root,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True)  # Start new session to avoid signal propagation
            
            logger.info(f"Started {service_name} service (PID: {process.pid})")
            return process
            
        except Exception as e:
            logger.error(f"Failed to start {service_name}: {e}")
            return None
    
    def start_all_services(self):
        """Start all microservices"""
        logger.info("Starting WebRadio9 microservices...")
        
        for service_name in self.services:
            process = self.start_service(service_name)
            if process:
                self.processes[service_name] = process
                time.sleep(1)  # Small delay between starts
    
    def stop_all_services(self):
        """Stop all running services"""
        logger.info("Stopping all services...")
        
        for service_name, process in self.processes.items():
            try:
                process.terminate()
                process.wait(timeout=5)
                logger.info(f"Stopped {service_name} service")
            except subprocess.TimeoutExpired:
                process.kill()
                logger.warning(f"Force killed {service_name} service")
            except Exception as e:
                logger.error(f"Error stopping {service_name}: {e}")
    
    def restart_all_services(self):
        """Restart all services"""
        logger.info("Restarting all services...")
        self.stop_all_services()
        time.sleep(2)
        
        # Reload config
        from shared.config import config
        config.load()
        
        self.processes.clear()
        self.start_all_services()
    
    def monitor_services(self):
        """Monitor running services and restart if needed"""
        while True:
            try:
                for service_name, process in list(self.processes.items()):
                    if process.poll() is not None:
                        logger.warning(f"Service {service_name} died, restarting...")
                        new_process = self.start_service(service_name)
                        if new_process:
                            self.processes[service_name] = new_process
                
                time.sleep(10)  # Check every 10 seconds
                
            except KeyboardInterrupt:
                logger.info("Shutdown requested")
                break
            except Exception as e:
                logger.error(f"Monitor error: {e}")
                time.sleep(5)
    
    def run(self):
        """Main run method"""
        # Acquire lock to prevent multiple instances
        if not self.acquire_lock():
            sys.exit(1)
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, lambda s, f: self.cleanup_and_exit())
        signal.signal(signal.SIGTERM, lambda s, f: self.cleanup_and_exit())
        
        try:
            self.start_all_services()
            self.monitor_services()
        finally:
            self.cleanup_and_exit()
    
    def cleanup_and_exit(self):
        """Clean shutdown"""
        logger.info("Shutting down all services...")
        self.stop_all_services()
        self.release_lock()
        sys.exit(0)

if __name__ == "__main__":
    runner = ServiceRunner()
    runner.run()
