import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_app_boots_and_health_returns_ok() -> None:
    client = TestClient(create_app())
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_settings_default_to_local_sqlite(monkeypatch: pytest.MonkeyPatch) -> None:
    """설정 소스를 끊고 기본값 자체를 본다.

    발행에 쓰는 backend/.env 에는 ADMIN_API_KEY 가 들어 있는 게 정상이라,
    get_settings() 를 그대로 읽으면 이 테스트는 로컬 환경에 따라 깨진다.
    """
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("ADMIN_API_KEY", raising=False)
    settings = Settings(_env_file=None)

    assert settings.database_url.startswith("sqlite:///")
    assert settings.admin_api_key == ""
