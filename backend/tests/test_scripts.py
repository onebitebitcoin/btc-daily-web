import datetime
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from scripts import collect_daily, generate_qa, push_edition, recent_editions

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
        "published_at": "2026-07-31T02:00:00+00:00",
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


def test_filter_news_ignores_dup_count_for_ordering() -> None:
    """dup_count 는 더 이상 정렬에 관여하지 않는다.

    실측상 dup_count 가 거의 항상 0이라 죽은 정렬키였다 — 그 자리를 시간 균등
    선별(NEWS_BUCKETS)이 대신한다. dup_count 를 crawled_at 과 반대로 둬서(가장
    오래된 게 dup_count 최대) 옛 정렬키였다면 뒤집혔을 순서가 crawled_at
    내림차순 그대로 나오는지 확인한다.
    """
    a = make_news(source_ref="A", dup_count=0, crawled_at="2026-07-31T02:55:00+00:00")
    b = make_news(source_ref="B", dup_count=3, crawled_at="2026-07-31T02:50:00+00:00")
    c = make_news(source_ref="C", dup_count=9, crawled_at="2026-07-31T02:45:00+00:00")

    result = collect_daily.filter_news([a, b, c], NOW)

    assert [n["source_ref"] for n in result] == ["A", "B", "C"]


def test_filter_news_orders_within_a_bucket_by_recency() -> None:
    """같은 6시간 구간 안에서는 crawled_at 이 더 최근인 기사가 먼저 나온다."""
    items = [
        make_news(source_ref="oldest", crawled_at="2026-07-31T02:00:00+00:00"),
        make_news(source_ref="newest", crawled_at="2026-07-31T02:50:00+00:00"),
        make_news(source_ref="middle", crawled_at="2026-07-31T02:25:00+00:00"),
    ]

    result = collect_daily.filter_news(items, NOW)

    assert [n["source_ref"] for n in result] == ["newest", "middle", "oldest"]


def test_filter_news_round_robins_evenly_across_the_four_buckets() -> None:
    """15/5/5/5 건으로 쏠려 있어도 라운드로빈이라 각 구간에서 최소 5건씩 나온다.

    NOW=2026-07-31T03:00 기준 구간은 6시간씩: b0=[21:00,03:00) b1=[15:00,21:00)
    b2=[09:00,15:00) b3=[03:00,09:00)(전날). b0 에 15건, b1/b2/b3 에 각 5건을 두면
    라운드로빈(구간당 1건씩, 0→1→2→3 순회)은 5라운드 만에 정확히 20건에 닿는다 —
    b1/b2/b3 는 가진 5건을 전부 내주고, b0 는 15건 중 가장 최신 5건만 내준다.
    최종 반환은 crawled_at 내림차순이고 구간끼리는 시간이 겹치지 않으므로,
    구간 순서(b0→b1→b2→b3) 그대로 이어붙인 모양이 된다.
    """
    b0 = [
        make_news(
            source_ref=f"b0-{i}", crawled_at=(NOW - datetime.timedelta(minutes=i + 1)).isoformat()
        )
        for i in range(15)
    ]
    b1_base = NOW - datetime.timedelta(hours=7)
    b1 = [
        make_news(
            source_ref=f"b1-{i}", crawled_at=(b1_base - datetime.timedelta(minutes=i)).isoformat()
        )
        for i in range(5)
    ]
    b2_base = NOW - datetime.timedelta(hours=13)
    b2 = [
        make_news(
            source_ref=f"b2-{i}", crawled_at=(b2_base - datetime.timedelta(minutes=i)).isoformat()
        )
        for i in range(5)
    ]
    b3_base = NOW - datetime.timedelta(hours=19)
    b3 = [
        make_news(
            source_ref=f"b3-{i}", crawled_at=(b3_base - datetime.timedelta(minutes=i)).isoformat()
        )
        for i in range(5)
    ]

    result = collect_daily.filter_news(b0 + b1 + b2 + b3, NOW)

    expected = (
        [f"b0-{i}" for i in range(5)]
        + [f"b1-{i}" for i in range(5)]
        + [f"b2-{i}" for i in range(5)]
        + [f"b3-{i}" for i in range(5)]
    )
    assert [n["source_ref"] for n in result] == expected


