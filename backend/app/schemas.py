import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Strict(BaseModel):
    """Reject unknown keys so a typo in a pushed edition fails loudly, not silently."""

    model_config = ConfigDict(extra="forbid")


class Meta(_Strict):
    title: str
    slug: str
    date: datetime.date


class Theme(_Strict):
    bg: str
    bg2: str
    bg_light: str
    bg2_light: str
    paper: str
    paper2: str
    ink: str
    ink_dim: str
    accent: str
    accent_strong: str
    glow: str
    accent2: str
    accent2_light: str
    line: str
    chip_bg: str
    seg_off: str


class Cover(_Strict):
    eyebrow: str
    mark: list[str]
    meta: list[str]
    hint: str


class Chip(_Strict):
    text: str
    emphasis: Literal["primary", "secondary"] | None = None


class Link(_Strict):
    label: str
    href: str


class Media(_Strict):
    image: str
    href: str | None = None
    cta: str | None = None


class QA(_Strict):
    question: str
    answer: str
    sources: list[str]


class Card(_Strict):
    num: int
    chip: Chip
    title: str
    subtitle: str
    chips_label: str
    chips: list[str]
    body: str
    quote: str | None = None
    link: Link | None = None
    media: Media | None = None
    qa: list[QA] | None = None


class Closing(_Strict):
    eyebrow: str
    mark_lines: list[str]
    links: list[Link]
    stamp: str
    restart: str
    sources: list[str]
    disclaimer: str


class TrendingLink(_Strict):
    """펼침 목록의 원문 하나.

    카드의 `Link`(label/href)를 재사용하지 않는 이유: 카드 링크는 "토큰포스트 원문"
    같은 단일 CTA라 라벨 한 줄이면 되지만, 여기는 기사 여러 건을 훑는 목록이다.
    무슨 기사인지가 먼저 보여야 하고 매체는 그 근거로 따라붙는다 — 라벨 하나로
    합치면 제목이 통째로 사라진다.
    """

    title: str
    href: str
    source: str | None = None


class TrendingItem(_Strict):
    rank: int
    topic: str
    heat: int = Field(ge=0, le=100)
    mentions: int
    sources: int
    # 펼침 목록. 없으면 그 줄은 펼칠 수 없는 상태로 렌더된다(트렌딩 도입 초기
    # 발행분이 이 필드 없이 나갔으므로 optional 이어야 한다).
    links: list[TrendingLink] | None = None


class Trending(_Strict):
    """단순 언급 빈도가 아니라 "무엇이 진짜 핫했는가"를 보여주는 순위 카드.

    기존 발행분 9편에는 이 블록이 없다 — EditionContent에서 optional로 둬야
    과거 에디션이 계속 슬라이드 12장으로 렌더된다.
    """

    eyebrow: str
    title: str
    note: str | None = None
    items: list[TrendingItem]

    @model_validator(mode="after")
    def _check_items(self) -> "Trending":
        if len(self.items) != 10:
            raise ValueError(f"trending.items는 정확히 10개여야 한다 (받음: {len(self.items)})")
        ranks = [item.rank for item in self.items]
        if ranks != list(range(1, 11)):
            raise ValueError(f"trending.items의 rank는 1~10 오름차순이어야 한다 (받음: {ranks})")
        # heat은 막대 길이로 그려진다. 순위와 어긋나면 3위 막대가 1위보다 긴 카드가
        # 그대로 발행되므로, 눈에 보이는 모순을 스키마에서 막는다.
        heats = [item.heat for item in self.items]
        if heats != sorted(heats, reverse=True):
            raise ValueError(
                f"trending.items의 heat은 순위를 따라 내림차순이어야 한다 (받음: {heats})"
            )
        return self


class EditionContent(_Strict):
    meta: Meta
    theme: Theme
    brand: str
    cover: Cover
    cards: list[Card]
    closing: Closing
    trending: Trending | None = None
