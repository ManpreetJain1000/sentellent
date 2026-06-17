from __future__ import annotations

import time

from app.core.config import get_settings
from app.services.redis_store import RedisSessionStore
from app.workers.celery_app import celery_app

WORKER_HEARTBEAT_KEY = "worker:heartbeat"
WORKER_HEARTBEAT_TTL_SECONDS = 120


@celery_app.task(name="app.workers.tasks.maintenance.worker_heartbeat")
def worker_heartbeat() -> dict[str, str]:
    settings = get_settings()
    store = RedisSessionStore(settings)
    store.set_value(WORKER_HEARTBEAT_KEY, str(time.time()), ttl_seconds=WORKER_HEARTBEAT_TTL_SECONDS)
    return {"status": "ok"}


def worker_is_alive(settings=None) -> bool:
    settings = settings or get_settings()
    store = RedisSessionStore(settings)
    return store.get_value(WORKER_HEARTBEAT_KEY) is not None
