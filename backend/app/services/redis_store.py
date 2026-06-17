from __future__ import annotations

import json
from typing import Any

import redis

from app.core.config import Settings


class RedisSessionStore:
    def __init__(self, settings: Settings) -> None:
        self._prefix = "session:"
        self._memory_sessions: dict[str, tuple[str, float]] = {}
        self._use_memory = False
        try:
            self._client = redis.from_url(settings.redis_url, decode_responses=True)
            self._client.ping()
        except redis.RedisError:
            self._client = None
            self._use_memory = True

    def _key(self, session_id: str) -> str:
        return f"{self._prefix}{session_id}"

    def set_session(self, session_id: str, payload: dict[str, Any], ttl_seconds: int) -> None:
        if self._use_memory:
            import time

            self._memory_sessions[self._key(session_id)] = (json.dumps(payload), time.time() + ttl_seconds)
            return
        self._client.setex(self._key(session_id), ttl_seconds, json.dumps(payload))

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        if self._use_memory:
            import time

            stored = self._memory_sessions.get(self._key(session_id))
            if stored is None:
                return None
            raw, expires_at = stored
            if time.time() > expires_at:
                self._memory_sessions.pop(self._key(session_id), None)
                return None
            return json.loads(raw)
        raw = self._client.get(self._key(session_id))
        if raw is None:
            return None
        return json.loads(raw)

    def delete_session(self, session_id: str) -> None:
        if self._use_memory:
            self._memory_sessions.pop(self._key(session_id), None)
            return
        self._client.delete(self._key(session_id))

    def ping(self) -> bool:
        if self._use_memory:
            return True
        return bool(self._client.ping())

    def set_value(self, key: str, value: str, *, ttl_seconds: int) -> None:
        if self._use_memory:
            import time

            self._memory_sessions[key] = (value, time.time() + ttl_seconds)
            return
        self._client.setex(key, ttl_seconds, value)

    def get_value(self, key: str) -> str | None:
        if self._use_memory:
            import time

            stored = self._memory_sessions.get(key)
            if stored is None:
                return None
            raw, expires_at = stored
            if time.time() > expires_at:
                self._memory_sessions.pop(key, None)
                return None
            return raw
        value = self._client.get(key)
        return value
