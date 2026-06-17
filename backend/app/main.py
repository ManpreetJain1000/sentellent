from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agent.checkpoint import ensure_checkpoint_schema
from app.core.config import get_settings
from app.core.exceptions import AppError, app_error_handler
from app.core.logging import RequestLoggingMiddleware, configure_structlog


def create_app() -> FastAPI:
    settings = get_settings()
    configure_structlog(environment=settings.app_environment)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if settings.sentry_dsn:
            import sentry_sdk

            sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.app_environment)
        if not settings.sqlalchemy_database_url.startswith("sqlite"):
            ensure_checkpoint_schema(settings.sqlalchemy_database_url)
        yield

    app = FastAPI(
        title=settings.app_name,
        version="0.4.0",
        debug=settings.app_debug,
        lifespan=lifespan,
    )
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_exception_handler(AppError, app_error_handler)

    from app.api.v1.router import api_router

    app.include_router(api_router)
    return app


app = create_app()
