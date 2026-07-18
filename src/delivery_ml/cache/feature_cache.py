"""Resilient Redis cache for point-in-time online feature data."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol, TypeVar, cast
from uuid import UUID

from redis import Redis

from delivery_ml.config import Settings
from delivery_ml.observability import get_logger

logger = get_logger(__name__)
ValueT = TypeVar("ValueT", bound=dict[str, Any])


class RedisClient(Protocol):
    """Subset of the Redis client required by the feature cache."""

    def get(self, name: str) -> str | None: ...

    def setex(self, name: str, time: int, value: str) -> bool | None: ...

    def delete(self, *names: str) -> int: ...

    def ping(self) -> bool: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class CacheRead:
    """A cache value and the layer that supplied it."""

    value: dict[str, Any] | None
    source: str


def _json_default(value: object) -> str | int | float | bool | None:
    """Encode common feature values without coupling the cache to pandas or NumPy."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    item = getattr(value, "item", None)
    if callable(item):
        scalar = item()
        if isinstance(scalar, (str, int, float, bool)) or scalar is None:
            return scalar
    raise TypeError(f"Unsupported cached value type: {type(value).__name__}")


class RedisFeatureCache:
    """Cache feature documents with safe failure semantics for inference paths.

    Redis failures never prevent the fallback loader from running. The caller receives the
    source that supplied a value so inference and observability can record cache behavior.
    """

    def __init__(self, settings: Settings, client: RedisClient | None = None) -> None:
        """Build the cache from runtime settings or inject a client for tests."""
        self._settings = settings
        resolved_client = Redis.from_url(
            settings.redis_url,
            socket_timeout=settings.redis_socket_timeout_seconds,
            decode_responses=True,
        )
        self._client: RedisClient = client if client is not None else cast(RedisClient, resolved_client)

    def close(self) -> None:
        """Close the underlying Redis connection pool during orderly shutdown."""
        self._client.close()

    def health_check(self) -> bool:
        """Return availability of the configured Redis deployment."""
        try:
            return bool(self._client.ping())
        except Exception:
            logger.warning("redis_health_check_failed", exc_info=True)
            return False

    def get_zone_features(self, zone_id: UUID, feature_timestamp: datetime) -> CacheRead:
        """Fetch a version-neutral zone feature vector at its point-in-time timestamp."""
        return self.get_json(self._key("zone-features", str(zone_id), feature_timestamp.isoformat()))

    def set_zone_features(
        self, zone_id: UUID, feature_timestamp: datetime, values: dict[str, Any]
    ) -> bool:
        """Cache a zone feature vector using the configured feature TTL."""
        return self.set_json(
            self._key("zone-features", str(zone_id), feature_timestamp.isoformat()),
            values,
            self._settings.redis_feature_ttl_seconds,
        )

    def get_weather(self, zone_id: UUID, observed_at: datetime) -> CacheRead:
        """Fetch a weather observation keyed by zone and observation timestamp."""
        return self.get_json(self._key("weather", str(zone_id), observed_at.isoformat()))

    def set_weather(self, zone_id: UUID, observed_at: datetime, values: dict[str, Any]) -> bool:
        """Cache weather using its shorter configurable freshness period."""
        return self.set_json(
            self._key("weather", str(zone_id), observed_at.isoformat()),
            values,
            self._settings.redis_weather_ttl_seconds,
        )

    def get_holiday(self, region_code: str, holiday_date: date) -> CacheRead:
        """Fetch a regional holiday flag and associated calendar metadata."""
        return self.get_json(self._key("holiday", region_code.lower(), holiday_date.isoformat()))

    def set_holiday(self, region_code: str, holiday_date: date, values: dict[str, Any]) -> bool:
        """Cache immutable holiday data with the standard feature TTL."""
        return self.set_json(
            self._key("holiday", region_code.lower(), holiday_date.isoformat()),
            values,
            self._settings.redis_feature_ttl_seconds,
        )

    def get_demand_features(self, zone_id: UUID, feature_timestamp: datetime) -> CacheRead:
        """Fetch demand-history feature values for a zone at a prediction cut-off."""
        return self.get_json(self._key("demand-features", str(zone_id), feature_timestamp.isoformat()))

    def set_demand_features(
        self, zone_id: UUID, feature_timestamp: datetime, values: dict[str, Any]
    ) -> bool:
        """Cache demand-history feature values with the configured feature TTL."""
        return self.set_json(
            self._key("demand-features", str(zone_id), feature_timestamp.isoformat()),
            values,
            self._settings.redis_feature_ttl_seconds,
        )

    def get_json(self, key: str) -> CacheRead:
        """Read and validate a JSON object, treating malformed data as a cache miss."""
        try:
            payload = self._client.get(key)
            if payload is None:
                return CacheRead(value=None, source="miss")
            decoded = json.loads(payload)
            if not isinstance(decoded, dict):
                raise ValueError("Cached payload is not a JSON object.")
            return CacheRead(value=decoded, source="cache")
        except Exception:
            logger.warning("redis_cache_read_failed", extra={"cache_key": key}, exc_info=True)
            return CacheRead(value=None, source="unavailable")

    def set_json(self, key: str, values: dict[str, Any], ttl_seconds: int) -> bool:
        """Serialize and cache a feature document, returning success without raising Redis errors."""
        try:
            payload = json.dumps(values, default=_json_default, separators=(",", ":"), sort_keys=True)
            self._client.setex(key, ttl_seconds, payload)
            return True
        except Exception:
            logger.warning("redis_cache_write_failed", extra={"cache_key": key}, exc_info=True)
            return False

    def get_or_load_json(
        self, key: str, ttl_seconds: int, loader: Callable[[], ValueT | None]
    ) -> CacheRead:
        """Read Redis first, then invoke a source-of-truth loader and refresh Redis on success."""
        cached = self.get_json(key)
        if cached.value is not None:
            return cached
        loaded = loader()
        if loaded is not None:
            self.set_json(key, loaded, ttl_seconds)
        return CacheRead(value=loaded, source="fallback")

    def invalidate(self, *keys: str) -> bool:
        """Invalidate explicit cache keys and return whether Redis accepted the command."""
        if not keys:
            return True
        try:
            self._client.delete(*keys)
            return True
        except Exception:
            logger.warning("redis_cache_invalidation_failed", extra={"cache_keys": list(keys)}, exc_info=True)
            return False

    def _key(self, category: str, *parts: str) -> str:
        """Build a collision-resistant, namespaced key from normalized components."""
        normalized = [part.replace(":", "_").strip() for part in parts]
        return ":".join((self._settings.redis_key_prefix, category, *normalized))
