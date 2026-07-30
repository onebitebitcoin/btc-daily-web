from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app


def test_app_boots_and_health_returns_ok() -> None:
    client = TestClient(create_app())
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_settings_default_to_local_sqlite() -> None:
    settings = get_settings()

    assert settings.database_url.startswith("sqlite:///")
    assert settings.admin_api_key == ""
