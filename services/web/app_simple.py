from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from shared.config import config
from shared.logging import setup_logger
from shared.models import get_db, Station, Recording, Podcast

app = Flask(__name__)
app.secret_key = 'webradio9-secret-key'
logger = setup_logger('web')

@app.route('/')
def index():
    if 'authenticated' not in session:
        return redirect(url_for('login'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if (username == config.get('auth', 'admin_username') and 
            password == config.get('auth', 'admin_password')):
            session['authenticated'] = True
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error='Invalid credentials')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('authenticated', None)
    return redirect(url_for('login'))

@app.route('/api/timezone')
def api_timezone():
    return jsonify({
        'timezone': config.get('app', 'timezone', 'Europe/Athens')
    })

@app.route('/api/stations')
def api_stations():
    if 'authenticated' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    db = next(get_db())
    stations = db.query(Station).all()
    return jsonify([{
        'id': s.id,
        'name': s.name,
        'stream_url': s.stream_url,
        'is_valid': s.is_valid,
        'format': s.format,
        'bitrate': s.bitrate
    } for s in stations])

@app.route('/api/recordings')
def api_recordings():
    if 'authenticated' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    db = next(get_db())
    recordings = db.query(Recording).order_by(Recording.created_at.desc()).all()
    return jsonify([{
        'id': r.id,
        'name': r.name,
        'status': r.status,
        'start_time': r.start_time.isoformat() if r.start_time else None,
        'duration': r.duration,
        'file_size': r.file_size
    } for r in recordings])

@app.route('/stations')
def stations():
    if 'authenticated' not in session:
        return redirect(url_for('login'))
    return render_template('stations.html')

@app.route('/recordings')
def recordings():
    if 'authenticated' not in session:
        return redirect(url_for('login'))
    return render_template('recordings.html')

@app.route('/recordings/<int:recording_id>/download')
def download_recording(recording_id):
    db = next(get_db())
    recording = db.query(Recording).filter(Recording.id == recording_id).first()
    
    if not recording or not recording.file_path:
        return "Recording not found", 404
    
    file_path = Path(recording.file_path)
    if not file_path.exists():
        return "File not found", 404
    
    return send_file(file_path, as_attachment=True)

if __name__ == '__main__':
    logger.info("Starting simplified web service...")
    app.run(debug=False, host='0.0.0.0', port=5000)
