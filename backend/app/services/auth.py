from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from jose import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.mixins import utcnow
from app.models.organization import Organization
from app.models.user import User
from app.models.workspace_connection import WorkspaceConnection
from app.services.encryption import TokenEncryptionService
from app.services.organization import OrganizationService, domain_to_org_slug, normalize_email_domain
from app.services.redis_store import RedisSessionStore


class AuthService:
    ALGORITHM = "HS256"

    def __init__(self, *, settings: Settings, db: Session) -> None:
        self.settings = settings
        self.db = db
        self.encryption = TokenEncryptionService(settings)
        self.sessions = RedisSessionStore(settings)

    def create_access_token(self, *, user: User, session_id: str) -> str:
        expires = utcnow() + timedelta(minutes=self.settings.jwt_access_token_expires_minutes)
        payload = {
            "sub": str(user.id),
            "org_id": str(user.organization_id),
            "email": user.email,
            "sid": session_id,
            "exp": expires,
        }
        return jwt.encode(payload, self.settings.jwt_secret_key, algorithm=self.ALGORITHM)

    def decode_access_token(self, token: str) -> dict[str, Any]:
        return jwt.decode(token, self.settings.jwt_secret_key, algorithms=[self.ALGORITHM])

    def create_session(self, user: User) -> tuple[str, str]:
        session_id = secrets.token_urlsafe(32)
        ttl_seconds = self.settings.jwt_access_token_expires_minutes * 60
        self.sessions.set_session(
            session_id,
            {
                "user_id": str(user.id),
                "organization_id": str(user.organization_id),
            },
            ttl_seconds=ttl_seconds,
        )
        token = self.create_access_token(user=user, session_id=session_id)
        return token, session_id

    def revoke_session(self, session_id: str) -> None:
        self.sessions.delete_session(session_id)

    def get_user_by_id(self, user_id: UUID, organization_id: UUID) -> User | None:
        stmt = select(User).where(User.id == user_id, User.organization_id == organization_id)
        return self.db.scalar(stmt)

    def get_user_by_google_subject(self, google_subject: str) -> User | None:
        stmt = select(User).where(User.google_subject == google_subject)
        return self.db.scalar(stmt)

    def get_or_create_user_from_google(
        self,
        *,
        google_subject: str,
        email: str,
        full_name: str | None,
    ) -> User:
        existing = self.get_user_by_google_subject(google_subject)
        if existing:
            existing.email = email
            existing.full_name = full_name
            self.db.commit()
            self.db.refresh(existing)
            return existing

        email_domain = normalize_email_domain(email)
        org_slug = domain_to_org_slug(email_domain)
        org_service = OrganizationService(db=self.db)
        organization = org_service.get_organization_by_email_domain(email_domain)

        if organization is None:
            organization = Organization(
                name=f"{org_slug} workspace",
                slug=org_slug,
                email_domain=email_domain,
            )
            self.db.add(organization)
            role = "owner"
        else:
            role = "member"

        user = User(
            organization=organization,
            email=email,
            full_name=full_name,
            google_subject=google_subject,
            role=role,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def upsert_workspace_connection(
        self,
        *,
        user: User,
        email: str | None,
        scopes: list[str],
        access_token: str | None,
        refresh_token: str | None,
        expires_at: datetime | None,
    ) -> WorkspaceConnection:
        stmt = select(WorkspaceConnection).where(
            WorkspaceConnection.organization_id == user.organization_id,
            WorkspaceConnection.user_id == user.id,
            WorkspaceConnection.provider == "google",
        )
        connection = self.db.scalar(stmt)
        if connection is None:
            connection = WorkspaceConnection(
                organization_id=user.organization_id,
                user_id=user.id,
                provider="google",
            )
            self.db.add(connection)

        connection.email = email
        connection.scopes = " ".join(scopes)
        connection.access_token_encrypted = (
            self.encryption.encrypt(access_token) if access_token else None
        )
        if refresh_token:
            connection.refresh_token_encrypted = self.encryption.encrypt(refresh_token)
        connection.token_expires_at = expires_at
        connection.is_connected = bool(access_token)
        self.db.commit()
        self.db.refresh(connection)
        return connection

    def get_workspace_connection(self, user: User) -> WorkspaceConnection | None:
        stmt = select(WorkspaceConnection).where(
            WorkspaceConnection.organization_id == user.organization_id,
            WorkspaceConnection.user_id == user.id,
            WorkspaceConnection.provider == "google",
        )
        return self.db.scalar(stmt)
