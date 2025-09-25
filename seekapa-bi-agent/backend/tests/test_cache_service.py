"""
Tests for cache service.
"""
import pytest
import json
from unittest.mock import Mock, patch, call
import asyncio

from app.services.cache_service import RedisCache


class TestRedisCache:
    """Test RedisCache functionality."""

    @pytest.mark.unit
    @pytest.mark.cache
    def test_cache_initialization(self, mock_redis):
        """Test cache service initialization."""
        cache = RedisCache(
            host='test-host',
            port=6380,
            db=1,
            password='test-password'
        )
        cache.redis_client = mock_redis

        assert cache.redis_client == mock_redis
        assert cache.lock_prefix == 'lock:'

    @pytest.mark.unit
    @pytest.mark.cache
    def test_set_value_with_default_ttl(self, cache_service):
        """Test setting a value with default TTL."""
        key = 'test:key'
        value = {'data': 'test_value', 'number': 42}

        cache_service.set(key, value)

        cache_service.redis_client.setex.assert_called_once_with(
            key, 3600, json.dumps(value)
        )

    @pytest.mark.unit
    @pytest.mark.cache
    def test_set_value_with_custom_ttl(self, cache_service):
        """Test setting a value with custom TTL."""
        key = 'test:key'
        value = {'data': 'test_value'}
        ttl = 1800

        cache_service.set(key, value, ttl)

        cache_service.redis_client.setex.assert_called_once_with(
            key, ttl, json.dumps(value)
        )

    @pytest.mark.unit
    @pytest.mark.cache
    def test_set_value_with_tags(self, cache_service):
        """Test setting a value with cache tags."""
        key = 'test:key'
        value = {'data': 'test_value'}
        ttl = 3600
        tags = ['users', 'active']

        cache_service.set(key, value, ttl, tags)

        # Check that value was set
        cache_service.redis_client.setex.assert_called_once_with(
            key, ttl, json.dumps(value)
        )

        # Check that tags were added
        expected_calls = [
            call('tag:users', key),
            call('tag:active', key)
        ]
        cache_service.redis_client.sadd.assert_has_calls(expected_calls)

    @pytest.mark.unit
    @pytest.mark.cache
    def test_get_existing_value(self, cache_service):
        """Test getting an existing value from cache."""
        key = 'test:key'
        cached_value = {'data': 'test_value', 'number': 42}
        cache_service.redis_client.get.return_value = json.dumps(cached_value)

        result = cache_service.get(key)

        cache_service.redis_client.get.assert_called_once_with(key)
        assert result == cached_value

    @pytest.mark.unit
    @pytest.mark.cache
    def test_get_non_existent_value(self, cache_service):
        """Test getting a non-existent value from cache."""
        key = 'non:existent'
        cache_service.redis_client.get.return_value = None

        result = cache_service.get(key)

        cache_service.redis_client.get.assert_called_once_with(key)
        assert result is None

    @pytest.mark.unit
    @pytest.mark.cache
    def test_get_invalid_json(self, cache_service):
        """Test handling invalid JSON in cache."""
        key = 'test:key'
        cache_service.redis_client.get.return_value = 'invalid-json{'

        with patch('builtins.print') as mock_print:
            result = cache_service.get(key)

        assert result is None
        mock_print.assert_called()
        assert 'Cache get failed:' in str(mock_print.call_args)

    @pytest.mark.unit
    @pytest.mark.cache
    def test_delete_key(self, cache_service):
        """Test deleting a key from cache."""
        key = 'test:key'

        cache_service.delete(key)

        cache_service.redis_client.delete.assert_called_once_with(key)

    @pytest.mark.unit
    @pytest.mark.cache
    def test_invalidate_by_tag(self, cache_service):
        """Test invalidating cache entries by tag."""
        tag = 'users'
        keys = ['user:1', 'user:2', 'user:3']
        cache_service.redis_client.smembers.return_value = keys

        cache_service.invalidate_by_tag(tag)

        # Check that tag keys were retrieved
        cache_service.redis_client.smembers.assert_called_once_with('tag:users')

        # Check that all keys were deleted
        expected_delete_calls = [call(key) for key in keys] + [call('tag:users')]
        cache_service.redis_client.delete.assert_has_calls(expected_delete_calls)

    @pytest.mark.unit
    @pytest.mark.cache
    def test_invalidate_by_empty_tag(self, cache_service):
        """Test invalidating by tag with no associated keys."""
        tag = 'empty_tag'
        cache_service.redis_client.smembers.return_value = []

        cache_service.invalidate_by_tag(tag)

        cache_service.redis_client.smembers.assert_called_once_with('tag:empty_tag')
        cache_service.redis_client.delete.assert_called_once_with('tag:empty_tag')

    @pytest.mark.unit
    @pytest.mark.cache
    def test_distributed_lock_default_timeout(self, cache_service):
        """Test creating distributed lock with default timeout."""
        lock_name = 'test_lock'
        mock_lock = Mock()
        cache_service.redis_client.lock.return_value = mock_lock

        result = cache_service.distributed_lock(lock_name)

        cache_service.redis_client.lock.assert_called_once_with(
            'lock:test_lock',
            timeout=60,
            blocking_timeout=10
        )
        assert result == mock_lock

    @pytest.mark.unit
    @pytest.mark.cache
    def test_distributed_lock_custom_timeout(self, cache_service):
        """Test creating distributed lock with custom timeout."""
        lock_name = 'test_lock'
        timeout = 120
        mock_lock = Mock()
        cache_service.redis_client.lock.return_value = mock_lock

        result = cache_service.distributed_lock(lock_name, timeout)

        cache_service.redis_client.lock.assert_called_once_with(
            'lock:test_lock',
            timeout=timeout,
            blocking_timeout=10
        )
        assert result == mock_lock

    @pytest.mark.unit
    @pytest.mark.cache
    def test_cached_decorator_cache_miss(self, cache_service):
        """Test cached decorator with cache miss."""
        # Mock cache miss
        cache_service.redis_client.get.return_value = None

        @cache_service.cached(ttl=1800, tags=['test'])
        def test_function(arg1, arg2):
            return f"result_{arg1}_{arg2}"

        result = test_function('hello', 'world')

        assert result == "result_hello_world"

        # Check that get was called to check cache
        cache_service.redis_client.get.assert_called()

        # Check that set was called to cache the result
        cache_service.redis_client.setex.assert_called()

    @pytest.mark.unit
    @pytest.mark.cache
    def test_cached_decorator_cache_hit(self, cache_service):
        """Test cached decorator with cache hit."""
        cached_result = "cached_result"
        cache_service.redis_client.get.return_value = json.dumps(cached_result)

        call_count = 0

        @cache_service.cached()
        def test_function(arg):
            nonlocal call_count
            call_count += 1
            return f"fresh_result_{arg}"

        result = test_function('test')

        assert result == cached_result
        assert call_count == 0  # Function should not be called
        cache_service.redis_client.get.assert_called()
        cache_service.redis_client.setex.assert_not_called()

    @pytest.mark.unit
    @pytest.mark.cache
    def test_cached_decorator_with_different_args(self, cache_service):
        """Test cached decorator generates different keys for different arguments."""
        cache_service.redis_client.get.return_value = None

        @cache_service.cached()
        def test_function(arg1, arg2=None):
            return f"result_{arg1}_{arg2}"

        # Call with different arguments
        test_function('arg1', 'arg2')
        test_function('different', arg2='args')

        # Should have been called twice with different cache keys
        assert cache_service.redis_client.get.call_count == 2

        # Get the cache keys that were used
        get_calls = cache_service.redis_client.get.call_args_list
        key1 = get_calls[0][0][0]
        key2 = get_calls[1][0][0]

        # Keys should be different
        assert key1 != key2
        assert key1.startswith('cache:')
        assert key2.startswith('cache:')

    @pytest.mark.unit
    @pytest.mark.cache
    def test_warm_cache_success(self, cache_service):
        """Test successful cache warming."""
        key_prefix = 'users'
        test_data = [
            {'id': '1', 'name': 'User 1'},
            {'id': '2', 'name': 'User 2'},
            {'id': '3', 'name': 'User 3'}
        ]

        def data_loader():
            return test_data

        cache_service.warm_cache(key_prefix, data_loader)

        # Check that each item was cached
        expected_calls = [
            call('users:1', 3600, json.dumps({'id': '1', 'name': 'User 1'})),
            call('users:2', 3600, json.dumps({'id': '2', 'name': 'User 2'})),
            call('users:3', 3600, json.dumps({'id': '3', 'name': 'User 3'}))
        ]
        cache_service.redis_client.setex.assert_has_calls(expected_calls)

    @pytest.mark.unit
    @pytest.mark.cache
    def test_warm_cache_data_loader_exception(self, cache_service):
        """Test cache warming with data loader exception."""
        key_prefix = 'users'

        def failing_data_loader():
            raise Exception("Data loading failed")

        with patch('builtins.print') as mock_print:
            cache_service.warm_cache(key_prefix, failing_data_loader)

        mock_print.assert_called()
        assert 'Cache warming failed:' in str(mock_print.call_args)
        cache_service.redis_client.setex.assert_not_called()

    @pytest.mark.unit
    @pytest.mark.cache
    def test_generate_cache_key_consistency(self, cache_service):
        """Test that cache key generation is consistent."""
        def test_function():
            pass

        test_function.__module__ = 'test.module'
        test_function.__name__ = 'test_function'

        # Generate keys with same arguments
        key1 = cache_service._generate_cache_key(test_function, ('arg1', 'arg2'), {'kwarg1': 'value1'})
        key2 = cache_service._generate_cache_key(test_function, ('arg1', 'arg2'), {'kwarg1': 'value1'})

        assert key1 == key2
        assert key1.startswith('cache:')

    @pytest.mark.unit
    @pytest.mark.cache
    def test_generate_cache_key_different_args(self, cache_service):
        """Test that cache key generation creates different keys for different arguments."""
        def test_function():
            pass

        test_function.__module__ = 'test.module'
        test_function.__name__ = 'test_function'

        key1 = cache_service._generate_cache_key(test_function, ('arg1',), {})
        key2 = cache_service._generate_cache_key(test_function, ('arg2',), {})
        key3 = cache_service._generate_cache_key(test_function, ('arg1',), {'kwarg': 'value'})

        assert key1 != key2
        assert key1 != key3
        assert key2 != key3

    @pytest.mark.unit
    @pytest.mark.cache
    def test_set_serialization_error(self, cache_service):
        """Test handling serialization errors during set operation."""
        key = 'test:key'
        # Create circular reference that can't be serialized
        circular_obj = {}
        circular_obj['self'] = circular_obj

        with patch('builtins.print') as mock_print:
            cache_service.set(key, circular_obj)

        mock_print.assert_called()
        assert 'Cache set failed:' in str(mock_print.call_args)

    @pytest.mark.integration
    @pytest.mark.cache
    def test_cache_workflow_integration(self, cache_service):
        """Test complete cache workflow integration."""
        # Set up mock responses for a complete workflow
        key = 'workflow:test'
        value = {'step': 'complete', 'data': [1, 2, 3]}
        tags = ['workflow', 'test']

        # Test setting value
        cache_service.set(key, value, ttl=1800, tags=tags)

        # Verify set operation
        cache_service.redis_client.setex.assert_called_with(
            key, 1800, json.dumps(value)
        )
        cache_service.redis_client.sadd.assert_any_call('tag:workflow', key)
        cache_service.redis_client.sadd.assert_any_call('tag:test', key)

        # Mock getting the value back
        cache_service.redis_client.get.return_value = json.dumps(value)
        result = cache_service.get(key)
        assert result == value

        # Test invalidating by tag
        cache_service.redis_client.smembers.return_value = [key]
        cache_service.invalidate_by_tag('workflow')

        # Verify invalidation
        cache_service.redis_client.delete.assert_any_call(key)
        cache_service.redis_client.delete.assert_any_call('tag:workflow')

    @pytest.mark.unit
    @pytest.mark.cache
    def test_cache_with_complex_objects(self, cache_service):
        """Test caching complex nested objects."""
        complex_object = {
            'users': [
                {
                    'id': 1,
                    'name': 'John Doe',
                    'profile': {
                        'age': 30,
                        'preferences': {
                            'theme': 'dark',
                            'notifications': ['email', 'push'],
                            'settings': {
                                'language': 'en',
                                'timezone': 'UTC'
                            }
                        }
                    }
                }
            ],
            'metadata': {
                'total_count': 1,
                'last_updated': '2024-01-15T10:30:00Z',
                'version': '1.0'
            }
        }

        key = 'complex:object'
        cache_service.set(key, complex_object)

        # Verify the object was serialized and stored
        cache_service.redis_client.setex.assert_called_with(
            key, 3600, json.dumps(complex_object)
        )

        # Mock retrieval
        cache_service.redis_client.get.return_value = json.dumps(complex_object)
        result = cache_service.get(key)

        assert result == complex_object
        assert result['users'][0]['profile']['preferences']['theme'] == 'dark'