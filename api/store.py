"""Session, history and rate-limit storage: Redis, or memory when Redis isn't running.

Redis is used so sessions and history survive an API restart and can be shared by
several API workers. The in-memory store keeps the demo and the tests working without
Redis, but it is per-process and lost on restart.
"""
import json
import logging
import os
import threading
import time

import redis

log = logging.getLogger(__name__)


class MemoryStore:
    kind = "memory"

    def __init__(self):
        self._data: dict[str, tuple[object, float | None]] = {}
        self._lock = threading.Lock()

    def _get(self, key):
        value, expires = self._data.get(key, (None, None))
        if expires is not None and expires < time.time():
            self._data.pop(key, None)
            return None
        return value

    def set(self, key: str, value: str, ttl: int):
        with self._lock:
            self._data[key] = (value, time.time() + ttl)

    def get(self, key: str) -> str | None:
        with self._lock:
            return self._get(key)

    def delete(self, key: str):
        with self._lock:
            self._data.pop(key, None)

    def take(self, key: str) -> str | None:
        """Read and delete in one step, so a token can be used once even under concurrent requests."""
        with self._lock:
            value = self._get(key)
            self._data.pop(key, None)
            return value

    def expire(self, key: str, ttl: int):
        with self._lock:
            value = self._get(key)
            if value is not None:
                self._data[key] = (value, time.time() + ttl)

    def incr(self, key: str, ttl: int) -> int:
        with self._lock:
            if self._get(key) is None:
                self._data[key] = (1, time.time() + ttl)  # the window starts at the first request, as in Redis
                return 1
            count, expires = self._data[key]
            self._data[key] = (count + 1, expires)
            return count + 1

    def push(self, key: str, item: dict, keep: int, ttl: int):
        with self._lock:
            items = (self._get(key) or [])[-(keep - 1):] + [json.dumps(item)]
            self._data[key] = (items, time.time() + ttl)

    def items(self, key: str) -> list[dict]:
        with self._lock:
            return [json.loads(i) for i in self._get(key) or []]


class RedisStore:
    kind = "redis"

    def __init__(self, client: redis.Redis):
        self.r = client

    def set(self, key, value, ttl):
        self.r.set(key, value, ex=ttl)

    def get(self, key):
        return self.r.get(key)

    def delete(self, key):
        self.r.delete(key)

    def take(self, key):
        return self.r.getdel(key)

    def expire(self, key, ttl):
        self.r.expire(key, ttl)

    def incr(self, key, ttl):
        count = self.r.incr(key)
        if count == 1:
            self.r.expire(key, ttl)
        return count

    def push(self, key, item, keep, ttl):
        pipe = self.r.pipeline()
        pipe.rpush(key, json.dumps(item))
        pipe.ltrim(key, -keep, -1)
        pipe.expire(key, ttl)
        pipe.execute()

    def items(self, key):
        return [json.loads(i) for i in self.r.lrange(key, 0, -1)]


class FallbackStore:
    """Redis first. If Redis fails while running, switch to memory so the site keeps working.

    Everyone is signed out once (their tokens were in Redis), and the switch lasts until the
    API restarts. Better than every request failing with a 500.
    """

    def __init__(self, primary):
        self.primary = primary
        self.backup: MemoryStore | None = None

    @property
    def kind(self):
        return "redis" if self.backup is None else "memory (Redis lost)"

    def __getattr__(self, name):
        def call(*args, **kwargs):
            if self.backup is None:
                try:
                    return getattr(self.primary, name)(*args, **kwargs)
                except redis.RedisError as e:
                    log.error("Redis failed (%s): switching to in-memory storage until restart", e)
                    self.backup = MemoryStore()
            return getattr(self.backup, name)(*args, **kwargs)
        return call


def make_store():
    url = os.environ.get("REDIS_URL", "redis://localhost:6380/0")
    try:
        client = redis.Redis.from_url(url, decode_responses=True, socket_connect_timeout=1, socket_timeout=1)
        client.ping()
        return FallbackStore(RedisStore(client))
    except redis.RedisError as e:
        log.warning("Redis unavailable at %s (%s): using in-memory storage", url, e)
        return MemoryStore()
