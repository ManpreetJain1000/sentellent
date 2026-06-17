from __future__ import annotations

from typing import List
from uuid import UUID, uuid4

from sqlalchemy import String
from sqlalchemy.types import Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship


from app.db.base import Base
from app.db.mixins import AuditMixin


class Organization(AuditMixin, Base):
    __tablename__ = "organizations"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    email_domain: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    users: Mapped[List["User"]] = relationship(back_populates="organization", cascade="all, delete-orphan")
    conversations: Mapped[List["Conversation"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    tasks: Mapped[List["Task"]] = relationship(back_populates="organization", cascade="all, delete-orphan")
    memory_items: Mapped[List["MemoryItem"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
