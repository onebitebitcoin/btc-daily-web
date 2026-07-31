import datetime
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from scripts import collect_daily, generate_qa, push_edition

NOW = datetime.datetime(2026, 7, 31, 3, 0, tzinfo=datetime.UTC)

REFERENCE_CONTENT = Path(__file__).resolve().parents[2] / "reference" / "content.json"


def reference_payload(date: str = "2026-07-30") -> dict[str, Any]:
    payload = json.loads(REFERENCE_CONTENT.read_text(encoding="utf-8"))
    payload["meta"]["date"] = date
    payload["cover"] = collect_daily.apply_date_to_cover(
        payload["cover"], datetime.date.fromisoformat(date)
    )
    return payload


def make_news(**overrides: Any) -> dict[str, Any]:
    base = {
        "source_ref": "Cointelegraph",
        "crawled_at": "2026-07-31T02:00:00+00:00",
        "is_duplicate": False,
        "dup_count": 0,
    }
    base.update(overrides)
    return base


def make_video(**overrides: Any) -> dict[str, Any]:
    base = {
        "id": "abc123",
        "topic": "비트코인",
        "summary": "요약",
        "added_at": "2026-07-31T02:00:00+00:00",
        "view_count": 100,
    }
    base.update(overrides)
    return base


def make_qa_response(prefix: str = "Q") -> dict[str, Any]:
    questions = [
        {
            "question": f"{prefix}{i}",
            "answer": f"A{i}",
            "sources": [f"https://example.com/{i}"],
        }
        for i in range(1, generate_qa.QUESTIONS_PER_CARD + 1)
    ]
    return {
        "steps": [
            {
                "type": "model_output",
                "content": [{"type": "text", "text": json.dumps({"questions": questions})}],
            }
        ]
    }


# ---- collect_daily.filter_news ----


def test_filter_news_excludes_duplicates() -> None:
    items = [make_news(is_duplicate=True), make_news(is_duplicate=False)]

    result = collect_daily.filter_news(items, NOW)

    assert len(result) == 1
    assert result[0]["is_duplicate"] is False


def test_filter_news_excludes_older_than_24h() -> None:
    items = [
        make_news(crawled_at="2026-07-29T00:00:00+00:00"),
        make_news(crawled_at="2026-07-31T01:00:00+00:00"),
    ]

    result = collect_daily.filter_news(items, NOW)

    assert len(result) == 1
    assert result[0]["crawled_at"] == "2026-07-31T01:00:00+00:00"


def test_filter_news_sorts_by_dup_count_then_recency() -> None:
    a = make_news(source_ref="A", dup_count=0, crawled_at="2026-07-31T02:50:00+00:00")
    b = make_news(source_ref="B", dup_count=3, crawled_at="2026-07-31T01:00:00+00:00")
    c = make_news(source_ref="C", dup_count=0, crawled_at="2026-07-31T02:55:00+00:00")

    result = collect_daily.filter_news([a, b, c], NOW)

    assert [n["source_ref"] for n in result] == ["B", "C", "A"]


def test_filter_news_caps_at_20() -> None:
    items = [make_news(source_ref=str(i)) for i in range(30)]

    result = collect_daily.filter_news(items, NOW)

    assert len(result) == 20


# ---- collect_daily.filter_videos ----


def test_filter_videos_requires_bitcoin_topic_and_summary() -> None:
    items = [make_video(id="wrong-topic", topic="AI"), make_video(id="no-summary", summary="")]

    assert collect_daily.filter_videos(items, NOW) == []


def test_filter_videos_excludes_older_than_24h() -> None:
    items = [make_video(added_at="2026-07-29T00:00:00+00:00")]

    assert collect_daily.filter_videos(items, NOW) == []


def test_filter_videos_sorts_by_view_count_desc_capped_at_5() -> None:
    items = [make_video(id=str(i), view_count=i) for i in range(7)]

    result = collect_daily.filter_videos(items, NOW)

    assert [v["id"] for v in result] == ["6", "5", "4", "3", "2"]


# ---- collect_daily.build_skeleton ----


def test_build_skeleton_generates_date_slug_title_and_sources() -> None:
    skeleton = collect_daily.build_skeleton(
        datetime.date(2026, 7, 31),
        theme={"bg": "#000"},
        brand="BTC DAILY",
        cover_fixed={"eyebrow": "E", "mark": ["a"], "meta": ["x", "y", "old"], "hint": "h"},
        closing_fixed={
            "eyebrow": "E",
            "mark_lines": ["a"],
            "rows": [["k", "v"]],
            "stamp": "s",
            "restart": "r",
            "sources": [],
        },
        sources=["A", "B"],
    )

    assert skeleton["meta"] == {
        "title": "비트코인 하이라이트 · 7.31",
        "slug": "btc-daily-0731",
        "date": "2026-07-31",
    }
    assert skeleton["cover"]["mark"] == ["7월 31일", "비트코인 카드뉴스"]
    assert skeleton["cover"]["meta"] == ["x", "y", "2026.07.31"]
    assert skeleton["closing"]["sources"] == ["A", "B"]


