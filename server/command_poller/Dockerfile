# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the shared requirements file first
COPY ./server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the poller-specific application code from the server directory
COPY ./server/command_poller /app

# Define the command to run the poller script
CMD ["python", "poller.py"]