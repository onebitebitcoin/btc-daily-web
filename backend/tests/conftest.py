import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_db
from app.main import create_app
from app.models import Base


@pytest.fixture
def client() -> TestClient:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    def override_get_db():
        with session_factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        test_client.session_factory = session_factory
        yield test_client
