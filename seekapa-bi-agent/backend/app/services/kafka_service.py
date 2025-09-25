"""
Apache Kafka Integration Service for event streaming in Seekapa BI Agent.
Provides robust Kafka producer/consumer implementation with error handling,
retry logic, and monitoring capabilities.
"""

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Any, Callable, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
import uuid

try:
    from kafka import KafkaProducer, KafkaConsumer
    from kafka.errors import (
        KafkaError, KafkaTimeoutError, KafkaConnectionError,
        NoBrokersAvailable, TopicAuthorizationFailedError
    )
    from kafka.admin import KafkaAdminClient, NewTopic
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False
    # Mock classes for when Kafka is not available
    class KafkaProducer:
        def __init__(self, **kwargs): pass
        def send(self, *args, **kwargs): pass
        def flush(self): pass
        def close(self): pass

    class KafkaConsumer:
        def __init__(self, *args, **kwargs): pass
        def subscribe(self, topics): pass
        def poll(self, timeout_ms): return {}
        def close(self): pass

    class KafkaAdminClient:
        def __init__(self, **kwargs): pass
        def create_topics(self, topics): pass

    class NewTopic:
        def __init__(self, name, num_partitions, replication_factor): pass

    KafkaError = Exception
    KafkaTimeoutError = Exception
    KafkaConnectionError = Exception
    NoBrokersAvailable = Exception
    TopicAuthorizationFailedError = Exception

logger = logging.getLogger(__name__)

class MessageStatus(Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    RETRYING = "retrying"

@dataclass
class KafkaMessage:
    """Kafka message structure with metadata."""
    id: str
    topic: str
    key: Optional[str]
    value: Any
    headers: Dict[str, str] = None
    timestamp: float = None
    partition: Optional[int] = None
    status: MessageStatus = MessageStatus.PENDING
    retry_count: int = 0
    max_retries: int = 3

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()
        if self.headers is None:
            self.headers = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "topic": self.topic,
            "key": self.key,
            "value": self.value,
            "headers": self.headers,
            "timestamp": self.timestamp,
            "partition": self.partition
        }

@dataclass
class KafkaConfig:
    """Kafka configuration settings."""
    bootstrap_servers: List[str]
    client_id: str = "seekapa-bi-agent"
    security_protocol: str = "PLAINTEXT"
    sasl_mechanism: Optional[str] = None
    sasl_username: Optional[str] = None
    sasl_password: Optional[str] = None
    ssl_cafile: Optional[str] = None
    ssl_certfile: Optional[str] = None
    ssl_keyfile: Optional[str] = None

    # Producer settings
    producer_batch_size: int = 16384
    producer_linger_ms: int = 10
    producer_buffer_memory: int = 33554432
    producer_compression_type: str = "gzip"
    producer_retries: int = 5
    producer_acks: str = "all"

    # Consumer settings
    consumer_group_id: str = "seekapa-consumers"
    consumer_auto_offset_reset: str = "earliest"
    consumer_enable_auto_commit: bool = False
    consumer_max_poll_records: int = 500
    consumer_session_timeout_ms: int = 30000
    consumer_heartbeat_interval_ms: int = 3000

