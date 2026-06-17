from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response

from app.core.deps import CurrentUser, DbSession, SettingsDep
from app.core.rate_limit import enforce_chat_rate_limit
from app.schemas.api import (
    ChatExchangeResponse,
    ConversationListResponse,
    ConversationResponse,
    CreateConversationRequest,
    MemoryItemResponse,
    MemoryListResponse,
    MessageListResponse,
    MessageResponse,
    SendMessageRequest,
    UpdateMemoryRequest,
)
from app.services.chat import ChatService
from app.services.memory import MemoryService

router = APIRouter(tags=["chat"])


def get_chat_service(db: DbSession, settings: SettingsDep) -> ChatService:
    return ChatService(db=db, settings=settings)


def get_memory_service(db: DbSession, settings: SettingsDep) -> MemoryService:
    return MemoryService(db=db, settings=settings)


@router.get("/conversations", response_model=ConversationListResponse)
def list_conversations(
    current_user: CurrentUser,
    chat_service: ChatService = Depends(get_chat_service),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ConversationListResponse:
    items, total = chat_service.list_conversations(user=current_user, page=page, page_size=page_size)
    return ConversationListResponse(
        items=[ConversationResponse.model_validate(item) for item in items],
        pagination=chat_service.pagination_meta(page=page, page_size=page_size, total_items=total),
    )


@router.post("/conversations", response_model=ConversationResponse)
def create_conversation(
    payload: CreateConversationRequest,
    current_user: CurrentUser,
    chat_service: ChatService = Depends(get_chat_service),
) -> ConversationResponse:
    conversation = chat_service.create_conversation(user=current_user, title=payload.title)
    return ConversationResponse.model_validate(conversation)


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(
    conversation_id: UUID,
    current_user: CurrentUser,
    chat_service: ChatService = Depends(get_chat_service),
) -> Response:
    chat_service.delete_conversation(user=current_user, conversation_id=conversation_id)
    return Response(status_code=204)


@router.get("/conversations/{conversation_id}/messages", response_model=MessageListResponse)
def list_messages(
    conversation_id: UUID,
    current_user: CurrentUser,
    chat_service: ChatService = Depends(get_chat_service),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> MessageListResponse:
    items, total = chat_service.list_messages(
        user=current_user,
        conversation_id=conversation_id,
        page=page,
        page_size=page_size,
    )
    return MessageListResponse(
        items=[MessageResponse.model_validate(item) for item in items],
        pagination=chat_service.pagination_meta(page=page, page_size=page_size, total_items=total),
    )


@router.post("/conversations/{conversation_id}/messages", response_model=ChatExchangeResponse)
def send_message(
    request: Request,
    conversation_id: UUID,
    payload: SendMessageRequest,
    current_user: CurrentUser,
    settings: SettingsDep,
    chat_service: ChatService = Depends(get_chat_service),
) -> ChatExchangeResponse:
    enforce_chat_rate_limit(request, settings)
    user_message, assistant_message, email_memories_learned = chat_service.send_message(
        user=current_user,
        conversation_id=conversation_id,
        content=payload.content,
    )
    memories = chat_service.memory_service.search_relevant_memories(
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        query=payload.content,
        limit=5,
    )
    return ChatExchangeResponse(
        user_message=MessageResponse.model_validate(user_message),
        assistant_message=MessageResponse.model_validate(assistant_message),
        memories_used=[memory.content for memory in memories],
        email_memories_learned=email_memories_learned,
    )


@router.get("/memory", response_model=MemoryListResponse)
def list_memory(
    current_user: CurrentUser,
    memory_service: MemoryService = Depends(get_memory_service),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    memory_type: str | None = Query(default=None),
) -> MemoryListResponse:
    items, total = memory_service.list_memories(
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        page=page,
        page_size=page_size,
        memory_type=memory_type,
    )
    return MemoryListResponse(
        items=[MemoryItemResponse.model_validate(item) for item in items],
        pagination={
            "page": page,
            "page_size": page_size,
            "total_items": total,
            "total_pages": (total + page_size - 1) // page_size if total else 0,
        },
    )


@router.patch("/memory/{memory_id}", response_model=MemoryItemResponse)
def correct_memory(
    memory_id: UUID,
    payload: UpdateMemoryRequest,
    current_user: CurrentUser,
    memory_service: MemoryService = Depends(get_memory_service),
) -> MemoryItemResponse:
    memory = memory_service.correct_memory(
        memory_id=memory_id,
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        content=payload.content,
    )
    return MemoryItemResponse.model_validate(memory)


@router.post("/memory/{memory_id}/forget", response_model=MemoryItemResponse)
def forget_memory(
    memory_id: UUID,
    current_user: CurrentUser,
    memory_service: MemoryService = Depends(get_memory_service),
) -> MemoryItemResponse:
    memory = memory_service.forget_memory(
        memory_id=memory_id,
        organization_id=current_user.organization_id,
        user_id=current_user.id,
    )
    return MemoryItemResponse.model_validate(memory)


@router.post("/memory/{memory_id}/pin", response_model=MemoryItemResponse)
def pin_memory(
    memory_id: UUID,
    current_user: CurrentUser,
    memory_service: MemoryService = Depends(get_memory_service),
) -> MemoryItemResponse:
    memory = memory_service.pin_memory(
        memory_id=memory_id,
        organization_id=current_user.organization_id,
        user_id=current_user.id,
    )
    return MemoryItemResponse.model_validate(memory)
