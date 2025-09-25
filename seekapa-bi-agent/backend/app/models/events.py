"""
Event models for event sourcing and CQRS pattern implementation.
These models represent events that occur in the system and are used
for audit trails and data consistency.
"""

import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict
from enum import Enum
from sqlalchemy import Column, String, DateTime, JSON, Integer, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class EventType(Enum):
    # User events
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    USER_DELETED = "user_deleted"
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"

    # Query events
    QUERY_EXECUTED = "query_executed"
    QUERY_FAILED = "query_failed"
    QUERY_OPTIMIZED = "query_optimized"

    # Data events
    DATA_UPDATED = "data_updated"
    DATA_IMPORTED = "data_imported"
    DATA_EXPORTED = "data_exported"
    DATA_DELETED = "data_deleted"

    # Report events
    REPORT_CREATED = "report_created"
    REPORT_UPDATED = "report_updated"
    REPORT_SHARED = "report_shared"
    REPORT_DELETED = "report_deleted"

    # System events
    SYSTEM_STARTED = "system_started"
    SYSTEM_STOPPED = "system_stopped"
    ERROR_OCCURRED = "error_occurred"
    PERFORMANCE_ALERT = "performance_alert"

    # Real-time streaming events
    STREAM_STARTED = "stream_started"
    STREAM_STOPPED = "stream_stopped"
    MESSAGE_SENT = "message_sent"
    CONNECTION_ESTABLISHED = "connection_established"
    CONNECTION_LOST = "connection_lost"

@dataclass
class BaseEvent:
    """Base event structure for all domain events."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: EventType = None
    aggregate_id: str = None  # ID of the entity this event relates to
    aggregate_type: str = None  # Type of aggregate (User, Query, Report, etc.)
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    version: int = 1
    data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary."""
        result = asdict(self)
        result['event_type'] = self.event_type.value if self.event_type else None
        result['timestamp'] = self.timestamp.isoformat()
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BaseEvent':
        """Create event from dictionary."""
        data = data.copy()
        if 'event_type' in data and isinstance(data['event_type'], str):
            data['event_type'] = EventType(data['event_type'])
        if 'timestamp' in data and isinstance(data['timestamp'], str):
            data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)

# Specific event types

@dataclass
class UserEvent(BaseEvent):
    """User-related events."""
    aggregate_type: str = field(default="User", init=False)

@dataclass
class QueryEvent(BaseEvent):
    """Query-related events."""
    aggregate_type: str = field(default="Query", init=False)
    execution_time: Optional[int] = None  # milliseconds
    row_count: Optional[int] = None
    query_text: Optional[str] = None

@dataclass
class DataEvent(BaseEvent):
    """Data-related events."""
    aggregate_type: str = field(default="Data", init=False)
    dataset_id: Optional[str] = None
    table_name: Optional[str] = None
    row_count: Optional[int] = None
    operation_type: Optional[str] = None

@dataclass
class ReportEvent(BaseEvent):
    """Report-related events."""
    aggregate_type: str = field(default="Report", init=False)
    report_id: Optional[str] = None
    report_title: Optional[str] = None

@dataclass
class StreamEvent(BaseEvent):
    """Streaming-related events."""
    aggregate_type: str = field(default="Stream", init=False)
    connection_id: Optional[str] = None
    topic: Optional[str] = None
    message_count: Optional[int] = None

# SQLAlchemy models for persistence