# ---- collect_daily.main (httpx.MockTransport) ----


def _mock_handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if "news" in url:
        return httpx.Response(200, json=[make_news(source_ref="X")])
    if "queue" in url:
        return httpx.Response(200, json={"items": [make_video(id="v1")]})
    return httpx.Response(404)


def test_collect_daily_main_writes_draft(tmp_path: Path) -> None:
    out_path = tmp_path / "draft.json"

    with httpx.Client(transport=httpx.MockTransport(_mock_handler)) as client:
        result_path = collect_daily.main(
            [
                "--date",
                "2026-07-31",
                "--out",
                str(out_path),
                "--news-url",
                "http://x/news",
                "--youtube-url",
                "http://x/queue",
            ],
            client=client,
        )

    assert result_path == out_path
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["skeleton"]["meta"]["slug"] == "btc-daily-0731"
    assert data["candidates"]["news"][0]["source_ref"] == "X"
    assert data["candidates"]["videos"][0]["thumbnail_url"] == (
        "https://i.ytimg.com/vi/v1/hqdefault.jpg"
    )


def test_collect_daily_main_fails_when_no_candidates(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "news" in str(request.url):
            return httpx.Response(200, json=[])
        return httpx.Response(200, json={"items": []})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SystemExit):
            collect_daily.main(
                [
                    "--date",
                    "2026-07-31",
                    "--out",
                    str(tmp_path / "draft.json"),
                    "--news-url",
                    "http://x/news",
                    "--youtube-url",
                    "http://x/queue",
                ],
                client=client,
            )


def test_collect_daily_main_fails_loudly_when_source_down(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SystemExit, match="my-news"):
            collect_daily.main(
                [
                    "--date",
                    "2026-07-31",
                    "--out",
                    str(tmp_path / "draft.json"),
                    "--news-url",
                    "http://x/news",
                    "--youtube-url",
                    "http://x/queue",
                ],
                client=client,
            )


# ---- push_edition ----


def test_push_edition_local_validation_fails_before_post(tmp_path: Path) -> None:
    payload = reference_payload()
    del payload["meta"]["date"]
    edition_path = tmp_path / "edition.json"
    edition_path.write_text(json.dumps(payload), encoding="utf-8")

    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SystemExit, match="스키마 검증 실패"):
            push_edition.main([str(edition_path)], client=client)

    assert called is False


def test_apply_date_to_cover_derives_mark_and_meta() -> None:
    cover = collect_daily.apply_date_to_cover(
        {"eyebrow": "E", "mark": ["old", "old"], "meta": ["x", "y", "old"], "hint": "h"},
        datetime.date(2026, 7, 31),
    )

    assert cover["mark"] == ["7월 31일", "비트코인 카드뉴스"]
    assert cover["meta"] == ["x", "y", "2026.07.31"]


def test_push_edition_rejects_cover_mark_contradicting_meta_date(tmp_path: Path) -> None:
    payload = reference_payload()
    payload["cover"]["mark"] = ["비트코인", "하이라이트"]  # stale/pre-fix cover
    edition_path = tmp_path / "edition.json"
    edition_path.write_text(json.dumps(payload), encoding="utf-8")

    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SystemExit, match="cover가 meta.date와 불일치"):
            push_edition.main([str(edition_path)], client=client)

    assert called is False


def test_push_edition_accepts_cover_matching_meta_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    edition_path = tmp_path / "edition.json"
    edition_path.write_text(json.dumps(reference_payload()), encoding="utf-8")
    env_file = tmp_path / ".env"
    env_file.write_text("ADMIN_API_KEY=secret\n", encoding="utf-8")
    monkeypatch.setattr(push_edition, "ENV_FILE", env_file)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=request.content)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = push_edition.main([str(edition_path)], client=client)

    assert result["cover"]["mark"] == ["7월 30일", "비트코인 카드뉴스"]


def test_push_edition_missing_api_key_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    edition_path = tmp_path / "edition.json"
    edition_path.write_text(json.dumps(reference_payload()), encoding="utf-8")
    monkeypatch.setattr(push_edition, "ENV_FILE", tmp_path / "nonexistent.env")

    with pytest.raises(SystemExit, match="ADMIN_API_KEY"):
        push_edition.main([str(edition_path)])


