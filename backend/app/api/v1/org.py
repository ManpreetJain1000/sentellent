from __future__ import annotations

from fastapi import APIRouter

from app.core.deps import CurrentUser, DbSession
from app.schemas.api import OrganizationMemberResponse, OrganizationResponse
from app.services.organization import OrganizationService

router = APIRouter(prefix="/org", tags=["organization"])


@router.get("", response_model=OrganizationResponse)
def get_current_organization(current_user: CurrentUser, db: DbSession) -> OrganizationResponse:
    org_service = OrganizationService(db=db)
    organization = org_service.get_organization(current_user.organization_id)
    return OrganizationResponse(
        id=organization.id,
        name=organization.name,
        slug=organization.slug,
        email_domain=organization.email_domain,
        member_count=org_service.member_count(organization.id),
    )


@router.get("/members", response_model=list[OrganizationMemberResponse])
def list_organization_members(current_user: CurrentUser, db: DbSession) -> list[OrganizationMemberResponse]:
    org_service = OrganizationService(db=db)
    org_service.require_owner(user=current_user)
    members = org_service.list_members(organization_id=current_user.organization_id)
    return [OrganizationMemberResponse.model_validate(member) for member in members]
