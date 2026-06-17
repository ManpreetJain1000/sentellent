from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str = "app_error",
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class NotFoundError(AppError):
    def __init__(self, message: str = "Resource not found", *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, code="not_found", status_code=404, details=details)


class UnauthorizedError(AppError):
    def __init__(self, message: str = "Unauthorized", *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, code="unauthorized", status_code=401, details=details)


class ForbiddenError(AppError):
    def __init__(self, message: str = "Forbidden", *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, code="forbidden", status_code=403, details=details)


class ConflictError(AppError):
    def __init__(self, message: str = "Conflict", *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, code="conflict", status_code=409, details=details)


def build_error_payload(
    *,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        }
    }


async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=build_error_payload(code=exc.code, message=exc.message, details=exc.details),
    )
