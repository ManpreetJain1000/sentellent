from __future__ import annotations

from tests.conftest import create_test_user_token


def test_cross_session_memory_recall(test_client) -> None:
    token = create_test_user_token(email="cross-session@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    first_conversation = test_client.post(
        "/api/v1/conversations",
        headers=headers,
        json={"title": "Preferences"},
    )
    assert first_conversation.status_code == 200
    first_id = first_conversation.json()["id"]

    teach = test_client.post(
        f"/api/v1/conversations/{first_id}/messages",
        headers=headers,
        json={"content": "I hate 9 AM meetings."},
    )
    assert teach.status_code == 200

    second_conversation = test_client.post(
        "/api/v1/conversations",
        headers=headers,
        json={"title": "Fresh session"},
    )
    assert second_conversation.status_code == 200
    second_id = second_conversation.json()["id"]
    assert second_id != first_id

    follow_up = test_client.post(
        f"/api/v1/conversations/{second_id}/messages",
        headers=headers,
        json={"content": "When should we schedule client calls?"},
    )
    assert follow_up.status_code == 200
    payload = follow_up.json()
    memories_used = " ".join(payload["memories_used"]).lower()
    assert "9 am" in memories_used or any(
        "9 AM" in item["content"] for item in test_client.get("/api/v1/memory", headers=headers).json()["items"]
    )


def test_private_memory_not_visible_to_other_user_in_org(db_session) -> None:
    from uuid import uuid4

    from app.core.config import get_settings
    from app.models.organization import Organization
    from app.models.user import User
    from app.services.memory import MemoryService

    organization = Organization(name="Shared Org", slug=f"shared-{uuid4().hex[:8]}")
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
        source_type="chat",
    )

    owner_items, owner_total = memory_service.list_memories(
        organization_id=organization.id,
        user_id=owner.id,
    )
    other_items, other_total = memory_service.list_memories(
        organization_id=organization.id,
        user_id=other.id,
    )

    assert owner_total == 1
    assert other_total == 0
    assert any("9 AM" in item.content for item in owner_items)


def test_forget_memory_excludes_from_list(test_client) -> None:
    token = create_test_user_token(email="forget-user@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    conversation = test_client.post(
        "/api/v1/conversations",
        headers=headers,
        json={"title": "Forget test"},
    )
    conversation_id = conversation.json()["id"]
    test_client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=headers,
        json={"content": "I hate 9 AM meetings."},
    )

    memory_list = test_client.get("/api/v1/memory", headers=headers)
    memory_id = next(item["id"] for item in memory_list.json()["items"] if "9 AM" in item["content"])

    forget = test_client.post(f"/api/v1/memory/{memory_id}/forget", headers=headers)
    assert forget.status_code == 200

    after_forget = test_client.get("/api/v1/memory", headers=headers)
    assert not any(item["id"] == memory_id for item in after_forget.json()["items"])


def test_correct_memory_updates_content(test_client) -> None:
    token = create_test_user_token(email="correct-user@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    conversation = test_client.post(
        "/api/v1/conversations",
        headers=headers,
        json={"title": "Correct test"},
    )
    conversation_id = conversation.json()["id"]
    test_client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=headers,
        json={"content": "Project X is delayed."},
    )

    memory_list = test_client.get("/api/v1/memory", headers=headers)
    memory_id = next(item["id"] for item in memory_list.json()["items"] if "Project X" in item["content"])

    corrected = test_client.patch(
        f"/api/v1/memory/{memory_id}",
        headers=headers,
        json={"content": "Project X is on track."},
    )
    assert corrected.status_code == 200
    assert corrected.json()["content"] == "Project X is on track."
    assert corrected.json()["corrected_at"] is not None
