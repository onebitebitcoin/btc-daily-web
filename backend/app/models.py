import datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Plain JSON on SQLite (dev), JSONB on Postgres (prod) — SPEC.md requires JSONB
# for indexing/containment queries; generic JSON silently stays JSON on Postgres.
EditionContentType = JSON().with_variant(JSONB(), "postgresql")


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


class Base(DeclarativeBase):
    pass


class Edition(Base):
    __tablename__ = "editions"

    date: Mapped[datetime.date] = mapped_column(Date, primary_key=True)
    slug: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(EditionContentType, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
