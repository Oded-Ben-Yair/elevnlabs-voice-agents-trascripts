"""
Event Sourcing Service for Seekapa BI Agent.
Implements complete event sourcing pattern with event store,
snapshots, and aggregate reconstruction for audit trails and data consistency.
"""

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Type, TypeVar, Generic, Union
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import uuid
import pickle
import hashlib
from collections import defaultdict
import threading

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc, asc, func
from sqlalchemy.exc import SQLAlchemyError

from ..models.events import (
    BaseEvent, EventType, EventStore, EventSnapshot,
    create_user_event, create_query_event, create_data_event, create_report_event, create_stream_event
)

logger = logging.getLogger(__name__)

# Type variables for generic aggregate handling
T = TypeVar('T', bound='AggregateRoot')

class AggregateRoot(ABC):
    """Base class for all aggregates in the system."""

    def __init__(self, aggregate_id: str = None):
        self.aggregate_id = aggregate_id or str(uuid.uuid4())
        self.version = 0
        self.uncommitted_events: List[BaseEvent] = []
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    @abstractmethod
    def apply_event(self, event: BaseEvent) -> None:
        """Apply an event to the aggregate."""
        pass

    def add_event(self, event: BaseEvent) -> None:
        """Add an event to uncommitted events."""
        event.aggregate_id = self.aggregate_id
        event.version = self.version + len(self.uncommitted_events) + 1
        self.uncommitted_events.append(event)

    def mark_events_as_committed(self) -> None:
        """Mark all uncommitted events as committed."""
        self.version += len(self.uncommitted_events)
        self.uncommitted_events.clear()
        self.updated_at = datetime.utcnow()

    def load_from_history(self, events: List[BaseEvent]) -> None:
        """Load aggregate state from event history."""
        for event in sorted(events, key=lambda e: e.version):
            self.apply_event(event)
            self.version = max(self.version, event.version)

    def get_state_snapshot(self) -> Dict[str, Any]:
        """Get current state snapshot for persistence."""
        return {
            "aggregate_id": self.aggregate_id,
            "aggregate_type": self.__class__.__name__,
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "data": self._serialize_state()
        }

    @abstractmethod
    def _serialize_state(self) -> Dict[str, Any]:
        """Serialize aggregate state for snapshots."""
        pass

    @abstractmethod
    def _deserialize_state(self, data: Dict[str, Any]) -> None:
        """Deserialize aggregate state from snapshots."""
        pass

    def load_from_snapshot(self, snapshot_data: Dict[str, Any]) -> None:
        """Load aggregate from snapshot."""
        self.aggregate_id = snapshot_data["aggregate_id"]
        self.version = snapshot_data["version"]
        self.created_at = datetime.fromisoformat(snapshot_data["created_at"])
        self.updated_at = datetime.fromisoformat(snapshot_data["updated_at"])
        self._deserialize_state(snapshot_data["data"])

# Specific aggregate implementations

