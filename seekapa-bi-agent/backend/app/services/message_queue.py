"""
RabbitMQ Message Queue Service for Seekapa BI Agent.
Provides robust message queuing with RabbitMQ as an alternative to Kafka,
including dead letter handling, priority queues, and message persistence.
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Dict, List, Optional, Any, Callable, Union
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
import threading

try:
    import aio_pika
    from aio_pika import Message, DeliveryMode, ExchangeType, connect_robust
    from aio_pika.abc import AbstractConnection, AbstractChannel, AbstractExchange, AbstractQueue
    AIO_PIKA_AVAILABLE = True
except ImportError:
    AIO_PIKA_AVAILABLE = False
    # Mock classes for when aio_pika is not available
    class Message:
        def __init__(self, body, **kwargs): pass

    class DeliveryMode:
        PERSISTENT = 2

    class ExchangeType:
        DIRECT = "direct"
        TOPIC = "topic"
        FANOUT = "fanout"
        HEADERS = "headers"

    class AbstractConnection: pass
    class AbstractChannel: pass
    class AbstractExchange: pass
    class AbstractQueue: pass

logger = logging.getLogger(__name__)

class QueueType(Enum):
    STANDARD = "standard"
    PRIORITY = "priority"
    DELAYED = "delayed"
    DEAD_LETTER = "dead_letter"

class MessagePriority(Enum):
    LOW = 1
    NORMAL = 5
    HIGH = 8
    CRITICAL = 10

@dataclass
class QueueMessage:
    """Message structure for RabbitMQ."""
    id: str
    body: Any
    routing_key: str
    exchange: str = ""
    priority: MessagePriority = MessagePriority.NORMAL
    timestamp: float = None
    expiration: Optional[int] = None  # TTL in seconds
    headers: Dict[str, Any] = None
    correlation_id: Optional[str] = None
    reply_to: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()
        if self.headers is None:
            self.headers = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary."""
        return {
            "id": self.id,
            "body": self.body,
            "routing_key": self.routing_key,
            "exchange": self.exchange,
            "priority": self.priority.value,
            "timestamp": self.timestamp,
            "expiration": self.expiration,
            "headers": self.headers,
            "correlation_id": self.correlation_id,
            "reply_to": self.reply_to,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries
        }

@dataclass
class QueueConfig:
    """Configuration for RabbitMQ queue."""
    name: str
    exchange: str = ""
    routing_key: str = ""
    queue_type: QueueType = QueueType.STANDARD
    durable: bool = True
    exclusive: bool = False
    auto_delete: bool = False
    arguments: Dict[str, Any] = None

    def __post_init__(self):
        if self.arguments is None:
            self.arguments = {}

        # Set queue-specific arguments
        if self.queue_type == QueueType.PRIORITY:
            self.arguments["x-max-priority"] = 10
        elif self.queue_type == QueueType.DELAYED:
            self.arguments["x-delayed-type"] = "direct"

@dataclass
class ExchangeConfig:
    """Configuration for RabbitMQ exchange."""
    name: str
    exchange_type: ExchangeType = ExchangeType.DIRECT
    durable: bool = True
    auto_delete: bool = False
    arguments: Dict[str, Any] = None

    def __post_init__(self):
        if self.arguments is None:
            self.arguments = {}

@dataclass
class RabbitMQConfig:
    """RabbitMQ connection configuration."""
    host: str = "localhost"
    port: int = 5672
    username: str = "guest"
    password: str = "guest"
    virtual_host: str = "/"
    connection_timeout: int = 30
    heartbeat: int = 600
    max_channels: int = 1000

    # Connection pooling
    pool_size: int = 10
    max_overflow: int = 20

    # SSL configuration
    ssl_enabled: bool = False
    ssl_cafile: Optional[str] = None
    ssl_certfile: Optional[str] = None
    ssl_keyfile: Optional[str] = None

