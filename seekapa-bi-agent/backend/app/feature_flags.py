"""
Feature flags management system for Seekapa BI Agent.
Supports multiple providers: LaunchDarkly, Split.io, and custom implementation.
"""

import os
import json
import hashlib
from typing import Any, Dict, Optional, Union, List
from enum import Enum
from datetime import datetime, timedelta
from functools import wraps
import asyncio

import redis
from pydantic import BaseModel, Field
from fastapi import HTTPException, Request
import ldclient
from ldclient.config import Config as LDConfig
from splitio import get_factory
from splitio.exceptions import TimeoutException
import logging

from .monitoring.metrics import feature_flag_evaluations

logger = logging.getLogger(__name__)


class FeatureFlagProvider(Enum):
    """Supported feature flag providers."""
    LAUNCHDARKLY = "launchdarkly"
    SPLIT_IO = "split_io"
    CUSTOM = "custom"
    REDIS = "redis"


class FeatureFlagConfig(BaseModel):
    """Configuration for feature flags."""
    provider: FeatureFlagProvider = FeatureFlagProvider.CUSTOM
    launchdarkly_sdk_key: Optional[str] = Field(None, env="LAUNCHDARKLY_SDK_KEY")
    split_io_sdk_key: Optional[str] = Field(None, env="SPLIT_IO_SDK_KEY")
    redis_url: str = Field("redis://localhost:6379", env="REDIS_URL")
    cache_ttl: int = Field(300, description="Cache TTL in seconds")
    default_percentage_rollout: int = Field(0, ge=0, le=100)
    environment: str = Field("production", env="ENVIRONMENT")


class FeatureFlag(BaseModel):
    """Feature flag model."""
    name: str
    enabled: bool = False
    description: Optional[str] = None
    rollout_percentage: int = Field(0, ge=0, le=100)
    user_whitelist: List[str] = Field(default_factory=list)
    user_blacklist: List[str] = Field(default_factory=list)
    conditions: Dict[str, Any] = Field(default_factory=dict)
    variants: Optional[Dict[str, Any]] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None


