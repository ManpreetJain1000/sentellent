from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import EmailStr, Field

from app.schemas.common import APIModel, PaginatedResponse


class UserResponse(APIModel):
    id: UUID
    organization_id: UUID
    email: EmailStr
    full_name: str | None
    role: str
    is_active: bool


class AuthTokenResponse(APIModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    user: UserResponse


class GoogleAuthUrlResponse(APIModel):
    authorization_url: str


class WorkspaceConnectionResponse(APIModel):
    provider: str
    email: str | None
    scopes: list[str]
    is_connected: bool
    token_expires_at: datetime | None
    has_gmail_access: bool = False
    has_calendar_access: bool = False
    has_calendar_write_access: bool = False
    needs_reconnect: bool = False
    reconnect_url: str | None = None


class ConversationResponse(APIModel):
    id: UUID
    organization_id: UUID
    user_id: UUID | None
    title: str | None
    status: str
    expires_at: datetime
    created_at: datetime


class MessageResponse(APIModel):
    id: UUID
    conversation_id: UUID
    role: str
    content: str
    sent_at: datetime


class CreateConversationRequest(APIModel):
    title: str | None = Field(default=None, max_length=255)


class SendMessageRequest(APIModel):
    content: str = Field(min_length=1, max_length=8000)


class ChatExchangeResponse(APIModel):
    user_message: MessageResponse
    assistant_message: MessageResponse
    memories_used: list[str] = Field(default_factory=list)
    email_memories_learned: int = 0


class MemoryItemResponse(APIModel):
    id: UUID
    memory_type: str
    content: str
    source_type: str
    source_kind: str | None = None
    visibility: str = "private"
    pinned_at: datetime | None = None
    corrected_at: datetime | None = None
    created_at: datetime


class UpdateMemoryRequest(APIModel):
    content: str = Field(min_length=1, max_length=8000)


class OrganizationResponse(APIModel):
    id: UUID
    name: str
    slug: str
    email_domain: str | None
    member_count: int


class OrganizationMemberResponse(APIModel):
    id: UUID
    email: EmailStr
    full_name: str | None
    role: str


class BackgroundJobResponse(APIModel):
    id: UUID
    job_type: str
    status: str
    payload: dict[str, object] | None = None
    result: dict[str, object] | None = None
    error_message: str | None = None
    created_at: datetime


class IngestWorkspaceRequest(APIModel):
    max_results: int = Field(default=10, ge=1, le=25)


ConversationListResponse = PaginatedResponse[ConversationResponse]
MessageListResponse = PaginatedResponse[MessageResponse]
MemoryListResponse = PaginatedResponse[MemoryItemResponse]
