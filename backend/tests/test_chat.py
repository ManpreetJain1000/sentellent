from tests.conftest import create_test_user_token


def test_chat_flow_persists_memory_and_responds(test_client) -> None:
    token = create_test_user_token()
    headers = {"Authorization": f"Bearer {token}"}

    create_conversation = test_client.post(
        "/api/v1/conversations",
        headers=headers,
        json={"title": "Planning"},
    )
    assert create_conversation.status_code == 200
    conversation_id = create_conversation.json()["id"]

    send_message = test_client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=headers,
        json={"content": "I hate 9 AM meetings."},
    )
    assert send_message.status_code == 200
    payload = send_message.json()
    assert payload["user_message"]["role"] == "user"
    assert payload["assistant_message"]["role"] == "assistant"
    assert payload["assistant_message"]["content"]

    memory_response = test_client.get("/api/v1/memory", headers=headers)
    assert memory_response.status_code == 200
    memory_items = memory_response.json()["items"]
    assert any("9 AM" in item["content"] for item in memory_items)

    follow_up = test_client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=headers,
        json={"content": "When should we schedule client calls?"},
    )
    assert follow_up.status_code == 200
    assert "memory" in follow_up.json()["assistant_message"]["content"].lower() or follow_up.json()["memories_used"]


def test_create_conversation_auto_numbers_titles(test_client) -> None:
    token = create_test_user_token(email="numbered@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    first = test_client.post("/api/v1/conversations", headers=headers, json={})
    second = test_client.post("/api/v1/conversations", headers=headers, json={})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["title"] == "Conversation 1"
    assert second.json()["title"] == "Conversation 2"


def test_delete_conversation_removes_it_from_list(test_client) -> None:
    token = create_test_user_token(email="delete@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    create_conversation = test_client.post(
        "/api/v1/conversations",
        headers=headers,
        json={"title": "To delete"},
    )
    assert create_conversation.status_code == 200
    conversation_id = create_conversation.json()["id"]

    delete_response = test_client.delete(
        f"/api/v1/conversations/{conversation_id}",
        headers=headers,
    )
    assert delete_response.status_code == 204

    list_response = test_client.get("/api/v1/conversations", headers=headers)
    assert list_response.status_code == 200
    conversation_ids = [item["id"] for item in list_response.json()["items"]]
    assert conversation_id not in conversation_ids


def test_delete_conversation_requires_ownership(test_client) -> None:
    owner_token = create_test_user_token(email="owner@acme.com")
    other_token = create_test_user_token(email="other@beta.com")
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    other_headers = {"Authorization": f"Bearer {other_token}"}

    create_conversation = test_client.post(
        "/api/v1/conversations",
        headers=owner_headers,
        json={"title": "Private"},
    )
    conversation_id = create_conversation.json()["id"]

    delete_response = test_client.delete(
        f"/api/v1/conversations/{conversation_id}",
        headers=other_headers,
    )
    assert delete_response.status_code == 404