def test_filter_news_fills_20_from_remaining_buckets_when_others_are_empty() -> None:
    """구간1·2가 비어 있어도(기사가 구간0·3에만 몰려 있어도) 20건을 채운다.

    구간0에 18건, 구간3에 10건을 두면 라운드로빈이 빈 구간(1,2)을 건너뛰고
    남은 두 구간(0,3)에서만 번갈아 뽑는다 — 20건에 닿으려면 각 10건씩 필요하고,
    구간3은 정확히 10건을 갖고 있어 마침 그 시점에 소진된다.
    """
    b0 = [
        make_news(
            source_ref=f"b0-{i}", crawled_at=(NOW - datetime.timedelta(minutes=i + 1)).isoformat()
        )
        for i in range(18)
    ]
    b3_base = NOW - datetime.timedelta(hours=19)
    b3 = [
        make_news(
            source_ref=f"b3-{i}", crawled_at=(b3_base - datetime.timedelta(minutes=i)).isoformat()
        )
        for i in range(10)
    ]

    result = collect_daily.filter_news(b0 + b3, NOW)
    refs = [n["source_ref"] for n in result]

    assert len(refs) == 20
    assert sum(1 for r in refs if r.startswith("b0-")) == 10
    assert sum(1 for r in refs if r.startswith("b3-")) == 10


def test_filter_news_caps_at_20() -> None:
    """30건이 전부 같은 6시간 구간(bucket0)에 몰려 있어 나머지 3구간은 빈다.

    빈 구간이 있어도 유일하게 채워진 구간이 20건 몫을 전부 대신 내줘야 한다.
    """
    items = [make_news(source_ref=str(i)) for i in range(30)]

    result = collect_daily.filter_news(items, NOW)

    assert len(result) == 20


# ---- collect_daily 이미지 중복배제 (average hash) ----
#
# 실제 이미지를 내려받지 않는다 — hash_image 를 가짜 함수로 주입해 필터 로직만 본다.
# 해시 계산 자체(average_hash)는 Pillow 로 만든 단색 이미지로 따로 확인한다.


def solid_png(shade: int) -> bytes:
    """한 가지 밝기로 채운 8x8 PNG. average_hash 테스트용."""
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("L", (8, 8), shade).save(buffer, format="PNG")
    return buffer.getvalue()


def test_average_hash_is_stable_for_the_same_image() -> None:
    image = solid_png(128)

    assert collect_daily.average_hash(image) == collect_daily.average_hash(image)


