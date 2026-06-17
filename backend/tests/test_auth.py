from tests.conftest import create_test_user_token


def test_me_requires_authentication(test_client) -> None:
    response = test_client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_me_returns_current_user(test_client) -> None:
    token = create_test_user_token(email="owner@example.com", full_name="Owner")

    response = test_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["email"] == "owner@example.com"
