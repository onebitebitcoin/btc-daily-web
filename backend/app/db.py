from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

engine = create_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine)


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
