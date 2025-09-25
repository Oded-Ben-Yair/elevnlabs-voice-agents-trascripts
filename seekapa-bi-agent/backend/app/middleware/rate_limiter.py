"""
Rate Limiting Middleware to prevent DDoS attacks and API abuse
Implements token bucket algorithm with Redis-like in-memory storage
"""
import time
import asyncio
import json
import logging
from typing import Dict, Optional, Tuple
from collections import defaultdict, deque
from datetime import datetime, timedelta
from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from dataclasses import dataclass
from threading import Lock
import hashlib

from app.core.security import audit_logger, SecurityLevel

logger = logging.getLogger(__name__)

@dataclass
class RateLimitConfig:
    """Configuration for rate limiting"""
    requests_per_minute: int
    requests_per_hour: int
    requests_per_day: int
    burst_size: int  # Maximum burst allowed
    block_duration: int  # Seconds to block after limit exceeded

    @classmethod
    def for_role(cls, role: SecurityLevel) -> 'RateLimitConfig':
        """Get rate limit config based on user role"""
        configs = {
            SecurityLevel.PUBLIC: cls(
                requests_per_minute=10,
                requests_per_hour=100,
                requests_per_day=500,
                burst_size=20,
                block_duration=300  # 5 minutes
            ),
            SecurityLevel.READ_ONLY: cls(
                requests_per_minute=30,
                requests_per_hour=500,
                requests_per_day=2000,
                burst_size=50,
                block_duration=180  # 3 minutes
            ),
            SecurityLevel.ANALYST: cls(
                requests_per_minute=60,
                requests_per_hour=1000,
                requests_per_day=5000,
                burst_size=100,
                block_duration=120  # 2 minutes
            ),
            SecurityLevel.ADMIN: cls(
                requests_per_minute=120,
                requests_per_hour=2000,
                requests_per_day=10000,
                burst_size=200,
                block_duration=60  # 1 minute
            ),
            SecurityLevel.SUPER_ADMIN: cls(
                requests_per_minute=500,
                requests_per_hour=10000,
                requests_per_day=50000,
                burst_size=1000,
                block_duration=30  # 30 seconds
            )
        }
        return configs.get(role, configs[SecurityLevel.PUBLIC])

