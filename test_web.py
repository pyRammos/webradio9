#!/usr/bin/env python3
"""
Minimal web service test to identify crash cause
"""
import sys
import os
sys.path.append(os.path.dirname(__file__))

from flask import Flask
from shared.logging import setup_logger

app = Flask(__name__)
logger = setup_logger('test_web')

@app.route('/')
def index():
    return "Test Web Service Running"

@app.route('/health')
def health():
    return {"status": "ok"}

if __name__ == '__main__':
    logger.info("Starting minimal test web service...")
    try:
        app.run(debug=False, host='0.0.0.0', port=5001)  # Use different port
    except Exception as e:
        logger.error(f"Web service failed: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
