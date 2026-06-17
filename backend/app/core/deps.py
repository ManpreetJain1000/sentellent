from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, Request
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.db.session import get_db
from app.models.user import User
from app.services.auth import AuthService

DbSession = Annotated[Session, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_auth_service(settings: SettingsDep, db: DbSession) -> AuthService:
    return AuthService(settings=settings, db=db)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


def get_current_user(
    auth_service: AuthServiceDep,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedError("Missing or invalid authorization header")

    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = auth_service.decode_access_token(token)
    except JWTError as exc:
        raise UnauthorizedError("Invalid or expired token") from exc

    user_id = payload.get("sub")
    organization_id = payload.get("org_id")
    if not user_id or not organization_id:
        raise UnauthorizedError("Token missing required claims")

    user = auth_service.get_user_by_id(UUID(user_id), UUID(organization_id))
    if user is None or not user.is_active:
        raise UnauthorizedError("User not found or inactive")
    return user


def bind_user_to_request(request, user: User) -> User:
    request.state.user_id = str(user.id)
    request.state.organization_id = str(user.organization_id)
    return user


def get_current_user_with_request(
    request: Request,
    auth_service: AuthServiceDep,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    user = get_current_user(auth_service=auth_service, authorization=authorization)
    return bind_user_to_request(request, user)


CurrentUser = Annotated[User, Depends(get_current_user_with_request)]


def require_organization_scope(user: CurrentUser, organization_id: UUID) -> None:
    if user.organization_id != organization_id:
        raise ForbiddenError("Cross-tenant access denied")
