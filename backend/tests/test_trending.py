import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.trending import rank_topics

KST = ZoneInfo("Asia/Seoul")
# 매일 오전 6시 발행 기준 시각. published_at을 이 기준으로 오프셋을 줘서 recency를 검증한다.
NOW = datetime.datetime(2026, 8, 5, 6, 0, tzinfo=KST)


def make_news(
    tags: list[str],
    source_ref: str = "매체A",
    published_at: str = "2026-08-05T02:00:00",
    title: str = "기사 제목",
) -> dict[str, Any]:
    return {"title": title, "tags": tags, "source_ref": source_ref, "published_at": published_at}


def make_video(
    title: str = "영상 제목",
    topic: str = "비트코인",
    channel_title: str = "채널A",
    view_count: int = 1000,
    published_at: str = "2026-08-05T02:00:00+00:00",
) -> dict[str, Any]:
    return {
        "title": title,
        "topic": topic,
        "view_count": view_count,
        "channel_title": channel_title,
        "published_at": published_at,
    }


def test_stopwords_are_filtered_out() -> None:
    items = [make_news(["#비트코인", "#시장", "#가격", "#레귤레이션"])]

    result = rank_topics(items, [], NOW)

    topics = {r["topic"] for r in result}
    assert "비트코인" not in topics
    assert "시장" not in topics
    assert "가격" not in topics
    assert "레귤레이션" in topics


def test_synonyms_merge_into_one_topic() -> None:
    items = [
        make_news(["#Fed"], source_ref="매체A"),
        make_news(["#연준"], source_ref="매체B"),
        make_news(["#FOMC"], source_ref="매체C"),
        make_news(["#연방준비제도"], source_ref="매체A"),  # 매체A 중복 — 다양성엔 안 더해짐
    ]

    result = rank_topics(items, [], NOW)
    matches = [r for r in result if r["topic"] == "연준"]

    assert len(matches) == 1
    assert matches[0]["mentions"] == 4
    assert matches[0]["sources"] == 3  # 매체A/B/C, 매체A 중복은 한 번만


def test_media_diversity_outranks_repeated_single_source_mentions() -> None:
    """요구사항의 핵심: "자주 언급"이 아니라 "여러 매체가 동시에 다뤘는가"가 이겨야 한다."""
    diverse = [make_news(["#다양매체토픽"], source_ref=f"매체{i}") for i in range(5)]
    repeated = [make_news(["#반복매체토픽"], source_ref="매체X") for _ in range(5)]

    result = rank_topics(diverse + repeated, [], NOW)
    by_topic = {r["topic"]: r for r in result}

    # 언급 수는 동일(5건)한데 매체 다양성만 다르다.
    assert by_topic["다양매체토픽"]["mentions"] == by_topic["반복매체토픽"]["mentions"] == 5
    assert by_topic["다양매체토픽"]["sources"] == 5
    assert by_topic["반복매체토픽"]["sources"] == 1
    assert by_topic["다양매체토픽"]["score"] > by_topic["반복매체토픽"]["score"]


def test_recent_mentions_score_higher_than_stale_ones() -> None:
    recent = make_news(["#최근토픽"], published_at="2026-08-05T02:00:00")  # NOW-4h
    stale = make_news(["#오래된토픽"], published_at="2026-08-04T10:00:00")  # NOW-20h

    result = rank_topics([recent, stale], [], NOW)
    by_topic = {r["topic"]: r for r in result}

    assert by_topic["최근토픽"]["score"] > by_topic["오래된토픽"]["score"]


def test_heat_normalizes_top_topic_to_100() -> None:
    top = [make_news(["#1위토픽"], source_ref=f"매체{i}") for i in range(5)]
    low = [make_news(["#하위토픽"], source_ref="매체X")]

    result = rank_topics(top + low, [], NOW)

    assert result[0]["topic"] == "1위토픽"
    assert result[0]["heat"] == 100
    assert result[-1]["heat"] < 100


def test_empty_candidates_return_empty_list() -> None:
    assert rank_topics([], [], NOW) == []


def test_video_hashtags_and_view_count_contribute() -> None:
    """영상은 topic 필드(대개 "비트코인"이라 불용어로 걸러짐)와 제목 해시태그를 후보로 쓴다."""
    videos = [
        make_video(
            title="긴급 #coldcard 공급망 공격 총정리",
            view_count=500_000,
            channel_title="채널A",
        )
    ]

    result = rank_topics([], videos, NOW)
    matches = [r for r in result if r["topic"] == "콜드카드"]

    assert len(matches) == 1
    assert matches[0]["mentions"] == 1
    assert matches[0]["sources"] == 1


def test_top15_cap_even_with_more_candidate_topics() -> None:
    items = [make_news([f"#토픽{i}"], source_ref=f"매체{i}") for i in range(20)]

    result = rank_topics(items, [], NOW)

    assert len(result) == 15
