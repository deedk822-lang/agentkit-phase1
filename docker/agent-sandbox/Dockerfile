FROM ubuntu:22.04

# Create non-root user for agent execution
RUN useradd -m -u 1001 -s /bin/bash agentuser

# Install minimal dependencies
RUN apt-get update && apt-get install -y \
    nodejs \
    npm \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create restricted directories
RUN mkdir -p /app/agent /app/logs /app/temp && \
    chown -R agentuser:agentuser /app

# Set resource limits
COPY --chown=agentuser:agentuser limits.conf /etc/security/limits.d/agentuser.conf

# Copy agent code
COPY --chown=agentuser:agentuser src/ /app/agent/
WORKDIR /app/agent

# Install dependencies as root, then switch to agent user
RUN npm install --production
USER agentuser

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:3000/health || exit 1

EXPOSE 3000
CMD ["node", "dist/index.js"]