class UserAggregate(AggregateRoot):
    """User aggregate for event sourcing."""

    def __init__(self, aggregate_id: str = None):
        super().__init__(aggregate_id)
        self.username: Optional[str] = None
        self.email: Optional[str] = None
        self.hashed_password: Optional[str] = None
        self.is_active: bool = True
        self.last_login: Optional[datetime] = None
        self.login_count: int = 0

    def create_user(self, username: str, email: str, hashed_password: str, user_id: str = None) -> None:
        """Create a new user."""
        event = create_user_event(
            EventType.USER_CREATED,
            user_id=user_id or self.aggregate_id,
            data={
                "username": username,
                "email": email,
                "hashed_password": hashed_password
            }
        )
        self.add_event(event)

    def update_user(self, updates: Dict[str, Any], user_id: str = None) -> None:
        """Update user information."""
        event = create_user_event(
            EventType.USER_UPDATED,
            user_id=user_id or self.aggregate_id,
            data=updates
        )
        self.add_event(event)

    def user_login(self, user_id: str = None, session_id: str = None) -> None:
        """Record user login."""
        event = create_user_event(
            EventType.USER_LOGIN,
            user_id=user_id or self.aggregate_id,
            session_id=session_id,
            data={"login_time": datetime.utcnow().isoformat()}
        )
        self.add_event(event)

    def user_logout(self, user_id: str = None, session_id: str = None) -> None:
        """Record user logout."""
        event = create_user_event(
            EventType.USER_LOGOUT,
            user_id=user_id or self.aggregate_id,
            session_id=session_id,
            data={"logout_time": datetime.utcnow().isoformat()}
        )
        self.add_event(event)

    def apply_event(self, event: BaseEvent) -> None:
        """Apply event to user aggregate."""
        if event.event_type == EventType.USER_CREATED:
            self.username = event.data.get("username")
            self.email = event.data.get("email")
            self.hashed_password = event.data.get("hashed_password")
            self.is_active = event.data.get("is_active", True)
        elif event.event_type == EventType.USER_UPDATED:
            for key, value in event.data.items():
                if hasattr(self, key):
                    setattr(self, key, value)
        elif event.event_type == EventType.USER_LOGIN:
            self.last_login = datetime.fromisoformat(event.data.get("login_time", event.timestamp.isoformat()))
            self.login_count += 1
        elif event.event_type == EventType.USER_LOGOUT:
            pass  # Logout doesn't change persistent state

    def _serialize_state(self) -> Dict[str, Any]:
        return {
            "username": self.username,
            "email": self.email,
            "hashed_password": self.hashed_password,
            "is_active": self.is_active,
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "login_count": self.login_count
        }

    def _deserialize_state(self, data: Dict[str, Any]) -> None:
        self.username = data.get("username")
        self.email = data.get("email")
        self.hashed_password = data.get("hashed_password")
        self.is_active = data.get("is_active", True)
        self.last_login = datetime.fromisoformat(data["last_login"]) if data.get("last_login") else None
        self.login_count = data.get("login_count", 0)

class QueryAggregate(AggregateRoot):
    """Query aggregate for event sourcing."""

    def __init__(self, aggregate_id: str = None):
        super().__init__(aggregate_id)
        self.user_id: Optional[str] = None
        self.query_text: Optional[str] = None
        self.execution_count: int = 0
        self.total_execution_time: int = 0
        self.success_count: int = 0
        self.failure_count: int = 0
        self.last_executed: Optional[datetime] = None

    def execute_query(self, user_id: str, query_text: str, execution_time: int,
                     success: bool = True, result_count: int = None) -> None:
        """Record query execution."""
        event_type = EventType.QUERY_EXECUTED if success else EventType.QUERY_FAILED

        event = create_query_event(
            event_type,
            query_id=self.aggregate_id,
            user_id=user_id,
            query_text=query_text,
            execution_time=execution_time,
            row_count=result_count,
            data={
                "success": success,
                "result_count": result_count
            }
        )
        self.add_event(event)

    def optimize_query(self, optimization_details: Dict[str, Any]) -> None:
        """Record query optimization."""
        event = create_query_event(
            EventType.QUERY_OPTIMIZED,
            query_id=self.aggregate_id,
            user_id=self.user_id,
            data=optimization_details
        )
        self.add_event(event)

    def apply_event(self, event: BaseEvent) -> None:
        """Apply event to query aggregate."""
        if event.event_type == EventType.QUERY_EXECUTED:
            if not self.user_id:
                self.user_id = event.user_id
                self.query_text = event.query_text

            self.execution_count += 1
            self.total_execution_time += event.execution_time or 0
            self.success_count += 1
            self.last_executed = event.timestamp

        elif event.event_type == EventType.QUERY_FAILED:
            if not self.user_id:
                self.user_id = event.user_id
                self.query_text = event.query_text

            self.execution_count += 1
            self.total_execution_time += event.execution_time or 0
            self.failure_count += 1
            self.last_executed = event.timestamp

        elif event.event_type == EventType.QUERY_OPTIMIZED:
            pass  # Optimization events don't change basic metrics

    def _serialize_state(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "query_text": self.query_text,
            "execution_count": self.execution_count,
            "total_execution_time": self.total_execution_time,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "last_executed": self.last_executed.isoformat() if self.last_executed else None
        }

    def _deserialize_state(self, data: Dict[str, Any]) -> None:
        self.user_id = data.get("user_id")
        self.query_text = data.get("query_text")
        self.execution_count = data.get("execution_count", 0)
        self.total_execution_time = data.get("total_execution_time", 0)
        self.success_count = data.get("success_count", 0)
        self.failure_count = data.get("failure_count", 0)
        self.last_executed = datetime.fromisoformat(data["last_executed"]) if data.get("last_executed") else None

