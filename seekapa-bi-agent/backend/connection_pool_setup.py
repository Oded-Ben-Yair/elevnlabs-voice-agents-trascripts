#!/usr/bin/env python3
"""
Database Connection Pool Setup and Optimization
"""

import asyncio
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import create_engine, text, pool
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# Database configuration
DATABASE_URL = "postgresql://seekapa_admin:S33kpDB2025@localhost:5432/seekapa_bi"
ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

print(f"Database URL: {DATABASE_URL}")


class DatabaseConnectionManager:
    def __init__(self):
        self.sync_engine = None
        self.async_engine = None
        self.async_session_maker = None

    def configure_sync_pool(self):
        """Configure synchronous connection pool for high concurrency"""
        try:
            # Optimized connection pool settings for CEO deployment
            self.sync_engine = create_engine(
                DATABASE_URL,
                pool_size=20,           # Base connections
                max_overflow=30,        # Additional connections under load
                pool_timeout=30,        # Wait time for connection
                pool_recycle=3600,      # Recycle connections every hour
                pool_pre_ping=True,     # Validate connections before use
                pool_reset_on_return='commit',  # Clean state on return
                echo=False,             # Set to True for SQL debugging
                connect_args={
                    'connect_timeout': 10,
                    'server_settings': {
                        'application_name': 'seekapa_bi_ceo_deployment',
                    }
                }
            )

            print("✅ Synchronous connection pool configured:")
            print(f"   - Pool Size: 20 base connections")
            print(f"   - Max Overflow: 30 additional connections")
            print(f"   - Pool Timeout: 30 seconds")
            print(f"   - Connection Recycle: 1 hour")
            print(f"   - Pre-ping validation: Enabled")

            return True

        except Exception as e:
            print(f"❌ Sync connection pool setup failed: {e}")
            return False

    def configure_async_pool(self):
        """Configure async connection pool for high concurrency"""
        try:
            # Async engine with optimized pool settings
            self.async_engine = create_async_engine(
                ASYNC_DATABASE_URL,
                pool_size=15,           # Slightly smaller for async
                max_overflow=25,        # Additional async connections
                pool_timeout=30,
                pool_recycle=3600,
                pool_pre_ping=True,
                echo=False,
                connect_args={
                    'command_timeout': 60,
                    'server_settings': {
                        'application_name': 'seekapa_bi_ceo_async',
                    }
                }
            )

            # Create session maker
            self.async_session_maker = async_sessionmaker(
                self.async_engine,
                class_=AsyncSession,
                expire_on_commit=False
            )

            print("✅ Asynchronous connection pool configured:")
            print(f"   - Pool Size: 15 base connections")
            print(f"   - Max Overflow: 25 additional connections")
            print(f"   - Session expiry on commit: Disabled")

            return True

        except Exception as e:
            print(f"❌ Async connection pool setup failed: {e}")
            return False

    def test_sync_pool_performance(self, concurrent_connections=10):
        """Test synchronous pool under load"""
        print(f"🚀 Testing sync pool with {concurrent_connections} concurrent connections...")

        def execute_query(connection_id):
            """Execute a test query"""
            try:
                # Test the engine first
                if not self.sync_engine:
                    return {
                        'connection_id': connection_id,
                        'error': 'Sync engine not configured',
                        'success': False
                    }

                with self.sync_engine.connect() as conn:
                    start_time = time.time()
                    result = conn.execute(text("SELECT COUNT(*) FROM users")).scalar()
                    end_time = time.time()

                    return {
                        'connection_id': connection_id,
                        'query_time': end_time - start_time,
                        'result': result,
                        'success': True
                    }
            except Exception as e:
                return {
                    'connection_id': connection_id,
                    'error': str(e)[:100],  # Truncate long errors
                    'success': False
                }

        # Execute concurrent queries
        start_time = time.time()
        with ThreadPoolExecutor(max_workers=concurrent_connections) as executor:
            futures = [executor.submit(execute_query, i) for i in range(concurrent_connections)]
            results = [future.result() for future in futures]

        total_time = time.time() - start_time

        # Analyze results
        successful = [r for r in results if r['success']]
        failed = [r for r in results if not r['success']]

        if successful:
            avg_query_time = sum(r['query_time'] for r in successful) / len(successful)
            print(f"   ✅ Sync Pool Performance:")
            print(f"      - Total time: {total_time:.3f}s")
            print(f"      - Successful queries: {len(successful)}/{concurrent_connections}")
            print(f"      - Average query time: {avg_query_time:.3f}s")
            print(f"      - Queries per second: {len(successful)/total_time:.1f}")

        if failed:
            print(f"   ⚠️  Failed queries: {len(failed)}")
            for failure in failed[:3]:  # Show first 3 errors
                print(f"      - {failure['error'][:50]}...")

        return len(successful) == concurrent_connections

    async def test_async_pool_performance(self, concurrent_connections=10):
        """Test asynchronous pool under load"""
        print(f"🚀 Testing async pool with {concurrent_connections} concurrent connections...")

        async def execute_async_query(session_id):
            """Execute an async test query"""
            try:
                async with self.async_session_maker() as session:
                    start_time = time.time()
                    result = await session.execute(text("SELECT COUNT(*) FROM users"))
                    count = result.scalar()
                    end_time = time.time()

                    return {
                        'session_id': session_id,
                        'query_time': end_time - start_time,
                        'result': count,
                        'success': True
                    }
            except Exception as e:
                return {
                    'session_id': session_id,
                    'error': str(e),
                    'success': False
                }

        # Execute concurrent async queries
        start_time = time.time()
        tasks = [execute_async_query(i) for i in range(concurrent_connections)]
        results = await asyncio.gather(*tasks)
        total_time = time.time() - start_time

        # Analyze results
        successful = [r for r in results if r['success']]
        failed = [r for r in results if not r['success']]

        if successful:
            avg_query_time = sum(r['query_time'] for r in successful) / len(successful)
            print(f"   ✅ Async Pool Performance:")
            print(f"      - Total time: {total_time:.3f}s")
            print(f"      - Successful queries: {len(successful)}/{concurrent_connections}")
            print(f"      - Average query time: {avg_query_time:.3f}s")
            print(f"      - Queries per second: {len(successful)/total_time:.1f}")

        if failed:
            print(f"   ⚠️  Failed queries: {len(failed)}")

        return len(successful) == concurrent_connections

    def get_pool_status(self):
        """Get current pool status"""
        if self.sync_engine:
            pool_status = self.sync_engine.pool.status()
            print("📊 Connection Pool Status:")
            print(f"   - Pool Size: {self.sync_engine.pool.size()}")
            print(f"   - Checked Out: {self.sync_engine.pool.checkedout()}")
            print(f"   - Overflow: {self.sync_engine.pool.overflow()}")
            print(f"   - Status: {pool_status}")

    async def cleanup(self):
        """Clean up connections"""
        if self.async_engine:
            await self.async_engine.dispose()
        if self.sync_engine:
            self.sync_engine.dispose()


