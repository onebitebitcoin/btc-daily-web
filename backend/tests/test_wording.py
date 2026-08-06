import datetime
import json
from pathlib import Path
from typing import Any

from app.schemas import EditionContent
from app.wording import EFFECTIVE_DATE, find_problems

REFERENCE_CONTENT = Path(__file__).resolve().parents[2] / "reference" / "content.json"

AFTER = EFFECTIVE_DATE.isoformat()
BEFORE = (EFFECTIVE_DATE - datetime.timedelta(days=1)).isoformat()


def build(date: str = AFTER, **card_overrides: Any) -> EditionContent:
    """레퍼런스 콘텐츠에 카드 1장만 남기고 필드를 갈아끼운 에디션."""
    payload = json.loads(REFERENCE_CONTENT.read_text(encoding="utf-8"))
    payload["meta"]["date"] = date
    card = payload["cards"][0]
    card.update(
        {
            "title": "비트코인, 박스권 상단을 다시 두드린다",
            "body": "비트코인이 상단을 다시 두드리고 있습니다.",
            "quote": "아직 하락장이 아닙니다.",
            "chips": ["#비트코인", "#박스권", "#지지선"],
            "qa": None,
        }
    )
    card.update(card_overrides)
    payload["cards"] = [card]
    payload.pop("trending", None)
    return EditionContent.model_validate(payload)


def test_clean_edition_passes() -> None:
    assert find_problems(build()) == []


def test_banned_transliteration_is_caught() -> None:
    problems = find_problems(build(body="갈럭시 인프라를 쓴다고 밝혔습니다."))

    assert len(problems) == 1
    assert "갈럭시" in problems[0] and "갤럭시" in problems[0]
    assert "카드 1 body" in problems[0]


def test_btc_in_korean_copy_is_caught() -> None:
    problems = find_problems(build(title="594 BTC가 한 지갑으로 빨려 들어갔다"))

    assert len(problems) == 1
    assert "비트코인" in problems[0]
    assert "카드 1 title" in problems[0]


def test_english_subtitle_may_keep_btc() -> None:
    # CLAUDE.md의 명시적 예외 — 전체가 영문인 필드는 영문 표기 관례를 따른다.
    assert find_problems(build(subtitle="Fed Holds, BTC Slides")) == []


def test_btc_inside_a_longer_token_is_not_flagged() -> None:
    # "BTCUSD" 같은 티커나 slug 를 오탐하면 게이트를 신뢰할 수 없게 된다.
    assert find_problems(build(body="BTCUSD 차트를 봤습니다.")) == []


def test_plain_style_body_is_caught() -> None:
    problems = find_problems(build(body="비트코인이 상단을 다시 두드리고 있다."))

    assert len(problems) == 1
    assert "했습니다체가 아니다" in problems[0]


def test_plain_style_quote_is_caught() -> None:
    problems = find_problems(build(quote="아직 하락장이 아니다."))

    assert [p for p in problems if "quote" in p and "했습니다체" in p]


def test_composed_polite_endings_are_accepted() -> None:
    # 아닙니다/탑니다/기댑니다는 "습니다"로 끝나지 않는다 — 종성 ㅂ으로 봐야 통과한다.
    for ending in ("같은 배관을 탑니다.", "안전성에만 기댑니다.", "하락장이 아닙니다."):
        assert find_problems(build(body=ending)) == [], ending


def test_plain_style_anida_is_not_mistaken_for_polite() -> None:
    # "아니다"도 '니다'로 끝난다. 종성을 안 보면 평서체가 그대로 통과한다.
    problems = find_problems(build(body="지금은 하락장이 아니다."))

    assert len(problems) == 1
    assert "했습니다체가 아니다" in problems[0]


def test_trailing_quote_mark_does_not_break_the_ending_check() -> None:
    assert find_problems(build(quote='"아직 하락장이 아닙니다."')) == []


def test_quote_may_be_absent() -> None:
    assert find_problems(build(quote=None)) == []


def test_qa_answers_are_checked_too() -> None:
    qa = [{"question": "왜 그런가요?", "answer": "갈럭시가 맡고 있습니다.", "sources": []}]
    problems = find_problems(build(qa=qa))

    assert len(problems) == 1
    assert "qa[1].answer" in problems[0]


def test_editions_before_the_contract_date_are_skipped() -> None:
    # 07-27~08-06 발행분은 평서체에 제목 BTC 도 있다. 소급 적용하면 재발행이 막힌다.
    stale = build(date=BEFORE, title="594 BTC가 움직였다", body="가격이 밀렸다.", quote="끝났다.")

    assert find_problems(stale) == []


def test_trending_topic_is_checked_but_source_titles_are_not() -> None:
    payload = json.loads(REFERENCE_CONTENT.read_text(encoding="utf-8"))
    payload["meta"]["date"] = AFTER
    for card in payload["cards"]:
        card.update({"body": "그렇습니다.", "quote": None, "qa": None})
    items: list[dict[str, Any]] = [
        {"rank": rank, "topic": f"토픽 {rank}", "heat": 100 - rank, "mentions": 3, "sources": 2}
        for rank in range(1, 11)
    ]
    items[0]["topic"] = "갈럭시 수탁"
    # 기사 원제는 그대로 옮기는 게 계약이라 여기서 걸면 안 된다.
    items[0]["links"] = [
        {"title": "594 BTC moved", "href": "https://e.com/a", "source": "Decrypt"}
    ]
    payload["trending"] = {
        "eyebrow": "24H TRENDING",
        "title": "지난 24시간 가장 뜨거웠던 토픽",
        "note": "뉴스 10건 3매체 집계",
        "items": items,
    }
    problems = find_problems(EditionContent.model_validate(payload))

    assert len(problems) == 1
    assert "트렌딩 1위 topic" in problems[0]


def test_cover_quote_is_not_subject_to_the_polite_ending_rule() -> None:
    """인용문은 번역된 남의 말이라 어미를 고칠 대상이 아니다.

    미제스를 "…없습니다"로 바꿀 수는 없다. 나중에 누가 "커버도 검사해야지" 하고
    find_problems 에 cover 를 추가하면 이 테스트가 막는다.
    """
    payload = json.loads(REFERENCE_CONTENT.read_text(encoding="utf-8"))
    payload["meta"]["date"] = AFTER
    for card in payload["cards"]:
        card.update({"body": "그렇습니다.", "quote": None, "qa": None})
    payload["cover"]["quote"] = {
        "id": "mises-boom-collapse",
        "text": "신용 확장이 만들어낸 호황은 끝내 붕괴를 피할 방법이 없다.",
        "author": "루트비히 폰 미제스",
        "portrait": None,
    }
    payload.pop("trending", None)

    assert find_problems(EditionContent.model_validate(payload)) == []
