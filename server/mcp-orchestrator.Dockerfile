FROM node:18-alpine AS builder

WORKDIR /app

# Copy package files
COPY server/mcp-orchestrator/package*.json ./
COPY mcp/ ./mcp/

# Install dependencies
RUN npm ci --only=production

# Production stage
FROM node:18-alpine AS runtime

# Create non-root user
RUN addgroup -g 1001 -S quantum && \
    adduser -S quantum -u 1001

# Install dumb-init for signal handling
RUN apk add --no-cache dumb-init

WORKDIR /app

# Copy built application
COPY --from=builder --chown=quantum:quantum /app .
COPY --chown=quantum:quantum server/mcp-orchestrator/app.js .

# Security hardening
RUN chmod -R 755 /app && \
    chmod 644 /app/package.json /app/app.js

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD node -e "require('http').get('http://localhost:8080/health', (res) => process.exit(res.statusCode === 200 ? 0 : 1)).on('error', () => process.exit(1))"

# Switch to non-root user
USER quantum

# Expose port
EXPOSE 8080

# Environment defaults
ENV NODE_ENV=production
ENV PORT=8080
ENV CORS_ORIGINS=https://qo.deedk822.com

# Start server with dumb-init
ENTRYPOINT ["/usr/bin/dumb-init", "--"]
CMD ["node", "app.js"]