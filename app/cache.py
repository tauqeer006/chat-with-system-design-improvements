"""Redis cache helpers (cache-aside).

Everything here fails open: if Redis is slow or down, the app falls back to the DB.
Set CACHE_ENABLED=false to bypass the cache completely (used for before/after tests).
"""
import os

import redis

CACHE_ENABLED = os.getenv("CACHE_ENABLED", "true").lower() in ("1", "true", "yes")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
CACHE_TTL = int(os.getenv("CACHE_TTL", "30"))  # seconds; also bounds how stale data can get

VERSION_KEY = "tasks:ver"      # bumped on every write -> all list pages become stale at once
STATS_KEY = "cache:stats"      # hash with hit/miss counters shared by all workers

_pool = redis.ConnectionPool.from_url(
    REDIS_URL, max_connections=64, socket_timeout=0.25, socket_connect_timeout=0.25
)
r = redis.Redis(connection_pool=_pool)


def _safe(fn, default=None):
    try:
        return fn()
    except redis.RedisError:
        return default


def list_key(limit: int, offset: int) -> str:
    ver = _safe(lambda: r.get(VERSION_KEY))
    return f"tasks:list:{int(ver) if ver else 0}:{limit}:{offset}"


def item_key(task_id: int) -> str:
    return f"tasks:item:{task_id}"


def get(key: str):
    return _safe(lambda: r.get(key))


def put(key: str, payload: bytes) -> None:
    _safe(lambda: r.setex(key, CACHE_TTL, payload))


def record(event: str) -> None:
    """Count e.g. 'list_hit' / 'list_miss' (shared across workers, visible in /api/cache/stats)."""
    _safe(lambda: r.hincrby(STATS_KEY, event, 1))


def invalidate(task_id: int | None = None) -> None:
    """Call after every write: one Redis round trip."""
    if not CACHE_ENABLED:
        return

    def run():
        pipe = r.pipeline(transaction=False)
        pipe.incr(VERSION_KEY)                       # all cached list pages are now stale
        if task_id is not None:
            pipe.delete(item_key(task_id))           # drop the single-item entry
        pipe.execute()

    _safe(run)


def stats() -> dict:
    if not CACHE_ENABLED:
        return {"enabled": False}
    raw = _safe(lambda: r.hgetall(STATS_KEY), {}) or {}
    counts = {k.decode(): int(v) for k, v in raw.items()}
    out = {"enabled": True, "ttl_seconds": CACHE_TTL}
    for name in ("list", "item"):
        hit, miss = counts.get(f"{name}_hit", 0), counts.get(f"{name}_miss", 0)
        total = hit + miss
        out[name] = {"hits": hit, "misses": miss,
                     "hit_ratio": round(hit / total, 4) if total else None}
    out["keys_in_redis"] = _safe(lambda: r.dbsize())
    mem = _safe(lambda: r.info("memory"), {}) or {}
    out["used_memory"] = mem.get("used_memory_human")
    return out