class EventStore(Base):
    """SQLAlchemy model for storing events."""
    __tablename__ = 'event_store'

    id = Column(String, primary_key=True)
    event_type = Column(String, nullable=False, index=True)
    aggregate_id = Column(String, nullable=True, index=True)
    aggregate_type = Column(String, nullable=True, index=True)
    user_id = Column(String, nullable=True, index=True)
    session_id = Column(String, nullable=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    data = Column(JSON, nullable=True)
    metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_event(self) -> BaseEvent:
        """Convert to domain event."""
        return BaseEvent(
            id=self.id,
            event_type=EventType(self.event_type),
            aggregate_id=self.aggregate_id,
            aggregate_type=self.aggregate_type,
            user_id=self.user_id,
            session_id=self.session_id,
            timestamp=self.timestamp,
            version=self.version,
            data=self.data or {},
            metadata=self.metadata or {}
        )

    @classmethod
    def from_event(cls, event: BaseEvent) -> 'EventStore':
        """Create from domain event."""
        return cls(
            id=event.id,
            event_type=event.event_type.value,
            aggregate_id=event.aggregate_id,
            aggregate_type=event.aggregate_type,
            user_id=event.user_id,
            session_id=event.session_id,
            timestamp=event.timestamp,
            version=event.version,
            data=event.data,
            metadata=event.metadata
        )

class EventSnapshot(Base):
    """Snapshots for aggregate state reconstruction optimization."""
    __tablename__ = 'event_snapshots'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    aggregate_id = Column(String, nullable=False, index=True)
    aggregate_type = Column(String, nullable=False, index=True)
    version = Column(Integer, nullable=False)
    data = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

# Read models for CQRS pattern

class QueryReadModel(Base):
    """Optimized read model for queries."""
    __tablename__ = 'query_read_model'

    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    query_text = Column(Text, nullable=False)
    query_hash = Column(String, nullable=False, index=True)  # For deduplication
    execution_count = Column(Integer, default=1)
    total_execution_time = Column(Integer, default=0)  # Total milliseconds
    average_execution_time = Column(Integer, default=0)  # Average milliseconds
    last_executed = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Performance metrics
    min_execution_time = Column(Integer, default=0)
    max_execution_time = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    failure_count = Column(Integer, default=0)

class UserActivityReadModel(Base):
    """Optimized read model for user activity analytics."""
    __tablename__ = 'user_activity_read_model'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, index=True)
    date = Column(DateTime, nullable=False, index=True)  # Daily aggregation
    query_count = Column(Integer, default=0)
    report_count = Column(Integer, default=0)
    session_duration = Column(Integer, default=0)  # Total seconds
    login_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ReportMetricsReadModel(Base):
    """Optimized read model for report metrics."""
    __tablename__ = 'report_metrics_read_model'

    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False)
    view_count = Column(Integer, default=0)
    share_count = Column(Integer, default=0)
    last_viewed = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Engagement metrics
    unique_viewers = Column(Integer, default=0)
    average_view_duration = Column(Integer, default=0)  # seconds
    download_count = Column(Integer, default=0)

class SystemMetricsReadModel(Base):
    """System-wide metrics read model."""
    __tablename__ = 'system_metrics_read_model'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    metric_date = Column(DateTime, nullable=False, index=True)
    active_users = Column(Integer, default=0)
    total_queries = Column(Integer, default=0)
    total_reports = Column(Integer, default=0)
    average_response_time = Column(Integer, default=0)  # milliseconds
    error_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Resource utilization
    cpu_usage_percent = Column(Integer, default=0)
    memory_usage_percent = Column(Integer, default=0)
    disk_usage_percent = Column(Integer, default=0)
    active_connections = Column(Integer, default=0)

# Factory functions for creating events

def create_user_event(event_type: EventType, user_id: str, data: Dict[str, Any] = None,
                     session_id: str = None) -> UserEvent:
    """Create a user event."""
    return UserEvent(
        event_type=event_type,
        aggregate_id=user_id,
        user_id=user_id,
        session_id=session_id,
        data=data or {}
    )

def create_query_event(event_type: EventType, query_id: str, user_id: str,
                      query_text: str = None, execution_time: int = None,
                      row_count: int = None, data: Dict[str, Any] = None,
                      session_id: str = None) -> QueryEvent:
    """Create a query event."""
    return QueryEvent(
        event_type=event_type,
        aggregate_id=query_id,
        user_id=user_id,
        session_id=session_id,
        execution_time=execution_time,
        row_count=row_count,
        query_text=query_text,
        data=data or {}
    )

def create_data_event(event_type: EventType, dataset_id: str, user_id: str,
                     table_name: str = None, row_count: int = None,
                     operation_type: str = None, data: Dict[str, Any] = None,
                     session_id: str = None) -> DataEvent:
    """Create a data event."""
    return DataEvent(
        event_type=event_type,
        aggregate_id=dataset_id,
        user_id=user_id,
        session_id=session_id,
        dataset_id=dataset_id,
        table_name=table_name,
        row_count=row_count,
        operation_type=operation_type,
        data=data or {}
    )

def create_report_event(event_type: EventType, report_id: str, user_id: str,
                       report_title: str = None, data: Dict[str, Any] = None,
                       session_id: str = None) -> ReportEvent:
    """Create a report event."""
    return ReportEvent(
        event_type=event_type,
        aggregate_id=report_id,
        user_id=user_id,
        session_id=session_id,
        report_id=report_id,
        report_title=report_title,
        data=data or {}
    )

def create_stream_event(event_type: EventType, connection_id: str, user_id: str = None,
                       topic: str = None, message_count: int = None,
                       data: Dict[str, Any] = None, session_id: str = None) -> StreamEvent:
    """Create a stream event."""
    return StreamEvent(
        event_type=event_type,
        aggregate_id=connection_id,
        user_id=user_id,
        session_id=session_id,
        connection_id=connection_id,
        topic=topic,
        message_count=message_count,
        data=data or {}
    )