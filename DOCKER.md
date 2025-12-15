# WebRadio9 Docker Deployment

## Quick Start

### Development Deployment
```bash
# Clone the repository
git clone https://github.com/pyRammos/webradio9.git
cd webradio9

# Start all services
docker compose up -d

# Access the application
open http://localhost:5000
```

### Production Deployment
```bash
# Build and push to Docker Hub
./scripts/build-docker.sh

# Deploy with production configuration
./scripts/deploy.sh
```

## Services

- **WebRadio9**: http://localhost:5000 (main application)
- **RabbitMQ Management**: http://localhost:15672 (guest/guest)
- **MySQL**: localhost:3306 (webradio/webradio_pass)

## Docker Images

### Pre-built Image
```bash
docker pull teleram/webradio9:latest
```

### Build Locally
```bash
docker build -t teleram/webradio9:latest .
```

## Configuration

### Custom Configuration
Copy the example config and customize:
```bash
cp config/settings.cfg.example config/settings.cfg
# Edit config/settings.cfg with your settings
```

The `config/` folder is mounted into the container, allowing you to customize:
- Database settings
- Authentication credentials  
- Storage locations
- Timezone settings
- Service ports

### Volumes
- `recordings_data`: Audio recordings storage
- `logs_data`: Application logs
- `static_data`: Static files and uploads
- `config/`: Configuration files (mounted from host)
- `mysql_data`: Database files
- `rabbitmq_data`: Message queue data

## Production Considerations

### Security
- Change default passwords in production
- Use Docker secrets for sensitive data
- Configure firewall rules
- Enable SSL/TLS

### Scaling
- Use external MySQL/RabbitMQ for high availability
- Scale WebRadio9 containers horizontally
- Use load balancer for multiple instances

### Monitoring
- Health checks are built-in
- Monitor container logs: `docker compose logs -f`
- Check service status: `curl http://localhost:5000/api/system/health`

## Troubleshooting

### Common Issues
1. **Port conflicts**: Change ports in docker-compose.yml
2. **Permission errors**: Check volume permissions
3. **Database connection**: Ensure MySQL is healthy before WebRadio9 starts
4. **FFmpeg not found**: Rebuild image if needed

### Logs
```bash
# View all logs
docker compose logs -f

# View specific service logs
docker compose logs -f webradio9
docker compose logs -f mysql
docker compose logs -f rabbitmq
```

### Reset Everything
```bash
# Stop and remove all containers, networks, and volumes
docker compose down -v
docker system prune -f
```

## Development

### Local Development with Docker
```bash
# Start dependencies only
docker compose up -d mysql rabbitmq

# Run WebRadio9 locally
python run_services.py
```

### Building Custom Images
```bash
# Build with custom tag
docker build -t myregistry/webradio9:v1.0 .

# Push to custom registry
docker push myregistry/webradio9:v1.0
```