def test_push_edition_success_posts_validated_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    edition_path = tmp_path / "edition.json"
    edition_path.write_text(json.dumps(reference_payload()), encoding="utf-8")
    env_file = tmp_path / ".env"
    env_file.write_text("ADMIN_API_KEY=secret\n", encoding="utf-8")
    monkeypatch.setattr(push_edition, "ENV_FILE", env_file)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer secret"
        return httpx.Response(200, content=request.content)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = push_edition.main([str(edition_path)], client=client)

    assert result["meta"]["date"] == "2026-07-30"


# ---- generate_qa ----


def _write_edition(tmp_path: Path, num_cards: int = 2, qa: Any = None) -> Path:
    payload = reference_payload()
    payload["cards"] = payload["cards"][:num_cards]
    if qa is not None:
        payload["cards"][0]["qa"] = qa
    edition_path = tmp_path / "edition.json"
    edition_path.write_text(json.dumps(payload), encoding="utf-8")
    return edition_path


def _write_gemini_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("GEMINI_API_KEY=secret\n", encoding="utf-8")
    monkeypatch.setattr(generate_qa, "ENV_FILE", env_file)


def test_generate_qa_main_fills_cards(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    edition_path = _write_edition(tmp_path, num_cards=2)
    _write_gemini_env(tmp_path, monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-goog-api-key"] == "secret"
        return httpx.Response(200, json=make_qa_response())

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result_path = generate_qa.main(
            [str(edition_path)], client=client, sleep=lambda seconds: None
        )

    assert result_path == edition_path
    data = json.loads(edition_path.read_text(encoding="utf-8"))
    for card in data["cards"]:
        assert len(card["qa"]) == generate_qa.QUESTIONS_PER_CARD
        assert card["qa"][0] == {
            "question": "Q1",
            "answer": "A1",
            "sources": ["https://example.com/1"],
        }


def test_generate_qa_main_continues_after_per_card_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    edition_path = _write_edition(tmp_path, num_cards=2)
    _write_gemini_env(tmp_path, monkeypatch)
    failing_card_title = json.loads(edition_path.read_text(encoding="utf-8"))["cards"][0]["title"]

    def handler(request: httpx.Request) -> httpx.Response:
        # 500은 재시도 가능(retryable) 오류라 여러 번(백오프 포함) 재시도한다 — 실패 카드는
        # 매 시도 500을 받아야 재시도로도 살아나지 않는다는 걸 검증한다 (호출 횟수 기반이면
        # 재시도에 우연히 성공해버려 이 테스트가 뭘 확인하는지 흐려진다). sleep은 no-op을
        # 주입해 백오프로 인한 실제 대기를 없앤다.
        if failing_card_title in request.content.decode("utf-8"):
            return httpx.Response(500)
        return httpx.Response(200, json=make_qa_response())

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        generate_qa.main([str(edition_path)], client=client, sleep=lambda seconds: None)

    data = json.loads(edition_path.read_text(encoding="utf-8"))
    assert data["cards"][0]["qa"] is None
    assert len(data["cards"][1]["qa"]) == generate_qa.QUESTIONS_PER_CARD

    captured = capsys.readouterr()
    assert "성공 1" in captured.out
    assert "실패 1" in captured.out


def test_generate_qa_recovers_on_retry_after_transient_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    edition_path = _write_edition(tmp_path, num_cards=1)
    _write_gemini_env(tmp_path, monkeypatch)

    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(500)
        return httpx.Response(200, json=make_qa_response())

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        generate_qa.main([str(edition_path)], client=client, sleep=lambda seconds: None)

    data = json.loads(edition_path.read_text(encoding="utf-8"))
    assert len(data["cards"][0]["qa"]) == generate_qa.QUESTIONS_PER_CARD
    assert calls == 2

    captured = capsys.readouterr()
    assert "성공 1" in captured.out
    assert "실패 0" in captured.out


def test_generate_qa_strips_markdown_code_fence_around_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    edition_path = _write_edition(tmp_path, num_cards=1)
    _write_gemini_env(tmp_path, monkeypatch)

    fenced = make_qa_response()
    raw_text = fenced["steps"][0]["content"][0]["text"]
    fenced["steps"][0]["content"][0]["text"] = f"```json\n{raw_text}\n```"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=fenced)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        generate_qa.main([str(edition_path)], client=client)

    data = json.loads(edition_path.read_text(encoding="utf-8"))
    assert len(data["cards"][0]["qa"]) == generate_qa.QUESTIONS_PER_CARD


def test_generate_qa_main_skips_existing_qa_without_force(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    existing_qa = [
        {"question": "old", "answer": "old-a", "sources": ["https://old.example.com"]}
    ] * generate_qa.QUESTIONS_PER_CARD
    edition_path = _write_edition(tmp_path, num_cards=1, qa=existing_qa)
    _write_gemini_env(tmp_path, monkeypatch)

    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=make_qa_response())

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        generate_qa.main([str(edition_path)], client=client)

    assert calls == 0
    data = json.loads(edition_path.read_text(encoding="utf-8"))
    assert data["cards"][0]["qa"] == existing_qa


def test_generate_qa_main_force_regenerates_existing_qa(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    existing_qa = [
        {"question": "old", "answer": "old-a", "sources": ["https://old.example.com"]}
    ] * generate_qa.QUESTIONS_PER_CARD
    edition_path = _write_edition(tmp_path, num_cards=1, qa=existing_qa)
    _write_gemini_env(tmp_path, monkeypatch)

    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=make_qa_response())

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        generate_qa.main([str(edition_path), "--force"], client=client)

    assert calls == 1
    data = json.loads(edition_path.read_text(encoding="utf-8"))
    assert data["cards"][0]["qa"] != existing_qa
    assert data["cards"][0]["qa"][0]["question"] == "Q1"


def test_generate_qa_missing_api_key_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    edition_path = _write_edition(tmp_path, num_cards=1)
    monkeypatch.setattr(generate_qa, "ENV_FILE", tmp_path / "nonexistent.env")

    with pytest.raises(SystemExit, match="GEMINI_API_KEY"):
        generate_qa.main([str(edition_path)])


def test_generate_qa_retries_after_429_then_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    edition_path = _write_edition(tmp_path, num_cards=1)
    _write_gemini_env(tmp_path, monkeypatch)

    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429)
        return httpx.Response(200, json=make_qa_response())

    sleeps: list[float] = []

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        generate_qa.main([str(edition_path)], client=client, sleep=sleeps.append)

    data = json.loads(edition_path.read_text(encoding="utf-8"))
    assert len(data["cards"][0]["qa"]) == generate_qa.QUESTIONS_PER_CARD
    assert calls == 2
    # 백오프로 실제 대기를 걸었는지(핫루프가 아닌지) 확인한다.
    assert sleeps == [generate_qa.RETRYABLE_BACKOFF_SECONDS[0]]