class TokenBucket:
    """Token bucket implementation for rate limiting"""

    def __init__(self, capacity: int, refill_rate: float):
        """
        Initialize token bucket
        capacity: Maximum number of tokens
        refill_rate: Tokens added per second
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity
        self.last_refill = time.time()
        self.lock = Lock()

    def consume(self, tokens: int = 1) -> bool:
        """Attempt to consume tokens from bucket"""
        with self.lock:
            # Refill tokens based on elapsed time
            now = time.time()
            elapsed = now - self.last_refill
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
            self.last_refill = now

            # Try to consume tokens
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

    def get_wait_time(self, tokens: int = 1) -> float:
        """Get time to wait until tokens are available"""
        with self.lock:
            if self.tokens >= tokens:
                return 0
            return (tokens - self.tokens) / self.refill_rate

class SlidingWindowCounter:
    """Sliding window counter for distributed rate limiting"""

    def __init__(self, window_size: int):
        """window_size in seconds"""
        self.window_size = window_size
        self.requests = deque()
        self.lock = Lock()

    def add_request(self) -> None:
        """Add a request timestamp"""
        with self.lock:
            now = time.time()
            # Remove old requests outside the window
            while self.requests and self.requests[0] < now - self.window_size:
                self.requests.popleft()
            self.requests.append(now)

    def get_count(self) -> int:
        """Get current request count in window"""
        with self.lock:
            now = time.time()
            # Clean old requests
            while self.requests and self.requests[0] < now - self.window_size:
                self.requests.popleft()
            return len(self.requests)

class RateLimiter:
    """Main rate limiter implementation"""

    def __init__(self):
        # Store buckets per client
        self.minute_buckets: Dict[str, TokenBucket] = {}
        self.hour_counters: Dict[str, SlidingWindowCounter] = {}
        self.day_counters: Dict[str, SlidingWindowCounter] = {}
        self.blocked_clients: Dict[str, float] = {}  # client_id -> unblock_time
        self.request_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        self.lock = Lock()

    def get_client_id(self, request: Request) -> str:
        """Generate unique client identifier"""
        # Use user ID if authenticated
        if hasattr(request.state, 'user_id') and request.state.user_id:
            return f"user:{request.state.user_id}"

        # Use IP address for anonymous users
        ip = request.client.host
        # Hash IP for privacy
        return f"ip:{hashlib.sha256(ip.encode()).hexdigest()[:16]}"

    def is_blocked(self, client_id: str) -> Tuple[bool, Optional[float]]:
        """Check if client is blocked"""
        with self.lock:
            if client_id in self.blocked_clients:
                unblock_time = self.blocked_clients[client_id]
                if time.time() < unblock_time:
                    return True, unblock_time - time.time()
                else:
                    del self.blocked_clients[client_id]
            return False, None

    def block_client(self, client_id: str, duration: int):
        """Block a client for specified duration"""
        with self.lock:
            self.blocked_clients[client_id] = time.time() + duration
            logger.warning(f"Blocked client {client_id} for {duration} seconds")

    def check_rate_limit(self, client_id: str, config: RateLimitConfig) -> Tuple[bool, Optional[Dict]]:
        """
        Check if request is within rate limits
        Returns: (allowed, rate_limit_info)
        """
        # Check if client is blocked
        is_blocked, wait_time = self.is_blocked(client_id)
        if is_blocked:
            return False, {
                'blocked': True,
                'retry_after': int(wait_time),
                'reason': 'Rate limit exceeded - client temporarily blocked'
            }

        # Get or create token bucket for minute limit
        if client_id not in self.minute_buckets:
            self.minute_buckets[client_id] = TokenBucket(
                capacity=config.burst_size,
                refill_rate=config.requests_per_minute / 60.0
            )

        # Get or create sliding window counters
        if client_id not in self.hour_counters:
            self.hour_counters[client_id] = SlidingWindowCounter(3600)  # 1 hour
        if client_id not in self.day_counters:
            self.day_counters[client_id] = SlidingWindowCounter(86400)  # 24 hours

        # Check minute limit (token bucket)
        if not self.minute_buckets[client_id].consume():
            wait_time = self.minute_buckets[client_id].get_wait_time()
            return False, {
                'blocked': False,
                'retry_after': int(wait_time),
                'reason': 'Minute rate limit exceeded',
                'limit': config.requests_per_minute,
                'window': 'minute'
            }

        # Check hour limit
        self.hour_counters[client_id].add_request()
        hour_count = self.hour_counters[client_id].get_count()
        if hour_count > config.requests_per_hour:
            self.block_client(client_id, config.block_duration)
            return False, {
                'blocked': True,
                'retry_after': config.block_duration,
                'reason': 'Hourly rate limit exceeded',
                'limit': config.requests_per_hour,
                'window': 'hour',
                'count': hour_count
            }

        # Check day limit
        self.day_counters[client_id].add_request()
        day_count = self.day_counters[client_id].get_count()
        if day_count > config.requests_per_day:
            self.block_client(client_id, config.block_duration * 2)  # Longer block for daily limit
            return False, {
                'blocked': True,
                'retry_after': config.block_duration * 2,
                'reason': 'Daily rate limit exceeded',
                'limit': config.requests_per_day,
                'window': 'day',
                'count': day_count
            }

        # Request allowed
        return True, {
            'allowed': True,
            'remaining': {
                'minute': config.requests_per_minute - int(self.minute_buckets[client_id].tokens),
                'hour': config.requests_per_hour - hour_count,
                'day': config.requests_per_day - day_count
            }
        }

    def record_request(self, client_id: str, endpoint: str, status_code: int):
        """Record request for analysis"""
        self.request_history[client_id].append({
            'timestamp': time.time(),
            'endpoint': endpoint,
            'status_code': status_code
        })

    def detect_attack_pattern(self, client_id: str) -> bool:
        """Detect potential DDoS attack patterns"""
        history = list(self.request_history[client_id])
        if len(history) < 10:
            return False

        # Check for rapid repeated requests to same endpoint
        last_10 = history[-10:]
        endpoints = [r['endpoint'] for r in last_10]
        if len(set(endpoints)) == 1:  # All requests to same endpoint
            time_span = last_10[-1]['timestamp'] - last_10[0]['timestamp']
            if time_span < 1:  # 10 requests in 1 second
                return True

        # Check for high error rate (potential scanning)
        errors = sum(1 for r in last_10 if r['status_code'] >= 400)
        if errors > 7:  # More than 70% errors
            return True

        return False

class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for rate limiting"""

    def __init__(self, app):
        super().__init__(app)
        self.rate_limiter = RateLimiter()

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks and docs
        if request.url.path in ["/health", "/docs", "/openapi.json"]:
            return await call_next(request)

        # Get client identifier
        client_id = self.rate_limiter.get_client_id(request)

        # Get user role for rate limit config
        role = getattr(request.state, 'user_role', SecurityLevel.PUBLIC)
        config = RateLimitConfig.for_role(role)

        # Check rate limit
        allowed, info = self.rate_limiter.check_rate_limit(client_id, config)

        if not allowed:
            # Log rate limit violation
            audit_logger.log_security_event(
                event_type="RATE_LIMIT_EXCEEDED",
                severity="HIGH" if info.get('blocked') else "MEDIUM",
                user_id=getattr(request.state, 'user_id', None),
                ip_address=request.client.host,
                details={
                    'client_id': client_id,
                    'endpoint': request.url.path,
                    'rate_limit_info': info
                }
            )

            # Return rate limit error
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "Rate limit exceeded",
                    "message": info['reason'],
                    "retry_after": info['retry_after']
                },
                headers={
                    "Retry-After": str(info['retry_after']),
                    "X-RateLimit-Limit": str(config.requests_per_minute),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time() + info['retry_after']))
                }
            )

        # Process request
        response = await call_next(request)

        # Record request
        self.rate_limiter.record_request(client_id, request.url.path, response.status_code)

        # Check for attack patterns
        if self.rate_limiter.detect_attack_pattern(client_id):
            # Block client for extended period
            self.rate_limiter.block_client(client_id, 3600)  # 1 hour block
            audit_logger.log_security_event(
                event_type="DDOS_PATTERN_DETECTED",
                severity="CRITICAL",
                user_id=getattr(request.state, 'user_id', None),
                ip_address=request.client.host,
                details={
                    'client_id': client_id,
                    'action': 'blocked_for_1_hour'
                }
            )

        # Add rate limit headers to response
        if info and 'remaining' in info:
            response.headers["X-RateLimit-Limit"] = str(config.requests_per_minute)
            response.headers["X-RateLimit-Remaining"] = str(info['remaining']['minute'])
            response.headers["X-RateLimit-Reset"] = str(int(time.time() + 60))

        return response

class DistributedRateLimiter:
    """
    Distributed rate limiter for multi-instance deployments
    Can be extended to use Redis or other distributed cache
    """

    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url
        self.local_limiter = RateLimiter()
        # In production, initialize Redis connection here

    async def check_rate_limit_async(self, client_id: str, config: RateLimitConfig) -> Tuple[bool, Optional[Dict]]:
        """Async version for distributed rate limiting"""
        # For now, use local limiter
        # In production, implement Redis-based checking
        return self.local_limiter.check_rate_limit(client_id, config)

# Export main classes
__all__ = [
    'RateLimitConfig',
    'RateLimiter',
    'RateLimitMiddleware',
    'DistributedRateLimiter'
]