class KafkaProducerService:
    """High-level Kafka producer service with retry logic and monitoring."""

    def __init__(self, config: KafkaConfig):
        self.config = config
        self.producer: Optional[KafkaProducer] = None
        self.is_connected = False
        self.pending_messages: Dict[str, KafkaMessage] = {}
        self.failed_messages: Dict[str, KafkaMessage] = {}
        self.statistics = {
            "messages_sent": 0,
            "messages_failed": 0,
            "messages_retried": 0,
            "connection_errors": 0,
            "last_error": None,
            "uptime_start": datetime.utcnow()
        }
        self._retry_task: Optional[asyncio.Task] = None

    async def connect(self) -> bool:
        """Connect to Kafka brokers."""
        if not KAFKA_AVAILABLE:
            logger.error("Kafka libraries not available. Install kafka-python package.")
            return False

        try:
            producer_config = {
                'bootstrap_servers': self.config.bootstrap_servers,
                'client_id': self.config.client_id,
                'security_protocol': self.config.security_protocol,
                'batch_size': self.config.producer_batch_size,
                'linger_ms': self.config.producer_linger_ms,
                'buffer_memory': self.config.producer_buffer_memory,
                'compression_type': self.config.producer_compression_type,
                'retries': self.config.producer_retries,
                'acks': self.config.producer_acks,
                'value_serializer': lambda v: json.dumps(v).encode('utf-8'),
                'key_serializer': lambda k: k.encode('utf-8') if k else None
            }

            # Add authentication if configured
            if self.config.sasl_mechanism:
                producer_config.update({
                    'sasl_mechanism': self.config.sasl_mechanism,
                    'sasl_plain_username': self.config.sasl_username,
                    'sasl_plain_password': self.config.sasl_password
                })

            # Add SSL configuration if provided
            if self.config.ssl_cafile:
                producer_config.update({
                    'ssl_cafile': self.config.ssl_cafile,
                    'ssl_certfile': self.config.ssl_certfile,
                    'ssl_keyfile': self.config.ssl_keyfile
                })

            self.producer = KafkaProducer(**producer_config)
            self.is_connected = True

            # Start retry task
            if not self._retry_task or self._retry_task.done():
                self._retry_task = asyncio.create_task(self._retry_failed_messages())

            logger.info("Kafka producer connected successfully")
            return True

        except Exception as e:
            self.statistics["connection_errors"] += 1
            self.statistics["last_error"] = str(e)
            logger.error(f"Failed to connect to Kafka: {e}")
            return False

    async def disconnect(self):
        """Disconnect from Kafka."""
        if self._retry_task:
            self._retry_task.cancel()

        if self.producer:
            self.producer.flush(timeout=5)
            self.producer.close(timeout=5)
            self.producer = None

        self.is_connected = False
        logger.info("Kafka producer disconnected")

    async def send_message(self, message: KafkaMessage) -> bool:
        """Send message to Kafka topic."""
        if not self.is_connected or not self.producer:
            logger.error("Kafka producer not connected")
            return False

        try:
            message.status = MessageStatus.PENDING
            self.pending_messages[message.id] = message

            # Prepare headers
            headers = [(k, v.encode('utf-8')) for k, v in message.headers.items()]

            # Send message
            future = self.producer.send(
                topic=message.topic,
                key=message.key,
                value=message.value,
                headers=headers,
                partition=message.partition
            )

            # Add callback for success/failure
            future.add_callback(self._on_send_success, message.id)
            future.add_errback(self._on_send_error, message.id)

            logger.debug(f"Message {message.id} sent to topic {message.topic}")
            return True

        except Exception as e:
            message.status = MessageStatus.FAILED
            self.failed_messages[message.id] = message
            self.statistics["messages_failed"] += 1
            self.statistics["last_error"] = str(e)
            logger.error(f"Error sending message {message.id}: {e}")
            return False

    def _on_send_success(self, record_metadata, message_id: str):
        """Callback for successful message send."""
        if message_id in self.pending_messages:
            message = self.pending_messages.pop(message_id)
            message.status = MessageStatus.SENT
            message.partition = record_metadata.partition
            self.statistics["messages_sent"] += 1
            logger.debug(f"Message {message_id} sent successfully to partition {record_metadata.partition}")

    def _on_send_error(self, exception, message_id: str):
        """Callback for failed message send."""
        if message_id in self.pending_messages:
            message = self.pending_messages.pop(message_id)
            message.status = MessageStatus.FAILED
            self.failed_messages[message_id] = message
            self.statistics["messages_failed"] += 1
            self.statistics["last_error"] = str(exception)
            logger.error(f"Failed to send message {message_id}: {exception}")

    async def _retry_failed_messages(self):
        """Retry failed messages with exponential backoff."""
        while self.is_connected:
            try:
                if self.failed_messages:
                    retry_messages = list(self.failed_messages.values())

                    for message in retry_messages:
                        if message.retry_count < message.max_retries:
                            message.retry_count += 1
                            message.status = MessageStatus.RETRYING

                            # Remove from failed messages
                            self.failed_messages.pop(message.id, None)

                            # Retry sending
                            success = await self.send_message(message)
                            if success:
                                self.statistics["messages_retried"] += 1

                            # Wait between retries
                            await asyncio.sleep(min(2 ** message.retry_count, 30))
                        else:
                            logger.error(f"Message {message.id} exceeded max retries")
                            self.failed_messages.pop(message.id, None)

                await asyncio.sleep(10)  # Check for failed messages every 10 seconds

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in retry task: {e}")
                await asyncio.sleep(10)

    async def send_batch(self, messages: List[KafkaMessage]) -> Dict[str, bool]:
        """Send multiple messages in batch."""
        results = {}

        for message in messages:
            results[message.id] = await self.send_message(message)

        # Flush to ensure all messages are sent
        if self.producer:
            self.producer.flush(timeout=10)

        return results

    def get_statistics(self) -> Dict[str, Any]:
        """Get producer statistics."""
        uptime = (datetime.utcnow() - self.statistics["uptime_start"]).total_seconds()

        return {
            **self.statistics,
            "pending_messages": len(self.pending_messages),
            "failed_messages": len(self.failed_messages),
            "is_connected": self.is_connected,
            "uptime_seconds": uptime
        }

