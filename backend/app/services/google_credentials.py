from __future__ import annotations

from datetime import timedelta

import httpx
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import AppError
from app.db.mixins import utcnow
from app.models.workspace_connection import WorkspaceConnection
from app.services.encryption import TokenEncryptionService
from app.services.google_oauth import GOOGLE_TOKEN_URL


class GoogleCredentialsService:
    """Resolve and refresh Google OAuth access tokens for workspace connections."""

    def __init__(self, *, settings: Settings, db: Session) -> None:
        self.settings = settings
        self.db = db
        self.encryption = TokenEncryptionService(settings)

    async def get_valid_access_token(self, connection: WorkspaceConnection) -> str:
        if not connection.is_connected or not connection.access_token_encrypted:
            raise AppError(
                "Google Workspace is not connected. Sign in again to grant Gmail and Calendar access.",
                code="workspace_not_connected",
                status_code=400,
            )

        access_token = self.encryption.decrypt(connection.access_token_encrypted)
        expires_at = connection.token_expires_at
        if expires_at is not None and expires_at <= utcnow() + timedelta(minutes=2):
            access_token = await self._refresh_access_token(connection)
        return access_token

    async def _refresh_access_token(self, connection: WorkspaceConnection) -> str:
        if not connection.refresh_token_encrypted:
            raise AppError(
                "Google access token expired. Reconnect your Google Workspace account.",
                code="workspace_token_expired",
                status_code=401,
            )

        refresh_token = self.encryption.decrypt(connection.refresh_token_encrypted)
        payload = {
            "client_id": self.settings.google_oauth_client_id,
            "client_secret": self.settings.google_oauth_client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(GOOGLE_TOKEN_URL, data=payload)
            if response.status_code >= 400:
                raise AppError(
                    "Unable to refresh Google access token. Reconnect your Google Workspace account.",
                    code="workspace_token_refresh_failed",
                    status_code=401,
                )
            token_data = response.json()

        access_token = token_data["access_token"]
        expires_in = token_data.get("expires_in")
        connection.access_token_encrypted = self.encryption.encrypt(access_token)
        if expires_in:
            connection.token_expires_at = utcnow() + timedelta(seconds=int(expires_in))
        self.db.commit()
        self.db.refresh(connection)
        return access_token
