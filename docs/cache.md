# Cache module

`RedisFeatureCache` provides resilient Redis access for online inference. It stores JSON
objects under a configurable `REDIS_KEY_PREFIX` and separates zone features, weather,
holiday, and demand-history keys. Feature and weather TTLs come from the corresponding
environment settings.

Use `get_or_load_json()` at an inference boundary: it checks Redis first, executes the
database fallback only on a miss or Redis outage, then refreshes Redis when a value was
found. Cache errors are logged and never prevent the source-of-truth fallback.

```python
cache = RedisFeatureCache(settings)
result = cache.get_or_load_json(key, settings.redis_feature_ttl_seconds, load_from_database)
```

Close the cache on application shutdown with `cache.close()`.
