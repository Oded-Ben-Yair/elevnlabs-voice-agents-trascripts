#!/usr/bin/env python3
"""
Database Setup Script for Seekapa BI Agent
"""

import os
import sys
import asyncio
from datetime import datetime, timedelta
import uuid
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# Add the backend directory to Python path
sys.path.insert(0, '/home/odedbe/seekapa-bi-agent/backend')

try:
    from app.core.database import database_config
    from app.db.models import Base, User, Session, Query, Report, Insight

    # Database URL
    DATABASE_URL = f"postgresql://{database_config.POSTGRES_USER}:{database_config.POSTGRES_PASSWORD or 'S33kpDB2025'}@{database_config.POSTGRES_HOST}:{database_config.POSTGRES_PORT}/{database_config.POSTGRES_DB}"
except ImportError:
    # Fallback to hardcoded values
    DATABASE_URL = "postgresql://seekapa_admin:S33kpDB2025@localhost:5432/seekapa_bi"

    # Import models directly
    from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey, Boolean
    from sqlalchemy.orm import relationship
    from sqlalchemy.ext.declarative import declarative_base

    Base = declarative_base()

    class User(Base):
        __tablename__ = 'users'
        id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
        username = Column(String, unique=True, nullable=False)
        email = Column(String, unique=True, nullable=False)
        hashed_password = Column(String, nullable=False)
        is_active = Column(Boolean, default=True)
        created_at = Column(DateTime, default=datetime.utcnow)
        last_login = Column(DateTime, nullable=True)

    class Query(Base):
        __tablename__ = 'queries'
        id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
        user_id = Column(String, ForeignKey('users.id'), nullable=False)
        query_text = Column(String, nullable=False)
        execution_time = Column(Integer, nullable=True)
        created_at = Column(DateTime, default=datetime.utcnow)

    class Report(Base):
        __tablename__ = 'reports'
        id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
        user_id = Column(String, ForeignKey('users.id'), nullable=False)
        title = Column(String, nullable=False)
        description = Column(String, nullable=True)
        data = Column(JSON, nullable=False)
        created_at = Column(DateTime, default=datetime.utcnow)

    class Insight(Base):
        __tablename__ = 'insights'
        id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
        query_id = Column(String, ForeignKey('queries.id'), nullable=True)
        type = Column(String, nullable=False)
        details = Column(JSON, nullable=False)
        created_at = Column(DateTime, default=datetime.utcnow)

ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

print(f"Database URL: {DATABASE_URL}")

def create_tables():
    """Create all database tables"""
    try:
        engine = create_engine(DATABASE_URL)
        Base.metadata.create_all(engine)
        print("✅ Database tables created successfully")
        return True
    except Exception as e:
        print(f"❌ Error creating tables: {e}")
        return False

def create_performance_indexes():
    """Create performance indexes"""
    try:
        engine = create_engine(DATABASE_URL)

        # Create indexes one by one using separate connections
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);",
            "CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at);",
            "CREATE INDEX IF NOT EXISTS idx_queries_user_id ON queries(user_id);",
            "CREATE INDEX IF NOT EXISTS idx_queries_created_at ON queries(created_at);",
            "CREATE INDEX IF NOT EXISTS idx_reports_user_id ON reports(user_id);",
            "CREATE INDEX IF NOT EXISTS idx_reports_created_at ON reports(created_at);",
            "CREATE INDEX IF NOT EXISTS idx_insights_created_at ON insights(created_at);"
        ]

        # Use autocommit mode for PostgreSQL
        with engine.connect() as conn:
            conn.execute(text("COMMIT;"))  # Close any existing transaction

            for index_sql in indexes:
                try:
                    with conn.begin():  # Start new transaction for each index
                        conn.execute(text(index_sql))
                    print(f"   ✓ Created index: {index_sql.split()[4]}")
                except Exception as idx_error:
                    print(f"   ⚠️  Index creation skipped: {index_sql.split()[4]} - {str(idx_error)[:50]}...")

        print("✅ Performance indexes created successfully")
        return True
    except Exception as e:
        print(f"❌ Error creating indexes: {e}")
        return False

