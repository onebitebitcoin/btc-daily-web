from sqlalchemy.orm import Session

from app.db import get_db


def test_get_db_yields_and_closes_a_session() -> None:
    generator = get_db()

    session = next(generator)
    assert isinstance(session, Session)

    generator.close()
