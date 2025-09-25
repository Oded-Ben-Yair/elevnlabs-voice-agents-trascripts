"""
Circuit Breaker Pattern Implementation for Seekapa BI Agent.
Provides resilience and fault tolerance for external service calls
and critical system operations.
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Callable, List, Union
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import statistics
from collections import deque
import threading

try:
    import pybreaker
    PYBREAKER_AVAILABLE = True
except ImportError:
    PYBREAKER_AVAILABLE = False

logger = logging.getLogger(__name__)

class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Circuit is open, failing fast
    HALF_OPEN = "half_open"  # Testing if service is back

@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""
    name: str
    failure_threshold: int = 5  # Number of failures before opening
    recovery_timeout: float = 60.0  # Seconds to wait before trying again
    expected_exception: tuple = (Exception,)  # Exceptions to count as failures
    timeout: Optional[float] = None  # Optional timeout for operations

    # Advanced settings
    success_threshold: int = 3  # Successful calls needed to close from half-open
    monitor_window_size: int = 100  # Size of the monitoring window
    min_calls_to_trip: int = 10  # Minimum calls before considering trip

    # Listener settings
    enable_notifications: bool = True
    alert_on_state_change: bool = True

@dataclass
class CallResult:
    """Result of a circuit breaker protected call."""
    success: bool
    duration: float
    timestamp: float
    exception: Optional[Exception] = None
    result: Any = None

class CircuitBreakerMetrics:
    """Metrics collector for circuit breaker."""

    def __init__(self, window_size: int = 100):
        self.window_size = window_size
        self.call_history: deque = deque(maxlen=window_size)
        self.state_changes: List[Dict[str, Any]] = []
        self.lock = threading.RLock()

        # Current metrics
        self.total_calls = 0
        self.successful_calls = 0
        self.failed_calls = 0
        self.total_duration = 0.0

    def record_call(self, result: CallResult):
        """Record a call result."""
        with self.lock:
            self.call_history.append(result)
            self.total_calls += 1

            if result.success:
                self.successful_calls += 1
            else:
                self.failed_calls += 1

            self.total_duration += result.duration

    def record_state_change(self, old_state: CircuitState, new_state: CircuitState, reason: str = ""):
        """Record a state change."""
        with self.lock:
            self.state_changes.append({
                "timestamp": time.time(),
                "from_state": old_state.value,
                "to_state": new_state.value,
                "reason": reason
            })

    def get_failure_rate(self) -> float:
        """Get current failure rate."""
        with self.lock:
            if not self.call_history:
                return 0.0

            failed_count = sum(1 for call in self.call_history if not call.success)
            return failed_count / len(self.call_history)

    def get_average_response_time(self) -> float:
        """Get average response time."""
        with self.lock:
            if not self.call_history:
                return 0.0

            return statistics.mean(call.duration for call in self.call_history)

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics."""
        with self.lock:
            recent_calls = len(self.call_history)
            recent_failures = sum(1 for call in self.call_history if not call.success)

            return {
                "total_calls": self.total_calls,
                "successful_calls": self.successful_calls,
                "failed_calls": self.failed_calls,
                "recent_calls": recent_calls,
                "recent_failures": recent_failures,
                "failure_rate": self.get_failure_rate(),
                "average_response_time": self.get_average_response_time(),
                "state_changes": len(self.state_changes),
                "last_state_changes": self.state_changes[-5:] if self.state_changes else []
            }

class CircuitBreakerListener(ABC):
    """Abstract base class for circuit breaker event listeners."""

    @abstractmethod
    async def on_state_change(self, breaker_name: str, old_state: CircuitState,
                             new_state: CircuitState, reason: str = ""):
        """Called when circuit breaker state changes."""
        pass

    @abstractmethod
    async def on_call_success(self, breaker_name: str, duration: float):
        """Called on successful call."""
        pass

    @abstractmethod
    async def on_call_failure(self, breaker_name: str, exception: Exception, duration: float):
        """Called on failed call."""
        pass

class LoggingCircuitBreakerListener(CircuitBreakerListener):
    """Logging-based circuit breaker listener."""

    async def on_state_change(self, breaker_name: str, old_state: CircuitState,
                             new_state: CircuitState, reason: str = ""):
        logger.info(f"Circuit breaker '{breaker_name}' state changed from {old_state.value} to {new_state.value}. Reason: {reason}")

    async def on_call_success(self, breaker_name: str, duration: float):
        logger.debug(f"Circuit breaker '{breaker_name}' call succeeded in {duration:.3f}s")

    async def on_call_failure(self, breaker_name: str, exception: Exception, duration: float):
        logger.warning(f"Circuit breaker '{breaker_name}' call failed after {duration:.3f}s: {exception}")

