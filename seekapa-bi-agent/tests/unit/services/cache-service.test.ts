import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { createMockCacheEntry } from '../../fixtures/test-data';

// Mock Redis
const mockRedisClient = {
  setex: vi.fn(),
  get: vi.fn(),
  delete: vi.fn(),
  sadd: vi.fn(),
  smembers: vi.fn(),
  lock: vi.fn(),
};

vi.mock('redis', () => ({
  default: {
    Redis: vi.fn(() => mockRedisClient),
  },
}));

// Import after mocking
import { RedisCache } from '../../../backend/app/services/cache_service';

describe('RedisCache', () => {
  let cache: RedisCache;

  beforeEach(() => {
    vi.clearAllMocks();
    cache = new RedisCache();
  });

  afterEach(() => {
    vi.resetAllMocks();
  });

  describe('set', () => {
    it('should set value with TTL', async () => {
      const key = 'test-key';
      const value = { data: 'test-value' };
      const ttl = 3600;

      await cache.set(key, value, ttl);

      expect(mockRedisClient.setex).toHaveBeenCalledWith(
        key,
        ttl,
        JSON.stringify(value)
      );
    });

    it('should set value with default TTL', async () => {
      const key = 'test-key';
      const value = { data: 'test-value' };

      await cache.set(key, value);

      expect(mockRedisClient.setex).toHaveBeenCalledWith(
        key,
        3600, // default TTL
        JSON.stringify(value)
      );
    });

    it('should set tags for cache invalidation', async () => {
      const key = 'test-key';
      const value = { data: 'test-value' };
      const tags = ['tag1', 'tag2'];

      await cache.set(key, value, 3600, tags);

      expect(mockRedisClient.sadd).toHaveBeenCalledWith('tag:tag1', key);
      expect(mockRedisClient.sadd).toHaveBeenCalledWith('tag:tag2', key);
    });

    it('should handle serialization errors gracefully', async () => {
      const key = 'test-key';
      const circularObj: any = {};
      circularObj.self = circularObj; // Create circular reference

      const consoleSpy = vi.spyOn(console, 'log').mockImplementation(() => {});

      await cache.set(key, circularObj);

      expect(consoleSpy).toHaveBeenCalledWith(
        expect.stringContaining('Cache set failed:')
      );

      consoleSpy.mockRestore();
    });
  });

  describe('get', () => {
    it('should get and deserialize value', async () => {
      const key = 'test-key';
      const value = { data: 'test-value' };
      mockRedisClient.get.mockResolvedValue(JSON.stringify(value));

      const result = await cache.get(key);

      expect(mockRedisClient.get).toHaveBeenCalledWith(key);
      expect(result).toEqual(value);
    });

    it('should return null when key does not exist', async () => {
      const key = 'non-existent-key';
      mockRedisClient.get.mockResolvedValue(null);

      const result = await cache.get(key);

      expect(result).toBeNull();
    });

    it('should handle deserialization errors gracefully', async () => {
      const key = 'test-key';
      mockRedisClient.get.mockResolvedValue('invalid-json{');

      const consoleSpy = vi.spyOn(console, 'log').mockImplementation(() => {});

      const result = await cache.get(key);

      expect(result).toBeNull();
      expect(consoleSpy).toHaveBeenCalledWith(
        expect.stringContaining('Cache get failed:')
      );

      consoleSpy.mockRestore();
    });
  });

  describe('delete', () => {
    it('should delete a key', async () => {
      const key = 'test-key';

      await cache.delete(key);

      expect(mockRedisClient.delete).toHaveBeenCalledWith(key);
    });
  });

  describe('invalidate_by_tag', () => {
    it('should invalidate all keys with given tag', async () => {
      const tag = 'test-tag';
      const keys = ['key1', 'key2', 'key3'];
      mockRedisClient.smembers.mockResolvedValue(keys);

      await cache.invalidate_by_tag(tag);

      expect(mockRedisClient.smembers).toHaveBeenCalledWith(`tag:${tag}`);
      expect(mockRedisClient.delete).toHaveBeenCalledWith('key1');
      expect(mockRedisClient.delete).toHaveBeenCalledWith('key2');
      expect(mockRedisClient.delete).toHaveBeenCalledWith('key3');
      expect(mockRedisClient.delete).toHaveBeenCalledWith(`tag:${tag}`);
    });

    it('should handle empty tag set', async () => {
      const tag = 'empty-tag';
      mockRedisClient.smembers.mockResolvedValue([]);

      await cache.invalidate_by_tag(tag);

      expect(mockRedisClient.smembers).toHaveBeenCalledWith(`tag:${tag}`);
      expect(mockRedisClient.delete).toHaveBeenCalledWith(`tag:${tag}`);
    });
  });

  describe('distributed_lock', () => {
    it('should create distributed lock with default timeout', async () => {
      const lockName = 'test-lock';
      const mockLock = { acquire: vi.fn(), release: vi.fn() };
      mockRedisClient.lock.mockReturnValue(mockLock);

      const lock = cache.distributed_lock(lockName);

      expect(mockRedisClient.lock).toHaveBeenCalledWith(
        `lock:${lockName}`,
        {
          timeout: 60,
          blocking_timeout: 10,
        }
      );
      expect(lock).toBe(mockLock);
    });

    it('should create distributed lock with custom timeout', async () => {
      const lockName = 'test-lock';
      const timeout = 120;
      const mockLock = { acquire: vi.fn(), release: vi.fn() };
      mockRedisClient.lock.mockReturnValue(mockLock);

      const lock = cache.distributed_lock(lockName, timeout);

      expect(mockRedisClient.lock).toHaveBeenCalledWith(
        `lock:${lockName}`,
        {
          timeout,
          blocking_timeout: 10,
        }
      );
    });
  });

  describe('cached decorator', () => {
    it('should cache function result', async () => {
      const testFunction = vi.fn().mockResolvedValue('function-result');
      const cachedFunction = cache.cached()(testFunction);

      mockRedisClient.get.mockResolvedValue(null); // Cache miss

      const result = await cachedFunction('arg1', 'arg2');

      expect(testFunction).toHaveBeenCalledWith('arg1', 'arg2');
      expect(result).toBe('function-result');
      expect(mockRedisClient.setex).toHaveBeenCalled();
    });

    it('should return cached result on cache hit', async () => {
      const testFunction = vi.fn().mockResolvedValue('function-result');
      const cachedFunction = cache.cached()(testFunction);
      const cachedValue = 'cached-result';

      mockRedisClient.get.mockResolvedValue(JSON.stringify(cachedValue));

      const result = await cachedFunction('arg1', 'arg2');

      expect(testFunction).not.toHaveBeenCalled();
      expect(result).toBe(cachedValue);
    });

    it('should use custom TTL and tags', async () => {
      const testFunction = vi.fn().mockResolvedValue('function-result');
      const ttl = 1800;
      const tags = ['test-tag'];
      const cachedFunction = cache.cached(ttl, tags)(testFunction);

      mockRedisClient.get.mockResolvedValue(null); // Cache miss

      await cachedFunction('arg1');

      expect(mockRedisClient.setex).toHaveBeenCalledWith(
        expect.any(String),
        ttl,
        JSON.stringify('function-result')
      );
      expect(mockRedisClient.sadd).toHaveBeenCalledWith('tag:test-tag', expect.any(String));
    });
  });

  describe('warm_cache', () => {
    it('should pre-load data into cache', async () => {
      const keyPrefix = 'users';
      const testData = [
        { id: '1', name: 'User 1' },
        { id: '2', name: 'User 2' },
      ];
      const dataLoader = vi.fn().mockReturnValue(testData);

      await cache.warm_cache(keyPrefix, dataLoader);

      expect(dataLoader).toHaveBeenCalled();
      expect(mockRedisClient.setex).toHaveBeenCalledWith(
        'users:1',
        3600,
        JSON.stringify({ id: '1', name: 'User 1' })
      );
      expect(mockRedisClient.setex).toHaveBeenCalledWith(
        'users:2',
        3600,
        JSON.stringify({ id: '2', name: 'User 2' })
      );
    });

    it('should handle data loader errors', async () => {
      const keyPrefix = 'users';
      const dataLoader = vi.fn().mockImplementation(() => {
        throw new Error('Data loader failed');
      });

      const consoleSpy = vi.spyOn(console, 'log').mockImplementation(() => {});

      await cache.warm_cache(keyPrefix, dataLoader);

      expect(consoleSpy).toHaveBeenCalledWith(
        expect.stringContaining('Cache warming failed:')
      );

      consoleSpy.mockRestore();
    });
  });

  describe('_generate_cache_key', () => {
    it('should generate consistent cache keys', () => {
      const testFunction = () => {};
      testFunction.__module__ = 'test.module';
      testFunction.__name__ = 'testFunction';

      const args = ['arg1', 'arg2'];
      const kwargs = { key1: 'value1', key2: 'value2' };

      const key1 = cache._generate_cache_key(testFunction, args, kwargs);
      const key2 = cache._generate_cache_key(testFunction, args, kwargs);

      expect(key1).toBe(key2);
      expect(key1).toMatch(/^cache:/);
    });

    it('should generate different keys for different arguments', () => {
      const testFunction = () => {};
      testFunction.__module__ = 'test.module';
      testFunction.__name__ = 'testFunction';

      const key1 = cache._generate_cache_key(testFunction, ['arg1'], {});
      const key2 = cache._generate_cache_key(testFunction, ['arg2'], {});

      expect(key1).not.toBe(key2);
    });
  });

  describe('integration tests', () => {
    it('should work end-to-end with real-like scenarios', async () => {
      // Simulate setting and getting complex data
      const complexData = createMockCacheEntry({
        value: {
          users: [
            { id: 1, name: 'John', preferences: { theme: 'dark' } },
            { id: 2, name: 'Jane', preferences: { theme: 'light' } },
          ],
          metadata: {
            totalCount: 2,
            lastUpdated: new Date().toISOString(),
          },
        },
      });

      mockRedisClient.get.mockResolvedValue(null).mockResolvedValueOnce(null);

      // Set data
      await cache.set(complexData.key, complexData.value, complexData.ttl, complexData.tags);

      // Mock successful get
      mockRedisClient.get.mockResolvedValue(JSON.stringify(complexData.value));

      // Get data
      const result = await cache.get(complexData.key);

      expect(result).toEqual(complexData.value);
    });

    it('should handle concurrent access patterns', async () => {
      const promises = [];

      // Simulate multiple concurrent operations
      for (let i = 0; i < 10; i++) {
        promises.push(
          cache.set(`key-${i}`, { value: i }, 3600, [`tag-${i % 3}`])
        );
      }

      await Promise.all(promises);

      // Verify all operations were attempted
      expect(mockRedisClient.setex).toHaveBeenCalledTimes(10);
      expect(mockRedisClient.sadd).toHaveBeenCalledTimes(10);
    });
  });
});