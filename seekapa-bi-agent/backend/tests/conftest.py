"""
Test configuration and fixtures for pytest.
"""
import os
import pytest
import asyncio
from typing import AsyncGenerator, Generator
from unittest.mock import Mock, AsyncMock

import pytest_asyncio
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app.db.models import Base, User, Session as UserSession, Query, Report, Insight
from app.core.database import DatabaseSettings
from app.services.cache_service import RedisCache


# Test database configuration
TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def test_db_engine():
    """Create a test database engine."""
    engine = create_engine(
        TEST_DATABASE_URL,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
        echo=False,
    )

    # Create all tables
    Base.metadata.create_all(bind=engine)

    yield engine

    # Drop all tables
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session(test_db_engine) -> Generator[Session, None, None]:
    """Create a test database session."""
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=test_db_engine
    )

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def clean_db(db_session):
    """Clean database between tests."""
    yield db_session

    # Clean up data after each test
    for table in reversed(Base.metadata.sorted_tables):
        db_session.execute(table.delete())
    db_session.commit()


@pytest.fixture
def mock_redis():
    """Mock Redis client for cache tests."""
    redis_mock = Mock()
    redis_mock.setex = Mock()
    redis_mock.get = Mock(return_value=None)
    redis_mock.delete = Mock()
    redis_mock.sadd = Mock()
    redis_mock.smembers = Mock(return_value=set())
    redis_mock.lock = Mock()

    return redis_mock


@pytest.fixture
def cache_service(mock_redis):
    """Create a cache service with mocked Redis."""
    cache = RedisCache()
    cache.redis_client = mock_redis
    return cache


