from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import Settings
from app.core.exceptions import AppError


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


class GoogleOAuthService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def is_configured(self) -> bool:
        return bool(self.settings.google_oauth_client_id and self.settings.google_oauth_client_secret)

    def build_authorization_url(self, *, state: str, redirect_uri: str | None = None) -> str:
        if not self.is_configured():
            raise AppError("Google OAuth is not configured", code="oauth_not_configured", status_code=503)

        params = {
            "client_id": self.settings.google_oauth_client_id,
            "redirect_uri": redirect_uri or str(self.settings.google_oauth_redirect_uri),
            "response_type": "code",
            "scope": " ".join(self.settings.google_scope_list),
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, *, code: str, redirect_uri: str | None = None) -> dict[str, Any]:
        if not self.is_configured():
            raise AppError("Google OAuth is not configured", code="oauth_not_configured", status_code=503)

        payload = {
            "code": code,
            "client_id": self.settings.google_oauth_client_id,
            "client_secret": self.settings.google_oauth_client_secret,
            "redirect_uri": redirect_uri or str(self.settings.google_oauth_redirect_uri),
            "grant_type": "authorization_code",
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            token_response = await client.post(GOOGLE_TOKEN_URL, data=payload)
            token_response.raise_for_status()
            token_data = token_response.json()

            headers = {"Authorization": f"Bearer {token_data['access_token']}"}
            userinfo_response = await client.get(GOOGLE_USERINFO_URL, headers=headers)
            userinfo_response.raise_for_status()
            userinfo = userinfo_response.json()

        expires_in = token_data.get("expires_in")
        expires_at = None
        if expires_in:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))

        return {
            "access_token": token_data.get("access_token"),
            "refresh_token": token_data.get("refresh_token"),
            "expires_at": expires_at,
            "scopes": token_data.get("scope", "").split(),
            "google_subject": userinfo.get("sub"),
            "email": userinfo.get("email"),
            "full_name": userinfo.get("name"),
        }
