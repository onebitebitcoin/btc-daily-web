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
    url: str | None = "https://news.example/1",
) -> dict[str, Any]:
    return {
        "title": title,
        "tags": tags,
        "source_ref": source_ref,
        "published_at": published_at,
        "url": url,
    }


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


def test_daily_commentary_tags_do_not_outrank_real_events() -> None:
    """매일 붙는 시황 서술어는 채널 수가 아무리 많아도 토픽이 되면 안 된다.

    유튜브는 대부분이 일일 시황 코멘터리라, `시황`/`가격분석` 같은 태그를 세면
    채널 수가 그대로 매체 다양성으로 둔갑해 실제 사건을 전부 눌러버린다
    (2026-08-05 실측: 25건 19매체로 1위 차지). 여기서는 채널 19곳이 시황을,
    3곳만 실제 사건을 다룬 상황을 만들어 사건이 1위로 남는지 본다.
    """
    videos = [
        make_video(title=f"오늘의 #시황 #가격분석 #변동성 {i}", channel_title=f"채널{i}")
        for i in range(19)
    ]
    news = [make_news(["#콜드카드"], source_ref=f"매체{i}") for i in range(3)]

    result = rank_topics(news, videos, NOW)

    topics = {r["topic"] for r in result}
    assert topics.isdisjoint({"시황", "가격분석", "변동성"})
    assert result[0]["topic"] == "콜드카드"


def test_articles_carry_the_source_links_behind_a_topic() -> None:
    """펼침 목록의 재료 — 토픽마다 실제로 어떤 기사에서 나왔는지."""
    items = [
        make_news(["#콜드카드"], source_ref="토큰포스트", title="A", url="https://a.example/1"),
        make_news(["#콜드카드"], source_ref="CoinDesk", title="B", url="https://b.example/2"),
    ]

    result = rank_topics(items, [], NOW)

    articles = result[0]["articles"]
    assert [a["title"] for a in articles] == ["A", "B"]
    assert [a["url"] for a in articles] == ["https://a.example/1", "https://b.example/2"]
    assert [a["source"] for a in articles] == ["토큰포스트", "CoinDesk"]


def test_articles_drop_entries_without_a_url() -> None:
    """누르면 아무 데도 안 가는 줄이 목록에 남으면 고장으로 보인다."""
    items = [
        make_news(["#콜드카드"], title="링크 있음", url="https://a.example/1"),
        make_news(["#콜드카드"], source_ref="매체B", title="링크 없음", url=None),
    ]

    result = rank_topics(items, [], NOW)

    assert [a["title"] for a in result[0]["articles"]] == ["링크 있음"]
    # 집계 자체는 링크 유무와 무관하다 — 언급 수는 둘 다 센다.
    assert result[0]["mentions"] == 2


def test_articles_do_not_repeat_one_item_matched_by_two_tags() -> None:
    items = [make_news(["#콜드카드", "#보안"], title="같은 기사", url="https://a.example/1")]

    result = rank_topics(items, [], NOW)

    for entry in result:
        assert [a["title"] for a in entry["articles"]] == ["같은 기사"]


def test_video_articles_fall_back_to_a_watch_url_from_the_id() -> None:
    """my-youtube 응답에 url 이 빠진 항목이 있어 id 로 복원한다."""
    video = make_video(title="#콜드카드 분석")
    video["id"] = "abc123"

    result = rank_topics([], [video], NOW)

    assert result[0]["articles"][0]["url"] == "https://www.youtube.com/watch?v=abc123"


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