class RabbitMQProducer:
    """RabbitMQ message producer with connection management."""

    def __init__(self, config: RabbitMQConfig):
        self.config = config
        self.connection: Optional[AbstractConnection] = None
        self.channel: Optional[AbstractChannel] = None
        self.exchanges: Dict[str, AbstractExchange] = {}
        self.is_connected = False
        self.statistics = {
            "messages_sent": 0,
            "messages_failed": 0,
            "connection_errors": 0,
            "last_error": None,
            "uptime_start": datetime.utcnow()
        }
        self._connection_lock = threading.RLock()

    async def connect(self) -> bool:
        """Connect to RabbitMQ."""
        if not AIO_PIKA_AVAILABLE:
            logger.error("aio_pika library not available. Install it with: pip install aio-pika")
            return False

        try:
            # Build connection URL
            connection_url = (
                f"amqp://{self.config.username}:{self.config.password}@"
                f"{self.config.host}:{self.config.port}{self.config.virtual_host}"
            )

            # Connection parameters
            connection_params = {
                "url": connection_url,
                "timeout": self.config.connection_timeout,
                "heartbeat": self.config.heartbeat
            }

            # Add SSL configuration if enabled
            if self.config.ssl_enabled:
                connection_params["ssl"] = True
                if self.config.ssl_cafile:
                    connection_params["ssl_options"] = {
                        "cafile": self.config.ssl_cafile,
                        "certfile": self.config.ssl_certfile,
                        "keyfile": self.config.ssl_keyfile
                    }

            self.connection = await connect_robust(**connection_params)
            self.channel = await self.connection.channel()

            # Set QoS for the channel
            await self.channel.set_qos(prefetch_count=100)

            self.is_connected = True
            logger.info("RabbitMQ producer connected successfully")
            return True

        except Exception as e:
            self.statistics["connection_errors"] += 1
            self.statistics["last_error"] = str(e)
            logger.error(f"Failed to connect RabbitMQ producer: {e}")
            return False

    async def disconnect(self):
        """Disconnect from RabbitMQ."""
        try:
            if self.connection:
                await self.connection.close()
            self.is_connected = False
            logger.info("RabbitMQ producer disconnected")
        except Exception as e:
            logger.error(f"Error disconnecting RabbitMQ producer: {e}")

    async def declare_exchange(self, config: ExchangeConfig) -> bool:
        """Declare an exchange."""
        if not self.is_connected or not self.channel:
            logger.error("RabbitMQ producer not connected")
            return False

        try:
            exchange = await self.channel.declare_exchange(
                config.name,
                config.exchange_type.value,
                durable=config.durable,
                auto_delete=config.auto_delete,
                arguments=config.arguments
            )

            self.exchanges[config.name] = exchange
            logger.info(f"Exchange '{config.name}' declared successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to declare exchange '{config.name}': {e}")
            return False

    async def send_message(self, message: QueueMessage) -> bool:
        """Send message to RabbitMQ."""
        if not self.is_connected or not self.channel:
            logger.error("RabbitMQ producer not connected")
            return False

        try:
            # Prepare message body
            if isinstance(message.body, (dict, list)):
                body = json.dumps(message.body).encode()
            else:
                body = str(message.body).encode()

            # Prepare message headers
            headers = {
                "message_id": message.id,
                "timestamp": message.timestamp,
                "retry_count": message.retry_count,
                **message.headers
            }

            # Create AMQP message
            amqp_message = Message(
                body,
                message_id=message.id,
                correlation_id=message.correlation_id,
                reply_to=message.reply_to,
                timestamp=datetime.fromtimestamp(message.timestamp),
                headers=headers,
                priority=message.priority.value,
                delivery_mode=DeliveryMode.PERSISTENT,
                expiration=message.expiration * 1000 if message.expiration else None  # Convert to milliseconds
            )

            # Get or use default exchange
            if message.exchange and message.exchange in self.exchanges:
                exchange = self.exchanges[message.exchange]
            else:
                exchange = self.channel.default_exchange

            # Send message
            await exchange.publish(amqp_message, routing_key=message.routing_key)

            self.statistics["messages_sent"] += 1
            logger.debug(f"Message {message.id} sent successfully")
            return True

        except Exception as e:
            self.statistics["messages_failed"] += 1
            self.statistics["last_error"] = str(e)
            logger.error(f"Failed to send message {message.id}: {e}")
            return False

    async def send_batch(self, messages: List[QueueMessage]) -> Dict[str, bool]:
        """Send multiple messages in batch."""
        results = {}

        for message in messages:
            results[message.id] = await self.send_message(message)

        return results

    def get_statistics(self) -> Dict[str, Any]:
        """Get producer statistics."""
        uptime = (datetime.utcnow() - self.statistics["uptime_start"]).total_seconds()

        return {
            **self.statistics,
            "is_connected": self.is_connected,
            "uptime_seconds": uptime,
            "declared_exchanges": list(self.exchanges.keys())
        }

