import datetime

import pytest

from app.quotes import Quote, as_cover_quote, is_exhausted, load_pool, pick_quote

DAY = datetime.date(2026, 8, 7)


def make(qid: str, **overrides: object) -> Quote:
    base: dict[str, object] = {
        "id": qid,
        "ko": f"{qid} 한국어",
        "en": f"{qid} english",
        "author": "루트비히 폰 미제스",
        "work": "인간행동",
        "year": 1949,
    }
    base.update(overrides)
    return Quote(**base)  # type: ignore[arg-type]


def test_shipped_pool_loads_and_has_no_duplicate_ids() -> None:
    pool = load_pool()

    assert len(pool) >= 20, f"풀이 너무 작다: {len(pool)}"
    assert len({q.id for q in pool}) == len(pool)


def test_shipped_pool_records_a_source_for_every_quote() -> None:
    # 오귀속을 막는 장치 — 나중에 검증하려면 저작과 연도가 있어야 한다.
    for quote in load_pool():
        assert quote.en.strip(), quote.id
        assert quote.work.strip(), quote.id
        assert quote.year > 1800, quote.id


def test_shipped_pool_records_license_for_every_portrait() -> None:
    # 초상을 넣었다면 출처·라이선스가 반드시 따라와야 한다. 공개 사이트다.
    for quote in load_pool():
        if quote.portrait:
            assert quote.portrait_source, f"{quote.id}: 초상 출처 없음"
            assert quote.portrait_license, f"{quote.id}: 초상 라이선스 없음"


def test_duplicate_ids_in_the_pool_are_rejected(tmp_path: object) -> None:
    from pathlib import Path

    path = Path(str(tmp_path)) / "dupes.json"
    entry = {
        "id": "same",
        "ko": "가",
        "en": "a",
        "author": "A",
        "work": "W",
        "year": 1949,
        "portrait": None,
        "portrait_source": None,
        "portrait_license": None,
    }
    import json

    path.write_text(json.dumps([entry, entry]), encoding="utf-8")

    with pytest.raises(ValueError, match="중복"):
        load_pool(path)


def test_picks_something_when_nothing_has_been_used() -> None:
    pool = [make("a"), make("b"), make("c")]

    assert pick_quote(pool, [], DAY) in pool


def test_same_date_and_history_picks_the_same_quote() -> None:
    # 재발행이 인용구를 바꾸면 안 된다.
    pool = [make("a"), make("b"), make("c")]

    assert pick_quote(pool, ["a"], DAY).id == pick_quote(pool, ["a"], DAY).id


def test_already_used_quotes_are_never_picked() -> None:
    pool = [make("a"), make("b"), make("c")]

    for offset in range(30):
        day = DAY + datetime.timedelta(days=offset)
        assert pick_quote(pool, ["a", "b"], day).id == "c"


def test_a_full_pool_cycle_never_repeats() -> None:
    # 핵심 요구사항 — 풀을 한 바퀴 도는 동안 같은 인용구가 두 번 나오면 안 된다.
    pool = load_pool()
    recent: list[str] = []

    for offset in range(len(pool)):
        picked = pick_quote(pool, recent, DAY + datetime.timedelta(days=offset))
        recent.insert(0, picked.id)  # 최신이 앞

    assert len(set(recent)) == len(pool)


def test_exhausted_pool_reuses_the_oldest_first() -> None:
    pool = [make("a"), make("b"), make("c")]
    # 최신 -> 오래된 순. 가장 오래전에 쓴 것은 "a".
    recent = ["c", "b", "a"]

    assert pick_quote(pool, recent, DAY).id == "a"


def test_exhausted_ignores_unknown_ids_from_older_editions() -> None:
    # 풀에서 뺀 인용구가 과거 발행분에 남아 있어도 그걸 되살리면 안 된다.
    pool = [make("a"), make("b")]
    recent = ["b", "a", "retired-quote"]

    assert pick_quote(pool, recent, DAY).id == "a"


def test_is_exhausted_reports_the_full_cycle() -> None:
    pool = [make("a"), make("b")]

    assert is_exhausted(pool, ["a", "b"]) is True
    assert is_exhausted(pool, ["a"]) is False


def test_empty_pool_is_an_error_not_a_silent_none() -> None:
    with pytest.raises(ValueError, match="비었다"):
        pick_quote([], [], DAY)


def test_cover_quote_payload_keeps_the_id_for_next_day_dedup() -> None:
    payload = as_cover_quote(make("mises-boom", portrait="mises"))

    assert payload == {
        "id": "mises-boom",
        "text": "mises-boom 한국어",
        "author": "루트비히 폰 미제스",
        "portrait": "mises",
    }
