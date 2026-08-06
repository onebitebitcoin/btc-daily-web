"""Collect BTC news(24h)/youtube(48h) candidates and write a draft skeleton.

Deterministic only — no LLM calls. Fills every field of an edition that doesn't
require judgement (meta/theme/brand/cover/closing) and dumps ranked candidates
for a human (or a Claude Code session) to pick 10 cards from.

--date 를 오늘이 아닌 과거로 주면 "지금부터 24h"가 아니라 그 날짜(KST) 자정까지의
24h 창으로 자동 전환된다(백필). 단, 소스 API 는 최신순 정렬이라 며칠 전 날짜는
기본 --news-url 의 limit=100 으로 안 닿을 수 있다 — limit 을 넉넉히 올려서 넘겨라.

Usage: python scripts/collect_daily.py [--date YYYY-MM-DD] [--out PATH]
                                        [--news-url URL] [--youtube-url URL]
       python scripts/collect_daily.py --date 2026-07-27 \
           --news-url "http://localhost:8000/api/news?asset=btc&limit=1000"
"""

import argparse
import datetime
import json
import sys
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

KST = ZoneInfo("Asia/Seoul")
REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
FIXTURE_CONTENT = REPO_ROOT / "frontend" / "src" / "fixtures" / "content.json"

# 직접 실행하면 sys.path[0]이 scripts/라 app을 못 찾는다 (push_edition.py와 동일 이유).
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.quotes import as_cover_quote, is_exhausted, load_pool, pick_quote  # noqa: E402
from app.trending import rank_topics  # noqa: E402  (sys.path 조정 후여야 함)
from scripts.recent_editions import fetch_dates, fetch_edition  # noqa: E402

DEFAULT_NEWS_URL = "http://localhost:8000/api/news?asset=btc&limit=100"
# 트렌딩 집계는 카드 후보와 목적이 다르다 — 카드는 "쓸 만한 10건"을 고르지만
# 집계는 24시간에 무슨 일이 있었는지 전부 봐야 한다. 같은 소스를 따로, 넓게 받는다
# (2026-08-05 실측: 24h 코퍼스 205건인데 카드 후보 필터를 거치면 20건만 남았다).
DEFAULT_TRENDING_NEWS_URL = "http://localhost:8000/api/news?asset=btc&limit=500"
# full=1 없으면 my-youtube 가 summary/highlights/description 을 뺀 경량 응답을 준다.
# 그러면 filter_videos 의 `summary` 조건에 전부 걸려 후보가 조용히 0건이 된다(2026-08-05).
DEFAULT_YOUTUBE_URL = "http://localhost:23456/api/queue?full=1"
# 표지 인용구 중복 회피는 "실제로 발행된 것"을 봐야 한다 — 로컬 DB는 리허설 발행까지
# 섞여 있어 기준이 안 된다. 그래서 다른 소스와 달리 기본값이 프로덕션이다.
DEFAULT_EDITION_API = "https://daily.onebitebitcoin.com"
NEWS_LIMIT = 20
VIDEO_LIMIT = 5
# 영상 창은 게시 시각 기준 48h. 24h 로 좁히면 my-youtube 가 요약을 늦게 끝낸 영상이
# 통째로 빠진다 — 게시 25h 뒤에 요약이 붙는 경우가 흔하다.
VIDEO_WINDOW_HOURS = 48


def _parse_dt(value: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))


def filter_news(items: list[dict[str, Any]], now: datetime.datetime) -> list[dict[str, Any]]:
    """Exclude duplicates, keep last-24h, sort by (dup_count desc, crawled_at desc)."""
    cutoff = now - datetime.timedelta(hours=24)
    fresh = [
        n
        for n in items
        if not n.get("is_duplicate") and _parse_dt(n["crawled_at"]) >= cutoff
    ]
    fresh.sort(key=lambda n: (n.get("dup_count", 0), _parse_dt(n["crawled_at"])), reverse=True)
    return fresh[:NEWS_LIMIT]