class RabbitMQConsumer:
    """RabbitMQ message consumer with automatic acknowledgment and retry logic."""

    def __init__(self, config: RabbitMQConfig):
        self.config = config
        self.connection: Optional[AbstractConnection] = None
        self.channel: Optional[AbstractChannel] = None
        self.queues: Dict[str, AbstractQueue] = {}
        self.message_handlers: Dict[str, Callable] = {}
        self.is_connected = False
        self.is_consuming = False
        self.statistics = {
            "messages_consumed": 0,
            "messages_processed": 0,
            "messages_failed": 0,
            "connection_errors": 0,
            "last_error": None,
            "uptime_start": datetime.utcnow()
        }
        self._consumer_tasks: Dict[str, asyncio.Task] = {}

    async def connect(self) -> bool:
        """Connect to RabbitMQ."""
        if not AIO_PIKA_AVAILABLE:
            logger.error("aio_pika library not available. Install it with: pip install aio-pika")
            return False

        try:
            # Build connection URL
            connection_url = (
                f"amqp://{self.config.username}:{self.config.password}@"
                f"{self.config.host}:{self.config.port}{self.config.virtual_host}"
            )

            # Connection parameters
            connection_params = {
                "url": connection_url,
                "timeout": self.config.connection_timeout,
                "heartbeat": self.config.heartbeat
            }

            self.connection = await connect_robust(**connection_params)
            self.channel = await self.connection.channel()

            # Set QoS for fair dispatch
            await self.channel.set_qos(prefetch_count=10)

            self.is_connected = True
            logger.info("RabbitMQ consumer connected successfully")
            return True

        except Exception as e:
            self.statistics["connection_errors"] += 1
            self.statistics["last_error"] = str(e)
            logger.error(f"Failed to connect RabbitMQ consumer: {e}")
            return False

    async def disconnect(self):
        """Disconnect from RabbitMQ."""
        try:
            self.is_consuming = False

            # Cancel all consumer tasks
            for task in self._consumer_tasks.values():
                task.cancel()
            self._consumer_tasks.clear()

            if self.connection:
                await self.connection.close()

            self.is_connected = False
            logger.info("RabbitMQ consumer disconnected")

        except Exception as e:
            logger.error(f"Error disconnecting RabbitMQ consumer: {e}")

    async def declare_queue(self, config: QueueConfig) -> bool:
        """Declare a queue."""
        if not self.is_connected or not self.channel:
            logger.error("RabbitMQ consumer not connected")
            return False

        try:
            # Configure dead letter queue if needed
            if config.queue_type == QueueType.DEAD_LETTER:
                config.arguments.update({
                    "x-dead-letter-exchange": f"{config.name}.dlx",
                    "x-dead-letter-routing-key": f"{config.name}.dead"
                })

            queue = await self.channel.declare_queue(
                config.name,
                durable=config.durable,
                exclusive=config.exclusive,
                auto_delete=config.auto_delete,
                arguments=config.arguments
            )

            self.queues[config.name] = queue

            # Bind queue to exchange if specified
            if config.exchange:
                await queue.bind(config.exchange, config.routing_key)

            logger.info(f"Queue '{config.name}' declared successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to declare queue '{config.name}': {e}")
            return False

    async def register_handler(self, queue_name: str, handler: Callable) -> bool:
        """Register message handler for a queue."""
        if queue_name not in self.queues:
            logger.error(f"Queue '{queue_name}' not declared")
            return False

        self.message_handlers[queue_name] = handler
        logger.info(f"Handler registered for queue '{queue_name}'")
        return True

    async def start_consuming(self, queue_name: str) -> bool:
        """Start consuming messages from a queue."""
        if queue_name not in self.queues:
            logger.error(f"Queue '{queue_name}' not declared")
            return False

        if queue_name not in self.message_handlers:
            logger.error(f"No handler registered for queue '{queue_name}'")
            return False

        try:
            queue = self.queues[queue_name]
            handler = self.message_handlers[queue_name]

            # Start consuming
            consumer_tag = await queue.consume(
                lambda message: self._handle_message(message, handler, queue_name)
            )

            self.is_consuming = True
            logger.info(f"Started consuming from queue '{queue_name}'")
            return True

        except Exception as e:
            logger.error(f"Failed to start consuming from queue '{queue_name}': {e}")
            return False

    async def _handle_message(self, message, handler: Callable, queue_name: str):
        """Handle incoming message."""
        try:
            self.statistics["messages_consumed"] += 1

            # Parse message
            headers = message.headers or {}
            message_id = headers.get("message_id", str(uuid.uuid4()))
            retry_count = headers.get("retry_count", 0)

            # Deserialize body
            try:
                body = json.loads(message.body.decode())
            except (json.JSONDecodeError, UnicodeDecodeError):
                body = message.body.decode()

            # Create QueueMessage object
            queue_message = QueueMessage(
                id=message_id,
                body=body,
                routing_key=message.routing_key,
                headers=headers,
                correlation_id=message.correlation_id,
                reply_to=message.reply_to,
                retry_count=retry_count
            )

            # Process message with handler
            success = await handler(queue_message)

            if success:
                await message.ack()
                self.statistics["messages_processed"] += 1
                logger.debug(f"Message {message_id} processed successfully")
            else:
                # Retry logic
                if retry_count < queue_message.max_retries:
                    await self._retry_message(queue_message, queue_name)
                    await message.ack()  # Remove from original queue
                else:
                    await message.nack(requeue=False)  # Send to DLQ if configured
                    logger.error(f"Message {message_id} exceeded max retries")

        except Exception as e:
            self.statistics["messages_failed"] += 1
            logger.error(f"Error handling message: {e}")
            await message.nack(requeue=False)

    async def _retry_message(self, message: QueueMessage, queue_name: str):
        """Retry failed message with delay."""
        try:
            message.retry_count += 1
            message.headers["retry_count"] = message.retry_count

            # Calculate delay (exponential backoff)
            delay = min(2 ** message.retry_count, 300)  # Max 5 minutes

            # Send to delayed queue for retry
            retry_queue_name = f"{queue_name}.retry"
            if retry_queue_name in self.queues:
                # Add delay headers for delayed message plugin
                message.headers["x-delay"] = delay * 1000  # Convert to milliseconds

                # Re-send message
                retry_message = Message(
                    json.dumps(message.body).encode(),
                    headers=message.headers,
                    message_id=message.id,
                    correlation_id=message.correlation_id
                )

                retry_queue = self.queues[retry_queue_name]
                await retry_queue.publish(retry_message)

                logger.info(f"Message {message.id} scheduled for retry in {delay} seconds")

        except Exception as e:
            logger.error(f"Failed to retry message {message.id}: {e}")

    def get_statistics(self) -> Dict[str, Any]:
        """Get consumer statistics."""
        uptime = (datetime.utcnow() - self.statistics["uptime_start"]).total_seconds()

        return {
            **self.statistics,
            "is_connected": self.is_connected,
            "is_consuming": self.is_consuming,
            "uptime_seconds": uptime,
            "declared_queues": list(self.queues.keys()),
            "active_handlers": list(self.message_handlers.keys())
        }