class KafkaConsumerService:
    """High-level Kafka consumer service with automatic offset management."""

    def __init__(self, config: KafkaConfig):
        self.config = config
        self.consumer: Optional[KafkaConsumer] = None
        self.is_connected = False
        self.subscribed_topics: Set[str] = set()
        self.message_handlers: Dict[str, Callable] = {}
        self.statistics = {
            "messages_consumed": 0,
            "messages_processed": 0,
            "messages_failed": 0,
            "connection_errors": 0,
            "last_error": None,
            "uptime_start": datetime.utcnow()
        }
        self._consumer_task: Optional[asyncio.Task] = None

    async def connect(self) -> bool:
        """Connect to Kafka brokers."""
        if not KAFKA_AVAILABLE:
            logger.error("Kafka libraries not available. Install kafka-python package.")
            return False

        try:
            consumer_config = {
                'bootstrap_servers': self.config.bootstrap_servers,
                'client_id': self.config.client_id,
                'group_id': self.config.consumer_group_id,
                'security_protocol': self.config.security_protocol,
                'auto_offset_reset': self.config.consumer_auto_offset_reset,
                'enable_auto_commit': self.config.consumer_enable_auto_commit,
                'max_poll_records': self.config.consumer_max_poll_records,
                'session_timeout_ms': self.config.consumer_session_timeout_ms,
                'heartbeat_interval_ms': self.config.consumer_heartbeat_interval_ms,
                'value_deserializer': lambda m: json.loads(m.decode('utf-8')),
                'key_deserializer': lambda k: k.decode('utf-8') if k else None
            }

            # Add authentication if configured
            if self.config.sasl_mechanism:
                consumer_config.update({
                    'sasl_mechanism': self.config.sasl_mechanism,
                    'sasl_plain_username': self.config.sasl_username,
                    'sasl_plain_password': self.config.sasl_password
                })

            self.consumer = KafkaConsumer(**consumer_config)
            self.is_connected = True

            # Start consumer task
            if not self._consumer_task or self._consumer_task.done():
                self._consumer_task = asyncio.create_task(self._consume_messages())

            logger.info("Kafka consumer connected successfully")
            return True

        except Exception as e:
            self.statistics["connection_errors"] += 1
            self.statistics["last_error"] = str(e)
            logger.error(f"Failed to connect to Kafka consumer: {e}")
            return False

    async def disconnect(self):
        """Disconnect from Kafka."""
        if self._consumer_task:
            self._consumer_task.cancel()

        if self.consumer:
            self.consumer.close()
            self.consumer = None

        self.is_connected = False
        logger.info("Kafka consumer disconnected")

    async def subscribe_to_topic(self, topic: str, handler: Callable):
        """Subscribe to a Kafka topic with message handler."""
        if not self.is_connected:
            logger.error("Kafka consumer not connected")
            return False

        try:
            self.subscribed_topics.add(topic)
            self.message_handlers[topic] = handler

            # Subscribe consumer to all topics
            self.consumer.subscribe(list(self.subscribed_topics))

            logger.info(f"Subscribed to topic: {topic}")
            return True

        except Exception as e:
            logger.error(f"Error subscribing to topic {topic}: {e}")
            return False

    async def unsubscribe_from_topic(self, topic: str):
        """Unsubscribe from a Kafka topic."""
        if topic in self.subscribed_topics:
            self.subscribed_topics.remove(topic)
            self.message_handlers.pop(topic, None)

            if self.subscribed_topics:
                self.consumer.subscribe(list(self.subscribed_topics))
            else:
                self.consumer.unsubscribe()

            logger.info(f"Unsubscribed from topic: {topic}")

    async def _consume_messages(self):
        """Main consumer loop."""
        while self.is_connected and self.consumer:
            try:
                # Poll for messages
                message_batch = self.consumer.poll(timeout_ms=1000)

                for topic_partition, messages in message_batch.items():
                    topic = topic_partition.topic

                    for message in messages:
                        self.statistics["messages_consumed"] += 1

                        try:
                            # Process message with appropriate handler
                            if topic in self.message_handlers:
                                await self.message_handlers[topic](
                                    topic=topic,
                                    key=message.key,
                                    value=message.value,
                                    partition=message.partition,
                                    offset=message.offset,
                                    timestamp=message.timestamp,
                                    headers=dict(message.headers) if message.headers else {}
                                )
                                self.statistics["messages_processed"] += 1
                            else:
                                logger.warning(f"No handler for topic: {topic}")

                        except Exception as e:
                            self.statistics["messages_failed"] += 1
                            logger.error(f"Error processing message from topic {topic}: {e}")

                # Manually commit offsets if auto-commit is disabled
                if not self.config.consumer_enable_auto_commit:
                    self.consumer.commit()

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.statistics["connection_errors"] += 1
                self.statistics["last_error"] = str(e)
                logger.error(f"Error in consumer loop: {e}")
                await asyncio.sleep(5)  # Wait before retrying

    def get_statistics(self) -> Dict[str, Any]:
        """Get consumer statistics."""
        uptime = (datetime.utcnow() - self.statistics["uptime_start"]).total_seconds()

        return {
            **self.statistics,
            "subscribed_topics": list(self.subscribed_topics),
            "is_connected": self.is_connected,
            "uptime_seconds": uptime
        }