def filter_videos(items: list[dict[str, Any]], now: datetime.datetime) -> list[dict[str, Any]]:
    """Keep 비트코인-topic, summarized videos published within the window, by view_count desc.

    창을 published_at 으로 잡는 게 핵심이다. 큐 등록 시각(added_at)으로 잡으면
    my-youtube 가 과거 영상을 한꺼번에 백필한 날 몇 주 지난 영상이 "최근 24시간"으로
    딸려 들어오고, 조회수가 그만큼 누적돼 있어 상위 칸을 독차지한다.
    (2026-08-04: 6~7월 영상 5건이 8/3 게시분을 전부 밀어냄)

    published_at 이 없는 항목은 신선도를 판정할 수 없으므로 버린다.
    """
    cutoff = now - datetime.timedelta(hours=VIDEO_WINDOW_HOURS)
    fresh = [
        v
        for v in items
        if v.get("topic") == "비트코인"
        and v.get("summary")
        and v.get("published_at")
        and _parse_dt(v["published_at"]) >= cutoff
    ]
    fresh.sort(key=lambda v: v.get("view_count", 0), reverse=True)
    return fresh[:VIDEO_LIMIT]


def trending_pool_news(
    items: list[dict[str, Any]], now: datetime.datetime
) -> list[dict[str, Any]]:
    """트렌딩 집계용 24시간 뉴스 코퍼스 — 카드 후보 필터를 쓰지 않는다.

    filter_news 를 재사용하면 안 되는 이유가 둘이다.
    1. `is_duplicate` 를 버린다. 카드에는 같은 사건을 두 번 싣지 않으려는 올바른
       필터지만, 집계에서는 **여러 매체가 같은 사건을 다뤘다는 사실 자체가 신호다.**
    2. 상위 20건으로 자른다. "가장 핫한 토픽"은 그날 전체를 봐야 나온다.
    """
    cutoff = now - datetime.timedelta(hours=24)
    return [n for n in items if n.get("crawled_at") and _parse_dt(n["crawled_at"]) >= cutoff]


def trending_pool_videos(
    items: list[dict[str, Any]], now: datetime.datetime
) -> list[dict[str, Any]]:
    """트렌딩 집계용 24시간 영상 코퍼스.

    filter_videos 와 달리 `summary` 를 요구하지 않는다 — 요약은 카드 문구를 쓸 때나
    필요하고, 집계에는 제목·태그·조회수면 충분하다. 요약이 아직 안 붙었다는 이유로
    그날 화제작이 통계에서 빠지면 순위가 왜곡된다. 창도 카드(48h)와 달리 24h다 —
    카드가 48h를 보는 건 요약 지연을 흡수하려는 것이지 신선도 기준이 아니다.
    """
    cutoff = now - datetime.timedelta(hours=24)
    return [
        v
        for v in items
        if v.get("topic") == "비트코인"
        and v.get("published_at")
        and _parse_dt(v["published_at"]) >= cutoff
    ]


def corpus_summary(
    news: list[dict[str, Any]], videos: list[dict[str, Any]]
) -> dict[str, Any]:
    """트렌딩 집계가 실제로 무엇을 봤는지 — 건수와 매체/채널 수.

    `note` 문자열까지 여기서 완성해 draft 에 굽는다. 발행 문구를 쓰는 주체는
    Claude 지만 **이 숫자만은 세는 것이지 쓰는 게 아니다.** draft 에 없으면 무인
    실행이 트렌딩 카드의 "N건 집계"를 지어내는 수밖에 없다(2026-08-05: 사람이
    수동으로 세어 넣었다). 세어서 넘겨주면 그대로 베끼면 된다.
    """
    outlets = {n.get("source_ref") for n in news if n.get("source_ref")}
    channels = {v.get("channel_title") for v in videos if v.get("channel_title")}
    return {
        "news": len(news),
        "outlets": len(outlets),
        "videos": len(videos),
        "channels": len(channels),
        "outlet_names": sorted(outlets),
        "channel_names": sorted(channels),
        "note": (
            f"뉴스 {len(news)}건 {len(outlets)}매체 · "
            f"유튜브 {len(videos)}건 {len(channels)}채널 집계"
        ),
    }


def warn_video_drought(items: list[dict[str, Any]]) -> None:
    """영상 후보가 0건일 때 원인을 stderr 로 구분해 알린다.

    소스 스키마가 바뀌어 summary 가 통째로 빠지면 filter_videos 가 전부 걸러내는데,
    그대로 두면 '오늘은 영상이 없었나 보다'로 읽혀 넘어간다(2026-08-05 실제 사례).
    """
    btc = [v for v in items if v.get("topic") == "비트코인"]
    if btc and not any(v.get("summary") for v in btc):
        print(
            f"WARNING: 비트코인 영상 {len(btc)}건이 있는데 summary 가 하나도 없다 — "
            "my-youtube 응답에서 요약이 빠졌는지 확인하라(--youtube-url 에 full=1 필요).",
            file=sys.stderr,
        )
    else:
        print("WARNING: 창 안에 비트코인 영상 후보가 없다 — 뉴스만으로 구성된다.", file=sys.stderr)