class FeatureFlagService:
    """Service for managing feature flags."""

    def __init__(self, config: FeatureFlagConfig):
        self.config = config
        self.provider = config.provider
        self._redis_client = None
        self._ld_client = None
        self._split_factory = None
        self._cache = {}
        self._initialize_provider()

    def _initialize_provider(self):
        """Initialize the configured feature flag provider."""
        try:
            if self.provider == FeatureFlagProvider.LAUNCHDARKLY:
                self._initialize_launchdarkly()
            elif self.provider == FeatureFlagProvider.SPLIT_IO:
                self._initialize_split_io()
            elif self.provider == FeatureFlagProvider.REDIS:
                self._initialize_redis()
            else:  # CUSTOM provider
                logger.info("Using custom feature flag implementation")
        except Exception as e:
            logger.error(f"Failed to initialize feature flag provider: {e}")
            # Fall back to custom implementation
            self.provider = FeatureFlagProvider.CUSTOM

    def _initialize_launchdarkly(self):
        """Initialize LaunchDarkly client."""
        if not self.config.launchdarkly_sdk_key:
            raise ValueError("LaunchDarkly SDK key not configured")

        ld_config = LDConfig(
            sdk_key=self.config.launchdarkly_sdk_key,
            connect_timeout=10,
            read_timeout=10,
            offline=self.config.environment == "test"
        )

        ldclient.set_config(ld_config)
        self._ld_client = ldclient.get()

        if not self._ld_client.is_initialized():
            raise RuntimeError("LaunchDarkly client failed to initialize")

        logger.info("LaunchDarkly client initialized successfully")

    def _initialize_split_io(self):
        """Initialize Split.io client."""
        if not self.config.split_io_sdk_key:
            raise ValueError("Split.io SDK key not configured")

        factory = get_factory(
            self.config.split_io_sdk_key,
            config={
                'impressionsMode': 'OPTIMIZED',
                'impressionsRefreshRate': 60,
                'impressionsQueueSize': 10000,
                'metricsRefreshRate': 60,
                'ready': 10000
            }
        )

        try:
            factory.block_until_ready(5)
        except TimeoutException:
            logger.warning("Split.io initialization timeout, continuing anyway")

        self._split_factory = factory
        logger.info("Split.io client initialized successfully")

    def _initialize_redis(self):
        """Initialize Redis client for custom flags."""
        self._redis_client = redis.from_url(
            self.config.redis_url,
            decode_responses=True
        )
        self._redis_client.ping()
        logger.info("Redis client initialized for feature flags")

    def evaluate(
        self,
        flag_name: str,
        user_context: Optional[Dict[str, Any]] = None,
        default_value: Any = False
    ) -> Any:
        """
        Evaluate a feature flag for a given user context.

        Args:
            flag_name: Name of the feature flag
            user_context: User context for evaluation
            default_value: Default value if flag evaluation fails

        Returns:
            The evaluated flag value
        """
        try:
            # Check cache first
            cache_key = self._get_cache_key(flag_name, user_context)
            if cache_key in self._cache:
                cached_result = self._cache[cache_key]
                if cached_result['expires'] > datetime.utcnow():
                    result = cached_result['value']
                    self._track_evaluation(flag_name, result)
                    return result

            # Evaluate based on provider
            if self.provider == FeatureFlagProvider.LAUNCHDARKLY:
                result = self._evaluate_launchdarkly(flag_name, user_context, default_value)
            elif self.provider == FeatureFlagProvider.SPLIT_IO:
                result = self._evaluate_split_io(flag_name, user_context, default_value)
            elif self.provider == FeatureFlagProvider.REDIS:
                result = self._evaluate_redis(flag_name, user_context, default_value)
            else:
                result = self._evaluate_custom(flag_name, user_context, default_value)

            # Cache the result
            self._cache[cache_key] = {
                'value': result,
                'expires': datetime.utcnow() + timedelta(seconds=self.config.cache_ttl)
            }

            self._track_evaluation(flag_name, result)
            return result

        except Exception as e:
            logger.error(f"Error evaluating feature flag {flag_name}: {e}")
            self._track_evaluation(flag_name, default_value)
            return default_value

    def _evaluate_launchdarkly(
        self,
        flag_name: str,
        user_context: Optional[Dict[str, Any]],
        default_value: Any
    ) -> Any:
        """Evaluate flag using LaunchDarkly."""
        if not self._ld_client:
            return default_value

        user = self._build_ld_user(user_context)
        return self._ld_client.variation(flag_name, user, default_value)

    def _evaluate_split_io(
        self,
        flag_name: str,
        user_context: Optional[Dict[str, Any]],
        default_value: Any
    ) -> Any:
        """Evaluate flag using Split.io."""
        if not self._split_factory:
            return default_value

        client = self._split_factory.client()
        user_key = user_context.get('user_id', 'anonymous') if user_context else 'anonymous'

        treatment = client.get_treatment(user_key, flag_name, user_context)

        # Convert Split.io treatments to boolean
        if treatment == "on":
            return True
        elif treatment == "off":
            return False
        else:
            return default_value

    def _evaluate_redis(
        self,
        flag_name: str,
        user_context: Optional[Dict[str, Any]],
        default_value: Any
    ) -> Any:
        """Evaluate flag using Redis-stored custom flags."""
        if not self._redis_client:
            return default_value

        flag_key = f"feature_flag:{flag_name}"
        flag_data = self._redis_client.get(flag_key)

        if not flag_data:
            return default_value

        try:
            flag = FeatureFlag(**json.loads(flag_data))
            return self._evaluate_flag_logic(flag, user_context)
        except Exception as e:
            logger.error(f"Error parsing flag data from Redis: {e}")
            return default_value

    def _evaluate_custom(
        self,
        flag_name: str,
        user_context: Optional[Dict[str, Any]],
        default_value: Any
    ) -> Any:
        """Evaluate flag using custom logic."""
        # Define custom flags here
        custom_flags = {
            "new_dashboard": {
                "enabled": True,
                "rollout_percentage": 50,
                "user_whitelist": ["admin@seekapa.com"]
            },
            "ai_insights": {
                "enabled": True,
                "rollout_percentage": 100,
                "conditions": {"plan": ["pro", "enterprise"]}
            },
            "experimental_api": {
                "enabled": False,
                "rollout_percentage": 10,
                "user_whitelist": []
            },
            "dark_mode": {
                "enabled": True,
                "rollout_percentage": 100
            },
            "advanced_analytics": {
                "enabled": True,
                "conditions": {"plan": ["enterprise"]}
            }
        }

        flag_config = custom_flags.get(flag_name)
        if not flag_config:
            return default_value

        flag = FeatureFlag(name=flag_name, **flag_config)
        return self._evaluate_flag_logic(flag, user_context)

    def _evaluate_flag_logic(
        self,
        flag: FeatureFlag,
        user_context: Optional[Dict[str, Any]]
    ) -> bool:
        """Evaluate custom flag logic."""
        if not flag.enabled:
            return False

        # Check if flag has expired
        if flag.expires_at and flag.expires_at < datetime.utcnow():
            return False

        user_id = user_context.get('user_id') if user_context else None
        user_email = user_context.get('email') if user_context else None

        # Check blacklist
        if user_id and user_id in flag.user_blacklist:
            return False
        if user_email and user_email in flag.user_blacklist:
            return False

        # Check whitelist
        if flag.user_whitelist:
            if user_id and user_id in flag.user_whitelist:
                return True
            if user_email and user_email in flag.user_whitelist:
                return True
            # If whitelist exists but user not in it, and no other conditions
            if not flag.conditions and flag.rollout_percentage == 0:
                return False

        # Check conditions
        if flag.conditions and user_context:
            for key, expected_values in flag.conditions.items():
                user_value = user_context.get(key)
                if user_value not in expected_values:
                    return False

        # Check percentage rollout
        if flag.rollout_percentage > 0:
            if flag.rollout_percentage >= 100:
                return True

            # Use consistent hashing for stable rollout
            if user_id:
                hash_input = f"{flag.name}:{user_id}"
                hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
                user_bucket = hash_value % 100
                return user_bucket < flag.rollout_percentage

        return False

    def _build_ld_user(self, user_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Build LaunchDarkly user object from context."""
        if not user_context:
            return {"key": "anonymous"}

        return {
            "key": str(user_context.get("user_id", "anonymous")),
            "email": user_context.get("email"),
            "name": user_context.get("name"),
            "custom": {
                k: v for k, v in user_context.items()
                if k not in ["user_id", "email", "name"]
            }
        }

    def _get_cache_key(
        self,
        flag_name: str,
        user_context: Optional[Dict[str, Any]]
    ) -> str:
        """Generate cache key for flag evaluation."""
        if not user_context:
            return f"flag:{flag_name}:anonymous"

        user_id = user_context.get("user_id", "anonymous")
        return f"flag:{flag_name}:{user_id}"

    def _track_evaluation(self, flag_name: str, result: Any):
        """Track feature flag evaluation metrics."""
        try:
            feature_flag_evaluations.labels(
                flag_name=flag_name,
                result=str(result)
            ).inc()
        except Exception as e:
            logger.error(f"Failed to track feature flag evaluation: {e}")

    async def create_flag(self, flag: FeatureFlag) -> bool:
        """Create a new feature flag (Redis provider only)."""
        if self.provider != FeatureFlagProvider.REDIS:
            raise NotImplementedError(
                "Flag creation only supported for Redis provider"
            )

        try:
            flag_key = f"feature_flag:{flag.name}"
            flag_data = flag.json()
            self._redis_client.set(flag_key, flag_data)
            self._invalidate_cache(flag.name)
            return True
        except Exception as e:
            logger.error(f"Failed to create flag: {e}")
            return False

    async def update_flag(self, flag_name: str, updates: Dict[str, Any]) -> bool:
        """Update an existing feature flag (Redis provider only)."""
        if self.provider != FeatureFlagProvider.REDIS:
            raise NotImplementedError(
                "Flag updates only supported for Redis provider"
            )

        try:
            flag_key = f"feature_flag:{flag_name}"
            flag_data = self._redis_client.get(flag_key)

            if not flag_data:
                return False

            flag = FeatureFlag(**json.loads(flag_data))

            for key, value in updates.items():
                if hasattr(flag, key):
                    setattr(flag, key, value)

            flag.updated_at = datetime.utcnow()
            self._redis_client.set(flag_key, flag.json())
            self._invalidate_cache(flag_name)
            return True
        except Exception as e:
            logger.error(f"Failed to update flag: {e}")
            return False

    async def delete_flag(self, flag_name: str) -> bool:
        """Delete a feature flag (Redis provider only)."""
        if self.provider != FeatureFlagProvider.REDIS:
            raise NotImplementedError(
                "Flag deletion only supported for Redis provider"
            )

        try:
            flag_key = f"feature_flag:{flag_name}"
            result = self._redis_client.delete(flag_key)
            self._invalidate_cache(flag_name)
            return result > 0
        except Exception as e:
            logger.error(f"Failed to delete flag: {e}")
            return False

    def _invalidate_cache(self, flag_name: str):
        """Invalidate cache entries for a specific flag."""
        keys_to_delete = [
            key for key in self._cache.keys()
            if key.startswith(f"flag:{flag_name}:")
        ]
        for key in keys_to_delete:
            del self._cache[key]

    async def get_all_flags(self) -> List[FeatureFlag]:
        """Get all feature flags (Redis provider only)."""
        if self.provider != FeatureFlagProvider.REDIS:
            raise NotImplementedError(
                "Listing flags only supported for Redis provider"
            )

        try:
            pattern = "feature_flag:*"
            keys = self._redis_client.keys(pattern)
            flags = []

            for key in keys:
                flag_data = self._redis_client.get(key)
                if flag_data:
                    flags.append(FeatureFlag(**json.loads(flag_data)))

            return flags
        except Exception as e:
            logger.error(f"Failed to get all flags: {e}")
            return []

    def close(self):
        """Clean up resources."""
        try:
            if self._ld_client:
                self._ld_client.close()
            if self._split_factory:
                self._split_factory.destroy()
            if self._redis_client:
                self._redis_client.close()
        except Exception as e:
            logger.error(f"Error closing feature flag service: {e}")


# FastAPI dependency
_feature_flag_service = None


def get_feature_flag_service() -> FeatureFlagService:
    """Get or create feature flag service instance."""
    global _feature_flag_service
    if _feature_flag_service is None:
        config = FeatureFlagConfig()
        _feature_flag_service = FeatureFlagService(config)
    return _feature_flag_service


def feature_flag_required(flag_name: str, default_value: bool = False):
    """
    Decorator for endpoints that require a feature flag to be enabled.

    Usage:
        @app.get("/experimental")
        @feature_flag_required("experimental_api")
        async def experimental_endpoint():
            return {"message": "This is experimental"}
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            service = get_feature_flag_service()

            # Build user context from request
            user_context = {}
            if hasattr(request.state, "user"):
                user_context = {
                    "user_id": request.state.user.id,
                    "email": request.state.user.email,
                    "plan": request.state.user.plan
                }

            # Evaluate feature flag
            is_enabled = service.evaluate(flag_name, user_context, default_value)

            if not is_enabled:
                raise HTTPException(
                    status_code=403,
                    detail=f"Feature '{flag_name}' is not enabled for this user"
                )

            return await func(request, *args, **kwargs)
        return wrapper
    return decorator


def get_variant(flag_name: str, user_context: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """
    Get variant for A/B testing.

    Args:
        flag_name: Name of the feature flag
        user_context: User context for evaluation

    Returns:
        Variant name or None
    """
    service = get_feature_flag_service()
    return service.evaluate(f"{flag_name}_variant", user_context, None)