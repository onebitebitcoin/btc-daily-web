import datetime
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas import EditionContent

REFERENCE_CONTENT = Path(__file__).resolve().parents[2] / "reference" / "content.json"


def reference_payload() -> dict[str, Any]:
    payload = json.loads(REFERENCE_CONTENT.read_text(encoding="utf-8"))
    payload["meta"]["date"] = "2026-07-30"
    return payload


def test_reference_content_validates() -> None:
    content = EditionContent.model_validate(reference_payload())

    assert content.meta.date == datetime.date(2026, 7, 30)
    assert content.meta.slug == "btc-daily-0730"
    assert content.brand == "BTC DAILY"
    assert len(content.cards) == 10
    assert content.cards[0].chip.emphasis == "primary"
    assert content.cards[2].chip.emphasis is None
    assert content.cards[7].media is None
    assert content.closing.links[0].label == "유튜브 구독하기"
    assert content.theme.accent == "#f2a93b"


def test_missing_meta_date_fails() -> None:
    payload = reference_payload()
    del payload["meta"]["date"]

    with pytest.raises(ValidationError) as exc_info:
        EditionContent.model_validate(payload)

    errors = exc_info.value.errors()
    assert [e["loc"] for e in errors] == [("meta", "date")]
    assert errors[0]["type"] == "missing"


def test_invalid_chip_emphasis_fails() -> None:
    payload = reference_payload()
    payload["cards"][0]["chip"]["emphasis"] = "tertiary"

    with pytest.raises(ValidationError) as exc_info:
        EditionContent.model_validate(payload)

    assert any(e["loc"][:4] == ("cards", 0, "chip", "emphasis") for e in exc_info.value.errors())


def test_unknown_field_fails() -> None:
    payload = reference_payload()
    payload["cards"][0]["titel"] = "typo"

    with pytest.raises(ValidationError):
        EditionContent.model_validate(payload)


def test_closing_link_requires_href() -> None:
    payload = reference_payload()
    del payload["closing"]["links"][0]["href"]

    with pytest.raises(ValidationError):
        EditionContent.model_validate(payload)


def test_card_qa_accepts_missing_and_full_list() -> None:
    payload = reference_payload()
    assert "qa" not in payload["cards"][0]

    content = EditionContent.model_validate(payload)
    assert content.cards[0].qa is None

    payload["cards"][1]["qa"] = [
        {"question": "Q1", "answer": "A1", "sources": ["https://example.com"]},
        {"question": "Q2", "answer": "A2", "sources": []},
        {
            "question": "Q3",
            "answer": "A3",
            "sources": ["https://example.com/a", "https://example.com/b"],
        },
    ]

    content = EditionContent.model_validate(payload)
    assert content.cards[1].qa is not None
    assert len(content.cards[1].qa) == 3
    assert content.cards[1].qa[0].question == "Q1"


# ---- trending (선택 블록 — 기존 발행분 9편에는 없다) ----


def _trending_items(n: int = 10) -> list[dict[str, Any]]:
    return [
        {
            "rank": i,
            "topic": f"토픽{i}",
            "heat": 100 - (i - 1) * 5,
            "mentions": 11 - i,
            "sources": 3,
        }
        for i in range(1, n + 1)
    ]


def _trending_block(n: int = 10) -> dict[str, Any]:
    return {
        "eyebrow": "24H TRENDING",
        "title": "지난 24시간 가장 뜨거웠던 토픽",
        "note": "뉴스 20건 · 유튜브 5건 집계",
        "items": _trending_items(n),
    }


def test_trending_absent_still_validates() -> None:
    payload = reference_payload()
    assert "trending" not in payload

    content = EditionContent.model_validate(payload)

    assert content.trending is None


def test_trending_with_valid_items_validates() -> None:
    payload = reference_payload()
    payload["trending"] = _trending_block()

    content = EditionContent.model_validate(payload)

    assert content.trending is not None
    assert len(content.trending.items) == 10
    assert content.trending.items[0].rank == 1
    assert content.trending.items[0].heat == 100


def test_trending_item_links_are_optional() -> None:
    """트렌딩 도입 초기 발행분에는 links 가 없다 — 그 편들이 계속 살아 있어야 한다."""
    payload = reference_payload()
    payload["trending"] = _trending_block()
    assert "links" not in payload["trending"]["items"][0]

    content = EditionContent.model_validate(payload)

    assert content.trending is not None
    assert content.trending.items[0].links is None


def test_trending_item_accepts_source_links() -> None:
    payload = reference_payload()
    trending = _trending_block()
    trending["items"][0]["links"] = [
        {"title": "콜드카드 취약점 기사", "href": "https://a.example/1", "source": "토큰포스트"},
        {"title": "Coldcard exploit", "href": "https://b.example/2", "source": "CoinDesk"},
    ]
    payload["trending"] = trending

    content = EditionContent.model_validate(payload)

    links = content.trending.items[0].links  # type: ignore[union-attr]
    assert links is not None
    assert [link.href for link in links] == ["https://a.example/1", "https://b.example/2"]
    assert links[0].title == "콜드카드 취약점 기사"
    assert links[0].source == "토큰포스트"


def test_trending_link_source_is_optional() -> None:
    payload = reference_payload()
    trending = _trending_block()
    trending["items"][0]["links"] = [{"title": "출처 없는 기사", "href": "https://a.example/1"}]
    payload["trending"] = trending

    content = EditionContent.model_validate(payload)

    assert content.trending.items[0].links[0].source is None  # type: ignore[union-attr,index]