def apply_date_to_cover(cover_fixed: dict[str, Any], date: datetime.date) -> dict[str, Any]:
    """cover.mark/meta[2]는 날짜에서 파생된다 — 이 함수가 유일한 계산처(단일 진실 공급원).

    push_edition.py 도 발행 전 이 함수의 출력과 draft 의 cover 를 비교해 드리프트를
    막는다.
    """
    cover = dict(cover_fixed)
    cover["mark"] = [f"{date.month}월 {date.day}일", "비트코인 카드뉴스"]
    cover["meta"] = [*cover_fixed["meta"][:2], f"{date:%Y.%m.%d}"]
    return cover


def build_skeleton(
    date: datetime.date,
    theme: dict[str, Any],
    brand: str,
    cover_fixed: dict[str, Any],
    closing_fixed: dict[str, Any],
    sources: list[str],
    cover_quote: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cover = apply_date_to_cover(cover_fixed, date)
    if cover_quote is not None:
        cover = {**cover, "quote": cover_quote}
    closing = dict(closing_fixed)
    closing["sources"] = sources
    return {
        "meta": {
            "title": f"비트코인 하이라이트 · {date.month}.{date.day}",
            "slug": f"btc-daily-{date:%m%d}",
            "date": date.isoformat(),
        },
        "theme": theme,
        "brand": brand,
        "cover": cover,
        "closing": closing,
    }


def window_end(date: datetime.date, today_kst: datetime.date) -> datetime.datetime:
    """오늘이면 지금 이 순간(실시간 최근 24h), 과거 날짜면 그날 자정(KST) 기준 24h 창.

    filter_news/filter_videos 는 항상 "이 시각으로부터 24시간 전까지"만 본다 —
    과거 날짜를 백필할 때는 그 날짜가 끝나는 자정을 기준점으로 삼아야 그날 하루가
    창에 들어온다.
    """
    if date == today_kst:
        return datetime.datetime.now(datetime.UTC)
    next_midnight_kst = datetime.datetime.combine(
        date + datetime.timedelta(days=1), datetime.time(0, 0), tzinfo=KST
    )
    return next_midnight_kst.astimezone(datetime.UTC)


def fetch_json(client: httpx.Client, url: str, label: str) -> Any:
    try:
        response = client.get(url)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise SystemExit(f"{label} 소스 조회 실패 ({url}): {exc}") from exc
    return response.json()


def recent_quote_ids(
    client: httpx.Client, api: str, date: datetime.date, limit: int
) -> list[str]:
    """이미 쓴 표지 인용구 id를 최신 발행분부터 모은다.

    **실패해도 수집을 막지 않는다.** 인용구는 표지 장식이지 그날 뉴스가 아니다 —
    발행 이력 조회가 안 된다고 06:00 배치가 통째로 죽으면 손해가 훨씬 크다. 빈
    목록을 돌려주면 `pick_quote`가 날짜 기반 로테이션으로 폴백한다(그날은 중복
    회피가 약해질 뿐 발행은 나간다).
    """
    try:
        # fetch_dates 는 응답이 에러면 SystemExit 을 낸다 — 여기서는 치명적이지 않다.
        # TypeError/KeyError 는 응답 모양이 예상과 다를 때다(프록시가 끼어들거나 API가
        # 바뀐 경우). 어느 쪽이든 인용구 하나 때문에 수집을 죽일 이유가 없다.
        dates = fetch_dates(client, api, date, limit)
    except (httpx.HTTPError, SystemExit, TypeError, KeyError) as exc:
        print(f"경고: 발행 이력을 못 읽어 인용구 중복 회피를 건너뛴다 ({exc!r})", file=sys.stderr)
        return []

    ids: list[str] = []
    for published in dates:
        try:
            edition = fetch_edition(client, api, published)
        except httpx.HTTPError:
            continue
        # 발행분마다 모양을 확인한다 — 인용구 도입 전 12편에는 cover.quote 가 없고,
        # 응답이 통째로 다른 모양일 수도 있다.
        if not isinstance(edition, dict):
            continue
        cover = edition.get("cover")
        quote = cover.get("quote") if isinstance(cover, dict) else None
        if isinstance(quote, dict) and isinstance(quote.get("id"), str):
            ids.append(quote["id"])
    return ids


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="기본값: 오늘(Asia/Seoul)")
    parser.add_argument("--out", help="기본값: <repo>/drafts/draft-<date>.json")
    parser.add_argument("--news-url", default=DEFAULT_NEWS_URL)
    parser.add_argument("--trending-news-url", default=DEFAULT_TRENDING_NEWS_URL)
    parser.add_argument("--youtube-url", default=DEFAULT_YOUTUBE_URL)
    parser.add_argument(
        "--edition-api",
        default=DEFAULT_EDITION_API,
        help="표지 인용구 중복 회피용 발행 이력 조회처. 기본값: 프로덕션",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, client: httpx.Client | None = None) -> Path:
    args = parse_args(argv)
    today_kst = datetime.datetime.now(KST).date()
    date = datetime.date.fromisoformat(args.date) if args.date else today_kst
    window_end_utc = window_end(date, today_kst)
    fixture = json.loads(FIXTURE_CONTENT.read_text(encoding="utf-8"))

    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=10.0)
    try:
        news_raw = fetch_json(client, args.news_url, "my-news")
        # 트렌딩은 같은 소스를 더 넓게 한 번 더 받는다 — 카드 후보 한도(limit=100)에
        # 묶이면 24시간 전체를 못 본다. 로컬 서버라 추가 호출 비용은 무시할 수준.
        trending_news_raw = (
            news_raw
            if args.trending_news_url == args.news_url
            else fetch_json(client, args.trending_news_url, "my-news(trending)")
        )
        yt_raw = fetch_json(client, args.youtube_url, "my-youtube")["items"]
        quote_pool = load_pool()
        used_quote_ids = recent_quote_ids(client, args.edition_api, date, len(quote_pool))
    finally:
        if owns_client:
            client.close()

    news = filter_news(news_raw, window_end_utc)
    videos = filter_videos(yt_raw, window_end_utc)
    for video in videos:
        video["thumbnail_url"] = f"https://i.ytimg.com/vi/{video['id']}/hqdefault.jpg"

    # 후보 0건은 "그날 영상이 없었다"일 수도, 소스 응답이 바뀐 것일 수도 있다.
    # 조용히 넘어가면 뉴스만 10장인 에디션이 그대로 나가므로 이유를 구분해 알린다.
    if not videos:
        warn_video_drought(yt_raw)

    if not news and not videos:
        raise SystemExit(
            f"{date.isoformat()} 기준 24시간 내 후보가 없다 — 소스 응답이나 "
            "--news-url limit(과거 날짜는 100건으로 부족할 수 있다)을 확인하라."
        )

    sources = list(dict.fromkeys(n["source_ref"] for n in news))
    if is_exhausted(quote_pool, used_quote_ids):
        print(
            "경고: 표지 인용구 풀을 한 바퀴 다 돌았다 — 가장 오래전에 쓴 것부터 "
            f"재사용한다 (풀 {len(quote_pool)}개). austrian_quotes.json 을 늘려라.",
            file=sys.stderr,
        )
    quote = pick_quote(quote_pool, used_quote_ids, date)
    skeleton = build_skeleton(
        date,
        fixture["theme"],
        fixture["brand"],
        fixture["cover"],
        fixture["closing"],
        sources,
        as_cover_quote(quote),
    )
    # 집계는 카드 후보(뉴스 20 · 영상 5)가 아니라 24시간 코퍼스 전체를 본다.
    trending_news = trending_pool_news(trending_news_raw, window_end_utc)
    trending_videos = trending_pool_videos(yt_raw, window_end_utc)
    trending_candidates = rank_topics(trending_news, trending_videos, window_end_utc)
    trending_corpus = corpus_summary(trending_news, trending_videos)

    out_path = (
        Path(args.out) if args.out else REPO_ROOT / "drafts" / f"draft-{date.isoformat()}.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "skeleton": skeleton,
                "candidates": {"news": news, "videos": videos},
                "trending_candidates": trending_candidates,
                "trending_corpus": trending_corpus,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"news candidates: {len(news)}")
    print(f"video candidates: {len(videos)}")
    print(
        f"trending pool: news {len(trending_news)} / videos {len(trending_videos)}"
        f" -> {len(trending_candidates)} topics"
    )
    print(f"trending corpus: {trending_corpus['note']}")
    print(f"cover quote: {quote.id} ({quote.author}) — 최근 {len(used_quote_ids)}개 제외")
    print(f"wrote {out_path}")
    return out_path


if __name__ == "__main__":
    main()
