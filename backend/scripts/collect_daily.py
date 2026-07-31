"""Collect BTC news/youtube candidates from the last 24h and write a draft skeleton.

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
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

KST = ZoneInfo("Asia/Seoul")
REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_CONTENT = REPO_ROOT / "frontend" / "src" / "fixtures" / "content.json"

DEFAULT_NEWS_URL = "http://localhost:8000/api/news?asset=btc&limit=100"
DEFAULT_YOUTUBE_URL = "http://localhost:23456/api/queue"
NEWS_LIMIT = 20
VIDEO_LIMIT = 5


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
    """Keep 비트코인-topic, summarized, last-24h videos, sorted by view_count desc."""
    cutoff = now - datetime.timedelta(hours=24)
    fresh = [
        v
        for v in items
        if v.get("topic") == "비트코인"
        and v.get("summary")
        and _parse_dt(v["added_at"]) >= cutoff
    ]
    fresh.sort(key=lambda v: v.get("view_count", 0), reverse=True)
    return fresh[:VIDEO_LIMIT]


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
) -> dict[str, Any]:
    cover = apply_date_to_cover(cover_fixed, date)
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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="기본값: 오늘(Asia/Seoul)")
    parser.add_argument("--out", help="기본값: <repo>/drafts/draft-<date>.json")
    parser.add_argument("--news-url", default=DEFAULT_NEWS_URL)
    parser.add_argument("--youtube-url", default=DEFAULT_YOUTUBE_URL)
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
        yt_raw = fetch_json(client, args.youtube_url, "my-youtube")["items"]
    finally:
        if owns_client:
            client.close()

    news = filter_news(news_raw, window_end_utc)
    videos = filter_videos(yt_raw, window_end_utc)
    for video in videos:
        video["thumbnail_url"] = f"https://i.ytimg.com/vi/{video['id']}/hqdefault.jpg"

    if not news and not videos:
        raise SystemExit(
            f"{date.isoformat()} 기준 24시간 내 후보가 없다 — 소스 응답이나 "
            "--news-url limit(과거 날짜는 100건으로 부족할 수 있다)을 확인하라."
        )

    sources = list(dict.fromkeys(n["source_ref"] for n in news))
    skeleton = build_skeleton(
        date, fixture["theme"], fixture["brand"], fixture["cover"], fixture["closing"], sources
    )

    out_path = (
        Path(args.out) if args.out else REPO_ROOT / "drafts" / f"draft-{date.isoformat()}.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {"skeleton": skeleton, "candidates": {"news": news, "videos": videos}},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"news candidates: {len(news)}")
    print(f"video candidates: {len(videos)}")
    print(f"wrote {out_path}")
    return out_path


if __name__ == "__main__":
    main()
