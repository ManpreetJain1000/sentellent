from __future__ import annotations

from datetime import datetime, timezone
from math import ceil
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import NotFoundError
from app.db.mixins import retention_expiration
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User
from app.agent.checkpoint import delete_conversation_checkpoint
from app.agent.graph import ChiefOfStaffAgent
from app.agent.tools import WorkspaceToolContext
from app.services.memory import MemoryService


class ChatService:
    def __init__(self, *, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.memory_service = MemoryService(db=db, settings=settings)
        self._agent: ChiefOfStaffAgent | None = None

    @property
    def agent(self) -> ChiefOfStaffAgent:
        if self._agent is None:
            self._agent = ChiefOfStaffAgent(settings=self.settings, memory_service=self.memory_service)
        return self._agent

    def list_conversations(
        self,
        *,
        user: User,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Conversation], int]:
        stmt: Select[tuple[Conversation]] = select(Conversation).where(
            Conversation.organization_id == user.organization_id,
            Conversation.user_id == user.id,
        )
        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        items = list(
            self.db.scalars(
                stmt.order_by(Conversation.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return items, total

    def _next_conversation_title(self, *, user: User) -> str:
        titles = list(
            self.db.scalars(
                select(Conversation.title).where(
                    Conversation.organization_id == user.organization_id,
                    Conversation.user_id == user.id,
                )
            )
        )
        highest = 0
        for title in titles:
            if not title:
                continue
            normalized = title.strip()
            if normalized.lower().startswith("conversation "):
                suffix = normalized.split(" ", 1)[1].strip()
                if suffix.isdigit():
                    highest = max(highest, int(suffix))
        return f"Conversation {highest + 1}"

    def create_conversation(self, *, user: User, title: str | None = None) -> Conversation:
        resolved_title = title
        if not resolved_title or resolved_title.strip().lower() == "new conversation":
            resolved_title = self._next_conversation_title(user=user)
        conversation = Conversation(
            organization_id=user.organization_id,
            user_id=user.id,
            title=resolved_title,
            expires_at=retention_expiration(self.settings.conversation_retention_days),
        )
        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def get_conversation(self, *, user: User, conversation_id: UUID) -> Conversation:
        stmt = select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.organization_id == user.organization_id,
            Conversation.user_id == user.id,
        )
        conversation = self.db.scalar(stmt)
        if conversation is None:
            raise NotFoundError("Conversation not found")
        return conversation

    def delete_conversation(self, *, user: User, conversation_id: UUID) -> None:
        conversation = self.get_conversation(user=user, conversation_id=conversation_id)
        delete_conversation_checkpoint(settings=self.settings, conversation_id=conversation.id)
        self.db.delete(conversation)
        self.db.commit()

    def list_messages(
        self,
        *,
        user: User,
        conversation_id: UUID,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[Message], int]:
        conversation = self.get_conversation(user=user, conversation_id=conversation_id)
        stmt: Select[tuple[Message]] = select(Message).where(
            Message.organization_id == user.organization_id,
            Message.conversation_id == conversation.id,
        )
        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        items = list(
            self.db.scalars(
                stmt.order_by(Message.sent_at.asc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return items, total

    def send_message(self, *, user: User, conversation_id: UUID, content: str) -> tuple[Message, Message, int]:
        conversation = self.get_conversation(user=user, conversation_id=conversation_id)
        now = datetime.now(timezone.utc)

        user_message = Message(
            organization_id=user.organization_id,
            conversation_id=conversation.id,
            role="user",
            content=content,
            sent_at=now,
        )
        self.db.add(user_message)

        prior_messages, _ = self.list_messages(
            user=user,
            conversation_id=conversation.id,
            page=1,
            page_size=self.settings.agent_max_history_messages,
        )
        conversation_history = [(message.role, message.content) for message in prior_messages]

        workspace_context = WorkspaceToolContext(
            user=user,
            db=self.db,
            settings=self.settings,
            memory_service=self.memory_service,
            conversation_id=conversation.id,
        )

        agent_state = self.agent.run(
            organization_id=user.organization_id,
            user_id=user.id,
            conversation_id=conversation.id,
            user_message=content,
            conversation_history=conversation_history,
            workspace_context=workspace_context,
        )

        for extracted in agent_state["extracted_memories"]:
            self.memory_service.create_memory(
                organization_id=user.organization_id,
                owner_user_id=user.id,
                conversation_id=conversation.id,
                content=extracted["content"],
                memory_type=extracted["memory_type"],
                source_type="chat",
            )

        assistant_message = Message(
            organization_id=user.organization_id,
            conversation_id=conversation.id,
            role="assistant",
            content=agent_state["assistant_response"],
            sent_at=datetime.now(timezone.utc),
        )
        self.db.add(assistant_message)
        self.db.commit()
        self.db.refresh(user_message)
        self.db.refresh(assistant_message)
        return user_message, assistant_message, agent_state.get("email_memories_persisted", 0)

    @staticmethod
    def pagination_meta(*, page: int, page_size: int, total_items: int) -> dict[str, int]:
        total_pages = ceil(total_items / page_size) if total_items else 0
        return {
            "page": page,
            "page_size": page_size,
            "total_items": total_items,
            "total_pages": total_pages,
        }
