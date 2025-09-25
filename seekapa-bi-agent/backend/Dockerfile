# Multi-stage Dockerfile for FastAPI Backend
# Stage 1: Base Python environment
FROM python:3.11-slim as base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    libpq-dev \
    gcc \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r seekapa && useradd -r -g seekapa seekapa

# Set work directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Stage 2: Development environment
FROM base as development

# Install development dependencies
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir \
    watchdog \
    pytest \
    pytest-asyncio \
    black \
    flake8 \
    mypy \
    ipython

# Copy source code
COPY . .

# Change ownership to non-root user
RUN chown -R seekapa:seekapa /app

USER seekapa

# Create logs directory
RUN mkdir -p /app/logs

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Development command with hot reload
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# Stage 3: Production build
FROM base as builder

# Install production dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Remove development files and cache
RUN find . -type f -name "*.pyc" -delete \
    && find . -type d -name "__pycache__" -delete \
    && find . -type f -name "*.pyo" -delete \
    && find . -type d -name "*.egg-info" -exec rm -rf {} + \
    && find . -type d -name ".pytest_cache" -exec rm -rf {} + \
    && find . -type f -name ".coverage" -delete

# Stage 4: Production runtime
FROM python:3.11-slim as production

# Set environment variables for production
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

# Install only runtime dependencies
RUN apt-get update && apt-get install -y \
    libpq5 \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r seekapa && useradd -r -g seekapa seekapa

# Set work directory
WORKDIR /app

# Copy Python dependencies from builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code from builder stage
COPY --from=builder --chown=seekapa:seekapa /app .

# Create necessary directories
RUN mkdir -p /app/logs && chown -R seekapa:seekapa /app/logs

# Switch to non-root user
USER seekapa

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Production command with Gunicorn
CMD ["gunicorn", "app.main:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--access-logfile", "-", "--error-logfile", "-", "--log-level", "info"]

# Stage 5: Testing environment
FROM development as testing

# Install additional testing dependencies
RUN pip install --no-cache-dir \
    pytest-cov \
    pytest-xdist \
    pytest-benchmark \
    factory-boy \
    faker

# Copy test files
COPY tests/ tests/

# Run tests by default
CMD ["pytest", "tests/", "-v", "--cov=app", "--cov-report=html", "--cov-report=term"]

# Stage 6: Production with monitoring
FROM production as production-monitoring

# Install monitoring dependencies
USER root
RUN pip install --no-cache-dir \
    prometheus-client \
    structlog \
    elastic-apm

# Copy monitoring configuration
COPY monitoring/ monitoring/

# Switch back to non-root user
USER seekapa

# Enhanced health check with metrics
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health && curl -f http://localhost:8000/metrics || exit 1

# Production command with monitoring
CMD ["gunicorn", "app.main:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--access-logfile", "/app/logs/access.log", "--error-logfile", "/app/logs/error.log", "--log-level", "info", "--preload"]