@pytest.fixture
def sample_user(db_session) -> User:
    """Create a sample user for testing."""
    user = User(
        id="test-user-123",
        username="testuser",
        email="test@example.com",
        hashed_password="hashed_password",
        is_active=True
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def sample_users(db_session) -> list[User]:
    """Create multiple sample users for testing."""
    users = []
    for i in range(5):
        user = User(
            id=f"test-user-{i}",
            username=f"testuser{i}",
            email=f"test{i}@example.com",
            hashed_password="hashed_password",
            is_active=True
        )
        users.append(user)
        db_session.add(user)

    db_session.commit()
    for user in users:
        db_session.refresh(user)

    return users


@pytest.fixture
def sample_session(db_session, sample_user) -> UserSession:
    """Create a sample user session for testing."""
    from datetime import datetime, timedelta

    session = UserSession(
        id="test-session-123",
        user_id=sample_user.id,
        token="test-token-123",
        expires_at=datetime.utcnow() + timedelta(hours=1),
        is_active=True
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    return session


@pytest.fixture
def sample_query(db_session, sample_user) -> Query:
    """Create a sample query for testing."""
    query = Query(
        id="test-query-123",
        user_id=sample_user.id,
        query_text="SELECT * FROM users",
        params={"limit": 10},
        execution_time=150
    )
    db_session.add(query)
    db_session.commit()
    db_session.refresh(query)
    return query


@pytest.fixture
def sample_queries(db_session, sample_user) -> list[Query]:
    """Create multiple sample queries for testing."""
    queries = []
    for i in range(10):
        query = Query(
            id=f"test-query-{i}",
            user_id=sample_user.id,
            query_text=f"SELECT * FROM table_{i}",
            params={"limit": 10 * (i + 1)},
            execution_time=100 + (i * 10)
        )
        queries.append(query)
        db_session.add(query)

    db_session.commit()
    for query in queries:
        db_session.refresh(query)

    return queries


@pytest.fixture
def sample_report(db_session, sample_user) -> Report:
    """Create a sample report for testing."""
    report = Report(
        id="test-report-123",
        user_id=sample_user.id,
        title="Test Report",
        description="A test report",
        data={
            "charts": [
                {"type": "bar", "data": [1, 2, 3, 4, 5]},
                {"type": "line", "data": [10, 20, 30, 40, 50]}
            ]
        }
    )
    db_session.add(report)
    db_session.commit()
    db_session.refresh(report)
    return report


@pytest.fixture
def sample_insight(db_session, sample_query) -> Insight:
    """Create a sample insight for testing."""
    insight = Insight(
        id="test-insight-123",
        query_id=sample_query.id,
        type="performance",
        details={
            "message": "Query execution time is above average",
            "confidence": 0.85,
            "recommendations": ["Add index", "Optimize query"]
        }
    )
    db_session.add(insight)
    db_session.commit()
    db_session.refresh(insight)
    return insight


@pytest.fixture
def mock_database_config():
    """Mock database configuration for testing."""
    config = DatabaseSettings()
    config.POSTGRES_HOST = "test-host"
    config.POSTGRES_PORT = 5432
    config.POSTGRES_USER = "test-user"
    config.POSTGRES_PASSWORD = "test-password"
    config.POSTGRES_DB = "test-db"
    config.DB_POOL_SIZE = 5
    config.DB_MAX_OVERFLOW = 10
    return config


@pytest.fixture
async def mock_websocket():
    """Mock WebSocket connection for testing."""
    websocket = AsyncMock()
    websocket.send = AsyncMock()
    websocket.close = AsyncMock()
    websocket.closed = False
    websocket.accept = AsyncMock()
    websocket.receive_text = AsyncMock()
    websocket.receive_json = AsyncMock()
    return websocket


@pytest.fixture
def mock_powerbi_client():
    """Mock Power BI client for testing."""
    client = Mock()

    # Mock authentication
    client.authenticate = AsyncMock(return_value={
        "access_token": "mock-powerbi-token",
        "refresh_token": "mock-refresh-token",
        "expires_in": 3600
    })

    # Mock get reports
    client.get_reports = AsyncMock(return_value=[
        {
            "id": "report-1",
            "name": "Sales Dashboard",
            "datasetId": "dataset-1",
            "webUrl": "https://app.powerbi.com/reports/report-1"
        },
        {
            "id": "report-2",
            "name": "Marketing Analytics",
            "datasetId": "dataset-2",
            "webUrl": "https://app.powerbi.com/reports/report-2"
        }
    ])

    # Mock get embed token
    client.get_embed_token = AsyncMock(return_value={
        "token": "embed-token-123",
        "tokenId": "token-id-123",
        "expiration": "2024-12-31T23:59:59Z"
    })

    return client


@pytest.fixture
def api_client():
    """Create a test API client."""
    from fastapi.testclient import TestClient
    from app.main import app

    return TestClient(app)


@pytest.fixture
def auth_headers(sample_user):
    """Create authentication headers for API tests."""
    # Mock JWT token for testing
    token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjoidGVzdC11c2VyLTEyMyJ9"
    return {"Authorization": f"Bearer {token}"}


# Async fixtures
@pytest_asyncio.fixture
async def async_db_session(test_db_engine) -> AsyncGenerator[Session, None]:
    """Create an async test database session."""
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=test_db_engine
    )

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


# Environment setup
@pytest.fixture(scope="session", autouse=True)
def setup_test_env():
    """Set up test environment variables."""
    os.environ["TESTING"] = "1"
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    os.environ["REDIS_URL"] = "redis://localhost:6379/1"  # Use different DB for tests

    yield

    # Cleanup
    if "TESTING" in os.environ:
        del os.environ["TESTING"]


# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "unit: mark test as unit test")
    config.addinivalue_line("markers", "integration: mark test as integration test")
    config.addinivalue_line("markers", "slow: mark test as slow running")
    config.addinivalue_line("markers", "database: mark test as requiring database")
    config.addinivalue_line("markers", "cache: mark test as requiring cache")
    config.addinivalue_line("markers", "websocket: mark test as WebSocket test")
    config.addinivalue_line("markers", "powerbi: mark test as Power BI integration test")


# Custom assertions
def assert_user_equal(actual: User, expected: dict):
    """Assert user matches expected values."""
    assert actual.username == expected.get("username", actual.username)
    assert actual.email == expected.get("email", actual.email)
    assert actual.is_active == expected.get("is_active", actual.is_active)


def assert_query_equal(actual: Query, expected: dict):
    """Assert query matches expected values."""
    assert actual.query_text == expected.get("query_text", actual.query_text)
    assert actual.params == expected.get("params", actual.params)
    assert actual.execution_time == expected.get("execution_time", actual.execution_time)


def assert_report_equal(actual: Report, expected: dict):
    """Assert report matches expected values."""
    assert actual.title == expected.get("title", actual.title)
    assert actual.description == expected.get("description", actual.description)
    assert actual.data == expected.get("data", actual.data)


# Utility functions for tests
def create_test_user_data(**overrides):
    """Create test user data with optional overrides."""
    default_data = {
        "username": "testuser",
        "email": "test@example.com",
        "password": "testpassword",
        "is_active": True
    }
    default_data.update(overrides)
    return default_data


def create_test_query_data(**overrides):
    """Create test query data with optional overrides."""
    default_data = {
        "query_text": "SELECT * FROM users",
        "params": {"limit": 10},
        "execution_time": 150
    }
    default_data.update(overrides)
    return default_data


def create_test_report_data(**overrides):
    """Create test report data with optional overrides."""
    default_data = {
        "title": "Test Report",
        "description": "A test report",
        "data": {
            "charts": [
                {"type": "bar", "data": [1, 2, 3, 4, 5]},
                {"type": "line", "data": [10, 20, 30, 40, 50]}
            ]
        }
    }
    default_data.update(overrides)
    return default_data