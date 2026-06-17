from __future__ import annotations

import base64
import email.utils
from datetime import datetime, timezone

import httpx

from app.core.exceptions import AppError
from app.schemas.workspace import EmailSummary

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


class GmailService:
    def __init__(self, *, max_retries: int = 3) -> None:
        self.max_retries = max_retries

    async def list_recent_messages(
        self,
        *,
        access_token: str,
        max_results: int = 10,
        query: str = "in:inbox",
    ) -> list[EmailSummary]:
        params = {"maxResults": max(1, min(max_results, 25)), "q": query}
        list_payload = await self._request(
            access_token=access_token,
            method="GET",
            url=f"{GMAIL_API_BASE}/messages",
            params=params,
        )
        message_refs = list_payload.get("messages", [])
        summaries: list[EmailSummary] = []
        for ref in message_refs:
            summaries.append(await self.get_message(access_token=access_token, message_id=ref["id"]))
        return summaries

    async def get_message(self, *, access_token: str, message_id: str) -> EmailSummary:
        payload = await self._request(
            access_token=access_token,
            method="GET",
            url=f"{GMAIL_API_BASE}/messages/{message_id}",
            params={
                "format": "metadata",
                "metadataHeaders": ["Subject", "From", "Date"],
            },
        )
        headers = {item["name"].lower(): item["value"] for item in payload.get("payload", {}).get("headers", [])}
        received_at = self._parse_date(headers.get("date"))
        return EmailSummary(
            id=payload["id"],
            thread_id=payload.get("threadId", payload["id"]),
            subject=headers.get("subject", "(no subject)"),
            sender=headers.get("from", "unknown"),
            snippet=payload.get("snippet", ""),
            received_at=received_at,
        )

    async def _request(
        self,
        *,
        access_token: str,
        method: str,
        url: str,
        params: dict | None = None,
        json_body: dict | None = None,
    ) -> dict:
        headers = {"Authorization": f"Bearer {access_token}"}
        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.request(method, url, headers=headers, params=params, json=json_body)
                if response.status_code == 401:
                    raise AppError(
                        "Gmail access denied. Reconnect Google Workspace with Gmail permissions.",
                        code="gmail_unauthorized",
                        status_code=401,
                    )
                if response.status_code == 429 and attempt < self.max_retries - 1:
                    continue
                if response.status_code >= 400:
                    raise AppError(
                        "Unable to read Gmail inbox.",
                        code="gmail_api_error",
                        status_code=502,
                        details={"status_code": response.status_code},
                    )
                return response.json()
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt >= self.max_retries - 1:
                    break

        raise AppError(
            "Gmail request failed after retries.",
            code="gmail_request_failed",
            status_code=502,
            details={"error": str(last_error) if last_error else "unknown"},
        )

    @staticmethod
    def _parse_date(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            parsed = email.utils.parsedate_to_datetime(value)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed
        except (TypeError, ValueError):
            return None

    @staticmethod
    def format_summaries(emails: list[EmailSummary]) -> str:
        if not emails:
            return "No recent emails found in the inbox."
        lines: list[str] = []
        for index, item in enumerate(emails, start=1):
            received = item.received_at.isoformat() if item.received_at else "unknown time"
            lines.append(
                f"{index}. [{item.id}] From: {item.sender}\n"
                f"   Subject: {item.subject}\n"
                f"   Received: {received}\n"
                f"   Preview: {item.snippet}"
            )
        return "\n\n".join(lines)

    @staticmethod
    def memory_source_text(email: EmailSummary) -> str:
        return f"Subject: {email.subject}\nFrom: {email.sender}\nPreview: {email.snippet}"
