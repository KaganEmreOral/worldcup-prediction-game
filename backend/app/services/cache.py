"""Simple TTL cache for expensive read queries."""

import time
from typing import Any, Callable

_cache: dict[str, tuple[float, Any]] = {}


def cached(key: str, ttl_seconds: int, loader: Callable[[], Any]) -> Any:
    now = time.time()
    if key in _cache:
        expires, value = _cache[key]
        if now < expires:
            return value
    value = loader()
    _cache[key] = (now + ttl_seconds, value)
    return value


def invalidate(prefix: str | None = None) -> None:
    if prefix is None:
        _cache.clear()
        return
    for k in list(_cache.keys()):
        if k.startswith(prefix):
            del _cache[k]
