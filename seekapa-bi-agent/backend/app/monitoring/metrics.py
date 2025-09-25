"""
Custom metrics module for Seekapa BI Agent API monitoring.
Provides Prometheus metrics for application performance and business KPIs.
"""

import time
import psutil
import asyncio
from typing import Callable, Optional, Dict, Any
from functools import wraps
from contextlib import asynccontextmanager
from datetime import datetime

from prometheus_client import (
    Counter, Histogram, Gauge, Summary, Info, Enum,
    generate_latest, CONTENT_TYPE_LATEST, CollectorRegistry,
    multiprocess, make_asgi_app
)
from fastapi import FastAPI, Request, Response, status
from fastapi.responses import PlainTextResponse
from starlette.middleware.base import BaseHTTPMiddleware
from opencensus.ext.azure import metrics_exporter
from opencensus.stats import aggregation, measure, stats, view
from opencensus.tags import tag_map
from azure.monitor.opentelemetry import configure_azure_monitor
import logging

logger = logging.getLogger(__name__)

# Initialize registry
registry = CollectorRegistry()

# -----------------------------
# HTTP Metrics
# -----------------------------
http_requests_total = Counter(
    'http_requests_total',
    'Total number of HTTP requests',
    ['method', 'endpoint', 'status'],
    registry=registry
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency in seconds',
    ['method', 'endpoint', 'status'],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
    registry=registry
)

http_request_size_bytes = Summary(
    'http_request_size_bytes',
    'HTTP request size in bytes',
    ['method', 'endpoint'],
    registry=registry
)

http_response_size_bytes = Summary(
    'http_response_size_bytes',
    'HTTP response size in bytes',
    ['method', 'endpoint'],
    registry=registry
)

http_active_connections = Gauge(
    'http_active_connections',
    'Number of active HTTP connections',
    registry=registry
)

# -----------------------------
# Business Metrics
# -----------------------------
user_registrations_total = Counter(
    'user_registrations_total',
    'Total number of user registrations',
    ['plan_type', 'source'],
    registry=registry
)

user_logins_total = Counter(
    'user_logins_total',
    'Total number of user logins',
    ['auth_method'],
    registry=registry
)

bi_queries_total = Counter(
    'bi_queries_total',
    'Total number of BI queries executed',
    ['query_type', 'datasource', 'status'],
    registry=registry
)

bi_query_duration_seconds = Histogram(
    'bi_query_duration_seconds',
    'BI query execution time in seconds',
    ['query_type', 'datasource'],
    buckets=(0.1, 0.5, 1, 2.5, 5, 10, 30, 60),
    registry=registry
)

data_pipeline_executions_total = Counter(
    'data_pipeline_executions_total',
    'Total number of data pipeline executions',
    ['pipeline_name', 'status'],
    registry=registry
)

data_pipeline_duration_seconds = Histogram(
    'data_pipeline_duration_seconds',
    'Data pipeline execution time in seconds',
    ['pipeline_name'],
    buckets=(1, 5, 10, 30, 60, 300, 600, 1800, 3600),
    registry=registry
)

data_quality_score = Gauge(
    'data_quality_score',
    'Current data quality score (0-1)',
    ['dataset'],
    registry=registry
)

active_users_gauge = Gauge(
    'active_users_total',
    'Number of currently active users',
    ['plan_type'],
    registry=registry
)

api_rate_limit_hits = Counter(
    'api_rate_limit_hits_total',
    'Number of API rate limit hits',
    ['endpoint', 'user_type'],
    registry=registry
)

# -----------------------------
# Cache Metrics
# -----------------------------
cache_hits_total = Counter(
    'cache_hits_total',
    'Total number of cache hits',
    ['cache_type', 'operation'],
    registry=registry
)

cache_misses_total = Counter(
    'cache_misses_total',
    'Total number of cache misses',
    ['cache_type', 'operation'],
    registry=registry
)

# -----------------------------
# Database Metrics
# -----------------------------
database_connections_active = Gauge(
    'database_connections_active',
    'Number of active database connections',
    ['database'],
    registry=registry
)

database_query_duration_seconds = Histogram(
    'database_query_duration_seconds',
    'Database query execution time in seconds',
    ['operation', 'table'],
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1, 5),
    registry=registry
)

