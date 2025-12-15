#!/bin/bash
set -e

# Wait for database to be ready
echo "Waiting for MySQL to be ready..."
while ! mysqladmin ping -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" -p"$DB_PASSWORD" --silent; do
    sleep 1
done
echo "MySQL is ready!"

# Wait for RabbitMQ to be ready
echo "Waiting for RabbitMQ to be ready..."
while ! nc -z "$RABBITMQ_HOST" "$RABBITMQ_PORT"; do
    sleep 1
done
echo "RabbitMQ is ready!"

# Use Docker configuration
export CONFIG_FILE="/app/config/docker.cfg"

# Initialize database if needed
python init_db.py

# Start the application
exec "$@"
