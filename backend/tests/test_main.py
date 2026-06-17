from fastapi.testclient import TestClient

from app.main import create_app


def test_create_app_exposes_versioned_health_route() -> None:
    app = create_app()

    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["tenant_model"] == "shared_postgres_tenant_scoped"