async def seed_ceo_data():
    """Seed realistic CEO demo data"""
    try:
        async_engine = create_async_engine(ASYNC_DATABASE_URL)
        async_session = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

        async with async_session() as session:
            # Create CEO user
            ceo_user = User(
                id=str(uuid.uuid4()),
                username="ceo",
                email="ceo@seekapa.com",
                hashed_password="$2b$12$dummy.hash.for.demo",  # Dummy hash for demo
                is_active=True,
                created_at=datetime.utcnow()
            )
            session.add(ceo_user)
            await session.flush()

            # Create sample business queries
            queries_data = [
                {
                    "query_text": "Show me this quarter's revenue trends by product category",
                    "execution_time": 145
                },
                {
                    "query_text": "What are our top performing sales regions this month?",
                    "execution_time": 89
                },
                {
                    "query_text": "Compare customer acquisition costs across marketing channels",
                    "execution_time": 234
                },
                {
                    "query_text": "Show weekly active user growth over the last 6 months",
                    "execution_time": 167
                }
            ]

            queries = []
            for i, query_data in enumerate(queries_data):
                query = Query(
                    id=str(uuid.uuid4()),
                    user_id=ceo_user.id,
                    query_text=query_data["query_text"],
                    execution_time=query_data["execution_time"],
                    created_at=datetime.utcnow() - timedelta(days=i)
                )
                queries.append(query)
                session.add(query)

            await session.flush()

            # Create executive reports
            reports = [
                Report(
                    id=str(uuid.uuid4()),
                    user_id=ceo_user.id,
                    title="Executive Dashboard - Q3 2025",
                    description="Comprehensive business performance metrics",
                    data={
                        "revenue": 2400000,
                        "growth": 23.4,
                        "active_users": 15000,
                        "conversion_rate": 4.2,
                        "customer_satisfaction": 92.5
                    },
                    created_at=datetime.utcnow()
                ),
                Report(
                    id=str(uuid.uuid4()),
                    user_id=ceo_user.id,
                    title="Real-time KPI Monitor",
                    description="Live business intelligence metrics",
                    data={
                        "daily_active_users": 1247,
                        "revenue_today": 45600,
                        "new_customers": 23,
                        "support_tickets": 8,
                        "server_uptime": 99.97
                    },
                    created_at=datetime.utcnow()
                )
            ]

            for report in reports:
                session.add(report)

            # Create insights
            insights = [
                Insight(
                    id=str(uuid.uuid4()),
                    query_id=queries[0].id,
                    type="performance",
                    details={
                        "insight": "Product Category A shows 34% higher growth than average",
                        "recommendation": "Increase marketing spend on Category A products",
                        "impact": "Potential 15% revenue increase"
                    },
                    created_at=datetime.utcnow()
                ),
                Insight(
                    id=str(uuid.uuid4()),
                    query_id=queries[1].id,
                    type="optimization",
                    details={
                        "insight": "West Coast region outperforming by 28%",
                        "recommendation": "Replicate West Coast strategy in other regions",
                        "impact": "Projected 12% overall sales increase"
                    },
                    created_at=datetime.utcnow()
                )
            ]

            for insight in insights:
                session.add(insight)

            await session.commit()
            await async_engine.dispose()

        print("✅ CEO demo data seeded successfully")
        return True

    except Exception as e:
        print(f"❌ Error seeding data: {e}")
        return False

async def health_check():
    """Comprehensive database health check"""
    try:
        async_engine = create_async_engine(ASYNC_DATABASE_URL)
        async_session = async_sessionmaker(async_engine, class_=AsyncSession)

        async with async_session() as session:
            # Check table counts
            result = await session.execute(text("SELECT COUNT(*) FROM users"))
            user_count = result.scalar()

            result = await session.execute(text("SELECT COUNT(*) FROM queries"))
            query_count = result.scalar()

            result = await session.execute(text("SELECT COUNT(*) FROM reports"))
            report_count = result.scalar()

            # Check index usage (simplified query)
            result = await session.execute(text("""
                SELECT indexrelname, idx_scan
                FROM pg_stat_user_indexes
                WHERE schemaname = 'public'
                ORDER BY idx_scan DESC
                LIMIT 10;
            """))
            index_stats = result.fetchall()

            # Check database size
            result = await session.execute(text("""
                SELECT pg_size_pretty(pg_database_size('seekapa_bi')) as db_size;
            """))
            db_size = result.scalar()

            await async_engine.dispose()

        print(f"✅ Database Health Check:")
        print(f"   - Users: {user_count}")
        print(f"   - Queries: {query_count}")
        print(f"   - Reports: {report_count}")
        print(f"   - Database Size: {db_size}")
        print(f"   - Active Indexes: {len(index_stats)}")

        return True

    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return False

def main():
    """Run all database setup tasks"""
    print("🚀 Starting Database Stabilization Process...")

    # Step 1: Create tables
    if not create_tables():
        return False

    # Step 2: Create indexes
    if not create_performance_indexes():
        return False

    # Step 3: Seed data
    if not asyncio.run(seed_ceo_data()):
        return False

    # Step 4: Health check
    if not asyncio.run(health_check()):
        return False

    print("✅ Database stabilization completed successfully!")
    return True

if __name__ == "__main__":
    main()