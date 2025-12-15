#!/bin/bash
set -e

# Initialize database if needed
python init_db.py

# Start the application
exec "$@"
