"""Tests for Redis cache behavior, serialisation, and fallbacks."""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

from delivery_ml.cache import RedisFeatureCache
from delivery_ml.config import Settings


class FakeRedis:
    """Small deterministic in-memory Redis substitute used by unit tests."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.available = True

    def get(self, name: str) -> str | None:
        if not self.available:
            raise OSError("redis unavailable")
        return self.values.get(name)

    def setex(self, name: str, time: int, value: str) -> bool:
        if not self.available:
            raise OSError("redis unavailable")
        self.values[name] = value
        self.ttls[name] = time
        return True

    def delete(self, *names: str) -> int:
        for name in names:
            self.values.pop(name, None)
        return len(names)

    def ping(self) -> bool:
        if not self.available:
            raise OSError("redis unavailable")
        return True

    def close(self) -> None:
        return None


def test_feature_cache_uses_namespaced_keys_and_configured_ttl() -> None:
    """Zone feature reads round-trip through a deterministic namespaced Redis key."""
    client = FakeRedis()
    settings = Settings(redis_key_prefix="platform", redis_feature_ttl_seconds=90)
    cache = RedisFeatureCache(settings, client)
    zone_id = uuid4()
    timestamp = datetime(2026, 7, 18, 10, tzinfo=UTC)

    assert cache.set_zone_features(zone_id, timestamp, {"lag_1h": 10}) is True
    result = cache.get_zone_features(zone_id, timestamp)

    assert result.value == {"lag_1h": 10}
    assert result.source == "cache"
    assert client.ttls[f"platform:zone-features:{zone_id}:{timestamp.isoformat().replace(':', '_')}"] == 90


def test_cache_serializes_feature_scalars_and_falls_back_when_unavailable() -> None:
    """Date-like feature values serialize safely and source loaders survive Redis failure."""
    client = FakeRedis()
    cache = RedisFeatureCache(Settings(), client)
    key = "delivery-ml:test:feature"

    assert cache.set_json(key, {"day": date(2026, 7, 18), "amount": 2.5}, 60) is True
    assert cache.get_json(key).value == {"amount": 2.5, "day": "2026-07-18"}

    client.available = False
    calls = 0

    def loader() -> dict[str, int]:
        nonlocal calls
        calls += 1
        return {"demand": 12}

    result = cache.get_or_load_json(key, 60, loader)
    assert result == type(result)(value={"demand": 12}, source="fallback")
    assert calls == 1


def test_weather_holiday_and_invalidation_operations() -> None:
    """Dedicated context helpers use the expected TTLs and explicit invalidation."""
    client = FakeRedis()
    settings = Settings(redis_weather_ttl_seconds=45)
    cache = RedisFeatureCache(settings, client)
    zone_id = uuid4()
    observed_at = datetime(2026, 7, 18, 10, tzinfo=UTC)

    assert cache.set_weather(zone_id, observed_at, {"condition": "rain"}) is True
    assert cache.get_weather(zone_id, observed_at).value == {"condition": "rain"}
    assert cache.set_holiday("IN-KA", date(2026, 8, 15), {"is_holiday": True}) is True
    assert cache.get_holiday("IN-KA", date(2026, 8, 15)).value == {"is_holiday": True}
    assert cache.invalidate(*list(client.values)) is True
    assert client.values == {}