class RabbitMQService:
    """Complete RabbitMQ service combining producer and consumer."""

    def __init__(self, config: RabbitMQConfig):
        self.config = config
        self.producer = RabbitMQProducer(config)
        self.consumer = RabbitMQConsumer(config)
        self.is_initialized = False

    async def initialize(self) -> bool:
        """Initialize RabbitMQ service."""
        try:
            producer_connected = await self.producer.connect()
            consumer_connected = await self.consumer.connect()

            self.is_initialized = producer_connected and consumer_connected

            if self.is_initialized:
                # Declare default exchanges and queues
                await self._setup_default_infrastructure()
                logger.info("RabbitMQ service initialized successfully")
            else:
                logger.error("Failed to initialize RabbitMQ service")

            return self.is_initialized

        except Exception as e:
            logger.error(f"Error initializing RabbitMQ service: {e}")
            return False

    async def _setup_default_infrastructure(self):
        """Setup default exchanges and queues."""
        try:
            # Default topic exchange for BI events
            bi_exchange_config = ExchangeConfig(
                name="bi.events",
                exchange_type=ExchangeType.TOPIC
            )
            await self.producer.declare_exchange(bi_exchange_config)

            # Default queues
            default_queues = [
                QueueConfig(name="bi.queries", exchange="bi.events", routing_key="query.*"),
                QueueConfig(name="bi.reports", exchange="bi.events", routing_key="report.*"),
                QueueConfig(name="bi.alerts", exchange="bi.events", routing_key="alert.*", queue_type=QueueType.PRIORITY),
                QueueConfig(name="bi.notifications", exchange="bi.events", routing_key="notification.*"),
            ]

            for queue_config in default_queues:
                await self.consumer.declare_queue(queue_config)

        except Exception as e:
            logger.error(f"Error setting up default infrastructure: {e}")

    async def shutdown(self):
        """Shutdown RabbitMQ service."""
        await self.producer.disconnect()
        await self.consumer.disconnect()
        self.is_initialized = False
        logger.info("RabbitMQ service shut down")

    async def send_event(self, routing_key: str, data: Dict[str, Any],
                        priority: MessagePriority = MessagePriority.NORMAL,
                        exchange: str = "bi.events") -> bool:
        """Send event to RabbitMQ."""
        message = QueueMessage(
            id=str(uuid.uuid4()),
            body=data,
            routing_key=routing_key,
            exchange=exchange,
            priority=priority,
            headers={
                "source": "seekapa-bi-agent",
                "timestamp": str(int(time.time()))
            }
        )

        return await self.producer.send_message(message)

    async def register_event_handler(self, queue_name: str, handler: Callable) -> bool:
        """Register event handler for a queue."""
        return await self.consumer.register_handler(queue_name, handler)

    async def start_event_processing(self, queue_name: str) -> bool:
        """Start processing events from a queue."""
        return await self.consumer.start_consuming(queue_name)

    def get_health_status(self) -> Dict[str, Any]:
        """Get health status of RabbitMQ service."""
        return {
            "initialized": self.is_initialized,
            "producer": self.producer.get_statistics(),
            "consumer": self.consumer.get_statistics(),
            "aio_pika_available": AIO_PIKA_AVAILABLE
        }

