#!/usr/bin/env python3
import sys
import os
import subprocess
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.append(str(project_root))

def test_web_service():
    service_path = project_root / 'services' / 'web' / 'app.py'
    
    print(f"Starting web service: {service_path}")
    print(f"Python executable: {sys.executable}")
    print(f"Working directory: {project_root}")
    
    env = os.environ.copy()
    
    process = subprocess.Popen([
        sys.executable, str(service_path)
    ], 
    cwd=str(project_root),
    env=env,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE)
    
    print(f"Started process PID: {process.pid}")
    
    # Wait a bit and check if it's still running
    import time
    time.sleep(5)
    
    if process.poll() is None:
        print("Service is still running")
        process.terminate()
    else:
        print(f"Service died with return code: {process.returncode}")
        stdout, stderr = process.communicate()
        if stdout:
            print(f"STDOUT: {stdout.decode()}")
        if stderr:
            print(f"STDERR: {stderr.decode()}")

if __name__ == '__main__':
    test_web_service()