def test_generate_qa_honors_retry_after_header(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    edition_path = _write_edition(tmp_path, num_cards=1)
    _write_gemini_env(tmp_path, monkeypatch)

    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "2"})
        return httpx.Response(200, json=make_qa_response())

    sleeps: list[float] = []

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        generate_qa.main([str(edition_path)], client=client, sleep=sleeps.append)

    data = json.loads(edition_path.read_text(encoding="utf-8"))
    assert len(data["cards"][0]["qa"]) == generate_qa.QUESTIONS_PER_CARD
    # Retry-After 헤더 값(2초)을 써야지 기본 백오프(5초)를 쓰면 안 된다.
    assert sleeps == [2.0]


def test_generate_qa_persistent_429_reports_rate_limit_in_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    edition_path = _write_edition(tmp_path, num_cards=1)
    _write_gemini_env(tmp_path, monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429)

    sleeps: list[float] = []

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        generate_qa.main([str(edition_path)], client=client, sleep=sleeps.append)

    data = json.loads(edition_path.read_text(encoding="utf-8"))
    assert data["cards"][0]["qa"] is None
    assert sleeps == list(generate_qa.RETRYABLE_BACKOFF_SECONDS)

    captured = capsys.readouterr()
    assert "실패 1" in captured.out
    assert "레이트 리밋" in captured.out


def test_generate_qa_non_retryable_error_skips_backoff_sleep(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    edition_path = _write_edition(tmp_path, num_cards=1)
    _write_gemini_env(tmp_path, monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400)

    sleeps: list[float] = []

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        generate_qa.main([str(edition_path)], client=client, sleep=sleeps.append)

    data = json.loads(edition_path.read_text(encoding="utf-8"))
    assert data["cards"][0]["qa"] is None
    assert sleeps == []

    captured = capsys.readouterr()
    assert "레이트 리밋" not in captured.out


def test_generate_qa_delay_applied_between_cards_not_before_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    edition_path = _write_edition(tmp_path, num_cards=2)
    _write_gemini_env(tmp_path, monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=make_qa_response())

    sleeps: list[float] = []

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        generate_qa.main(
            [str(edition_path), "--delay", "7"], client=client, sleep=sleeps.append
        )

    # 카드 2장, 둘 다 첫 시도에 성공 — 카드 사이 대기 1번만 걸리고, 첫 카드 전에는 없다.
    assert sleeps == [7.0]
