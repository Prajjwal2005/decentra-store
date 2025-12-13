# Dockerfile for DecentraStore
# Multi-purpose image for discovery, backend, and node services

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directories
RUN mkdir -p /app/data /app/node_storage

# Set Python path
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Default port (Railway will override with PORT env var)
ENV PORT=5000

# Use gunicorn with gevent for WebSocket support
# Railway will provide PORT via environment variable
CMD gunicorn --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker --workers 1 --bind 0.0.0.0:$PORT --timeout 120 server:app

# Expose port (Railway ignores this, uses PORT env var)
EXPOSE 5000
