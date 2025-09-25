#!/usr/bin/env python3
"""
Redis Cache Setup and Testing Script
"""

import asyncio
import redis.asyncio as redis
import json
import time
from datetime import datetime, timedelta


class RedisCache:
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.redis_client = None

    async def connect(self):
        """Connect to Redis"""
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            # Test connection
            await self.redis_client.ping()
            print("✅ Redis connection established successfully")
            return True
        except Exception as e:
            print(f"❌ Redis connection failed: {e}")
            return False

    async def disconnect(self):
        """Disconnect from Redis"""
        if self.redis_client:
            await self.redis_client.close()

    async def set(self, key: str, value: str, ttl: int = 300):
        """Set a value with TTL (Time To Live)"""
        try:
            await self.redis_client.set(key, value, ex=ttl)
            return True
        except Exception as e:
            print(f"❌ Cache set failed for key {key}: {e}")
            return False

    async def get(self, key: str):
        """Get a value from cache"""
        try:
            return await self.redis_client.get(key)
        except Exception as e:
            print(f"❌ Cache get failed for key {key}: {e}")
            return None

    async def delete(self, key: str):
        """Delete a key from cache"""
        try:
            await self.redis_client.delete(key)
            return True
        except Exception as e:
            print(f"❌ Cache delete failed for key {key}: {e}")
            return False

    async def warm_cache(self, cache_data: list):
        """Pre-populate cache with important data"""
        try:
            pipe = self.redis_client.pipeline()

            for key, value in cache_data:
                # Serialize complex data as JSON
                if isinstance(value, (dict, list)):
                    value = json.dumps(value)
                pipe.set(key, value, ex=3600)  # 1 hour TTL

            await pipe.execute()
            print(f"✅ Cache warmed with {len(cache_data)} entries")
            return True
        except Exception as e:
            print(f"❌ Cache warming failed: {e}")
            return False

    async def get_cache_stats(self):
        """Get cache performance statistics"""
        try:
            info = await self.redis_client.info()

            stats = {
                'connected_clients': info.get('connected_clients', 0),
                'used_memory': info.get('used_memory_human', '0B'),
                'keyspace_hits': info.get('keyspace_hits', 0),
                'keyspace_misses': info.get('keyspace_misses', 0),
                'total_commands_processed': info.get('total_commands_processed', 0)
            }

            # Calculate hit rate
            hits = stats['keyspace_hits']
            misses = stats['keyspace_misses']
            hit_rate = (hits / (hits + misses)) * 100 if (hits + misses) > 0 else 0
            stats['hit_rate'] = round(hit_rate, 2)

            return stats
        except Exception as e:
            print(f"❌ Failed to get cache stats: {e}")
            return {}

    async def performance_test(self):
        """Run performance test"""
        print("🚀 Running Redis performance test...")

        # Test data
        test_data = [
            ('user:1:profile', {'name': 'CEO', 'role': 'executive', 'last_login': '2025-09-25T06:20:00Z'}),
            ('query:results:revenue', {'q3_revenue': 2400000, 'growth': 23.4}),
            ('dashboard:kpis', {'active_users': 1247, 'conversion': 4.2, 'satisfaction': 92.5}),
            ('report:executive:latest', {'title': 'Q3 Executive Summary', 'created': '2025-09-25'}),
            ('insights:performance', {'top_product': 'Analytics Suite', 'growth': '34%'})
        ]

        # Set operations
        set_start = time.time()
        for key, value in test_data:
            await self.set(key, json.dumps(value), ttl=300)
        set_time = time.time() - set_start

        # Get operations
        get_start = time.time()
        retrieved = []
        for key, _ in test_data:
            result = await self.get(key)
            retrieved.append(result)
        get_time = time.time() - get_start

        print(f"   ✓ SET operations: {len(test_data)} keys in {set_time:.3f}s")
        print(f"   ✓ GET operations: {len(test_data)} keys in {get_time:.3f}s")
        print(f"   ✓ Average SET time: {(set_time/len(test_data))*1000:.2f}ms")
        print(f"   ✓ Average GET time: {(get_time/len(test_data))*1000:.2f}ms")

        return True


async def main():
    """Main Redis setup and testing function"""
    print("🚀 Starting Redis Cache Setup and Testing...")

    cache = RedisCache()

    # Step 1: Connect to Redis
    if not await cache.connect():
        print("❌ Cannot proceed without Redis connection")
        return False

    # Step 2: Performance test
    await cache.performance_test()

    # Step 3: Warm cache with CEO demo data
    ceo_cache_data = [
        ('dashboard:executive:q3_2025', {
            'revenue': 2400000,
            'growth': 23.4,
            'active_users': 15000,
            'conversion_rate': 4.2,
            'customer_satisfaction': 92.5,
            'last_updated': datetime.utcnow().isoformat()
        }),
        ('kpis:realtime', {
            'daily_active_users': 1247,
            'revenue_today': 45600,
            'new_customers': 23,
            'support_tickets': 8,
            'server_uptime': 99.97,
            'timestamp': datetime.utcnow().isoformat()
        }),
        ('reports:executive:recent', [
            {'title': 'Executive Dashboard - Q3 2025', 'id': 'exec_q3_2025'},
            {'title': 'Real-time KPI Monitor', 'id': 'kpi_realtime'},
            {'title': 'Performance Analytics', 'id': 'perf_analytics'}
        ]),
        ('queries:frequent', [
            'Show me this quarter\'s revenue trends',
            'What are our top performing products?',
            'Compare customer acquisition costs',
            'Show weekly active user growth'
        ]),
        ('insights:latest', {
            'product_growth': 'Category A shows 34% higher growth',
            'regional_performance': 'West Coast outperforming by 28%',
            'recommendation': 'Increase marketing spend on Category A',
            'generated_at': datetime.utcnow().isoformat()
        })
    ]

    await cache.warm_cache(ceo_cache_data)

    # Step 4: Get cache statistics
    stats = await cache.get_cache_stats()
    print("✅ Cache Statistics:")
    for key, value in stats.items():
        print(f"   - {key.replace('_', ' ').title()}: {value}")

    # Step 5: Test cache retrieval
    print("🔍 Testing cached data retrieval:")
    test_keys = ['dashboard:executive:q3_2025', 'kpis:realtime', 'insights:latest']
    for key in test_keys:
        cached_data = await cache.get(key)
        if cached_data:
            data = json.loads(cached_data)
            print(f"   ✓ Retrieved {key}: {len(str(data))} chars")
        else:
            print(f"   ❌ Failed to retrieve {key}")

    await cache.disconnect()
    print("✅ Redis cache setup and testing completed successfully!")
    return True


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)