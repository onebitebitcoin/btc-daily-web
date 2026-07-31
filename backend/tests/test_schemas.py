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
    assert content.closing.rows[0] == ("수집 기간", "최근 24시간")
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


def test_closing_row_must_be_a_pair() -> None:
    payload = reference_payload()
    payload["closing"]["rows"][0] = ["only-one"]

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