class ReportAggregate(AggregateRoot):
    """Report aggregate for event sourcing."""

    def __init__(self, aggregate_id: str = None):
        super().__init__(aggregate_id)
        self.user_id: Optional[str] = None
        self.title: Optional[str] = None
        self.description: Optional[str] = None
        self.data: Dict[str, Any] = {}
        self.view_count: int = 0
        self.share_count: int = 0
        self.is_public: bool = False

    def create_report(self, user_id: str, title: str, description: str = None, data: Dict[str, Any] = None) -> None:
        """Create a new report."""
        event = create_report_event(
            EventType.REPORT_CREATED,
            report_id=self.aggregate_id,
            user_id=user_id,
            report_title=title,
            data={
                "description": description,
                "report_data": data or {},
                "is_public": False
            }
        )
        self.add_event(event)

    def update_report(self, updates: Dict[str, Any]) -> None:
        """Update report information."""
        event = create_report_event(
            EventType.REPORT_UPDATED,
            report_id=self.aggregate_id,
            user_id=self.user_id,
            data=updates
        )
        self.add_event(event)

    def share_report(self, shared_with: List[str] = None) -> None:
        """Share report with users."""
        event = create_report_event(
            EventType.REPORT_SHARED,
            report_id=self.aggregate_id,
            user_id=self.user_id,
            data={
                "shared_with": shared_with or [],
                "shared_at": datetime.utcnow().isoformat()
            }
        )
        self.add_event(event)

    def apply_event(self, event: BaseEvent) -> None:
        """Apply event to report aggregate."""
        if event.event_type == EventType.REPORT_CREATED:
            self.user_id = event.user_id
            self.title = event.report_title
            self.description = event.data.get("description")
            self.data = event.data.get("report_data", {})
            self.is_public = event.data.get("is_public", False)

        elif event.event_type == EventType.REPORT_UPDATED:
            for key, value in event.data.items():
                if key == "title":
                    self.title = value
                elif key == "description":
                    self.description = value
                elif key == "data":
                    self.data.update(value)
                elif key == "is_public":
                    self.is_public = value

        elif event.event_type == EventType.REPORT_SHARED:
            self.share_count += 1

    def _serialize_state(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "title": self.title,
            "description": self.description,
            "data": self.data,
            "view_count": self.view_count,
            "share_count": self.share_count,
            "is_public": self.is_public
        }

    def _deserialize_state(self, data: Dict[str, Any]) -> None:
        self.user_id = data.get("user_id")
        self.title = data.get("title")
        self.description = data.get("description")
        self.data = data.get("data", {})
        self.view_count = data.get("view_count", 0)
        self.share_count = data.get("share_count", 0)
        self.is_public = data.get("is_public", False)

# Event store implementation

class EventStoreRepository:
    """Repository for event store operations."""

    def __init__(self, session: Session):
        self.session = session

    async def save_events(self, aggregate_id: str, events: List[BaseEvent],
                         expected_version: int = None) -> bool:
        """Save events to the event store."""
        try:
            # Check for concurrency conflicts if expected version provided
            if expected_version is not None:
                latest_version = await self.get_latest_version(aggregate_id, events[0].aggregate_type)
                if latest_version != expected_version:
                    raise ConcurrencyException(
                        f"Expected version {expected_version}, but latest is {latest_version}"
                    )

            # Save all events
            for event in events:
                event_record = EventStore.from_event(event)
                self.session.add(event_record)

            self.session.commit()
            logger.debug(f"Saved {len(events)} events for aggregate {aggregate_id}")
            return True

        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error saving events: {e}")
            return False

    async def get_events(self, aggregate_id: str, aggregate_type: str,
                        from_version: int = 0) -> List[BaseEvent]:
        """Get events for an aggregate."""
        try:
            query = self.session.query(EventStore).filter(
                and_(
                    EventStore.aggregate_id == aggregate_id,
                    EventStore.aggregate_type == aggregate_type,
                    EventStore.version > from_version
                )
            ).order_by(EventStore.version)

            event_records = query.all()
            return [record.to_event() for record in event_records]

        except SQLAlchemyError as e:
            logger.error(f"Error retrieving events: {e}")
            return []

    async def get_latest_version(self, aggregate_id: str, aggregate_type: str) -> int:
        """Get the latest version for an aggregate."""
        try:
            result = self.session.query(func.max(EventStore.version)).filter(
                and_(
                    EventStore.aggregate_id == aggregate_id,
                    EventStore.aggregate_type == aggregate_type
                )
            ).scalar()

            return result or 0

        except SQLAlchemyError as e:
            logger.error(f"Error getting latest version: {e}")
            return 0

    async def get_events_by_type(self, event_types: List[EventType],
                               start_time: datetime = None,
                               end_time: datetime = None,
                               limit: int = 1000) -> List[BaseEvent]:
        """Get events by type within time range."""
        try:
            query = self.session.query(EventStore)

            # Filter by event types
            if event_types:
                type_values = [et.value for et in event_types]
                query = query.filter(EventStore.event_type.in_(type_values))

            # Filter by time range
            if start_time:
                query = query.filter(EventStore.timestamp >= start_time)
            if end_time:
                query = query.filter(EventStore.timestamp <= end_time)

            # Order and limit
            query = query.order_by(desc(EventStore.timestamp)).limit(limit)

            event_records = query.all()
            return [record.to_event() for record in event_records]

        except SQLAlchemyError as e:
            logger.error(f"Error retrieving events by type: {e}")
            return []

