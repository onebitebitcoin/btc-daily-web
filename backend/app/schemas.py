import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


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


class EditionContent(_Strict):
    meta: Meta
    theme: Theme
    brand: str
    cover: Cover
    cards: list[Card]
    closing: Closing