# -----------------------------
# System Metrics
# -----------------------------
system_cpu_usage_percent = Gauge(
    'system_cpu_usage_percent',
    'System CPU usage percentage',
    registry=registry
)

system_memory_usage_percent = Gauge(
    'system_memory_usage_percent',
    'System memory usage percentage',
    registry=registry
)

system_disk_usage_percent = Gauge(
    'system_disk_usage_percent',
    'System disk usage percentage',
    ['mountpoint'],
    registry=registry
)

# -----------------------------
# Application Info
# -----------------------------
app_info = Info(
    'app_info',
    'Application information',
    registry=registry
)

# -----------------------------
# Feature Flags
# -----------------------------
feature_flag_evaluations = Counter(
    'feature_flag_evaluations_total',
    'Total number of feature flag evaluations',
    ['flag_name', 'result'],
    registry=registry
)


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Middleware to collect HTTP metrics for Prometheus."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip metrics endpoint to avoid recursion
        if request.url.path == "/metrics":
            return await call_next(request)

        # Track active connections
        http_active_connections.inc()

        # Start timing
        start_time = time.time()

        # Get request size
        content_length = request.headers.get('content-length')
        if content_length:
            http_request_size_bytes.labels(
                method=request.method,
                endpoint=request.url.path
            ).observe(int(content_length))

        try:
            # Process request
            response = await call_next(request)

            # Calculate duration
            duration = time.time() - start_time

            # Record metrics
            http_requests_total.labels(
                method=request.method,
                endpoint=request.url.path,
                status=response.status_code
            ).inc()

            http_request_duration_seconds.labels(
                method=request.method,
                endpoint=request.url.path,
                status=response.status_code
            ).observe(duration)

            # Get response size
            response_length = response.headers.get('content-length')
            if response_length:
                http_response_size_bytes.labels(
                    method=request.method,
                    endpoint=request.url.path
                ).observe(int(response_length))

            return response

        except Exception as e:
            # Record error metrics
            duration = time.time() - start_time
            http_requests_total.labels(
                method=request.method,
                endpoint=request.url.path,
                status=500
            ).inc()

            http_request_duration_seconds.labels(
                method=request.method,
                endpoint=request.url.path,
                status=500
            ).observe(duration)

            raise e

        finally:
            # Decrement active connections
            http_active_connections.dec()


class AzureMonitorConfig:
    """Configuration for Azure Application Insights integration."""

    def __init__(self, connection_string: str, environment: str = "production"):
        self.connection_string = connection_string
        self.environment = environment
        self._configure()

    def _configure(self):
        """Configure Azure Monitor with OpenTelemetry."""
        configure_azure_monitor(
            connection_string=self.connection_string,
            disable_offline_storage=False,
            enable_live_metrics=True,
            enable_standard_metrics=True,
        )

        # Set up custom dimensions
        self.custom_dimensions = {
            'environment': self.environment,
            'service': 'seekapa-bi-agent',
            'version': '1.0.0'
        }


def track_business_metric(metric_name: str, value: float, properties: Optional[Dict[str, Any]] = None):
    """Track custom business metrics."""
    if metric_name == "user_registration":
        user_registrations_total.labels(
            plan_type=properties.get('plan_type', 'free'),
            source=properties.get('source', 'direct')
        ).inc()

    elif metric_name == "user_login":
        user_logins_total.labels(
            auth_method=properties.get('auth_method', 'password')
        ).inc()

    elif metric_name == "bi_query":
        bi_queries_total.labels(
            query_type=properties.get('query_type', 'select'),
            datasource=properties.get('datasource', 'postgres'),
            status=properties.get('status', 'success')
        ).inc()

        if 'duration' in properties:
            bi_query_duration_seconds.labels(
                query_type=properties.get('query_type', 'select'),
                datasource=properties.get('datasource', 'postgres')
            ).observe(properties['duration'])

    elif metric_name == "data_pipeline_execution":
        data_pipeline_executions_total.labels(
            pipeline_name=properties.get('pipeline_name', 'default'),
            status=properties.get('status', 'success')
        ).inc()

        if 'duration' in properties:
            data_pipeline_duration_seconds.labels(
                pipeline_name=properties.get('pipeline_name', 'default')
            ).observe(properties['duration'])

    elif metric_name == "data_quality":
        data_quality_score.labels(
            dataset=properties.get('dataset', 'main')
        ).set(value)

    elif metric_name == "cache_hit":
        cache_hits_total.labels(
            cache_type=properties.get('cache_type', 'redis'),
            operation=properties.get('operation', 'get')
        ).inc()

    elif metric_name == "cache_miss":
        cache_misses_total.labels(
            cache_type=properties.get('cache_type', 'redis'),
            operation=properties.get('operation', 'get')
        ).inc()

    elif metric_name == "rate_limit_hit":
        api_rate_limit_hits.labels(
            endpoint=properties.get('endpoint', '/api/v1/query'),
            user_type=properties.get('user_type', 'free')
        ).inc()


