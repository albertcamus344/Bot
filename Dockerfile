FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
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
RUN useradd -r -u 1000 botuser && \
    chown -R botuser:botuser /app && \
    mkdir -p /tmp/youtube_bot && \
    chown botuser:botuser /tmp/youtube_bot

USER botuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe')" || exit 1

# Run the bot
CMD ["python", "youtube_bot.py"]