class CircuitBreaker:
    """Custom circuit breaker implementation with advanced features."""

    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self.last_attempt_time: Optional[float] = None
        self.metrics = CircuitBreakerMetrics(config.monitor_window_size)
        self.listeners: List[CircuitBreakerListener] = []
        self.lock = threading.RLock()

        # Add default logging listener
        self.add_listener(LoggingCircuitBreakerListener())

    def add_listener(self, listener: CircuitBreakerListener):
        """Add event listener."""
        self.listeners.append(listener)

    async def _notify_listeners(self, event_type: str, **kwargs):
        """Notify all listeners of an event."""
        if not self.config.enable_notifications:
            return

        for listener in self.listeners:
            try:
                if event_type == "state_change":
                    await listener.on_state_change(
                        self.config.name, kwargs["old_state"],
                        kwargs["new_state"], kwargs.get("reason", "")
                    )
                elif event_type == "call_success":
                    await listener.on_call_success(self.config.name, kwargs["duration"])
                elif event_type == "call_failure":
                    await listener.on_call_failure(
                        self.config.name, kwargs["exception"], kwargs["duration"]
                    )
            except Exception as e:
                logger.error(f"Error notifying listener: {e}")

    async def _change_state(self, new_state: CircuitState, reason: str = ""):
        """Change circuit breaker state."""
        with self.lock:
            old_state = self.state
            if old_state == new_state:
                return

            self.state = new_state
            self.metrics.record_state_change(old_state, new_state, reason)

            # Reset counters on state change
            if new_state == CircuitState.CLOSED:
                self.failure_count = 0
                self.success_count = 0
            elif new_state == CircuitState.HALF_OPEN:
                self.success_count = 0

        if self.config.alert_on_state_change:
            await self._notify_listeners("state_change",
                                        old_state=old_state,
                                        new_state=new_state,
                                        reason=reason)

    def _should_allow_request(self) -> bool:
        """Check if request should be allowed based on current state."""
        with self.lock:
            if self.state == CircuitState.CLOSED:
                return True
            elif self.state == CircuitState.OPEN:
                # Check if recovery timeout has passed
                if (self.last_failure_time and
                    time.time() - self.last_failure_time >= self.config.recovery_timeout):
                    return True
                return False
            elif self.state == CircuitState.HALF_OPEN:
                return True

        return False

    async def _handle_success(self, duration: float):
        """Handle successful call."""
        with self.lock:
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.config.success_threshold:
                    await self._change_state(CircuitState.CLOSED, "Sufficient successful calls")
            elif self.state == CircuitState.OPEN:
                await self._change_state(CircuitState.HALF_OPEN, "First successful call after timeout")
                self.success_count = 1

        await self._notify_listeners("call_success", duration=duration)

    async def _handle_failure(self, exception: Exception, duration: float):
        """Handle failed call."""
        with self.lock:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                await self._change_state(CircuitState.OPEN, "Failure in half-open state")
            elif (self.state == CircuitState.CLOSED and
                  self.failure_count >= self.config.failure_threshold and
                  self.metrics.total_calls >= self.config.min_calls_to_trip):
                await self._change_state(CircuitState.OPEN, f"Failure threshold exceeded ({self.failure_count} failures)")

        await self._notify_listeners("call_failure", exception=exception, duration=duration)

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection."""
        # Check if request should be allowed
        if not self._should_allow_request():
            raise CircuitBreakerOpenException(f"Circuit breaker '{self.config.name}' is open")

        # If in OPEN state but recovery timeout passed, transition to HALF_OPEN
        if self.state == CircuitState.OPEN:
            await self._change_state(CircuitState.HALF_OPEN, "Recovery timeout reached")

        start_time = time.time()
        self.last_attempt_time = start_time

        try:
            # Apply timeout if configured
            if self.config.timeout:
                if asyncio.iscoroutinefunction(func):
                    result = await asyncio.wait_for(func(*args, **kwargs), timeout=self.config.timeout)
                else:
                    # For sync functions, we can't apply async timeout
                    result = func(*args, **kwargs)
            else:
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)

            duration = time.time() - start_time

            # Record successful call
            call_result = CallResult(success=True, duration=duration, timestamp=start_time, result=result)
            self.metrics.record_call(call_result)

            await self._handle_success(duration)

            return result

        except self.config.expected_exception as e:
            duration = time.time() - start_time

            # Record failed call
            call_result = CallResult(success=False, duration=duration, timestamp=start_time, exception=e)
            self.metrics.record_call(call_result)

            await self._handle_failure(e, duration)

            raise
        except Exception as e:
            # Unexpected exceptions are not counted as failures unless explicitly configured
            duration = time.time() - start_time
            call_result = CallResult(success=True, duration=duration, timestamp=start_time, result=None)
            self.metrics.record_call(call_result)

            raise

    def get_state(self) -> CircuitState:
        """Get current circuit breaker state."""
        return self.state

    def get_metrics(self) -> Dict[str, Any]:
        """Get circuit breaker metrics."""
        with self.lock:
            base_metrics = self.metrics.get_stats()
            base_metrics.update({
                "name": self.config.name,
                "state": self.state.value,
                "failure_count": self.failure_count,
                "success_count": self.success_count,
                "last_failure_time": self.last_failure_time,
                "last_attempt_time": self.last_attempt_time
            })
            return base_metrics

    async def reset(self):
        """Reset circuit breaker to closed state."""
        await self._change_state(CircuitState.CLOSED, "Manual reset")
        with self.lock:
            self.failure_count = 0
            self.success_count = 0
            self.last_failure_time = None

class CircuitBreakerOpenException(Exception):
    """Exception raised when circuit breaker is open."""
    pass

class CircuitBreakerManager:
    """Manager for multiple circuit breakers."""

    def __init__(self):
        self.breakers: Dict[str, CircuitBreaker] = {}
        self.lock = threading.RLock()

    def create_breaker(self, config: CircuitBreakerConfig) -> CircuitBreaker:
        """Create or get circuit breaker."""
        with self.lock:
            if config.name not in self.breakers:
                self.breakers[config.name] = CircuitBreaker(config)
            return self.breakers[config.name]

    def get_breaker(self, name: str) -> Optional[CircuitBreaker]:
        """Get circuit breaker by name."""
        with self.lock:
            return self.breakers.get(name)

    def remove_breaker(self, name: str) -> bool:
        """Remove circuit breaker."""
        with self.lock:
            if name in self.breakers:
                del self.breakers[name]
                return True
            return False

    def get_all_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Get metrics for all circuit breakers."""
        with self.lock:
            return {name: breaker.get_metrics() for name, breaker in self.breakers.items()}

    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on all circuit breakers."""
        with self.lock:
            total_breakers = len(self.breakers)
            open_breakers = sum(1 for breaker in self.breakers.values() if breaker.get_state() == CircuitState.OPEN)
            half_open_breakers = sum(1 for breaker in self.breakers.values() if breaker.get_state() == CircuitState.HALF_OPEN)

            status = "healthy"
            if open_breakers > 0:
                status = "degraded" if open_breakers < total_breakers else "unhealthy"

            return {
                "status": status,
                "total_breakers": total_breakers,
                "open_breakers": open_breakers,
                "half_open_breakers": half_open_breakers,
                "closed_breakers": total_breakers - open_breakers - half_open_breakers
            }

# Global circuit breaker manager
circuit_breaker_manager = CircuitBreakerManager()

# Decorator for easy circuit breaker usage
def circuit_breaker(name: str, **config_kwargs):
    """Decorator to add circuit breaker protection to functions."""
    def decorator(func):
        config = CircuitBreakerConfig(name=name, **config_kwargs)
        breaker = circuit_breaker_manager.create_breaker(config)

        if asyncio.iscoroutinefunction(func):
            async def async_wrapper(*args, **kwargs):
                return await breaker.call(func, *args, **kwargs)
            return async_wrapper
        else:
            def sync_wrapper(*args, **kwargs):
                # For sync functions, we need to handle the async call differently
                loop = None
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    pass

                if loop:
                    # We're in an async context, but calling a sync function
                    return asyncio.run_coroutine_threadsafe(
                        breaker.call(func, *args, **kwargs), loop
                    ).result()
                else:
                    # We're in a sync context
                    return asyncio.run(breaker.call(func, *args, **kwargs))

            return sync_wrapper

    return decorator

# Example usage and helper functions

@circuit_breaker("database", failure_threshold=3, recovery_timeout=30.0, timeout=5.0)
async def database_operation():
    """Example database operation with circuit breaker protection."""
    # Simulate database call
    await asyncio.sleep(0.1)
    # Simulate occasional failures
    import random
    if random.random() < 0.1:  # 10% failure rate
        raise Exception("Database connection failed")
    return {"status": "success", "data": "mock_data"}

@circuit_breaker("external_api", failure_threshold=5, recovery_timeout=60.0, timeout=10.0)
async def external_api_call(endpoint: str, data: Dict[str, Any]):
    """Example external API call with circuit breaker protection."""
    # Simulate API call
    await asyncio.sleep(0.2)
    # Simulate occasional failures
    import random
    if random.random() < 0.05:  # 5% failure rate
        raise Exception("External API timeout")
    return {"status": "success", "endpoint": endpoint, "response": data}

# Utility functions

def get_circuit_breaker(name: str) -> Optional[CircuitBreaker]:
    """Get circuit breaker by name."""
    return circuit_breaker_manager.get_breaker(name)

def create_circuit_breaker(name: str, **config_kwargs) -> CircuitBreaker:
    """Create a new circuit breaker."""
    config = CircuitBreakerConfig(name=name, **config_kwargs)
    return circuit_breaker_manager.create_breaker(config)

async def reset_circuit_breaker(name: str) -> bool:
    """Reset circuit breaker to closed state."""
    breaker = circuit_breaker_manager.get_breaker(name)
    if breaker:
        await breaker.reset()
        return True
    return False

def get_all_circuit_breaker_metrics() -> Dict[str, Dict[str, Any]]:
    """Get metrics for all circuit breakers."""
    return circuit_breaker_manager.get_all_metrics()

async def circuit_breaker_health_check() -> Dict[str, Any]:
    """Get health status of all circuit breakers."""
    return await circuit_breaker_manager.health_check()