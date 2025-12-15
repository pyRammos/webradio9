#!/bin/bash
set -e

echo "Deploying WebRadio9..."

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null; then
    echo "docker-compose not found. Please install docker-compose."
    exit 1
fi

# Create production secrets (if they don't exist)
if ! docker secret ls | grep -q mysql_root_password; then
    echo "Creating Docker secrets..."
    echo "Please enter production passwords:"
    
    read -s -p "MySQL root password: " mysql_root_pass
    echo
    read -s -p "MySQL webradio password: " mysql_pass
    echo
    read -s -p "RabbitMQ password: " rabbitmq_pass
    echo
    
    echo "$mysql_root_pass" | docker secret create mysql_root_password -
    echo "$mysql_pass" | docker secret create mysql_password -
    echo "$rabbitmq_pass" | docker secret create rabbitmq_password -
    
    echo "Secrets created successfully!"
fi

# Deploy with production configuration
echo "Starting WebRadio9 services..."
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

echo "WebRadio9 deployed successfully!"
echo "Access the application at: http://localhost:5000"
echo "RabbitMQ Management: http://localhost:15672"