def test_average_hash_survives_resize() -> None:
    """리사이즈된 같은 그림은 해밍거리가 임계값 안에 들어와야 한다.

    토큰포스트처럼 같은 그림을 다른 크기·파일명으로 다시 올리는 매체를 잡는 근거다.
    실측(2026-08-23)에서는 _th_860x0 · -560x305 같은 실제 리사이즈 변형이 전부
    거리 0 으로 나왔다 — IMAGE_HASH_MAX_DISTANCE 를 0 쪽에 붙여 잡은 이유다.
    """
    import io

    from PIL import Image

    original = Image.new("L", (200, 120))
    for x in range(200):
        for y in range(120):
            original.putpixel((x, y), (x * 255) // 200)
    big, small = io.BytesIO(), io.BytesIO()
    original.save(big, format="PNG")
    original.resize((80, 48), Image.Resampling.LANCZOS).save(small, format="PNG")

    a = collect_daily.average_hash(big.getvalue())
    b = collect_daily.average_hash(small.getvalue())

    assert a is not None and b is not None
    assert collect_daily.hamming_distance(a, b) <= collect_daily.IMAGE_HASH_MAX_DISTANCE


def test_average_hash_returns_none_for_undecodable_bytes(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert collect_daily.average_hash(b"not an image") is None
    assert capsys.readouterr().err != ""


def test_hamming_distance_counts_differing_bits() -> None:
    assert collect_daily.hamming_distance(0b1010, 0b1010) == 0
    assert collect_daily.hamming_distance(0b1010, 0b1011) == 1
    assert collect_daily.hamming_distance(0b0000, 0b1111) == 4


def test_filter_news_drops_image_url_matching_a_recent_edition() -> None:
    """최근 발행분과 같은 이미지면 image_url 만 뗀다 — 기사 자체는 남는다."""
    items = [make_news(source_ref="a", image_url="https://cdn/new.jpg")]

    result = collect_daily.filter_news(items, NOW, [0b1010], lambda _url: 0b1010)

    assert len(result) == 1
    assert result[0]["image_url"] is None
    assert result[0]["source_ref"] == "a"


def test_filter_news_keeps_image_url_that_is_far_enough() -> None:
    far = (1 << (collect_daily.IMAGE_HASH_MAX_DISTANCE + 1)) - 1  # 임계값보다 1비트 더 다르다
    items = [make_news(source_ref="a", image_url="https://cdn/new.jpg")]

    result = collect_daily.filter_news(items, NOW, [0], lambda _url: far)

    assert result[0]["image_url"] == "https://cdn/new.jpg"


def test_image_threshold_stays_tight_enough_to_avoid_false_positives() -> None:
    """임계값이 느슨해지는 회귀를 막는다.

    처음 12 로 뒀을 때 실제로 베이지색 서류함 일러스트와 네온 실루엣이 거리 11 로
    묶여 멀쩡한 후보의 image_url 이 떨어졌다. 실측 표본에서 서로 다른 이미지의
    최소 거리가 6이었으므로 임계값은 그보다 작아야 한다.
    """
    assert collect_daily.IMAGE_HASH_MAX_DISTANCE < 6


def test_filter_news_drops_duplicate_images_within_the_same_draft() -> None:
    """URL 이 달라도 같은 그림이면 뒤에 오는 쪽을 뗀다 — 토큰포스트 재업로드 대응."""
    items = [
        make_news(
            source_ref="a", crawled_at="2026-07-31T02:00:00+00:00", image_url="https://cdn/x.jpg"
        ),
        make_news(
            source_ref="b", crawled_at="2026-07-31T01:00:00+00:00", image_url="https://cdn/y.jpg"
        ),
    ]

    result = collect_daily.filter_news(items, NOW, (), lambda _url: 0b1010)

    assert result[0]["image_url"] == "https://cdn/x.jpg"  # 먼저 나온 쪽을 살린다
    assert result[1]["image_url"] is None


def test_filter_news_keeps_image_when_hashing_fails() -> None:
    """다운로드/디코딩 실패는 판정 불가 — 지레 떼지 않는다."""
    items = [make_news(source_ref="a", image_url="https://cdn/x.jpg")]

    result = collect_daily.filter_news(items, NOW, [0b1010], lambda _url: None)

    assert result[0]["image_url"] == "https://cdn/x.jpg"


def test_filter_news_without_hash_image_behaves_as_before() -> None:
    """hash_image 를 안 넘기면 예전과 동일하게 동작한다(기존 호출부 보호)."""
    items = [make_news(source_ref="a", image_url="https://cdn/x.jpg")]

    result = collect_daily.filter_news(items, NOW)

    assert result[0]["image_url"] == "https://cdn/x.jpg"


def test_filter_news_does_not_mutate_input_items() -> None:
    original = make_news(source_ref="a", image_url="https://cdn/x.jpg")
    items = [original]

    collect_daily.filter_news(items, NOW, [0b1010], lambda _url: 0b1010)

    assert original["image_url"] == "https://cdn/x.jpg"


# ---- collect_daily.trending_pool_* (집계용 코퍼스 — 카드 후보 필터와 목적이 다르다) ----


def test_trending_pool_news_keeps_duplicates() -> None:
    """중복 기사는 카드에선 버리지만 집계에선 신호다 — 여러 매체가 같은 사건을 다뤘다는 뜻."""
    items = [make_news(is_duplicate=True), make_news(is_duplicate=False)]

    assert len(collect_daily.trending_pool_news(items, NOW)) == 2


def test_trending_pool_news_has_no_cap() -> None:
    """카드 후보는 20건에서 자르지만 "그날 뭐가 핫했나"는 전체를 봐야 나온다."""
    items = [make_news(source_ref=str(i)) for i in range(120)]

    assert len(collect_daily.trending_pool_news(items, NOW)) == 120


def test_trending_pool_news_still_bounded_to_24h() -> None:
    items = [
        make_news(crawled_at="2026-07-29T00:00:00+00:00"),
        make_news(crawled_at="2026-07-31T01:00:00+00:00"),
    ]

    result = collect_daily.trending_pool_news(items, NOW)

    assert [n["crawled_at"] for n in result] == ["2026-07-31T01:00:00+00:00"]


def test_trending_pool_videos_does_not_require_a_summary() -> None:
    """요약은 카드 문구를 쓸 때 필요하다. 아직 안 붙었다고 그날 화제작이 통계에서 빠지면 안 된다."""
    items = [make_video(id="no-summary", summary="")]

    assert len(collect_daily.trending_pool_videos(items, NOW)) == 1


def test_trending_pool_videos_excludes_other_topics() -> None:
    items = [make_video(id="btc"), make_video(id="ai", topic="AI")]

    result = collect_daily.trending_pool_videos(items, NOW)

    assert [v["id"] for v in result] == ["btc"]


def test_trending_pool_videos_uses_a_24h_window_not_the_card_48h() -> None:
    """카드가 48h를 보는 건 요약 지연을 흡수하려는 것이지 신선도 기준이 아니다."""
    items = [
        make_video(id="fresh", published_at="2026-07-31T01:00:00+00:00"),
        make_video(id="stale", published_at="2026-07-30T01:00:00+00:00"),
    ]

    result = collect_daily.trending_pool_videos(items, NOW)

    assert [v["id"] for v in result] == ["fresh"]


# ---- collect_daily.filter_videos ----


def test_filter_videos_requires_bitcoin_topic_and_summary() -> None:
    items = [make_video(id="wrong-topic", topic="AI"), make_video(id="no-summary", summary="")]

    assert collect_daily.filter_videos(items, NOW) == []


def test_filter_videos_excludes_published_before_window() -> None:
    items = [make_video(published_at="2026-07-28T02:00:00+00:00")]  # NOW-71h

    assert collect_daily.filter_videos(items, NOW) == []


def test_filter_videos_keeps_video_published_within_48h() -> None:
    items = [make_video(id="late-summary", published_at="2026-07-29T12:00:00+00:00")]  # NOW-39h

    assert [v["id"] for v in collect_daily.filter_videos(items, NOW)] == ["late-summary"]


def test_filter_videos_excludes_backfilled_old_video() -> None:
    """큐에 방금 들어왔어도 게시가 몇 주 전이면 버린다 (2026-08-04 회귀)."""
    items = [
        make_video(
            id="backfilled",
            published_at="2026-06-27T03:15:06+00:00",
            added_at="2026-07-31T02:55:00+00:00",  # 창 안이지만 게시는 한 달 전
            view_count=246_534,
        ),
        make_video(id="today", published_at="2026-07-31T01:00:00+00:00", view_count=900),
    ]

    assert [v["id"] for v in collect_daily.filter_videos(items, NOW)] == ["today"]


def test_filter_videos_excludes_missing_published_at() -> None:
    items = [make_video(published_at=None)]

    assert collect_daily.filter_videos(items, NOW) == []


def test_filter_videos_sorts_by_view_count_desc_capped_at_5() -> None:
    items = [make_video(id=str(i), view_count=i) for i in range(7)]

    result = collect_daily.filter_videos(items, NOW)

    assert [v["id"] for v in result] == ["6", "5", "4", "3", "2"]


def test_filter_videos_excludes_ids_in_exclude_ids() -> None:
    items = [make_video(id="keep", view_count=100), make_video(id="skip", view_count=200)]

    result = collect_daily.filter_videos(items, NOW, exclude_ids={"skip"})

    assert [v["id"] for v in result] == ["keep"]


def test_filter_videos_exclude_ids_defaults_to_empty_tuple() -> None:
    """기존 2-인자 호출(exclude_ids 생략)이 그대로 동작해야 한다."""
    items = [make_video(id="a", view_count=100), make_video(id="b", view_count=50)]

    result = collect_daily.filter_videos(items, NOW)

    assert [v["id"] for v in result] == ["a", "b"]


def test_filter_videos_backfills_from_lower_ranked_after_exclusion() -> None:
    """상위권이 exclude_ids 로 빠지면 그 아래가 VIDEO_LIMIT(5)까지 올라와야 한다."""
    items = [make_video(id=str(i), view_count=100 - i) for i in range(7)]  # id "0" 이 최고 조회수

    result = collect_daily.filter_videos(items, NOW, exclude_ids={"0", "1"})

    assert [v["id"] for v in result] == ["2", "3", "4", "5", "6"]


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


def test_collect_daily_main_writes_trending_corpus_note(tmp_path: Path) -> None:
    """무인 실행이 트렌딩 카드의 "N건 집계"를 지어내지 않도록 draft 가 note 를 준다."""
    out_path = tmp_path / "draft.json"

    with httpx.Client(transport=httpx.MockTransport(_mock_handler)) as client:
        collect_daily.main(
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

    corpus = json.loads(out_path.read_text(encoding="utf-8"))["trending_corpus"]
    assert corpus["news"] == 1
    assert corpus["outlets"] == 1
    assert corpus["outlet_names"] == ["X"]
    assert corpus["note"].startswith("뉴스 1건 1매체 · 유튜브 ")


def test_corpus_summary_counts_distinct_outlets_not_articles() -> None:
    """한 매체가 여러 건을 써도 매체 수는 1이다 — 토큰포스트가 코퍼스 절반을 차지한다."""
    news = [make_news(source_ref="토큰포스트") for _ in range(5)] + [make_news(source_ref="B")]
    videos = [make_video(id="a"), make_video(id="b")]
    videos[0]["channel_title"] = "채널A"
    videos[1]["channel_title"] = "채널A"

    summary = collect_daily.corpus_summary(news, videos)

    assert summary["news"] == 6
    assert summary["outlets"] == 2
    assert summary["videos"] == 2
    assert summary["channels"] == 1
    assert summary["note"] == "뉴스 6건 2매체 · 유튜브 2건 1채널 집계"


def test_corpus_summary_ignores_items_missing_source_name() -> None:
    """source_ref/channel_title 이 빠진 항목이 매체 수를 부풀리면 안 된다."""
    news = [make_news(source_ref="A"), {"title": "출처 없음"}]

    summary = collect_daily.corpus_summary(news, [])

    assert summary["news"] == 2
    assert summary["outlets"] == 1


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


def test_generate_qa_missing_api_key_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
        generate_qa.main([str(edition_path), "--delay", "7"], client=client, sleep=sleeps.append)

    # 카드 2장, 둘 다 첫 시도에 성공 — 카드 사이 대기 1번만 걸리고, 첫 카드 전에는 없다.
    assert sleeps == [7.0]


def _editions_transport(
    listing: list[dict[str, str]], bodies: dict[str, dict[str, Any]]
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/editions":
            return httpx.Response(200, json=listing)
        date = request.url.path.rsplit("/", 1)[-1]
        if date in bodies:
            return httpx.Response(200, json=bodies[date])
        return httpx.Response(404, json={"detail": "not found"})

    return httpx.MockTransport(handler)


def _edition_body(*cards: tuple[str, str, str]) -> dict[str, Any]:
    return {
        "cards": [
            {
                "num": i,
                "chip": {"text": chip, "emphasis": None},
                "title": title,
                "link": {"label": f"{outlet} 원문", "href": "https://example.com"},
            }
            for i, (chip, title, outlet) in enumerate(cards, 1)
        ]
    }


def test_recent_editions_takes_latest_days_strictly_before_the_cutoff() -> None:
    listing = [{"date": d} for d in ["2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06"]]
    bodies = {d["date"]: _edition_body(("시황", d["date"], "토큰포스트")) for d in listing}

    with httpx.Client(transport=_editions_transport(listing, bodies)) as client:
        dates = recent_editions.fetch_dates(client, "http://api", datetime.date(2026, 8, 6), days=2)

    # 커트오프 당일(08-06)은 아직 발행 전이라 제외하고, 그 이전 2일을 최신순으로.
    assert dates == ["2026-08-05", "2026-08-04"]


def test_recent_editions_output_lists_cards_and_counts_categories(
    capsys: pytest.CaptureFixture[str],
) -> None:
    listing = [{"date": "2026-08-05"}, {"date": "2026-08-06"}]
    bodies = {
        "2026-08-05": _edition_body(
            ("보안", "콜드카드는 왜 뚫렸나", "Decrypt"),
            ("시황", "6만4000달러는 되찾았다", "블록미디어"),
        ),
        "2026-08-06": _edition_body(("보안", "1500 비트코인이 남아 있었다", "TFTC")),
    }

    with httpx.Client(transport=_editions_transport(listing, bodies)) as client:
        output = recent_editions.main(
            ["--api", "http://api", "--before", "2026-08-07", "--days", "7"], client=client
        )

    assert "--- 2026-08-06 ---" in output
    assert "[보안] 콜드카드는 왜 뚫렸나  (Decrypt)" in output
    # 같은 카테고리가 이틀에 걸쳐 2장 — 이 빈도가 3.1단계 판단의 출발점이다.
    assert "보안: 2장 / 2일" in output
    assert "시황: 1장 / 1일" in output
    assert output in capsys.readouterr().out


def test_recent_editions_skips_dates_whose_body_is_missing() -> None:
    listing = [{"date": "2026-08-05"}, {"date": "2026-08-06"}]
    bodies = {"2026-08-06": _edition_body(("시황", "오늘의 시황", "토큰포스트"))}

    with httpx.Client(transport=_editions_transport(listing, bodies)) as client:
        output = recent_editions.main(
            ["--api", "http://api", "--before", "2026-08-07"], client=client
        )

    assert "2026-08-05" not in output
    assert "--- 2026-08-06 ---" in output


def test_recent_editions_fails_loudly_when_nothing_published_yet() -> None:
    with httpx.Client(transport=_editions_transport([], {})) as client:
        with pytest.raises(SystemExit, match="발행분이 없다"):
            recent_editions.main(["--api", "http://api", "--before", "2026-08-07"], client=client)


def test_build_skeleton_puts_the_cover_quote_beside_the_date_fields() -> None:
    cover_fixed = {"eyebrow": "E", "mark": ["old", "old"], "meta": ["x", "y", "old"], "hint": "h"}
    quote = {"id": "mises-boom", "text": "…", "author": "미제스", "portrait": None}

    skeleton = collect_daily.build_skeleton(
        datetime.date(2026, 8, 8), {}, "B", cover_fixed, {"sources": []}, [], quote
    )

    assert skeleton["cover"]["quote"] == quote
    # 날짜 파생 필드는 그대로여야 한다 — push_edition 의 cover 가드가 이걸 본다.
    assert skeleton["cover"]["mark"] == ["8월 8일", "비트코인 카드뉴스"]


def test_build_skeleton_omits_the_quote_key_when_there_is_none() -> None:
    cover_fixed = {"eyebrow": "E", "mark": ["a", "b"], "meta": ["x", "y", "z"], "hint": "h"}

    skeleton = collect_daily.build_skeleton(
        datetime.date(2026, 8, 8), {}, "B", cover_fixed, {"sources": []}, []
    )

    assert "quote" not in skeleton["cover"]


def _editions_handler(bodies: dict[str, Any]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/editions":
            return httpx.Response(200, json=[{"date": d} for d in sorted(bodies)])
        date = request.url.path.rsplit("/", 1)[-1]
        if date in bodies:
            return httpx.Response(200, json=bodies[date])
        return httpx.Response(404, json={})

    return httpx.MockTransport(handler)


def _with_quote(quote_id: str | None) -> dict[str, Any]:
    quote = {"id": quote_id, "text": "…", "author": "A"} if quote_id else None
    return {"cover": {"eyebrow": "E", "mark": [], "meta": [], "hint": "h", "quote": quote}}


def test_recent_quote_ids_collects_newest_first_and_skips_editions_without_one() -> None:
    bodies = {
        "2026-08-05": _with_quote("hayek-curious-task"),
        "2026-08-06": _with_quote(None),  # 인용구 도입 전 발행분
        "2026-08-07": _with_quote("mises-boom-collapse"),
    }

    with httpx.Client(transport=_editions_handler(bodies)) as client:
        ids = collect_daily.recent_quote_ids(
            client, "http://api", datetime.date(2026, 8, 8), limit=10
        )

    assert ids == ["mises-boom-collapse", "hayek-curious-task"]


def test_recent_quote_ids_survives_a_dead_api(capsys: pytest.CaptureFixture[str]) -> None:
    # 인용구는 표지 장식이다 — 이력 조회 실패로 06:00 배치가 죽으면 안 된다.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        ids = collect_daily.recent_quote_ids(
            client, "http://api", datetime.date(2026, 8, 8), limit=10
        )

    assert ids == []
    assert "중복 회피를 건너뛴다" in capsys.readouterr().err


def test_collect_daily_main_fills_the_cover_quote(tmp_path: Path) -> None:
    out_path = tmp_path / "draft.json"

    with httpx.Client(transport=httpx.MockTransport(_mock_handler)) as client:
        collect_daily.main(
            [
                "--date",
                "2026-07-31",
                "--out",
                str(out_path),
                "--news-url",
                "http://x/news",
                "--youtube-url",
                "http://x/queue",
                "--edition-api",
                "http://x",
            ],
            client=client,
        )

    quote = json.loads(out_path.read_text(encoding="utf-8"))["skeleton"]["cover"]["quote"]
    assert set(quote) == {"id", "text", "author", "portrait"}
    assert quote["id"] and quote["text"] and quote["author"]


def test_recent_quote_ids_survives_an_unexpected_response_shape(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # 발행 목록이 리스트가 아니라 딕셔너리로 오면 예전 코드는 TypeError 로 죽었다.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": []})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        ids = collect_daily.recent_quote_ids(
            client, "http://api", datetime.date(2026, 8, 8), limit=10
        )

    assert ids == []
    assert "중복 회피를 건너뛴다" in capsys.readouterr().err


def test_recent_quote_ids_ignores_editions_whose_body_is_not_a_dict() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/editions":
            return httpx.Response(200, json=[{"date": "2026-08-06"}, {"date": "2026-08-07"}])
        if request.url.path.endswith("2026-08-07"):
            return httpx.Response(200, json=["unexpected"])
        return httpx.Response(200, json=_with_quote("hayek-curious-task"))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        ids = collect_daily.recent_quote_ids(
            client, "http://api", datetime.date(2026, 8, 8), limit=10
        )

    assert ids == ["hayek-curious-task"]


# ---- collect_daily.recent_video_ids ----


def _video_card(link_href: str | None = None, media_image: str | None = None) -> dict[str, Any]:
    """recent_video_ids 가 읽는 카드 모양 — link.href 와 media.image 가 각각 id 출처다."""
    return {
        "link": {"href": link_href} if link_href else None,
        "media": {"image": media_image} if media_image else None,
    }


def _video_edition_body(cards: list[dict[str, Any]]) -> dict[str, Any]:
    return {"cards": cards}


def test_recent_video_ids_extracts_id_from_link_href_short_url() -> None:
    bodies = {"2026-08-07": _video_edition_body([_video_card(link_href="https://youtu.be/abc123")])}

    with httpx.Client(transport=_editions_handler(bodies)) as client:
        ids = collect_daily.recent_video_ids(
            client, "http://api", datetime.date(2026, 8, 8), days=3
        )

    assert ids == ["abc123"]


def test_recent_video_ids_extracts_id_from_link_href_watch_url() -> None:
    bodies = {
        "2026-08-07": _video_edition_body(
            [_video_card(link_href="https://www.youtube.com/watch?v=def456")]
        )
    }

    with httpx.Client(transport=_editions_handler(bodies)) as client:
        ids = collect_daily.recent_video_ids(
            client, "http://api", datetime.date(2026, 8, 8), days=3
        )

    assert ids == ["def456"]


def test_recent_video_ids_extracts_id_from_media_image_thumbnail() -> None:
    bodies = {
        "2026-08-07": _video_edition_body(
            [_video_card(media_image="https://i.ytimg.com/vi/xyz789/hqdefault.jpg")]
        )
    }

    with httpx.Client(transport=_editions_handler(bodies)) as client:
        ids = collect_daily.recent_video_ids(
            client, "http://api", datetime.date(2026, 8, 8), days=3
        )

    assert ids == ["xyz789"]


def test_recent_video_ids_deduplicates_ids_appearing_in_multiple_cards() -> None:
    bodies = {
        "2026-08-06": _video_edition_body([_video_card(link_href="https://youtu.be/dup1")]),
        "2026-08-07": _video_edition_body(
            [
                _video_card(link_href="https://youtu.be/dup1"),
                _video_card(media_image="https://i.ytimg.com/vi/dup1/hqdefault.jpg"),
            ]
        ),
    }

    with httpx.Client(transport=_editions_handler(bodies)) as client:
        ids = collect_daily.recent_video_ids(
            client, "http://api", datetime.date(2026, 8, 8), days=3
        )

    assert ids == ["dup1"]


def test_recent_video_ids_survives_null_or_non_dict_link_and_media() -> None:
    """실데이터에 media: null 인 카드가 존재한다.

    link/media 가 None 이거나 dict가 아니어도 죽지 않는다.
    """
    bodies = {
        "2026-08-07": _video_edition_body(
            [
                {"link": None, "media": None},
                {"link": "not-a-dict", "media": "not-a-dict"},
                _video_card(link_href="https://youtu.be/ok1"),
            ]
        )
    }

    with httpx.Client(transport=_editions_handler(bodies)) as client:
        ids = collect_daily.recent_video_ids(
            client, "http://api", datetime.date(2026, 8, 8), days=3
        )

    assert ids == ["ok1"]


def test_recent_video_ids_survives_a_dead_api(capsys: pytest.CaptureFixture[str]) -> None:
    # recent_quote_ids 와 같은 방어 자세 — 발행 이력 조회가 안 된다고 수집이 죽으면 안 된다.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        ids = collect_daily.recent_video_ids(
            client, "http://api", datetime.date(2026, 8, 8), days=3
        )

    assert ids == []
    assert capsys.readouterr().err != ""


# ---- collect_daily.recent_image_hashes ----


def _image_card(media_image: str | None) -> dict[str, Any]:
    return {"media": {"image": media_image} if media_image else None}


def _image_editions_handler(
    bodies: dict[str, Any], images: dict[str, bytes]
) -> httpx.MockTransport:
    """발행 이력 API + 이미지 CDN 을 한 트랜스포트로 흉내낸다."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url in images:
            return httpx.Response(200, content=images[url])
        if request.url.path == "/api/editions":
            return httpx.Response(200, json=[{"date": d} for d in sorted(bodies)])
        date = request.url.path.rsplit("/", 1)[-1]
        if date in bodies:
            return httpx.Response(200, json=bodies[date])
        return httpx.Response(404, json={})

    return httpx.MockTransport(handler)


def test_recent_image_hashes_collects_hashes_from_card_media() -> None:
    url = "https://cdn/a.png"
    bodies = {"2026-08-07": {"cards": [_image_card(url)]}}

    with httpx.Client(transport=_image_editions_handler(bodies, {url: solid_png(200)})) as client:
        digests = collect_daily.recent_image_hashes(
            client, "http://api", datetime.date(2026, 8, 8), days=3, cache={}
        )

    assert digests == [collect_daily.average_hash(solid_png(200))]


def test_recent_image_hashes_skips_youtube_thumbnails() -> None:
    """영상은 id 로 이미 중복배제된다 — 썸네일까지 이미지 풀에 넣지 않는다."""
    url = "https://i.ytimg.com/vi/abc123/hqdefault.jpg"
    bodies = {"2026-08-07": {"cards": [_image_card(url)]}}

    with httpx.Client(transport=_image_editions_handler(bodies, {url: solid_png(200)})) as client:
        digests = collect_daily.recent_image_hashes(
            client, "http://api", datetime.date(2026, 8, 8), days=3, cache={}
        )

    assert digests == []


def test_recent_image_hashes_skips_cards_without_media() -> None:
    bodies = {"2026-08-07": {"cards": [_image_card(None)]}}

    with httpx.Client(transport=_image_editions_handler(bodies, {})) as client:
        digests = collect_daily.recent_image_hashes(
            client, "http://api", datetime.date(2026, 8, 8), days=3, cache={}
        )

    assert digests == []


def test_recent_image_hashes_populates_the_cache_for_reuse() -> None:
    url = "https://cdn/a.png"
    bodies = {"2026-08-07": {"cards": [_image_card(url)]}}
    cache: dict[str, int] = {}

    with httpx.Client(transport=_image_editions_handler(bodies, {url: solid_png(200)})) as client:
        collect_daily.recent_image_hashes(
            client, "http://api", datetime.date(2026, 8, 8), days=3, cache=cache
        )

    assert cache == {url: collect_daily.average_hash(solid_png(200))}


def test_recent_image_hashes_returns_empty_when_history_is_unreachable(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """발행 이력을 못 읽어도 수집을 막지 않는다 — recent_video_ids 와 같은 원칙."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        digests = collect_daily.recent_image_hashes(
            client, "http://api", datetime.date(2026, 8, 8), days=3, cache={}
        )

    assert digests == []
    assert capsys.readouterr().err != ""