class SnapshotRepository:
    """Repository for aggregate snapshots."""

    def __init__(self, session: Session):
        self.session = session

    async def save_snapshot(self, aggregate: AggregateRoot) -> bool:
        """Save aggregate snapshot."""
        try:
            snapshot_data = aggregate.get_state_snapshot()

            # Remove existing snapshot
            self.session.query(EventSnapshot).filter(
                and_(
                    EventSnapshot.aggregate_id == aggregate.aggregate_id,
                    EventSnapshot.aggregate_type == aggregate.__class__.__name__
                )
            ).delete()

            # Create new snapshot
            snapshot = EventSnapshot(
                aggregate_id=aggregate.aggregate_id,
                aggregate_type=aggregate.__class__.__name__,
                version=aggregate.version,
                data=snapshot_data
            )

            self.session.add(snapshot)
            self.session.commit()

            logger.debug(f"Saved snapshot for aggregate {aggregate.aggregate_id}")
            return True

        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error saving snapshot: {e}")
            return False

    async def get_snapshot(self, aggregate_id: str, aggregate_type: str) -> Optional[Dict[str, Any]]:
        """Get latest snapshot for an aggregate."""
        try:
            snapshot = self.session.query(EventSnapshot).filter(
                and_(
                    EventSnapshot.aggregate_id == aggregate_id,
                    EventSnapshot.aggregate_type == aggregate_type
                )
            ).order_by(desc(EventSnapshot.version)).first()

            if snapshot:
                return snapshot.data
            return None

        except SQLAlchemyError as e:
            logger.error(f"Error retrieving snapshot: {e}")
            return None

class AggregateRepository(Generic[T]):
    """Generic repository for aggregates with event sourcing."""

    def __init__(self, aggregate_class: Type[T], event_store: EventStoreRepository,
                 snapshot_store: SnapshotRepository, snapshot_frequency: int = 10):
        self.aggregate_class = aggregate_class
        self.event_store = event_store
        self.snapshot_store = snapshot_store
        self.snapshot_frequency = snapshot_frequency

    async def get_by_id(self, aggregate_id: str) -> Optional[T]:
        """Get aggregate by ID, reconstructing from events and snapshots."""
        try:
            aggregate_type = self.aggregate_class.__name__

            # Try to load from snapshot first
            snapshot_data = await self.snapshot_store.get_snapshot(aggregate_id, aggregate_type)

            if snapshot_data:
                # Load from snapshot
                aggregate = self.aggregate_class(aggregate_id)
                aggregate.load_from_snapshot(snapshot_data)

                # Load events since snapshot
                events = await self.event_store.get_events(
                    aggregate_id, aggregate_type, aggregate.version
                )

                if events:
                    aggregate.load_from_history(events)

                return aggregate
            else:
                # Load all events
                events = await self.event_store.get_events(aggregate_id, aggregate_type)

                if not events:
                    return None

                aggregate = self.aggregate_class(aggregate_id)
                aggregate.load_from_history(events)
                return aggregate

        except Exception as e:
            logger.error(f"Error loading aggregate {aggregate_id}: {e}")
            return None

    async def save(self, aggregate: T, expected_version: int = None) -> bool:
        """Save aggregate, storing uncommitted events."""
        try:
            if not aggregate.uncommitted_events:
                return True

            # Save events
            success = await self.event_store.save_events(
                aggregate.aggregate_id,
                aggregate.uncommitted_events,
                expected_version
            )

            if success:
                # Mark events as committed
                aggregate.mark_events_as_committed()

                # Save snapshot if frequency reached
                if aggregate.version % self.snapshot_frequency == 0:
                    await self.snapshot_store.save_snapshot(aggregate)

                return True

            return False

        except Exception as e:
            logger.error(f"Error saving aggregate {aggregate.aggregate_id}: {e}")
            return False

