# WebRadio9

A comprehensive web-based radio recording and podcast management system built with Python microservices architecture.

## Features

### Core Functionality
- **Multi-Station Recording**: Schedule and record from multiple radio stations simultaneously
- **Podcast Management**: Convert recordings to podcast episodes with RSS feeds
- **Web Interface**: Complete web-based management dashboard
- **Microservices Architecture**: Scalable, fault-tolerant service design

### Advanced Features
- **Interrupted Recording Detection**: Automatically detects and resumes interrupted recordings
- **Health Monitoring**: Real-time service health checks and status monitoring
- **Service Management**: Web-based service restart and control
- **Log Viewer**: Real-time log monitoring with auto-refresh
- **Recurring Recordings**: Schedule daily, weekly, or monthly recordings
- **Multiple Storage Backends**: Local filesystem and AWS S3 support

## Architecture

WebRadio9 consists of 7 microservices:

- **Web Service** (Port 5000): Main web interface and API
- **Recording Service** (Port 5001): Handles audio recording with FFmpeg
- **Scheduler Service** (Port 5002): Manages recording schedules and timing
- **Station Service** (Port 5003): Manages radio station configurations
- **Storage Service** (Port 5004): Handles file storage operations
- **Notification Service** (Port 5005): Manages system notifications
- **Podcast Service** (Port 5006): Converts recordings to podcast episodes

## Quick Start

### Docker Deployment (Recommended)

**Prerequisites:**
- Docker and Docker Compose
- Git

**Installation:**
```bash
# Clone the repository
git clone https://github.com/pyRammos/webradio9.git
cd webradio9

# Start all services (MySQL, RabbitMQ, WebRadio9)
docker compose up -d

# Access the application
open http://localhost:5000
```

**Default login:** `admin` / `admin123`

**Services:**
- **WebRadio9**: http://localhost:5000
- **RabbitMQ Management**: http://localhost:15672 (webradio/webradio_pass)

### Manual Installation

**Prerequisites:**
- Python 3.8+
- FFmpeg
- MySQL or SQLite
- RabbitMQ
- Virtual environment support

**Installation:**

1. Clone the repository:
```bash
git clone https://github.com/pyRammos/webradio9.git
cd webradio9
```

2. Create and activate virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate     # Windows
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Initialize database:
```bash
python init_db.py
```

5. Start all services:
```bash
python run_services.py
```

6. Access the web interface at `http://localhost:5000`

Default login: `admin` / `password`

## Docker Deployment

### Using Docker Hub Image
```bash
# Pull and run the latest image
docker pull teleram/webradio9:latest
docker run -p 5000:5000 teleram/webradio9:latest
```

### Full Stack with Docker Compose
```bash
# Clone and deploy complete stack
git clone https://github.com/pyRammos/webradio9.git
cd webradio9
docker compose up -d
```

### Custom Configuration
```bash
# Copy example config and customize
cp config/settings.cfg.example config/settings.cfg
# Edit config/settings.cfg with your settings
docker compose up -d
```

For detailed Docker deployment instructions, see [DOCKER.md](DOCKER.md).

## Configuration

Edit `config/settings.cfg` to customize:
- Database settings
- Storage locations
- Service ports
- Authentication credentials
- Timezone settings

## Usage

### Adding Radio Stations
1. Navigate to **Stations** in the web interface
2. Add station name and stream URL
3. Test the stream connection

### Scheduling Recordings
1. Go to **Recordings**
2. Select station, set time and duration
3. Choose recording format (MP3/AAC)
4. Set recurrence if needed (daily/weekly/monthly)

### Managing Podcasts
1. Visit **Podcasts** section
2. Create podcast feeds from recordings
3. Access public RSS feeds for podcast clients

### System Monitoring
- **Logs**: View real-time system logs
- **Services**: Monitor service health and restart services
- **Dashboard**: Overview of recent recordings and system status

## API Endpoints

### Recordings
- `GET /api/recordings` - List all recordings
- `POST /api/recordings` - Create new recording
- `GET /api/recordings/active` - List active recordings
- `GET /api/recordings/history` - List completed recordings

### System
- `GET /api/system/health` - Service health status
- `POST /api/services/restart` - Restart services
- `GET /api/logs` - System logs

### Podcasts
- `GET /podcasts/{uuid}/rss` - RSS feed for podcast

## Development

### Running Tests
```bash
python -m pytest test_*.py
```

### Service Development
Each service is independently deployable and includes:
- Health check endpoints
- Event bus integration
- Automatic restart capability
- Comprehensive logging

### Adding New Features
1. Follow the microservices pattern
2. Add health checks to new services
3. Integrate with the event bus system
4. Update the web interface as needed

## Deployment

### Production Considerations
- Use proper authentication (change default credentials)
- Configure secure storage locations
- Set up proper logging rotation
- Consider using a process manager (systemd, supervisor)
- Configure firewall rules for service ports

### Docker Support
Docker configuration files are included for containerized deployment.

## Troubleshooting

### Common Issues
- **FFmpeg not found**: Install FFmpeg and ensure it's in PATH
- **Permission errors**: Check file permissions for storage directories
- **Service startup failures**: Check logs and ensure ports are available
- **Recording failures**: Verify stream URLs and network connectivity

### Log Files
- Main log: `logs/webradio9.log`
- Service-specific logs available through the web interface

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

## License

MIT License - see LICENSE file for details

## Support

For issues and feature requests, please use the GitHub issue tracker.
