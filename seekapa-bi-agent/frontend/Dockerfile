# Multi-stage build for React frontend
FROM node:18-alpine as builder

# Install dependencies for node-gyp
RUN apk add --no-cache python3 make g++

# Set working directory
WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci --only=production

# Copy application code
COPY . .

# Build arguments for environment variables
ARG REACT_APP_API_URL
ARG REACT_APP_VERSION
ARG REACT_APP_ENVIRONMENT=production

# Set environment variables for build
ENV REACT_APP_API_URL=$REACT_APP_API_URL \
    REACT_APP_VERSION=$REACT_APP_VERSION \
    REACT_APP_ENVIRONMENT=$REACT_APP_ENVIRONMENT \
    NODE_ENV=production

# Build the application
RUN npm run build

# Production stage with nginx
FROM nginx:alpine

# Install curl for health checks
RUN apk add --no-cache curl

# Remove default nginx config
RUN rm -rf /etc/nginx/conf.d/*

# Copy custom nginx config
COPY nginx.conf /etc/nginx/nginx.conf
COPY default.conf /etc/nginx/conf.d/default.conf

# Copy built application from builder
COPY --from=builder /app/build /usr/share/nginx/html

# Create non-root user
RUN addgroup -g 1001 -S nginx-user && \
    adduser -S -u 1001 -G nginx-user nginx-user && \
    chown -R nginx-user:nginx-user /usr/share/nginx/html && \
    chown -R nginx-user:nginx-user /var/cache/nginx && \
    chown -R nginx-user:nginx-user /var/log/nginx && \
    chown -R nginx-user:nginx-user /etc/nginx/conf.d && \
    touch /var/run/nginx.pid && \
    chown -R nginx-user:nginx-user /var/run/nginx.pid

# Add security headers script
COPY security-headers.sh /docker-entrypoint.d/40-security-headers.sh
RUN chmod +x /docker-entrypoint.d/40-security-headers.sh

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost/ || exit 1

# Switch to non-root user
USER nginx-user

# Expose port
EXPOSE 80

# Start nginx
CMD ["nginx", "-g", "daemon off;"]