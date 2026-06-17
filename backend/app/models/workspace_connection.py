from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.db.mixins import AuditMixin, OrganizationScopedMixin


class WorkspaceConnection(OrganizationScopedMixin, AuditMixin, Base):
    __tablename__ = "workspace_connections"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", "provider", name="uq_workspace_connections_scope"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="google")
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    scopes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    access_token_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    refresh_token_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_connected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    user = relationship("User", back_populates="workspace_connections")