class ConcurrencyException(Exception):
    """Exception raised when concurrent modification is detected."""
    pass

class EventSourcingService:
    """Main service for event sourcing operations."""

    def __init__(self, session: Session):
        self.session = session
        self.event_store = EventStoreRepository(session)
        self.snapshot_store = SnapshotRepository(session)

        # Create repositories for different aggregates
        self.users = AggregateRepository(UserAggregate, self.event_store, self.snapshot_store)
        self.queries = AggregateRepository(QueryAggregate, self.event_store, self.snapshot_store)
        self.reports = AggregateRepository(ReportAggregate, self.event_store, self.snapshot_store)

        # Statistics
        self.statistics = {
            "events_saved": 0,
            "aggregates_loaded": 0,
            "snapshots_created": 0,
            "concurrency_conflicts": 0
        }

    async def get_user(self, user_id: str) -> Optional[UserAggregate]:
        """Get user aggregate by ID."""
        result = await self.users.get_by_id(user_id)
        if result:
            self.statistics["aggregates_loaded"] += 1
        return result

    async def save_user(self, user: UserAggregate) -> bool:
        """Save user aggregate."""
        success = await self.users.save(user)
        if success:
            self.statistics["events_saved"] += len(user.uncommitted_events)
        return success

    async def get_query(self, query_id: str) -> Optional[QueryAggregate]:
        """Get query aggregate by ID."""
        result = await self.queries.get_by_id(query_id)
        if result:
            self.statistics["aggregates_loaded"] += 1
        return result

    async def save_query(self, query: QueryAggregate) -> bool:
        """Save query aggregate."""
        success = await self.queries.save(query)
        if success:
            self.statistics["events_saved"] += len(query.uncommitted_events)
        return success

    async def get_report(self, report_id: str) -> Optional[ReportAggregate]:
        """Get report aggregate by ID."""
        result = await self.reports.get_by_id(report_id)
        if result:
            self.statistics["aggregates_loaded"] += 1
        return result

    async def save_report(self, report: ReportAggregate) -> bool:
        """Save report aggregate."""
        success = await self.reports.save(report)
        if success:
            self.statistics["events_saved"] += len(report.uncommitted_events)
        return success

    async def get_audit_trail(self, aggregate_id: str, aggregate_type: str) -> List[BaseEvent]:
        """Get complete audit trail for an aggregate."""
        return await self.event_store.get_events(aggregate_id, aggregate_type)

    async def get_system_events(self, event_types: List[EventType] = None,
                              start_time: datetime = None,
                              end_time: datetime = None,
                              limit: int = 1000) -> List[BaseEvent]:
        """Get system events for monitoring and analysis."""
        return await self.event_store.get_events_by_type(event_types, start_time, end_time, limit)

    def get_statistics(self) -> Dict[str, Any]:
        """Get service statistics."""
        return {
            **self.statistics,
            "session_active": self.session.is_active if hasattr(self.session, 'is_active') else True
        }

    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on event sourcing service."""
        try:
            # Test basic database connectivity
            self.session.execute("SELECT 1").fetchone()

            # Get recent event count
            recent_events = len(await self.event_store.get_events_by_type(
                None, datetime.utcnow() - timedelta(hours=1), limit=100
            ))

            return {
                "status": "healthy",
                "database_connected": True,
                "recent_events": recent_events,
                "statistics": self.statistics
            }

        except Exception as e:
            logger.error(f"Event sourcing health check failed: {e}")
            return {
                "status": "unhealthy",
                "database_connected": False,
                "error": str(e),
                "statistics": self.statistics
            }

# Global event sourcing service instance
event_sourcing_service: Optional[EventSourcingService] = None

def get_event_sourcing_service() -> Optional[EventSourcingService]:
    """Get global event sourcing service instance."""
    return event_sourcing_service

def initialize_event_sourcing_service(session: Session) -> EventSourcingService:
    """Initialize global event sourcing service."""
    global event_sourcing_service
    event_sourcing_service = EventSourcingService(session)
    return event_sourcing_service