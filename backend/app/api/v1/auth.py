from __future__ import annotations

import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from app.core.deps import AuthServiceDep, CurrentUser, DbSession, SettingsDep
from app.core.exceptions import AppError
from app.core.rate_limit import enforce_auth_rate_limit
from app.schemas.api import (
    GoogleAuthUrlResponse,
    UserResponse,
    WorkspaceConnectionResponse,
)
from app.services.google_oauth import GoogleOAuthService
from app.services.google_scopes import (
    has_calendar_read_access,
    has_calendar_write_access,
    has_gmail_access,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _workspace_response(connection) -> WorkspaceConnectionResponse:
    scopes = connection.scopes.split() if connection.scopes else []
    gmail_access = has_gmail_access(scopes)
    calendar_access = has_calendar_read_access(scopes)
    calendar_write = has_calendar_write_access(scopes)
    needs_reconnect = connection.is_connected and (not gmail_access or not calendar_access)
    reconnect_url = "/api/v1/auth/google/reconnect" if needs_reconnect else None
    return WorkspaceConnectionResponse(
        provider=connection.provider,
        email=connection.email,
        scopes=scopes,
        is_connected=connection.is_connected,
        token_expires_at=connection.token_expires_at,
        has_gmail_access=gmail_access,
        has_calendar_access=calendar_access,
        has_calendar_write_access=calendar_write,
        needs_reconnect=needs_reconnect,
        reconnect_url=reconnect_url,
    )


def _user_response(user) -> UserResponse:
    return UserResponse.model_validate(user)


@router.get("/me", response_model=UserResponse)
def get_me(current_user: CurrentUser) -> UserResponse:
    return _user_response(current_user)


@router.post("/logout")
def logout(
    current_user: CurrentUser,
    auth_service: AuthServiceDep,
    authorization: str | None = None,
) -> dict[str, str]:
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        try:
            payload = auth_service.decode_access_token(token)
            session_id = payload.get("sid")
            if session_id:
                auth_service.revoke_session(session_id)
        except Exception:
            pass
    return {"status": "logged_out"}


@router.get("/google/login", response_model=GoogleAuthUrlResponse)
def google_login(request: Request, settings: SettingsDep) -> GoogleAuthUrlResponse:
    enforce_auth_rate_limit(request, settings)
    oauth = GoogleOAuthService(settings)
    state = secrets.token_urlsafe(24)
    return GoogleAuthUrlResponse(authorization_url=oauth.build_authorization_url(state=state))


@router.get("/google/start")
def google_login_start(settings: SettingsDep) -> RedirectResponse:
    oauth = GoogleOAuthService(settings)
    state = secrets.token_urlsafe(24)
    authorization_url = oauth.build_authorization_url(state=state)
    return RedirectResponse(url=authorization_url)


@router.get("/google/reconnect")
def google_reconnect(settings: SettingsDep) -> RedirectResponse:
    oauth = GoogleOAuthService(settings)
    state = secrets.token_urlsafe(24)
    authorization_url = oauth.build_authorization_url(state=state)
    return RedirectResponse(url=authorization_url)


@router.get("/google/callback")
async def google_callback(
    request: Request,
    auth_service: AuthServiceDep,
    settings: SettingsDep,
    db: DbSession,
    code: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    if error:
        query = urlencode({"error": error})
        return RedirectResponse(url=f"{settings.frontend_url}/auth/callback?{query}")

    if not code:
        raise AppError("Missing OAuth authorization code", code="oauth_code_missing")

    oauth = GoogleOAuthService(settings)
    token_payload = await oauth.exchange_code(code=code)
    user = auth_service.get_or_create_user_from_google(
        google_subject=token_payload["google_subject"],
        email=token_payload["email"],
        full_name=token_payload.get("full_name"),
    )
    auth_service.upsert_workspace_connection(
        user=user,
        email=token_payload["email"],
        scopes=token_payload.get("scopes", []),
        access_token=token_payload.get("access_token"),
        refresh_token=token_payload.get("refresh_token"),
        expires_at=token_payload.get("expires_at"),
    )
    if token_payload.get("access_token"):
        from app.services.jobs import JobService

        JobService(db=db, settings=settings).enqueue_email_ingest(user=user)
    token, _ = auth_service.create_session(user)
    query = urlencode({"token": token})
    return RedirectResponse(url=f"{settings.frontend_url}/auth/callback?{query}")


@router.get("/workspace", response_model=WorkspaceConnectionResponse)
def workspace_status(current_user: CurrentUser, auth_service: AuthServiceDep) -> WorkspaceConnectionResponse:
    connection = auth_service.get_workspace_connection(current_user)
    if connection is None:
        return WorkspaceConnectionResponse(
            provider="google",
            email=None,
            scopes=[],
            is_connected=False,
            token_expires_at=None,
            has_gmail_access=False,
            has_calendar_access=False,
            has_calendar_write_access=False,
            needs_reconnect=True,
            reconnect_url="/api/v1/auth/google/reconnect",
        )
    return _workspace_response(connection)
