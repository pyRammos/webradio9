import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from .config import config

def setup_logger(service_name):
    logger = logging.getLogger(service_name)
    logger.setLevel(getattr(logging, config.get('app', 'log_level', 'INFO')))
    
    # Create logs directory if it doesn't exist
    logs_dir = Path(__file__).parent.parent / 'logs'
    logs_dir.mkdir(exist_ok=True)
    
    # Single log file for all services
    log_file = logs_dir / 'webradio9.log'
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # Formatter includes service name
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

def cleanup_old_logs():
    """Remove log entries older than 30 days from webradio9.log"""
    logs_dir = Path(__file__).parent.parent / 'logs'
    log_file = logs_dir / 'webradio9.log'
    
    if not log_file.exists():
        return
    
    cutoff_date = datetime.now() - timedelta(days=30)
    temp_file = logs_dir / 'webradio9.log.tmp'
    
    with open(log_file, 'r') as infile, open(temp_file, 'w') as outfile:
        for line in infile:
            try:
                # Extract timestamp from log line
                timestamp_str = line.split(' - ')[0]
                log_date = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f')
                if log_date >= cutoff_date:
                    outfile.write(line)
            except (ValueError, IndexError):
                # Keep lines that don't match expected format
                outfile.write(line)
    
    # Replace original file with cleaned version
    temp_file.replace(log_file)
