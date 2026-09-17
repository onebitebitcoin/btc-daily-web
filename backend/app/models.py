import datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, Integer, String
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


class CardLike(Base):
    """카드 한 장에 쌓인 좋아요 수.

    로그인이 없는 사이트라 "누가 눌렀는지"는 서버에 남기지 않는다. 브라우저
    localStorage 가 자기가 누른 카드를 기억하고, 서버는 숫자만 센다. 그래서
    브라우저 데이터를 지우거나 다른 기기로 오면 다시 누를 수 있다 — 개인 정보를
    한 건도 저장하지 않는 대가로 받아들인 한계다.

    `Edition` 에 외래키를 걸지 않는다. 에디션은 같은 날짜로 재발행(upsert)되며
    갱신되는데, 외래키가 있으면 재발행 방식에 따라 좋아요가 함께 날아갈 수 있다.
    날짜와 카드 번호만 들고 있으면 본문이 바뀌어도 반응은 그대로 남는다. 대신
    존재하지 않는 날짜나 카드에 수치가 쌓이지 않도록 API 에서 검증한다.
    """

    __tablename__ = "card_likes"

    date: Mapped[datetime.date] = mapped_column(Date, primary_key=True)
    #: 슬라이드 위치가 아니라 카드 자체의 번호(`content.cards[].num`)다.
    card_num: Mapped[int] = mapped_column(Integer, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
