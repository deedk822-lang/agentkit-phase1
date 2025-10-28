FROM python:3.11-slim

# Create non-root user
RUN groupadd -r quantum && useradd -r -g quantum quantum

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    cron \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first for better caching
COPY agents/command-poller/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY --chown=quantum:quantum agents/command-poller/ ./

# Create directories for logs and config
RUN mkdir -p /app/logs /app/config && \
    chown -R quantum:quantum /app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8080/health', timeout=5)" || exit 1

# Switch to non-root user
USER quantum

# Environment defaults
ENV PYTHONPATH=/app
ENV POLL_INTERVAL=5
ENV RUN_ONCE=false

# Start command poller
CMD ["python", "poller.py"]