#!/bin/bash
set -e

# Read database credentials from config file
CONFIG_FILE="/app/config/settings.cfg"

if [ -f "$CONFIG_FILE" ]; then
    DB_HOST=$(grep -A 10 '^\[database\]' "$CONFIG_FILE" | grep '^host' | cut -d'=' -f2 | tr -d ' ')
    DB_PORT=$(grep -A 10 '^\[database\]' "$CONFIG_FILE" | grep '^port' | cut -d'=' -f2 | tr -d ' ')
    DB_USER=$(grep -A 10 '^\[database\]' "$CONFIG_FILE" | grep '^username' | cut -d'=' -f2 | tr -d ' ')
    DB_PASS=$(grep -A 10 '^\[database\]' "$CONFIG_FILE" | grep '^password' | cut -d'=' -f2 | tr -d ' ')
    
    RABBITMQ_HOST=$(grep -A 10 '^\[rabbitmq\]' "$CONFIG_FILE" | grep '^host' | cut -d'=' -f2 | tr -d ' ')
    RABBITMQ_PORT=$(grep -A 10 '^\[rabbitmq\]' "$CONFIG_FILE" | grep '^port' | cut -d'=' -f2 | tr -d ' ')
else
    echo "Config file not found at $CONFIG_FILE"
    exit 1
fi

# Wait for database to be ready
echo "Waiting for MySQL to be ready..."
while ! mysqladmin ping -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" -p"$DB_PASS" --ssl-mode=DISABLED --silent; do
    sleep 1
done
echo "MySQL is ready!"

# Wait for RabbitMQ to be ready
echo "Waiting for RabbitMQ to be ready..."
while ! nc -z "$RABBITMQ_HOST" "$RABBITMQ_PORT"; do
    sleep 1
done
echo "RabbitMQ is ready!"

# Initialize database if needed
python init_db.py

# Start the application
exec "$@"
