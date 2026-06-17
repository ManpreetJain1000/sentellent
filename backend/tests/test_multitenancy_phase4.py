from __future__ import annotations

from uuid import uuid4

from app.core.config import get_settings
from app.models.conversation import Conversation
from app.models.organization import Organization
from app.models.user import User
from app.services.auth import AuthService
from app.services.memory import MemoryService
from tests.conftest import create_test_user_token


def test_same_domain_users_share_organization(db_session) -> None:
    auth_service = AuthService(settings=get_settings(), db=db_session)
    first = auth_service.get_or_create_user_from_google(
        google_subject=f"google-{uuid4().hex}",
        email="alice@acme.com",
        full_name="Alice",
    )
    second = auth_service.get_or_create_user_from_google(
        google_subject=f"google-{uuid4().hex}",
        email="bob@acme.com",
        full_name="Bob",
    )

    assert first.organization_id == second.organization_id
    assert first.role == "owner"
    assert second.role == "member"


def test_org_api_returns_member_count(test_client) -> None:
    token = create_test_user_token(email="owner@acme.com")
    headers = {"Authorization": f"Bearer {token}"}

    response = test_client.get("/api/v1/org", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["email_domain"] == "acme.com"
    assert payload["slug"] == "acme-com"
    assert payload["member_count"] >= 1


def test_org_members_requires_owner(test_client, db_session) -> None:
    auth_service = AuthService(settings=get_settings(), db=db_session)
    owner = auth_service.get_or_create_user_from_google(
        google_subject=f"google-owner-{uuid4().hex}",
        email="owner@shared-org.com",
        full_name="Owner",
    )
    member = auth_service.get_or_create_user_from_google(
        google_subject=f"google-member-{uuid4().hex}",
        email="member@shared-org.com",
        full_name="Member",
    )
    owner_token, _ = auth_service.create_session(owner)
    member_token, _ = auth_service.create_session(member)

    owner_response = test_client.get(
        "/api/v1/org/members",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    member_response = test_client.get(
        "/api/v1/org/members",
        headers={"Authorization": f"Bearer {member_token}"},
    )

    assert owner_response.status_code == 200
    assert len(owner_response.json()) >= 2
    assert member_response.status_code == 403


def test_cross_org_conversation_isolation(test_client, db_session) -> None:
    org_a = Organization(name="Org A", slug=f"org-a-{uuid4().hex[:8]}", email_domain=f"a-{uuid4().hex[:6]}.com")
    org_b = Organization(name="Org B", slug=f"org-b-{uuid4().hex[:8]}", email_domain=f"b-{uuid4().hex[:6]}.com")
    user_a = User(
        organization=org_a,
        email="user-a@example.com",
        full_name="User A",
        google_subject=f"google-a-{uuid4().hex}",
        role="owner",
    )
    user_b = User(
        organization=org_b,
        email="user-b@example.com",
        full_name="User B",
        google_subject=f"google-b-{uuid4().hex}",
        role="owner",
    )
    db_session.add_all([org_a, org_b, user_a, user_b])
    db_session.commit()

    auth_service = AuthService(settings=get_settings(), db=db_session)
    token_a, _ = auth_service.create_session(user_a)
    token_b, _ = auth_service.create_session(user_b)

    conversation = Conversation(
        organization_id=org_a.id,
        user_id=user_a.id,
        title="Private A",
        status="active",
    )
    db_session.add(conversation)
    db_session.commit()

    denied = test_client.get(
        f"/api/v1/conversations/{conversation.id}/messages",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert denied.status_code == 404


def test_private_memory_not_visible_across_users_same_org(db_session) -> None:
    organization = Organization(name="Shared Org", slug=f"shared-{uuid4().hex[:8]}", email_domain="shared.com")
    owner = User(
        organization=organization,
        email="owner@shared.com",
        full_name="Owner",
        google_subject=f"google-owner-{uuid4().hex}",
        role="owner",
    )
    other = User(
        organization=organization,
        email="other@shared.com",
        full_name="Other",
        google_subject=f"google-other-{uuid4().hex}",
        role="member",
    )
    db_session.add(organization)
    db_session.add(owner)
    db_session.add(other)
    db_session.commit()

    memory_service = MemoryService(db=db_session, settings=get_settings())
    memory_service.create_memory(
        organization_id=organization.id,
        owner_user_id=owner.id,
        content="User prefers not to schedule meetings at 9 AM.",
        memory_type="preference",
        source_type="conversation",
    )

    visible_to_owner, owner_total = memory_service.list_memories(
        organization_id=organization.id,
        user_id=owner.id,
    )
    visible_to_other, other_total = memory_service.list_memories(
        organization_id=organization.id,
        user_id=other.id,
    )

    assert owner_total == 1
    assert other_total == 0
    assert len(visible_to_owner) == 1
    assert len(visible_to_other) == 0
