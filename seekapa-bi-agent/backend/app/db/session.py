from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import QueuePool
from .models import Base

# Configuration for connection pooling and database connection
class DatabaseSessionManager:
    def __init__(self, database_url: str):
        # Connection pool configuration
        self.engine = create_engine(
            database_url,
            poolclass=QueuePool,
            pool_size=10,  # Adjust based on your infrastructure
            max_overflow=20,  # Allow additional connections during peak load
            pool_timeout=30,  # Wait up to 30 seconds for a connection
            pool_recycle=1800,  # Recycle connections after 30 minutes
            pool_pre_ping=True  # Test connection health before using
        )

        # Create session factory
        self.SessionLocal = scoped_session(sessionmaker(
            autocommit=False,  # Require explicit commits
            autoflush=False,   # Manual flush for better performance
            bind=self.engine
        ))

    def get_session(self):
        """
        Get a database session with context management
        Provides automatic rollback on exception and session closure
        """
        session = self.SessionLocal()
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def create_all(self):
        """Create all database tables"""
        Base.metadata.create_all(self.engine)

    def drop_all(self):
        """Drop all database tables (use with caution)"""
        Base.metadata.drop_all(self.engine)