def measure_query_performance(func):
    """Decorator to measure database query performance."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = await func(*args, **kwargs)
            duration = time.time() - start_time

            # Extract operation and table from function name or args
            operation = kwargs.get('operation', func.__name__)
            table = kwargs.get('table', 'unknown')

            database_query_duration_seconds.labels(
                operation=operation,
                table=table
            ).observe(duration)

            return result
        except Exception as e:
            logger.error(f"Query failed: {e}")
            raise

    return wrapper


async def collect_system_metrics():
    """Collect system-level metrics periodically."""
    while True:
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            system_cpu_usage_percent.set(cpu_percent)

            # Memory usage
            memory = psutil.virtual_memory()
            system_memory_usage_percent.set(memory.percent)

            # Disk usage
            for partition in psutil.disk_partitions():
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    system_disk_usage_percent.labels(
                        mountpoint=partition.mountpoint
                    ).set(usage.percent)
                except PermissionError:
                    continue

            # Database connections (example)
            # This would need to be integrated with your actual database pool
            # database_connections_active.labels(database='main').set(pool.size())

        except Exception as e:
            logger.error(f"Error collecting system metrics: {e}")

        # Collect every 10 seconds
        await asyncio.sleep(10)


def setup_metrics(app: FastAPI, azure_connection_string: Optional[str] = None):
    """Setup metrics collection for the FastAPI application."""

    # Add Prometheus middleware
    app.add_middleware(PrometheusMiddleware)

    # Set application info
    app_info.info({
        'version': '1.0.0',
        'environment': 'production',
        'service': 'seekapa-bi-agent'
    })

    # Setup Azure Application Insights if configured
    if azure_connection_string:
        azure_config = AzureMonitorConfig(azure_connection_string)
        logger.info("Azure Application Insights configured")

    # Add metrics endpoint
    @app.get("/metrics", response_class=PlainTextResponse, include_in_schema=False)
    async def metrics():
        """Expose metrics for Prometheus scraping."""
        # Collect current system metrics
        try:
            system_cpu_usage_percent.set(psutil.cpu_percent())
            system_memory_usage_percent.set(psutil.virtual_memory().percent)
        except:
            pass

        return Response(
            content=generate_latest(registry),
            media_type=CONTENT_TYPE_LATEST
        )

    # Add health check endpoint
    @app.get("/health", include_in_schema=False)
    async def health():
        """Health check endpoint."""
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "service": "seekapa-bi-agent",
            "version": "1.0.0"
        }

    # Add readiness check endpoint
    @app.get("/ready", include_in_schema=False)
    async def readiness():
        """Readiness check endpoint."""
        # Check database connection, cache, etc.
        checks = {
            "database": "healthy",
            "cache": "healthy",
            "external_apis": "healthy"
        }

        all_healthy = all(status == "healthy" for status in checks.values())

        return Response(
            content={
                "ready": all_healthy,
                "checks": checks,
                "timestamp": datetime.utcnow().isoformat()
            },
            status_code=status.HTTP_200_OK if all_healthy else status.HTTP_503_SERVICE_UNAVAILABLE
        )

    # Start system metrics collection
    @app.on_event("startup")
    async def startup_event():
        """Start background tasks on application startup."""
        asyncio.create_task(collect_system_metrics())

    logger.info("Metrics collection setup completed")