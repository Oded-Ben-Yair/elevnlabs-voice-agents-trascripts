"""
Server-Sent Events (SSE) Service for one-way real-time data streaming.
Implements robust SSE with connection management, automatic reconnection,
and data buffering for the Seekapa BI Agent.
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Dict, List, Optional, Any, AsyncGenerator, Callable, Set
from datetime import datetime, timedelta
from collections import deque
from dataclasses import dataclass, asdict
from enum import Enum
import weakref
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

class SSEEventType(Enum):
    DATA = "data"
    HEARTBEAT = "heartbeat"
    ERROR = "error"
    RECONNECT = "reconnect"
    CLOSE = "close"

@dataclass
class SSEEvent:
    """Server-Sent Event data structure."""
    id: str
    event: str
    data: Any
    retry: Optional[int] = None
    timestamp: float = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()

    def format_sse(self) -> str:
        """Format event as SSE message."""
        lines = []

        if self.id:
            lines.append(f"id: {self.id}")

        if self.event:
            lines.append(f"event: {self.event}")

        if self.retry is not None:
            lines.append(f"retry: {self.retry}")

        # Handle multi-line data
        if isinstance(self.data, (dict, list)):
            data_str = json.dumps(self.data)
        else:
            data_str = str(self.data)

        for line in data_str.split('\n'):
            lines.append(f"data: {line}")

        # Add empty line to mark end of event
        lines.append("")

        return '\n'.join(lines)

@dataclass
class SSEClientConfig:
    """Configuration for SSE client connection."""
    buffer_size: int = 1000
    heartbeat_interval: float = 30.0
    retry_timeout: int = 3000  # milliseconds
    max_reconnect_attempts: int = 10
    compression_enabled: bool = True
    cors_origins: List[str] = None

    def __post_init__(self):
        if self.cors_origins is None:
            self.cors_origins = ["*"]

class SSEConnection:
    """Individual SSE connection handler with buffering and reconnection support."""

    def __init__(self, client_id: str, config: SSEClientConfig = None):
        self.client_id = client_id
        self.config = config or SSEClientConfig()
        self.event_buffer: deque = deque(maxlen=self.config.buffer_size)
        self.subscriptions: Set[str] = set()
        self.last_event_id: Optional[str] = None
        self.connected = False
        self.created_at = datetime.utcnow()
        self.last_activity = time.time()
        self.heartbeat_task: Optional[asyncio.Task] = None
        self.statistics = {
            "events_sent": 0,
            "events_buffered": 0,
            "reconnect_count": 0,
            "last_reconnect": None
        }

    async def send_event(self, event: SSEEvent) -> bool:
        """Send event to client or buffer if disconnected."""
        try:
            self.event_buffer.append(event)
            self.last_event_id = event.id
            self.statistics["events_buffered"] += 1
            self.last_activity = time.time()

            logger.debug(f"Event {event.id} buffered for client {self.client_id}")
            return True

        except Exception as e:
            logger.error(f"Error buffering event for client {self.client_id}: {e}")
            return False

    async def get_events_since(self, last_event_id: Optional[str]) -> List[SSEEvent]:
        """Get events since last_event_id for reconnection."""
        if not last_event_id:
            return list(self.event_buffer)

        events = []
        found_start = False

        for event in self.event_buffer:
            if found_start:
                events.append(event)
            elif event.id == last_event_id:
                found_start = True

        return events

    def subscribe_to_topic(self, topic: str):
        """Subscribe to a specific topic."""
        self.subscriptions.add(topic)
        logger.debug(f"Client {self.client_id} subscribed to topic: {topic}")

    def unsubscribe_from_topic(self, topic: str):
        """Unsubscribe from a specific topic."""
        self.subscriptions.discard(topic)
        logger.debug(f"Client {self.client_id} unsubscribed from topic: {topic}")

    def has_subscription(self, topic: str) -> bool:
        """Check if client is subscribed to topic."""
        return topic in self.subscriptions

    def get_info(self) -> Dict[str, Any]:
        """Get connection information."""
        return {
            "client_id": self.client_id,
            "connected": self.connected,
            "subscriptions": list(self.subscriptions),
            "buffer_size": len(self.event_buffer),
            "last_event_id": self.last_event_id,
            "created_at": self.created_at.isoformat(),
            "last_activity": datetime.fromtimestamp(self.last_activity).isoformat(),
            "statistics": self.statistics
        }

class SSEManager:
    """Manager for Server-Sent Events connections and streaming."""

    def __init__(self):
        self.connections: Dict[str, SSEConnection] = {}
        self.topic_subscribers: Dict[str, Set[str]] = {}
        self.event_handlers: Dict[str, Callable] = {}
        self.global_config = SSEClientConfig()
        self.statistics = {
            "total_connections": 0,
            "active_connections": 0,
            "events_broadcasted": 0,
            "total_events_sent": 0
        }
        self._cleanup_task: Optional[asyncio.Task] = None
        self._start_cleanup_task()

    def _start_cleanup_task(self):
        """Start background task for cleaning up inactive connections."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_inactive_connections())

    async def _cleanup_inactive_connections(self):
        """Clean up inactive connections periodically."""
        while True:
            try:
                await asyncio.sleep(300)  # Check every 5 minutes
                current_time = time.time()
                inactive_clients = []

                for client_id, connection in self.connections.items():
                    # Remove connections inactive for more than 1 hour
                    if current_time - connection.last_activity > 3600:
                        inactive_clients.append(client_id)

                for client_id in inactive_clients:
                    await self.remove_client(client_id)
                    logger.info(f"Removed inactive client: {client_id}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")

    async def create_client_stream(self, client_id: str, last_event_id: Optional[str] = None) -> AsyncGenerator[str, None]:
        """Create SSE stream for a client."""
        # Create or get existing connection
        if client_id not in self.connections:
            self.connections[client_id] = SSEConnection(client_id, self.global_config)
            self.statistics["total_connections"] += 1

        connection = self.connections[client_id]
        connection.connected = True
        connection.last_activity = time.time()
        self.statistics["active_connections"] += 1

        if last_event_id:
            connection.statistics["reconnect_count"] += 1
            connection.statistics["last_reconnect"] = datetime.utcnow().isoformat()

        try:
            # Send initial connection event
            welcome_event = SSEEvent(
                id=f"welcome_{int(time.time())}",
                event="connection",
                data={
                    "client_id": client_id,
                    "server_time": time.time(),
                    "retry_timeout": self.global_config.retry_timeout
                }
            )
            yield welcome_event.format_sse()

            # Send buffered events if reconnecting
            if last_event_id:
                buffered_events = await connection.get_events_since(last_event_id)
                for event in buffered_events:
                    yield event.format_sse()
                    connection.statistics["events_sent"] += 1
                    self.statistics["total_events_sent"] += 1

            # Start heartbeat
            connection.heartbeat_task = asyncio.create_task(
                self._heartbeat_loop(connection)
            )

            # Stream events from buffer
            last_buffer_size = 0
            while connection.connected:
                try:
                    current_buffer_size = len(connection.event_buffer)

                    # Send new events
                    if current_buffer_size > last_buffer_size:
                        new_events = list(connection.event_buffer)[last_buffer_size:]
                        for event in new_events:
                            yield event.format_sse()
                            connection.statistics["events_sent"] += 1
                            self.statistics["total_events_sent"] += 1

                        last_buffer_size = current_buffer_size

                    await asyncio.sleep(0.1)  # Small delay to prevent busy waiting

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Error in SSE stream for client {client_id}: {e}")
                    break

        finally:
            # Cleanup
            connection.connected = False
            self.statistics["active_connections"] = max(0, self.statistics["active_connections"] - 1)

            if connection.heartbeat_task:
                connection.heartbeat_task.cancel()

    async def _heartbeat_loop(self, connection: SSEConnection):
        """Send periodic heartbeat events."""
        while connection.connected:
            try:
                await asyncio.sleep(connection.config.heartbeat_interval)

                heartbeat_event = SSEEvent(
                    id=f"heartbeat_{int(time.time())}",
                    event="heartbeat",
                    data={"timestamp": time.time()}
                )

                await connection.send_event(heartbeat_event)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in heartbeat for client {connection.client_id}: {e}")

    async def broadcast_event(self, event: SSEEvent, topic: Optional[str] = None):
        """Broadcast event to all clients or topic subscribers."""
        if topic:
            # Send to topic subscribers
            if topic in self.topic_subscribers:
                for client_id in self.topic_subscribers[topic]:
                    if client_id in self.connections:
                        await self.connections[client_id].send_event(event)
        else:
            # Send to all clients
            for connection in self.connections.values():
                await connection.send_event(event)

        self.statistics["events_broadcasted"] += 1

    async def send_to_client(self, client_id: str, event: SSEEvent) -> bool:
        """Send event to specific client."""
        if client_id in self.connections:
            return await self.connections[client_id].send_event(event)
        return False

    async def subscribe_client_to_topic(self, client_id: str, topic: str):
        """Subscribe client to a topic."""
        if client_id in self.connections:
            self.connections[client_id].subscribe_to_topic(topic)

            if topic not in self.topic_subscribers:
                self.topic_subscribers[topic] = set()
            self.topic_subscribers[topic].add(client_id)

    async def unsubscribe_client_from_topic(self, client_id: str, topic: str):
        """Unsubscribe client from a topic."""
        if client_id in self.connections:
            self.connections[client_id].unsubscribe_from_topic(topic)

            if topic in self.topic_subscribers:
                self.topic_subscribers[topic].discard(client_id)
                # Clean up empty topic
                if not self.topic_subscribers[topic]:
                    del self.topic_subscribers[topic]

    async def remove_client(self, client_id: str):
        """Remove client and cleanup subscriptions."""
        if client_id in self.connections:
            connection = self.connections[client_id]
            connection.connected = False

            # Cancel heartbeat task
            if connection.heartbeat_task:
                connection.heartbeat_task.cancel()

            # Remove from topic subscriptions
            for topic in connection.subscriptions:
                if topic in self.topic_subscribers:
                    self.topic_subscribers[topic].discard(client_id)
                    if not self.topic_subscribers[topic]:
                        del self.topic_subscribers[topic]

            del self.connections[client_id]
            self.statistics["active_connections"] = max(0, self.statistics["active_connections"] - 1)

    def get_client_info(self, client_id: str) -> Optional[Dict[str, Any]]:
        """Get information about specific client."""
        if client_id in self.connections:
            return self.connections[client_id].get_info()
        return None

    def get_manager_stats(self) -> Dict[str, Any]:
        """Get manager statistics and information."""
        return {
            "statistics": self.statistics,
            "active_connections": len([c for c in self.connections.values() if c.connected]),
            "total_connections": len(self.connections),
            "topics": {
                topic: len(subscribers)
                for topic, subscribers in self.topic_subscribers.items()
            }
        }

    def register_event_handler(self, event_type: str, handler: Callable):
        """Register handler for specific event types."""
        self.event_handlers[event_type] = handler

    async def trigger_event(self, event_type: str, data: Any, topic: Optional[str] = None):
        """Trigger an event with custom handler."""
        event = SSEEvent(
            id=str(uuid.uuid4()),
            event=event_type,
            data=data
        )

        # Call custom handler if registered
        if event_type in self.event_handlers:
            try:
                await self.event_handlers[event_type](event, topic)
            except Exception as e:
                logger.error(f"Error in event handler for {event_type}: {e}")

        await self.broadcast_event(event, topic)

    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on SSE service."""
        active_connections = len([c for c in self.connections.values() if c.connected])
        total_buffer_size = sum(len(c.event_buffer) for c in self.connections.values())

        return {
            "status": "healthy",
            "active_connections": active_connections,
            "total_connections": len(self.connections),
            "total_buffer_size": total_buffer_size,
            "topics_count": len(self.topic_subscribers),
            "statistics": self.statistics,
            "uptime": (datetime.utcnow() - datetime.utcnow()).total_seconds()  # Would track actual uptime
        }

# Global SSE manager instance
sse_manager = SSEManager()

# Example event handlers
async def handle_data_update_event(event: SSEEvent, topic: Optional[str]):
    """Handle data update events."""
    logger.info(f"Data update event triggered for topic: {topic}")

async def handle_alert_event(event: SSEEvent, topic: Optional[str]):
    """Handle alert events."""
    logger.warning(f"Alert event triggered: {event.data}")

# Register default handlers
sse_manager.register_event_handler("data_update", handle_data_update_event)
sse_manager.register_event_handler("alert", handle_alert_event)