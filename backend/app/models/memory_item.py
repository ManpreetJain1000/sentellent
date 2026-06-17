from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.db.mixins import AuditMixin, OrganizationScopedMixin


class MemoryItem(OrganizationScopedMixin, AuditMixin, Base):
    __tablename__ = "memory_items"
    __table_args__ = (
        Index("ix_memory_items_organization_id_memory_type", "organization_id", "memory_type"),
        Index("ix_memory_items_organization_id_source_type", "organization_id", "source_type"),
        Index("ix_memory_items_organization_id_owner_user_id", "organization_id", "owner_user_id"),
        Index("ix_memory_items_organization_id_forgotten_at", "organization_id", "forgotten_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_user_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    conversation_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_type: Mapped[str] = mapped_column(String(100), nullable=False)
    source_kind: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    source_ref: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_excerpt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    memory_type: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    visibility: Mapped[str] = mapped_column(String(32), nullable=False, default="private")
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    embedding_vector: Mapped[Optional[list[float] | dict[str, object]]] = mapped_column(JSON, nullable=True)
    embedding_model: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    embedding_dimensions: Mapped[Optional[int]] = mapped_column(nullable=True)
    pinned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    corrected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    forgotten_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    organization = relationship("Organization", back_populates="memory_items")
    conversation = relationship("Conversation", back_populates="memory_items")
    owner = relationship("User")
