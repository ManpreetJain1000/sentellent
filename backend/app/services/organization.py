from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.organization import Organization
from app.models.user import User


def normalize_email_domain(email: str) -> str:
    return email.split("@")[-1].lower().strip()


def domain_to_org_slug(domain: str) -> str:
    return domain.replace(".", "-")


class OrganizationService:
    def __init__(self, *, db: Session) -> None:
        self.db = db

    def get_organization(self, organization_id: UUID) -> Organization:
        organization = self.db.scalar(select(Organization).where(Organization.id == organization_id))
        if organization is None:
            raise NotFoundError("Organization not found")
        return organization

    def get_organization_by_email_domain(self, domain: str) -> Organization | None:
        normalized = normalize_email_domain(domain) if "@" in domain else domain.lower()
        slug = domain_to_org_slug(normalized)
        return self.db.scalar(
            select(Organization).where(
                (Organization.email_domain == normalized) | (Organization.slug == slug)
            )
        )

    def member_count(self, organization_id: UUID) -> int:
        return (
            self.db.scalar(
                select(func.count())
                .select_from(User)
                .where(User.organization_id == organization_id, User.is_active.is_(True))
            )
            or 0
        )

    def list_members(self, *, organization_id: UUID) -> list[User]:
        return list(
            self.db.scalars(
                select(User)
                .where(User.organization_id == organization_id, User.is_active.is_(True))
                .order_by(User.created_at.asc())
            )
        )

    def require_owner(self, *, user: User) -> None:
        if user.role != "owner":
            raise ForbiddenError("Only organization owners can access this resource")
