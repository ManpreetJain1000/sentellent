from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "sentellent",
    broker=settings.celery_broker_url_resolved,
    backend=settings.celery_result_backend_resolved,
    include=["app.workers.tasks.email_ingestion", "app.workers.tasks.maintenance"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_always_eager=settings.celery_task_always_eager,
    task_eager_propagates=settings.celery_task_always_eager,
    beat_schedule={
        "worker-heartbeat": {
            "task": "app.workers.tasks.maintenance.worker_heartbeat",
            "schedule": 60.0,
        },
    },
)
