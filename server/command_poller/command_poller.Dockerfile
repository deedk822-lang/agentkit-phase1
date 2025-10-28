FROM python:3.9-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY server/command_poller/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY server/command_poller/command_poller.py .

# Create a non-root user
RUN addgroup -S appgroup && adduser -S appuser -G appgroup

# Switch to the non-root user
USER appuser

# Run the application
CMD ["python", "command_poller.py"]
