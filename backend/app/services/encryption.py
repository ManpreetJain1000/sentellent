from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import Settings


class TokenEncryptionService:
    def __init__(self, settings: Settings) -> None:
        self._fernet = Fernet(self._derive_key(settings))

    @staticmethod
    def _derive_key(settings: Settings) -> bytes:
        source = settings.token_encryption_key or settings.jwt_secret_key or "change-me"
        digest = hashlib.sha256(source.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest)

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("utf-8")

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("Unable to decrypt stored token") from exc
