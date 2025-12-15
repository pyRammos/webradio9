#!/usr/bin/env python3
"""
WebRadio9 Test Runner
Runs all test suites and provides comprehensive system validation
"""

import sys
import os
import subprocess
import time
from pathlib import Path

def run_test_suite(test_file, description):
    """Run a test suite and return results"""
    print(f"\n{'='*60}")
    print(f"Running {description}")
    print(f"{'='*60}")
    
    try:
        result = subprocess.run([
            sys.executable, test_file
        ], cwd=Path(__file__).parent, capture_output=False, text=True)
        
        return result.returncode == 0
        
    except Exception as e:
        print(f"Failed to run {description}: {e}")
        return False

def check_prerequisites():
    """Check if system prerequisites are met"""
    print("🔍 Checking Prerequisites...")
    
    checks = []
    
    # Check Docker containers
    try:
        result = subprocess.run(['docker', 'ps'], capture_output=True, text=True)
        if 'webradio9-mysql' in result.stdout and 'webradio9-rabbitmq' in result.stdout:
            print("✓ Docker containers running")
            checks.append(True)
        else:
            print("✗ Docker containers not running")
            print("  Run: docker ps to check container status")
            checks.append(False)
    except:
        print("✗ Docker not available")
        checks.append(False)
    
    # Check virtual environment
    venv_path = Path(__file__).parent / 'venv'
    if venv_path.exists():
        print("✓ Virtual environment exists")
        checks.append(True)
    else:
        print("✗ Virtual environment not found")
        checks.append(False)
    
    # Check FFmpeg
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=5)
        print("✓ FFmpeg available")
        checks.append(True)
    except:
        print("✗ FFmpeg not available")
        checks.append(False)
    
    return all(checks)

def main():
    """Main test runner"""
    print("🧪 WebRadio9 Comprehensive Test Suite")
    print("=" * 60)
    
    # Check prerequisites
    if not check_prerequisites():
        print("\n❌ Prerequisites not met. Please fix the issues above.")
        return False
    
    # Test suites to run
    test_suites = [
        ("test_system.py", "System Integration Tests"),
        ("test_recording.py", "Recording Functionality Tests"),
        ("test_microservices.py", "Microservices Tests")
    ]
    
    results = []
    
    # Run each test suite
    for test_file, description in test_suites:
        success = run_test_suite(test_file, description)
        results.append((description, success))
        
        if not success:
            print(f"\n⚠️  {description} had failures")
        
        time.sleep(2)  # Brief pause between test suites
    
    # Overall summary
    print(f"\n{'='*60}")
    print("🏁 OVERALL TEST SUMMARY")
    print(f"{'='*60}")
    
    passed_suites = sum(1 for _, success in results if success)
    total_suites = len(results)
    
    for description, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {description}")
    
    print(f"\nTest Suites: {passed_suites}/{total_suites} passed")
    success_rate = (passed_suites / total_suites) * 100
    print(f"Success Rate: {success_rate:.1f}%")
    
    if passed_suites == total_suites:
        print("\n🎉 ALL TESTS PASSED! WebRadio9 is ready for use.")
        return True
    else:
        print(f"\n⚠️  {total_suites - passed_suites} test suite(s) failed. Check logs above.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
