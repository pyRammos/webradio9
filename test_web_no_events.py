from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__)))

from shared.config import config
from shared.logging import setup_logger
from shared.models import get_db, Station, Recording

app = Flask(__name__)
app.secret_key = 'webradio9-secret-key'
logger = setup_logger('test_web_no_events')

# NO EVENT BUS INITIALIZATION

@app.route('/')
def index():
    return "Web service without events"

@app.route('/api/stations')
def api_stations():
    try:
        db = next(get_db())
        stations = db.query(Station).all()
        return jsonify([{
            'id': s.id,
            'name': s.name,
            'stream_url': s.stream_url,
            'is_valid': s.is_valid
        } for s in stations])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    logger.info("Starting web service without events...")
    app.run(debug=False, host='0.0.0.0', port=5003)
