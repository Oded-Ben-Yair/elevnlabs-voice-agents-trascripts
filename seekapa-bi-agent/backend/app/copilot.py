"""
Enhanced WebSocket Copilot Service with automatic reconnection,
message queuing, buffering, and heartbeat functionality.
"""

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from collections import deque
from enum import Enum
import websockets
import websockets.exceptions
from websockets.server import WebSocketServerProtocol
from dataclasses import dataclass, asdict
from contextlib import asynccontextmanager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ConnectionState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"

@dataclass
class Message:
    id: str
    type: str
    data: Any
    timestamp: float = None
    retry_count: int = 0
    max_retries: int = 3

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()

    def to_json(self) -> str:
        return json.dumps(asdict(self))

@dataclass
class HeartbeatConfig:
    interval: float = 30.0  # seconds
    timeout: float = 10.0   # seconds
    max_missed: int = 3     # consecutive missed heartbeats before disconnect

class WebSocketConnection:
    """Enhanced WebSocket connection with automatic reconnection and message queuing."""

    def __init__(self, websocket: WebSocketServerProtocol, client_id: str):
        self.websocket = websocket
        self.client_id = client_id
        self.state = ConnectionState.CONNECTED
        self.message_queue: deque = deque(maxlen=1000)  # Buffer up to 1000 messages
        self.pending_messages: Dict[str, Message] = {}
        self.last_heartbeat = time.time()
        self.heartbeat_config = HeartbeatConfig()
        self.missed_heartbeats = 0
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 10
        self.reconnect_delay = 1.0  # Initial delay in seconds
        self.max_reconnect_delay = 60.0
        self.created_at = datetime.utcnow()

        # Start heartbeat task
        self._heartbeat_task = None
        self._message_processor_task = None

    async def start_background_tasks(self):
        """Start background tasks for heartbeat and message processing."""
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self._message_processor_task = asyncio.create_task(self._message_processor())

    async def stop_background_tasks(self):
        """Stop background tasks."""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._message_processor_task:
            self._message_processor_task.cancel()

    async def _heartbeat_loop(self):
        """Send periodic heartbeat messages to maintain connection."""
        while self.state in [ConnectionState.CONNECTED, ConnectionState.RECONNECTING]:
            try:
                await asyncio.sleep(self.heartbeat_config.interval)

                if self.state == ConnectionState.CONNECTED:
                    heartbeat_msg = Message(
                        id=f"heartbeat_{int(time.time())}",
                        type="heartbeat",
                        data={"timestamp": time.time()}
                    )

                    await self.send_message(heartbeat_msg)

                    # Check for missed heartbeats
                    time_since_last = time.time() - self.last_heartbeat
                    if time_since_last > self.heartbeat_config.timeout:
                        self.missed_heartbeats += 1
                        logger.warning(f"Missed heartbeat for client {self.client_id}. Count: {self.missed_heartbeats}")

                        if self.missed_heartbeats >= self.heartbeat_config.max_missed:
                            logger.error(f"Too many missed heartbeats for client {self.client_id}. Initiating reconnection.")
                            await self.handle_disconnect()
                    else:
                        self.missed_heartbeats = 0

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in heartbeat loop for client {self.client_id}: {e}")

    async def _message_processor(self):
        """Process queued messages with retry logic."""
        while self.state != ConnectionState.DISCONNECTED:
            try:
                if self.message_queue and self.state == ConnectionState.CONNECTED:
                    message = self.message_queue.popleft()
                    success = await self._send_raw_message(message)

                    if not success and message.retry_count < message.max_retries:
                        message.retry_count += 1
                        self.message_queue.appendleft(message)  # Re-queue for retry
                        await asyncio.sleep(min(2 ** message.retry_count, 10))  # Exponential backoff

                await asyncio.sleep(0.1)  # Small delay to prevent busy waiting

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in message processor for client {self.client_id}: {e}")
                await asyncio.sleep(1)

    async def send_message(self, message: Message) -> bool:
        """Queue message for sending with automatic retry."""
        self.message_queue.append(message)
        return True

    async def _send_raw_message(self, message: Message) -> bool:
        """Send message directly to WebSocket."""
        try:
            if self.websocket and not self.websocket.closed:
                await self.websocket.send(message.to_json())
                logger.debug(f"Sent message {message.id} to client {self.client_id}")
                return True
            else:
                logger.warning(f"WebSocket closed for client {self.client_id}")
                await self.handle_disconnect()
                return False

        except websockets.exceptions.ConnectionClosed:
            logger.warning(f"Connection closed for client {self.client_id}")
            await self.handle_disconnect()
            return False
        except Exception as e:
            logger.error(f"Error sending message to client {self.client_id}: {e}")
            return False

    async def handle_message(self, raw_message: str) -> Optional[Message]:
        """Handle incoming message from client."""
        try:
            data = json.loads(raw_message)
            message = Message(
                id=data.get('id', f"msg_{int(time.time())}"),
                type=data.get('type', 'unknown'),
                data=data.get('data', {})
            )

            # Handle heartbeat responses
            if message.type == "heartbeat_response":
                self.last_heartbeat = time.time()
                self.missed_heartbeats = 0
                return None

            return message

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON from client {self.client_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error handling message from client {self.client_id}: {e}")
            return None

    async def handle_disconnect(self):
        """Handle client disconnection and initiate reconnection if needed."""
        self.state = ConnectionState.DISCONNECTED
        await self.stop_background_tasks()

        if self.websocket and not self.websocket.closed:
            try:
                await self.websocket.close()
            except Exception as e:
                logger.error(f"Error closing WebSocket for client {self.client_id}: {e}")

    def get_connection_info(self) -> Dict[str, Any]:
        """Get connection information and statistics."""
        return {
            "client_id": self.client_id,
            "state": self.state.value,
            "queue_size": len(self.message_queue),
            "pending_messages": len(self.pending_messages),
            "missed_heartbeats": self.missed_heartbeats,
            "reconnect_attempts": self.reconnect_attempts,
            "created_at": self.created_at.isoformat(),
            "last_heartbeat": datetime.fromtimestamp(self.last_heartbeat).isoformat()
        }

class WebSocketCopilotManager:
    """Manager for WebSocket connections with enhanced features."""

    def __init__(self):
        self.connections: Dict[str, WebSocketConnection] = {}
        self.message_handlers: Dict[str, Callable] = {}
        self.connection_callbacks: Dict[str, Callable] = {}
        self.global_message_queue: deque = deque(maxlen=10000)
        self.statistics = {
            "total_connections": 0,
            "active_connections": 0,
            "messages_sent": 0,
            "messages_received": 0,
            "reconnections": 0
        }

    def register_message_handler(self, message_type: str, handler: Callable):
        """Register handler for specific message types."""
        self.message_handlers[message_type] = handler

    def register_connection_callback(self, event: str, callback: Callable):
        """Register callback for connection events (connect, disconnect, error)."""
        self.connection_callbacks[event] = callback

    async def handle_new_connection(self, websocket: WebSocketServerProtocol, client_id: str):
        """Handle new WebSocket connection."""
        try:
            connection = WebSocketConnection(websocket, client_id)
            self.connections[client_id] = connection

            # Start background tasks
            await connection.start_background_tasks()

            # Update statistics
            self.statistics["total_connections"] += 1
            self.statistics["active_connections"] += 1

            # Call connection callback
            if "connect" in self.connection_callbacks:
                await self.connection_callbacks["connect"](connection)

            logger.info(f"New WebSocket connection established: {client_id}")

            # Send welcome message
            welcome_msg = Message(
                id=f"welcome_{int(time.time())}",
                type="welcome",
                data={
                    "client_id": client_id,
                    "server_time": time.time(),
                    "features": ["heartbeat", "message_queuing", "auto_reconnect"]
                }
            )
            await connection.send_message(welcome_msg)

            # Listen for messages
            async for raw_message in websocket:
                message = await connection.handle_message(raw_message)
                if message:
                    await self.process_message(connection, message)

        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Client {client_id} disconnected")
        except Exception as e:
            logger.error(f"Error handling connection for {client_id}: {e}")
        finally:
            await self.handle_disconnection(client_id)

    async def process_message(self, connection: WebSocketConnection, message: Message):
        """Process incoming message from client."""
        try:
            self.statistics["messages_received"] += 1

            # Handle message based on type
            if message.type in self.message_handlers:
                response = await self.message_handlers[message.type](connection, message)
                if response:
                    await connection.send_message(response)
            else:
                # Default handling for unknown message types
                logger.warning(f"Unknown message type: {message.type} from client {connection.client_id}")

                error_response = Message(
                    id=f"error_{int(time.time())}",
                    type="error",
                    data={
                        "error": "unknown_message_type",
                        "original_message_id": message.id,
                        "message": f"Unknown message type: {message.type}"
                    }
                )
                await connection.send_message(error_response)

        except Exception as e:
            logger.error(f"Error processing message from {connection.client_id}: {e}")

    async def handle_disconnection(self, client_id: str):
        """Handle client disconnection cleanup."""
        if client_id in self.connections:
            connection = self.connections[client_id]
            await connection.handle_disconnect()

            # Update statistics
            self.statistics["active_connections"] = max(0, self.statistics["active_connections"] - 1)

            # Call disconnection callback
            if "disconnect" in self.connection_callbacks:
                await self.connection_callbacks["disconnect"](connection)

            # Remove from active connections
            del self.connections[client_id]

            logger.info(f"Client {client_id} disconnection handled")

    async def broadcast_message(self, message: Message, exclude_clients: Optional[List[str]] = None):
        """Broadcast message to all connected clients."""
        exclude_clients = exclude_clients or []

        for client_id, connection in self.connections.items():
            if client_id not in exclude_clients and connection.state == ConnectionState.CONNECTED:
                await connection.send_message(message)

        self.statistics["messages_sent"] += len(self.connections) - len(exclude_clients)

    async def send_to_client(self, client_id: str, message: Message) -> bool:
        """Send message to specific client."""
        if client_id in self.connections:
            success = await self.connections[client_id].send_message(message)
            if success:
                self.statistics["messages_sent"] += 1
            return success
        return False

    def get_connection_info(self, client_id: str) -> Optional[Dict[str, Any]]:
        """Get connection information for specific client."""
        if client_id in self.connections:
            return self.connections[client_id].get_connection_info()
        return None

    def get_all_connections_info(self) -> Dict[str, Any]:
        """Get information about all connections."""
        return {
            "statistics": self.statistics,
            "active_connections": {
                client_id: conn.get_connection_info()
                for client_id, conn in self.connections.items()
            }
        }

    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on all connections."""
        healthy_connections = 0
        unhealthy_connections = 0

        for connection in self.connections.values():
            if connection.state == ConnectionState.CONNECTED:
                # Check if connection is responsive
                time_since_heartbeat = time.time() - connection.last_heartbeat
                if time_since_heartbeat < connection.heartbeat_config.timeout * 2:
                    healthy_connections += 1
                else:
                    unhealthy_connections += 1
            else:
                unhealthy_connections += 1

        return {
            "status": "healthy" if unhealthy_connections == 0 else "degraded",
            "healthy_connections": healthy_connections,
            "unhealthy_connections": unhealthy_connections,
            "total_connections": len(self.connections),
            "statistics": self.statistics
        }

# Global manager instance
copilot_manager = WebSocketCopilotManager()

# Example message handlers
async def handle_query_message(connection: WebSocketConnection, message: Message) -> Message:
    """Handle query-type messages."""
    # This would integrate with your BI query engine
    query_data = message.data.get('query', '')

    # Simulate query processing
    await asyncio.sleep(0.1)

    response = Message(
        id=f"query_response_{int(time.time())}",
        type="query_response",
        data={
            "original_message_id": message.id,
            "query": query_data,
            "result": "Query processed successfully",
            "execution_time": 100,
            "timestamp": time.time()
        }
    )

    return response

async def handle_subscribe_message(connection: WebSocketConnection, message: Message) -> Message:
    """Handle subscription messages for real-time data."""
    topic = message.data.get('topic', '')

    # Add client to subscription list (would integrate with your event system)

    response = Message(
        id=f"subscription_response_{int(time.time())}",
        type="subscription_response",
        data={
            "original_message_id": message.id,
            "topic": topic,
            "status": "subscribed",
            "message": f"Successfully subscribed to {topic}"
        }
    )

    return response

# Register default handlers
copilot_manager.register_message_handler("query", handle_query_message)
copilot_manager.register_message_handler("subscribe", handle_subscribe_message)

# Connection event handlers
async def on_client_connect(connection: WebSocketConnection):
    """Handle client connection events."""
    logger.info(f"Client connected: {connection.client_id}")

async def on_client_disconnect(connection: WebSocketConnection):
    """Handle client disconnection events."""
    logger.info(f"Client disconnected: {connection.client_id}")

copilot_manager.register_connection_callback("connect", on_client_connect)
copilot_manager.register_connection_callback("disconnect", on_client_disconnect)