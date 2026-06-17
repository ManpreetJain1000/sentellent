from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from limits import parse
from limits.storage import storage_from_string
from limits.strategies import MovingWindowRateLimiter
from slowapi.util import get_remote_address

from app.core.config import Settings
from app.core.exceptions import AppError, build_error_payload

_limiters: dict[str, MovingWindowRateLimiter] = {}


def reset_rate_limiters() -> None:
    _limiters.clear()


class RateLimitService:
    def __init__(self, settings: Settings) -> None:
        storage_uri = self._storage_uri(settings)
        if storage_uri not in _limiters:
            _limiters[storage_uri] = MovingWindowRateLimiter(storage_from_string(storage_uri))
        self._limiter = _limiters[storage_uri]

    @staticmethod
    def _storage_uri(settings: Settings) -> str:
        try:
            import redis

            client = redis.from_url(settings.redis_url, decode_responses=True)
            client.ping()
            return settings.redis_url
        except Exception:
            return "memory://"

    def hit(self, *, key: str, limit: str) -> None:
        rate_limit = parse(limit)
        if not self._limiter.hit(rate_limit, key, limit):
            raise AppError(
                "Too many requests. Please try again later.",
                code="rate_limit_exceeded",
                status_code=429,
            )


def user_or_ip_key(request: Request) -> str:
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ").strip()[:64]
    return get_remote_address(request)


def enforce_auth_rate_limit(request: Request, settings: Settings) -> None:
    RateLimitService(settings).hit(
        key=f"auth:{get_remote_address(request)}",
        limit=f"{settings.rate_limit_auth_per_minute}/minute",
    )


def enforce_chat_rate_limit(request: Request, settings: Settings) -> None:
    RateLimitService(settings).hit(
        key=f"chat:{user_or_ip_key(request)}",
        limit=f"{settings.rate_limit_chat_per_minute}/minute",
    )


def enforce_ingest_rate_limit(request: Request, settings: Settings) -> None:
    RateLimitService(settings).hit(
        key=f"ingest:{user_or_ip_key(request)}",
        limit=f"{settings.rate_limit_ingest_per_hour}/hour",
    )


async def rate_limit_exceeded_handler(_: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, AppError) and exc.code == "rate_limit_exceeded":
        return JSONResponse(
            status_code=429,
            content=build_error_payload(code=exc.code, message=exc.message, details=exc.details),
        )
    raise exc
