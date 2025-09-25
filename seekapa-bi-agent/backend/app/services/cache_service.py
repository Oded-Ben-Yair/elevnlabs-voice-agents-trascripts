import redis
import json
import functools
import uuid
from typing import Any, Callable, Optional
from redis.lock import Lock

class RedisCache:
    def __init__(self,
                 host: str = 'localhost',
                 port: int = 6379,
                 db: int = 0,
                 password: Optional[str] = None):
        """
        Initialize Redis cache with connection and configuration

        :param host: Redis server host
        :param port: Redis server port
        :param db: Redis database number
        :param password: Optional Redis password
        """
        self.redis_client = redis.Redis(
            host=host,
            port=port,
            db=db,
            password=password,
            decode_responses=True
        )
        self.lock_prefix = 'lock:'

    def warm_cache(self, key_prefix: str, data_loader: Callable):
        """
        Warm cache by pre-loading data for faster initial access

        :param key_prefix: Prefix for cache keys
        :param data_loader: Function to load data
        """
        try:
            data = data_loader()
            for item in data:
                cache_key = f"{key_prefix}:{item['id']}"
                self.set(cache_key, item, ttl=3600)  # 1-hour default TTL
        except Exception as e:
            print(f"Cache warming failed: {e}")

    def set(self, key: str, value: Any, ttl: int = 3600, tags: list = None):
        """
        Set a value in cache with optional TTL and tags

        :param key: Cache key
        :param value: Value to cache
        :param ttl: Time-to-live in seconds
        :param tags: Optional cache tags for invalidation
        """
        try:
            serialized_value = json.dumps(value)
            self.redis_client.setex(key, ttl, serialized_value)

            # Add tags for cache invalidation
            if tags:
                for tag in tags:
                    self.redis_client.sadd(f"tag:{tag}", key)
        except Exception as e:
            print(f"Cache set failed: {e}")

    def get(self, key: str):
        """
        Get a value from cache

        :param key: Cache key
        :return: Deserialized value or None
        """
        try:
            value = self.redis_client.get(key)
            return json.loads(value) if value else None
        except Exception as e:
            print(f"Cache get failed: {e}")
            return None

    def delete(self, key: str):
        """
        Delete a specific key from cache

        :param key: Cache key to delete
        """
        self.redis_client.delete(key)

    def invalidate_by_tag(self, tag: str):
        """
        Invalidate cache entries by tag

        :param tag: Tag to invalidate
        """
        tag_key = f"tag:{tag}"
        keys = self.redis_client.smembers(tag_key)

        for key in keys:
            self.redis_client.delete(key)

        self.redis_client.delete(tag_key)

    def distributed_lock(self, lock_name: str, timeout: int = 60) -> Lock:
        """
        Create a distributed lock for cache consistency

        :param lock_name: Name of the lock
        :param timeout: Lock timeout in seconds
        :return: Redis lock object
        """
        return self.redis_client.lock(
            f"{self.lock_prefix}{lock_name}",
            timeout=timeout,
            blocking_timeout=10
        )

    def cached(self, ttl: int = 3600, tags: list = None):
        """
        Decorator for caching function results

        :param ttl: Time-to-live for cache entry
        :param tags: Optional tags for cache invalidation
        """
        def decorator(func: Callable):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                # Generate a unique cache key based on function and arguments
                cache_key = self._generate_cache_key(func, args, kwargs)

                # Try to get from cache first
                cached_result = self.get(cache_key)
                if cached_result is not None:
                    return cached_result

                # If not in cache, call the function
                result = func(*args, **kwargs)

                # Cache the result
                self.set(cache_key, result, ttl=ttl, tags=tags)

                return result
            return wrapper
        return decorator

    def _generate_cache_key(self, func: Callable, args: tuple, kwargs: dict) -> str:
        """
        Generate a unique cache key based on function and arguments

        :param func: Function being cached
        :param args: Function positional arguments
        :param kwargs: Function keyword arguments
        :return: Unique cache key
        """
        key_parts = [func.__module__, func.__name__]
        key_parts.extend(str(arg) for arg in args)
        key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
        return f"cache:{hash(''.join(key_parts))}"