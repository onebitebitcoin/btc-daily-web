import datetime

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from app.models import Base, Edition


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_create_all_creates_editions_table_with_expected_columns() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    inspector = inspect(engine)
    assert inspector.has_table("editions")

    columns = {c["name"]: c for c in inspector.get_columns("editions")}
    assert set(columns) == {"date", "slug", "title", "content", "created_at", "updated_at"}
    assert columns["date"]["primary_key"] == 1
    assert all(not columns[name]["nullable"] for name in columns)


def test_edition_round_trip(session: Session) -> None:
    session.add(
        Edition(
            date=datetime.date(2026, 7, 30),
            slug="btc-daily-0730",
            title="비트코인 하이라이트 · 7.30",
            content={"meta": {"date": "2026-07-30"}},
        )
    )
    session.commit()

    stored = session.scalars(
        select(Edition).where(Edition.date == datetime.date(2026, 7, 30))
    ).one()

    assert stored.slug == "btc-daily-0730"
    assert stored.title == "비트코인 하이라이트 · 7.30"
    assert stored.content == {"meta": {"date": "2026-07-30"}}
    assert stored.created_at is not None
    assert stored.updated_at is not None
