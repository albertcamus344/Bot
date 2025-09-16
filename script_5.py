# Create systemd service file for Linux deployment
systemd_service = '''[Unit]
Description=YouTube Downloader Telegram Bot
After=network.target

[Service]
Type=simple
User=botuser
WorkingDirectory=/opt/youtube-bot
Environment=PATH=/opt/youtube-bot/youtube_bot_env/bin
ExecStart=/opt/youtube-bot/youtube_bot_env/bin/python /opt/youtube-bot/youtube_bot.py
Restart=always
RestartSec=10

# Security settings
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/opt/youtube-bot
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
'''

with open('youtube-bot.service', 'w') as f:
    f.write(systemd_service)

# Create deployment guide
deployment_guide = '''# Deployment Guide

## 🚀 Production Deployment

### Option 1: Local Development
```bash
# Clone or download the bot files
# Install dependencies
pip install -r requirements.txt

# Configure your bot token
cp .env.example .env
# Edit .env and add your bot token

# Run the bot
python youtube_bot.py
```

### Option 2: Linux Server with systemd

1. **Create bot user:**
```bash
sudo useradd -r -s /bin/false botuser
sudo mkdir -p /opt/youtube-bot
sudo chown botuser:botuser /opt/youtube-bot
```

2. **Install bot files:**
```bash
sudo cp * /opt/youtube-bot/
cd /opt/youtube-bot
sudo -u botuser python3 -m venv youtube_bot_env
sudo -u botuser youtube_bot_env/bin/pip install -r requirements.txt
```

3. **Configure environment:**
```bash
sudo -u botuser cp .env.example .env
sudo -u botuser nano .env  # Add your bot token
```

4. **Install systemd service:**
```bash
sudo cp youtube-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable youtube-bot
sudo systemctl start youtube-bot
```

5. **Check status:**
```bash
sudo systemctl status youtube-bot
sudo journalctl -u youtube-bot -f  # View logs
```

### Option 3: Docker Deployment

1. **Create Dockerfile:**
```dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \\
    ffmpeg \\
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user
RUN useradd -r -u 1000 botuser && chown -R botuser:botuser /app
USER botuser

# Run the bot
CMD ["python", "youtube_bot.py"]
```

2. **Build and run:**
```bash
docker build -t youtube-bot .
docker run -d --name youtube-bot -e TELEGRAM_BOT_TOKEN=your_token youtube-bot
```

### Option 4: Docker Compose
```yaml
version: '3.8'
services:
  youtube-bot:
    build: .
    environment:
      - TELEGRAM_BOT_TOKEN=${BOT_TOKEN}
      - DEBUG_MODE=false
    volumes:
      - ./downloads:/tmp/youtube_bot
    restart: unless-stopped
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

## 🔧 Configuration Options

### Environment Variables
- `TELEGRAM_BOT_TOKEN`: Your bot token (required)
- `MAX_FILE_SIZE_BYTES`: Max file size for direct upload (default: 50MB)
- `TEMP_DIR`: Custom temporary directory
- `DEBUG_MODE`: Enable debug logging (true/false)

### Security Considerations
- Never commit bot tokens to version control
- Use environment variables for sensitive data
- Run bot as non-root user
- Consider rate limiting for public bots
- Monitor disk usage for temporary files

## 📊 Monitoring

### Log Monitoring
```bash
# View live logs
sudo journalctl -u youtube-bot -f

# Check recent errors
sudo journalctl -u youtube-bot --since "1 hour ago" -p err
```

### Resource Monitoring
```bash
# Check disk usage
df -h /tmp

# Monitor memory usage
htop -u botuser
```

## 🔄 Updates

### Manual Update
```bash
sudo systemctl stop youtube-bot
# Update files
sudo -u botuser youtube_bot_env/bin/pip install --upgrade yt-dlp
sudo systemctl start youtube-bot
```

### Automated Updates (cron)
```bash
# Add to crontab for botuser
0 2 * * * /opt/youtube-bot/youtube_bot_env/bin/pip install --upgrade yt-dlp >/dev/null 2>&1
```

## 🐛 Troubleshooting

### Common Issues:

1. **Bot not responding**
   - Check bot token is correct
   - Verify internet connectivity
   - Check bot permissions in Telegram

2. **Downloads failing**
   - Update yt-dlp: `pip install --upgrade yt-dlp`
   - Check YouTube URL is valid
   - Verify ffmpeg is installed

3. **Large file upload issues**
   - Check temporary hosting services are accessible
   - Verify disk space in temp directory
   - Monitor network connectivity

4. **Permission errors**
   - Ensure bot user has write access to temp directory
   - Check systemd service user configuration

### Log Analysis:
```bash
# Check for specific errors
sudo journalctl -u youtube-bot | grep ERROR

# Monitor download attempts
sudo journalctl -u youtube-bot | grep "Downloading"
```

## 📈 Performance Optimization

### For High-Traffic Bots:
1. **Use SSD storage** for temporary files
2. **Increase RAM** for concurrent downloads
3. **Configure nginx** as reverse proxy if using webhooks
4. **Set up monitoring** with Prometheus/Grafana
5. **Use Redis** for session storage in multi-instance setups

### Resource Limits:
```bash
# In systemd service file, add:
[Service]
MemoryLimit=1G
CPUQuota=80%
TasksMax=100
```

## 🌐 Scaling

For multiple server deployment:
1. Use shared storage for temporary files
2. Implement load balancing
3. Use webhook mode instead of polling
4. Consider database for user session management
5. Implement caching for video metadata

---

Happy deploying! 🚀
'''

with open('DEPLOYMENT.md', 'w', encoding='utf-8') as f:
    f.write(deployment_guide)

# Create a Docker file as well
dockerfile_content = '''FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \\
    ffmpeg \\
    curl \\
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY youtube_bot.py .
COPY .env.example .

# Create non-root user
RUN useradd -r -u 1000 botuser && \\
    chown -R botuser:botuser /app && \\
    mkdir -p /tmp/youtube_bot && \\
    chown botuser:botuser /tmp/youtube_bot

USER botuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \\
    CMD python -c "import requests; requests.get('https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe')" || exit 1

# Run the bot
CMD ["python", "youtube_bot.py"]
'''

with open('Dockerfile', 'w') as f:
    f.write(dockerfile_content)

# Create docker-compose file
docker_compose = '''version: '3.8'

services:
  youtube-bot:
    build: .
    environment:
      - TELEGRAM_BOT_TOKEN=${BOT_TOKEN}
      - DEBUG_MODE=false
      - MAX_FILE_SIZE_BYTES=52428800
    volumes:
      - ./downloads:/tmp/youtube_bot
      - ./logs:/app/logs
    restart: unless-stopped
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
    healthcheck:
      test: ["CMD", "python", "-c", "import requests; requests.get('https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
'''

with open('docker-compose.yml', 'w') as f:
    f.write(docker_compose)

print("✅ Created deployment files:")
print("  - youtube-bot.service (systemd service)")
print("  - DEPLOYMENT.md (deployment guide)")  
print("  - Dockerfile")
print("  - docker-compose.yml")