from __future__ import annotations

from sqlalchemy import text

from fastapi import APIRouter

from app.core.config import get_settings
from app.db.session import get_engine
from app.schemas.health import HealthResponse
from app.services.redis_store import RedisSessionStore
from app.workers.tasks.maintenance import worker_is_alive

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def read_health() -> HealthResponse:
    settings = get_settings()
    checks: dict[str, str] = {}

    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"

    redis_store = RedisSessionStore(settings)
    checks["redis"] = "ok" if redis_store.ping() else "error"
    checks["worker"] = "ok" if worker_is_alive(settings) else "stale"

    status = "ok" if all(value == "ok" for key, value in checks.items() if key != "worker") else "degraded"
    if checks.get("database", "").startswith("error"):
        status = "error"

    return HealthResponse(
        status=status,
        service=settings.app_name,
        environment=settings.app_environment,
        tenant_model="shared_postgres_tenant_scoped",
        conversation_retention_days=settings.conversation_retention_days,
        encrypt_sensitive_data_at_rest=settings.encrypt_sensitive_data_at_rest,
        checks=checks,
    )
