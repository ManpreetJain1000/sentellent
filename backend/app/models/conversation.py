from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.db.mixins import AuditMixin, OrganizationScopedMixin, retention_expiration


class Conversation(OrganizationScopedMixin, AuditMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_organization_id_created_at", "organization_id", "created_at"),
        Index("ix_conversations_organization_id_expires_at", "organization_id", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization = relationship("Organization", back_populates="conversations")

    user_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=retention_expiration,
    )

    user = relationship("User")
    messages: Mapped[List["Message"]] = relationship(back_populates="conversation", cascade="all, delete-orphan")
    tasks: Mapped[List["Task"]] = relationship(back_populates="conversation")
    memory_items: Mapped[List["MemoryItem"]] = relationship(back_populates="conversation")