class KafkaService:
    """Main Kafka service combining producer and consumer functionality."""

    def __init__(self, config: KafkaConfig):
        self.config = config
        self.producer = KafkaProducerService(config)
        self.consumer = KafkaConsumerService(config)
        self.admin_client: Optional[KafkaAdminClient] = None
        self.is_initialized = False

    async def initialize(self) -> bool:
        """Initialize Kafka service."""
        try:
            # Connect producer and consumer
            producer_connected = await self.producer.connect()
            consumer_connected = await self.consumer.connect()

            # Initialize admin client for topic management
            if KAFKA_AVAILABLE:
                admin_config = {
                    'bootstrap_servers': self.config.bootstrap_servers,
                    'client_id': self.config.client_id,
                    'security_protocol': self.config.security_protocol
                }

                if self.config.sasl_mechanism:
                    admin_config.update({
                        'sasl_mechanism': self.config.sasl_mechanism,
                        'sasl_plain_username': self.config.sasl_username,
                        'sasl_plain_password': self.config.sasl_password
                    })

                self.admin_client = KafkaAdminClient(**admin_config)

            self.is_initialized = producer_connected and consumer_connected

            if self.is_initialized:
                logger.info("Kafka service initialized successfully")
            else:
                logger.error("Failed to initialize Kafka service")

            return self.is_initialized

        except Exception as e:
            logger.error(f"Error initializing Kafka service: {e}")
            return False

    async def shutdown(self):
        """Shutdown Kafka service."""
        await self.producer.disconnect()
        await self.consumer.disconnect()

        if self.admin_client:
            self.admin_client.close()
            self.admin_client = None

        self.is_initialized = False
        logger.info("Kafka service shut down")

    async def create_topic(self, topic_name: str, num_partitions: int = 3, replication_factor: int = 1) -> bool:
        """Create a new Kafka topic."""
        if not self.admin_client or not KAFKA_AVAILABLE:
            logger.error("Admin client not available")
            return False

        try:
            topic = NewTopic(
                name=topic_name,
                num_partitions=num_partitions,
                replication_factor=replication_factor
            )

            self.admin_client.create_topics([topic])
            logger.info(f"Topic '{topic_name}' created successfully")
            return True

        except Exception as e:
            logger.error(f"Error creating topic '{topic_name}': {e}")
            return False

    async def send_event(self, topic: str, event_data: Dict[str, Any], key: Optional[str] = None) -> bool:
        """Send event to Kafka topic."""
        message = KafkaMessage(
            id=str(uuid.uuid4()),
            topic=topic,
            key=key,
            value=event_data,
            headers={
                "source": "seekapa-bi-agent",
                "timestamp": str(int(time.time()))
            }
        )

        return await self.producer.send_message(message)

    async def subscribe_to_events(self, topic: str, handler: Callable) -> bool:
        """Subscribe to events from Kafka topic."""
        return await self.consumer.subscribe_to_topic(topic, handler)

    def get_health_status(self) -> Dict[str, Any]:
        """Get health status of Kafka service."""
        return {
            "initialized": self.is_initialized,
            "producer": self.producer.get_statistics(),
            "consumer": self.consumer.get_statistics(),
            "kafka_available": KAFKA_AVAILABLE
        }

# Example event handlers
async def handle_bi_query_event(topic: str, key: Optional[str], value: Dict[str, Any], **kwargs):
    """Handle BI query events."""
    logger.info(f"Processing BI query event: {value}")

    # Process the query event
    query_id = value.get('query_id')
    user_id = value.get('user_id')
    query_text = value.get('query_text')

    logger.info(f"Query {query_id} from user {user_id}: {query_text}")

async def handle_data_update_event(topic: str, key: Optional[str], value: Dict[str, Any], **kwargs):
    """Handle data update events."""
    logger.info(f"Processing data update event: {value}")

    # Trigger real-time updates to connected clients
    dataset = value.get('dataset')
    update_type = value.get('type')

    logger.info(f"Data update for dataset {dataset}: {update_type}")

# Global Kafka service instance (to be initialized with config)
kafka_service: Optional[KafkaService] = None

def get_kafka_service() -> Optional[KafkaService]:
    """Get global Kafka service instance."""
    return kafka_service

async def initialize_kafka_service(config: KafkaConfig) -> bool:
    """Initialize global Kafka service."""
    global kafka_service

    kafka_service = KafkaService(config)
    return await kafka_service.initialize()