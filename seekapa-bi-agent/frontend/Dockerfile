# Multi-stage Dockerfile for React Frontend
# Stage 1: Base Node environment
FROM node:18-alpine as base

# Set environment variables
ENV NODE_ENV=production \
    NPM_CONFIG_CACHE=/tmp/.npm

# Install system dependencies
RUN apk add --no-cache \
    curl \
    git \
    python3 \
    make \
    g++

# Create non-root user
RUN addgroup -g 1001 -S nodejs && \
    adduser -S nextjs -u 1001

# Stage 2: Development environment
FROM base as development

# Set development environment
ENV NODE_ENV=development

# Set work directory
WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies (including dev dependencies)
RUN npm ci --include=dev

# Copy source code
COPY . .

# Change ownership to non-root user
RUN chown -R nextjs:nodejs /app

USER nextjs

# Expose port
EXPOSE 3000

# Health check for development
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:3000 || exit 1

# Development command with hot reload
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# Stage 3: Dependencies installation
FROM base as deps

# Set work directory
WORKDIR /app

# Copy package files
COPY package*.json ./

# Install production dependencies only
RUN npm ci --only=production && npm cache clean --force

# Stage 4: Build application
FROM base as builder

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install all dependencies (including dev dependencies for build)
RUN npm ci --include=dev

# Copy source code
COPY . .

# Set build-time environment variables
ARG VITE_API_URL=http://localhost:8000
ARG VITE_APP_NAME="Seekapa BI Agent"
ARG VITE_APP_VERSION="2.0.0"
ARG REACT_APP_API_URL=http://localhost:8000
ARG REACT_APP_VERSION="2.0.0"
ARG REACT_APP_ENVIRONMENT=production

ENV VITE_API_URL=$VITE_API_URL \
    VITE_APP_NAME=$VITE_APP_NAME \
    VITE_APP_VERSION=$VITE_APP_VERSION \
    REACT_APP_API_URL=$REACT_APP_API_URL \
    REACT_APP_VERSION=$REACT_APP_VERSION \
    REACT_APP_ENVIRONMENT=$REACT_APP_ENVIRONMENT

# Build the application
RUN npm run build

# Remove source code after build
RUN rm -rf src/ public/ *.config.* *.json

# Stage 5: Nginx runtime for production
FROM nginx:alpine as production

# Install curl for health checks
RUN apk add --no-cache curl

# Remove default nginx configuration
RUN rm /etc/nginx/conf.d/default.conf

# Copy custom nginx configuration
COPY nginx.conf /etc/nginx/nginx.conf
COPY nginx/conf.d/ /etc/nginx/conf.d/

# Copy built application from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html
COPY --from=builder /app/build /usr/share/nginx/html

# Create nginx user and set permissions
RUN addgroup -g 101 -S nginx || true
RUN adduser -S -D -H -u 101 -h /var/cache/nginx -s /sbin/nologin -G nginx -g nginx nginx || true

# Set proper permissions
RUN chown -R nginx:nginx /usr/share/nginx/html && \
    chown -R nginx:nginx /var/cache/nginx && \
    chown -R nginx:nginx /etc/nginx && \
    mkdir -p /var/log/nginx && \
    chown -R nginx:nginx /var/log/nginx

# Create health check endpoint
RUN echo '<!DOCTYPE html><html><body><h1>OK</h1></body></html>' > /usr/share/nginx/html/health

# Expose ports
EXPOSE 80 443

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:80/health || exit 1

# Switch to non-root user
USER nginx

# Start nginx
CMD ["nginx", "-g", "daemon off;"]

# Stage 6: Production with SSL support
FROM production as production-ssl

USER root

# Install certbot for SSL certificates
RUN apk add --no-cache certbot certbot-nginx

# Copy SSL configuration
COPY nginx/ssl/ /etc/nginx/ssl/

# Copy SSL nginx configuration
COPY nginx/ssl-conf.d/ /etc/nginx/conf.d/

# Create SSL certificate directory
RUN mkdir -p /etc/letsencrypt/live && \
    chown -R nginx:nginx /etc/letsencrypt

# Switch back to nginx user
USER nginx

# Enhanced health check with SSL
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:80/health && (curl -f -k https://localhost:443/health || true) || exit 1

# Start nginx with SSL support
CMD ["nginx", "-g", "daemon off;"]

# Stage 7: Testing environment
FROM builder as testing

# Install additional testing dependencies
RUN npm install --save-dev \
    @testing-library/react \
    @testing-library/jest-dom \
    @testing-library/user-event \
    @vitest/ui \
    jsdom

# Copy test files
COPY tests/ tests/

# Run tests by default
CMD ["npm", "run", "test"]

# Stage 8: Production with monitoring
FROM production as production-monitoring

USER root

# Install monitoring tools
RUN apk add --no-cache \
    curl \
    jq \
    htop \
    prometheus-node-exporter

# Copy monitoring configuration
COPY monitoring/ /etc/monitoring/

# Create monitoring script
RUN echo '#!/bin/sh\n\
while true; do\n\
    curl -s http://localhost:80/health > /dev/null || echo "Health check failed at $(date)"\n\
    sleep 30\n\
done' > /usr/local/bin/monitor.sh && \
    chmod +x /usr/local/bin/monitor.sh

# Switch back to nginx user
USER nginx

# Enhanced health check with monitoring
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:80/health || exit 1

# Start nginx with background monitoring
CMD sh -c '/usr/local/bin/monitor.sh &' && nginx -g 'daemon off;'