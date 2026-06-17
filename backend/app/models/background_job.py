from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.db.mixins import AuditMixin, OrganizationScopedMixin


class BackgroundJob(OrganizationScopedMixin, AuditMixin, Base):
    __tablename__ = "background_jobs"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_background_jobs_idempotency_key"),
        Index("ix_background_jobs_organization_id_user_id", "organization_id", "user_id"),
        Index("ix_background_jobs_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    job_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    payload: Mapped[Optional[dict[str, object]]] = mapped_column(JSON, nullable=True)
    result: Mapped[Optional[dict[str, object]]] = mapped_column(JSON, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    organization = relationship("Organization")
    user = relationship("User")