def test_trending_link_requires_both_title_and_href() -> None:
    """제목만 있고 href 가 없으면 눌리지 않는 줄이 목록에 박힌다 — 그 반대도 마찬가지."""
    payload = reference_payload()

    for broken in ({"title": "제목만 있음"}, {"href": "https://a.example/1"}):
        trending = _trending_block()
        trending["items"][0]["links"] = [broken]
        payload["trending"] = trending

        with pytest.raises(ValidationError):
            EditionContent.model_validate(payload)


def test_trending_link_rejects_the_old_label_shape() -> None:
    """카드용 Link(label/href)를 그대로 넣으면 제목이 사라진 채 발행된다 — 막는다."""
    payload = reference_payload()
    trending = _trending_block()
    trending["items"][0]["links"] = [{"label": "토큰포스트 원문", "href": "https://a.example/1"}]
    payload["trending"] = trending

    with pytest.raises(ValidationError):
        EditionContent.model_validate(payload)


def test_trending_rejects_wrong_item_count() -> None:
    payload = reference_payload()
    payload["trending"] = _trending_block(n=9)

    with pytest.raises(ValidationError):
        EditionContent.model_validate(payload)


def test_trending_rejects_non_ascending_rank() -> None:
    payload = reference_payload()
    trending = _trending_block()
    trending["items"][0]["rank"], trending["items"][1]["rank"] = (
        trending["items"][1]["rank"],
        trending["items"][0]["rank"],
    )
    payload["trending"] = trending

    with pytest.raises(ValidationError):
        EditionContent.model_validate(payload)


def test_trending_rejects_heat_that_contradicts_the_rank() -> None:
    """heat은 막대 길이로 그려진다 — 3위 막대가 1위보다 길면 눈에 보이는 모순이다."""
    payload = reference_payload()
    trending = _trending_block()
    trending["items"][2]["heat"] = 100
    trending["items"][0]["heat"] = 40
    payload["trending"] = trending

    with pytest.raises(ValidationError):
        EditionContent.model_validate(payload)


def test_trending_allows_tied_heat() -> None:
    """꼬리 토픽들은 근거가 같아 점수가 동률로 나오는 게 정상이다."""
    payload = reference_payload()
    trending = _trending_block()
    for item in trending["items"][5:]:
        item["heat"] = 5
    payload["trending"] = trending

    assert EditionContent.model_validate(payload).trending is not None


def test_trending_rejects_item_note_that_the_card_never_renders() -> None:
    """items[].note는 계약에서 뺐다 — 카드가 렌더하지 않는 필드를 조용히 받지 않는다."""
    payload = reference_payload()
    trending = _trending_block()
    trending["items"][0]["note"] = "어딘가에 쓰이겠지"
    payload["trending"] = trending

    with pytest.raises(ValidationError):
        EditionContent.model_validate(payload)


def test_trending_rejects_heat_out_of_range() -> None:
    payload = reference_payload()
    trending = _trending_block()
    trending["items"][0]["heat"] = 101
    payload["trending"] = trending

    with pytest.raises(ValidationError):
        EditionContent.model_validate(payload)


def test_trending_rejects_unknown_field() -> None:
    payload = reference_payload()
    trending = _trending_block()
    trending["typo_field"] = "x"
    payload["trending"] = trending

    with pytest.raises(ValidationError):
        EditionContent.model_validate(payload)


def cover_quote() -> dict[str, Any]:
    return {
        "id": "mises-boom-collapse",
        "text": "신용 확장이 만들어낸 호황은 끝내 붕괴를 피할 방법이 없다.",
        "author": "루트비히 폰 미제스",
        "portrait": None,
    }


def test_cover_quote_is_optional_so_earlier_editions_still_validate() -> None:
    # 07-27~08-07 발행분에는 cover.quote 가 없다. 필수로 만들면 재발행이 막힌다.
    content = EditionContent.model_validate(reference_payload())

    assert content.cover.quote is None


def test_cover_quote_round_trips() -> None:
    payload = reference_payload()
    payload["cover"]["quote"] = cover_quote()

    content = EditionContent.model_validate(payload)

    assert content.cover.quote is not None
    assert content.cover.quote.id == "mises-boom-collapse"
    assert content.cover.quote.author == "루트비히 폰 미제스"
    assert content.cover.quote.portrait is None


def test_cover_quote_portrait_defaults_to_none() -> None:
    payload = reference_payload()
    quote = cover_quote()
    del quote["portrait"]
    payload["cover"]["quote"] = quote

    assert EditionContent.model_validate(payload).cover.quote.portrait is None


def test_cover_quote_rejects_unknown_keys() -> None:
    payload = reference_payload()
    payload["cover"]["quote"] = {**cover_quote(), "en": "There is no means..."}

    # 원문·저작은 austrian_quotes.json 에만 산다 — 발행물에 실어 나르지 않는다.
    with pytest.raises(ValidationError):
        EditionContent.model_validate(payload)


def test_cover_quote_requires_an_id_for_next_day_dedup() -> None:
    payload = reference_payload()
    quote = cover_quote()
    del quote["id"]
    payload["cover"]["quote"] = quote

    with pytest.raises(ValidationError):
        EditionContent.model_validate(payload)
