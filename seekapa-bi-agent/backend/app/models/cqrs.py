"""
CQRS (Command Query Responsibility Segregation) implementation for Seekapa BI Agent.
Separates read and write operations with dedicated models and handlers.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Type, Union
from dataclasses import dataclass
from datetime import datetime, timedelta
import uuid

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc, asc, func

from .events import (
    BaseEvent, EventType, EventStore, EventSnapshot,
    QueryReadModel, UserActivityReadModel, ReportMetricsReadModel, SystemMetricsReadModel,
    create_user_event, create_query_event, create_data_event, create_report_event, create_stream_event
)

logger = logging.getLogger(__name__)

# Command interfaces

class Command(ABC):
    """Base command interface."""
    command_id: str
    user_id: Optional[str]
    session_id: Optional[str]
    timestamp: datetime

    def __init__(self, user_id: str = None, session_id: str = None):
        self.command_id = str(uuid.uuid4())
        self.user_id = user_id
        self.session_id = session_id
        self.timestamp = datetime.utcnow()

class Query(ABC):
    """Base query interface."""
    query_id: str
    user_id: Optional[str]
    timestamp: datetime

    def __init__(self, user_id: str = None):
        self.query_id = str(uuid.uuid4())
        self.user_id = user_id
        self.timestamp = datetime.utcnow()

# Specific commands

@dataclass
class CreateUserCommand(Command):
    username: str
    email: str
    hashed_password: str

@dataclass
class UpdateUserCommand(Command):
    user_id: str
    updates: Dict[str, Any]

@dataclass
class ExecuteQueryCommand(Command):
    query_text: str
    params: Dict[str, Any]

@dataclass
class CreateReportCommand(Command):
    title: str
    description: str
    data: Dict[str, Any]

@dataclass
class UpdateReportCommand(Command):
    report_id: str
    updates: Dict[str, Any]

@dataclass
class StartStreamCommand(Command):
    connection_id: str
    topic: str
    config: Dict[str, Any]

# Specific queries

@dataclass
class GetUserQuery(Query):
    user_id: str

@dataclass
class GetUserQueriesQuery(Query):
    user_id: str
    limit: int = 50
    offset: int = 0

@dataclass
class GetQueryMetricsQuery(Query):
    query_hash: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

@dataclass
class GetUserActivityQuery(Query):
    user_id: str
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

@dataclass
class GetReportMetricsQuery(Query):
    report_id: Optional[str] = None
    user_id: Optional[str] = None

@dataclass
class GetSystemMetricsQuery(Query):
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    metric_type: Optional[str] = None

# Command handlers

class CommandHandler(ABC):
    """Base command handler interface."""

    @abstractmethod
    async def handle(self, command: Command, db_session: Session) -> Dict[str, Any]:
        pass

class EventSourcedCommandHandler(CommandHandler):
    """Base class for event-sourced command handlers."""

    def __init__(self, event_store_session: Session):
        self.event_store_session = event_store_session

    async def save_event(self, event: BaseEvent):
        """Save event to event store."""
        event_record = EventStore.from_event(event)
        self.event_store_session.add(event_record)
        await self.event_store_session.commit()

    async def get_events_for_aggregate(self, aggregate_id: str, aggregate_type: str) -> List[BaseEvent]:
        """Get all events for an aggregate."""
        events = self.event_store_session.query(EventStore).filter(
            and_(
                EventStore.aggregate_id == aggregate_id,
                EventStore.aggregate_type == aggregate_type
            )
        ).order_by(EventStore.version).all()

        return [event.to_event() for event in events]

class UserCommandHandler(EventSourcedCommandHandler):
    """Handler for user-related commands."""

    async def handle(self, command: Command, db_session: Session) -> Dict[str, Any]:
        if isinstance(command, CreateUserCommand):
            return await self._handle_create_user(command, db_session)
        elif isinstance(command, UpdateUserCommand):
            return await self._handle_update_user(command, db_session)
        else:
            raise ValueError(f"Unsupported command type: {type(command)}")

    async def _handle_create_user(self, command: CreateUserCommand, db_session: Session) -> Dict[str, Any]:
        user_id = str(uuid.uuid4())

        # Create and save event
        event = create_user_event(
            EventType.USER_CREATED,
            user_id=user_id,
            data={
                "username": command.username,
                "email": command.email,
                "hashed_password": command.hashed_password
            },
            session_id=command.session_id
        )

        await self.save_event(event)

        logger.info(f"User created: {user_id}")
        return {"user_id": user_id, "success": True}

    async def _handle_update_user(self, command: UpdateUserCommand, db_session: Session) -> Dict[str, Any]:
        # Create and save event
        event = create_user_event(
            EventType.USER_UPDATED,
            user_id=command.user_id,
            data=command.updates,
            session_id=command.session_id
        )

        await self.save_event(event)

        logger.info(f"User updated: {command.user_id}")
        return {"user_id": command.user_id, "success": True}

class QueryCommandHandler(EventSourcedCommandHandler):
    """Handler for query-related commands."""

    async def handle(self, command: Command, db_session: Session) -> Dict[str, Any]:
        if isinstance(command, ExecuteQueryCommand):
            return await self._handle_execute_query(command, db_session)
        else:
            raise ValueError(f"Unsupported command type: {type(command)}")

    async def _handle_execute_query(self, command: ExecuteQueryCommand, db_session: Session) -> Dict[str, Any]:
        query_id = str(uuid.uuid4())
        start_time = datetime.utcnow()

        try:
            # Simulate query execution (replace with actual query engine)
            await asyncio.sleep(0.1)  # Simulate processing time
            execution_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            # Create success event
            event = create_query_event(
                EventType.QUERY_EXECUTED,
                query_id=query_id,
                user_id=command.user_id,
                query_text=command.query_text,
                execution_time=execution_time,
                data={
                    "params": command.params,
                    "result_count": 100  # Mock result count
                },
                session_id=command.session_id
            )

            await self.save_event(event)

            # Update read model
            await self._update_query_read_model(command, query_id, execution_time, db_session)

            logger.info(f"Query executed successfully: {query_id}")
            return {
                "query_id": query_id,
                "execution_time": execution_time,
                "success": True
            }

        except Exception as e:
            execution_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            # Create failure event
            event = create_query_event(
                EventType.QUERY_FAILED,
                query_id=query_id,
                user_id=command.user_id,
                query_text=command.query_text,
                execution_time=execution_time,
                data={
                    "params": command.params,
                    "error": str(e)
                },
                session_id=command.session_id
            )

            await self.save_event(event)

            logger.error(f"Query execution failed: {query_id} - {e}")
            return {
                "query_id": query_id,
                "execution_time": execution_time,
                "success": False,
                "error": str(e)
            }

    async def _update_query_read_model(self, command: ExecuteQueryCommand, query_id: str,
                                     execution_time: int, db_session: Session):
        """Update query read model for optimized querying."""
        import hashlib
        query_hash = hashlib.md5(command.query_text.encode()).hexdigest()

        # Find existing read model or create new one
        existing = db_session.query(QueryReadModel).filter(
            QueryReadModel.query_hash == query_hash
        ).first()

        if existing:
            # Update existing record
            existing.execution_count += 1
            existing.total_execution_time += execution_time
            existing.average_execution_time = existing.total_execution_time // existing.execution_count
            existing.last_executed = datetime.utcnow()
            existing.updated_at = datetime.utcnow()

            if execution_time < existing.min_execution_time or existing.min_execution_time == 0:
                existing.min_execution_time = execution_time
            if execution_time > existing.max_execution_time:
                existing.max_execution_time = execution_time

            existing.success_count += 1
        else:
            # Create new record
            new_read_model = QueryReadModel(
                id=query_id,
                user_id=command.user_id,
                query_text=command.query_text,
                query_hash=query_hash,
                execution_count=1,
                total_execution_time=execution_time,
                average_execution_time=execution_time,
                last_executed=datetime.utcnow(),
                min_execution_time=execution_time,
                max_execution_time=execution_time,
                success_count=1
            )
            db_session.add(new_read_model)

        db_session.commit()

# Query handlers

class QueryHandler(ABC):
    """Base query handler interface."""

    @abstractmethod
    async def handle(self, query: Query, db_session: Session) -> Dict[str, Any]:
        pass

class UserQueryHandler(QueryHandler):
    """Handler for user-related queries."""

    async def handle(self, query: Query, db_session: Session) -> Dict[str, Any]:
        if isinstance(query, GetUserQuery):
            return await self._handle_get_user(query, db_session)
        elif isinstance(query, GetUserActivityQuery):
            return await self._handle_get_user_activity(query, db_session)
        else:
            raise ValueError(f"Unsupported query type: {type(query)}")

    async def _handle_get_user(self, query: GetUserQuery, db_session: Session) -> Dict[str, Any]:
        # In a real implementation, this would reconstruct user state from events
        # For now, we'll return mock data
        return {
            "user_id": query.user_id,
            "username": "mock_user",
            "email": "mock@example.com",
            "created_at": datetime.utcnow().isoformat()
        }

    async def _handle_get_user_activity(self, query: GetUserActivityQuery, db_session: Session) -> Dict[str, Any]:
        """Get user activity from read model."""
        query_filter = [UserActivityReadModel.user_id == query.user_id]

        if query.start_date:
            query_filter.append(UserActivityReadModel.date >= query.start_date)
        if query.end_date:
            query_filter.append(UserActivityReadModel.date <= query.end_date)

        activities = db_session.query(UserActivityReadModel).filter(
            and_(*query_filter)
        ).order_by(desc(UserActivityReadModel.date)).all()

        return {
            "user_id": query.user_id,
            "activities": [
                {
                    "date": activity.date.isoformat(),
                    "query_count": activity.query_count,
                    "report_count": activity.report_count,
                    "session_duration": activity.session_duration,
                    "login_count": activity.login_count
                }
                for activity in activities
            ]
        }

class QueryMetricsHandler(QueryHandler):
    """Handler for query metrics queries."""

    async def handle(self, query: Query, db_session: Session) -> Dict[str, Any]:
        if isinstance(query, GetQueryMetricsQuery):
            return await self._handle_get_query_metrics(query, db_session)
        else:
            raise ValueError(f"Unsupported query type: {type(query)}")

    async def _handle_get_query_metrics(self, query: GetQueryMetricsQuery, db_session: Session) -> Dict[str, Any]:
        """Get query metrics from read model."""
        query_filter = []

        if query.query_hash:
            query_filter.append(QueryReadModel.query_hash == query.query_hash)
        if query.start_date:
            query_filter.append(QueryReadModel.last_executed >= query.start_date)
        if query.end_date:
            query_filter.append(QueryReadModel.last_executed <= query.end_date)

        if query_filter:
            queries = db_session.query(QueryReadModel).filter(
                and_(*query_filter)
            ).order_by(desc(QueryReadModel.last_executed)).all()
        else:
            queries = db_session.query(QueryReadModel).order_by(
                desc(QueryReadModel.last_executed)
            ).limit(100).all()

        return {
            "queries": [
                {
                    "query_hash": q.query_hash,
                    "execution_count": q.execution_count,
                    "average_execution_time": q.average_execution_time,
                    "min_execution_time": q.min_execution_time,
                    "max_execution_time": q.max_execution_time,
                    "success_count": q.success_count,
                    "failure_count": q.failure_count,
                    "last_executed": q.last_executed.isoformat()
                }
                for q in queries
            ]
        }

class SystemMetricsHandler(QueryHandler):
    """Handler for system metrics queries."""

    async def handle(self, query: Query, db_session: Session) -> Dict[str, Any]:
        if isinstance(query, GetSystemMetricsQuery):
            return await self._handle_get_system_metrics(query, db_session)
        else:
            raise ValueError(f"Unsupported query type: {type(query)}")

    async def _handle_get_system_metrics(self, query: GetSystemMetricsQuery, db_session: Session) -> Dict[str, Any]:
        """Get system metrics from read model."""
        query_filter = []

        if query.start_date:
            query_filter.append(SystemMetricsReadModel.metric_date >= query.start_date)
        if query.end_date:
            query_filter.append(SystemMetricsReadModel.metric_date <= query.end_date)

        if query_filter:
            metrics = db_session.query(SystemMetricsReadModel).filter(
                and_(*query_filter)
            ).order_by(desc(SystemMetricsReadModel.metric_date)).all()
        else:
            # Default to last 7 days
            start_date = datetime.utcnow() - timedelta(days=7)
            metrics = db_session.query(SystemMetricsReadModel).filter(
                SystemMetricsReadModel.metric_date >= start_date
            ).order_by(desc(SystemMetricsReadModel.metric_date)).all()

        return {
            "metrics": [
                {
                    "date": m.metric_date.isoformat(),
                    "active_users": m.active_users,
                    "total_queries": m.total_queries,
                    "total_reports": m.total_reports,
                    "average_response_time": m.average_response_time,
                    "error_count": m.error_count,
                    "cpu_usage_percent": m.cpu_usage_percent,
                    "memory_usage_percent": m.memory_usage_percent,
                    "active_connections": m.active_connections
                }
                for m in metrics
            ]
        }

# CQRS Bus implementation

class CommandBus:
    """Command bus for routing commands to appropriate handlers."""

    def __init__(self):
        self.handlers: Dict[Type[Command], CommandHandler] = {}

    def register_handler(self, command_type: Type[Command], handler: CommandHandler):
        """Register a command handler."""
        self.handlers[command_type] = handler

    async def execute(self, command: Command, db_session: Session) -> Dict[str, Any]:
        """Execute a command."""
        handler = self.handlers.get(type(command))
        if not handler:
            raise ValueError(f"No handler registered for command type: {type(command)}")

        try:
            result = await handler.handle(command, db_session)
            logger.info(f"Command executed successfully: {command.command_id}")
            return result
        except Exception as e:
            logger.error(f"Command execution failed: {command.command_id} - {e}")
            raise

class QueryBus:
    """Query bus for routing queries to appropriate handlers."""

    def __init__(self):
        self.handlers: Dict[Type[Query], QueryHandler] = {}

    def register_handler(self, query_type: Type[Query], handler: QueryHandler):
        """Register a query handler."""
        self.handlers[query_type] = handler

    async def execute(self, query: Query, db_session: Session) -> Dict[str, Any]:
        """Execute a query."""
        handler = self.handlers.get(type(query))
        if not handler:
            raise ValueError(f"No handler registered for query type: {type(query)}")

        try:
            result = await handler.handle(query, db_session)
            logger.info(f"Query executed successfully: {query.query_id}")
            return result
        except Exception as e:
            logger.error(f"Query execution failed: {query.query_id} - {e}")
            raise

# Global CQRS setup

class CQRSManager:
    """Manager for CQRS pattern implementation."""

    def __init__(self, event_store_session: Session, read_model_session: Session):
        self.command_bus = CommandBus()
        self.query_bus = QueryBus()
        self.event_store_session = event_store_session
        self.read_model_session = read_model_session

        self._register_handlers()

    def _register_handlers(self):
        """Register default command and query handlers."""
        # Command handlers
        user_handler = UserCommandHandler(self.event_store_session)
        query_handler = QueryCommandHandler(self.event_store_session)

        self.command_bus.register_handler(CreateUserCommand, user_handler)
        self.command_bus.register_handler(UpdateUserCommand, user_handler)
        self.command_bus.register_handler(ExecuteQueryCommand, query_handler)

        # Query handlers
        user_query_handler = UserQueryHandler()
        metrics_handler = QueryMetricsHandler()
        system_handler = SystemMetricsHandler()

        self.query_bus.register_handler(GetUserQuery, user_query_handler)
        self.query_bus.register_handler(GetUserActivityQuery, user_query_handler)
        self.query_bus.register_handler(GetQueryMetricsQuery, metrics_handler)
        self.query_bus.register_handler(GetSystemMetricsQuery, system_handler)

    async def execute_command(self, command: Command) -> Dict[str, Any]:
        """Execute a command through the command bus."""
        return await self.command_bus.execute(command, self.read_model_session)

    async def execute_query(self, query: Query) -> Dict[str, Any]:
        """Execute a query through the query bus."""
        return await self.query_bus.execute(query, self.read_model_session)

# Global instance (to be initialized with database sessions)
cqrs_manager: Optional[CQRSManager] = None

def get_cqrs_manager() -> Optional[CQRSManager]:
    """Get global CQRS manager instance."""
    return cqrs_manager

def initialize_cqrs_manager(event_store_session: Session, read_model_session: Session) -> CQRSManager:
    """Initialize global CQRS manager."""
    global cqrs_manager
    cqrs_manager = CQRSManager(event_store_session, read_model_session)
    return cqrs_manager