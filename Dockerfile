FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    netcat-openbsd \
    mariadb-client \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p logs recordings static/images/podcasts

# Make entrypoint executable
RUN chmod +x docker-entrypoint.sh

# Create non-root user
RUN useradd -m -u 1000 webradio && chown -R webradio:webradio /app
USER webradio

# Expose ports
EXPOSE 5000 5001 5002 5003 5004 5005 5006

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/api/system/health || exit 1

# Set entrypoint
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["python", "run_services.py"]