# Example event handlers
async def handle_query_event(message: QueueMessage) -> bool:
    """Handle query events."""
    try:
        logger.info(f"Processing query event: {message.id}")
        query_data = message.body

        # Process the query event
        query_id = query_data.get('query_id')
        user_id = query_data.get('user_id')
        query_text = query_data.get('query_text')

        logger.info(f"Query {query_id} from user {user_id}: {query_text}")

        # Simulate processing
        await asyncio.sleep(0.1)

        return True

    except Exception as e:
        logger.error(f"Error processing query event: {e}")
        return False

async def handle_alert_event(message: QueueMessage) -> bool:
    """Handle alert events."""
    try:
        logger.warning(f"Processing alert event: {message.id}")
        alert_data = message.body

        # Process alert
        alert_type = alert_data.get('type')
        severity = alert_data.get('severity')
        description = alert_data.get('description')

        logger.warning(f"Alert: {alert_type} - {severity} - {description}")

        # Simulate processing
        await asyncio.sleep(0.05)

        return True

    except Exception as e:
        logger.error(f"Error processing alert event: {e}")
        return False

# Global RabbitMQ service instance
rabbitmq_service: Optional[RabbitMQService] = None

def get_rabbitmq_service() -> Optional[RabbitMQService]:
    """Get global RabbitMQ service instance."""
    return rabbitmq_service

async def initialize_rabbitmq_service(config: RabbitMQConfig) -> bool:
    """Initialize global RabbitMQ service."""
    global rabbitmq_service

    rabbitmq_service = RabbitMQService(config)
    success = await rabbitmq_service.initialize()

    if success:
        # Register default handlers
        await rabbitmq_service.register_event_handler("bi.queries", handle_query_event)
        await rabbitmq_service.register_event_handler("bi.alerts", handle_alert_event)

        # Start processing
        await rabbitmq_service.start_event_processing("bi.queries")
        await rabbitmq_service.start_event_processing("bi.alerts")

    return success