async def main():
    """Main connection pool setup and testing"""
    print("🚀 Starting Database Connection Pool Optimization...")

    db_manager = DatabaseConnectionManager()

    # Step 1: Configure connection pools
    sync_success = db_manager.configure_sync_pool()
    async_success = db_manager.configure_async_pool()

    if not (sync_success and async_success):
        print("❌ Connection pool setup failed")
        return False

    # Step 2: Test sync pool performance
    sync_test_success = db_manager.test_sync_pool_performance(concurrent_connections=15)

    # Step 3: Test async pool performance
    async_test_success = await db_manager.test_async_pool_performance(concurrent_connections=15)

    # Step 4: Show pool status
    db_manager.get_pool_status()

    # Step 5: CEO Load Test (simulate dashboard queries)
    print("📈 Running CEO Dashboard Load Simulation...")

    async def simulate_ceo_dashboard():
        """Simulate CEO dashboard queries"""
        queries = [
            "SELECT COUNT(*) FROM users WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'",
            "SELECT COUNT(*) FROM queries WHERE created_at >= CURRENT_DATE",
            "SELECT COUNT(*) FROM reports WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'",
            "SELECT AVG(execution_time) FROM queries WHERE created_at >= CURRENT_DATE"
        ]

        async def run_dashboard_query(query):
            async with db_manager.async_session_maker() as session:
                result = await session.execute(text(query))
                return result.scalar()

        start_time = time.time()
        tasks = [run_dashboard_query(query) for query in queries for _ in range(5)]  # 20 total queries
        results = await asyncio.gather(*tasks)
        end_time = time.time()

        print(f"   ✅ Dashboard simulation completed:")
        print(f"      - Executed {len(tasks)} dashboard queries")
        print(f"      - Total time: {end_time - start_time:.3f}s")
        print(f"      - Average time per query: {(end_time - start_time)/len(tasks):.3f}s")

        return True

    dashboard_success = await simulate_ceo_dashboard()

    # Cleanup
    await db_manager.cleanup()

    overall_success = sync_test_success and async_test_success and dashboard_success

    if overall_success:
        print("✅ Database connection pool optimization completed successfully!")
        print("🎯 System ready for CEO deployment with optimized performance")
    else:
        print("⚠️  Connection pool setup completed with some issues")

    return overall_success


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)