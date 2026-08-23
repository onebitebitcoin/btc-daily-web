"""Collect BTC news(24h)/youtube(48h) candidates and write a draft skeleton.

Deterministic only — no LLM calls. Fills every field of an edition that doesn't
require judgement (meta/theme/brand/cover/closing) and dumps ranked candidates
for a human (or a Claude Code session) to pick 10 cards from.

--date 를 오늘이 아닌 과거로 주면 "지금부터 24h"가 아니라 그 날짜(KST) 자정까지의
24h 창으로 자동 전환된다(백필). 단, 소스 API 는 최신순 정렬이라 며칠 전 날짜는
기본 --news-url 의 limit=500 으로 안 닿을 수 있다 — limit 을 넉넉히 올려서 넘겨라.

Usage: python scripts/collect_daily.py [--date YYYY-MM-DD] [--out PATH]
                                        [--news-url URL] [--youtube-url URL]
       python scripts/collect_daily.py --date 2026-07-27 \
           --news-url "http://localhost:8000/api/news?asset=btc&limit=1000"
"""

import argparse
import datetime
import io
import json
import sys
import urllib.parse
from collections.abc import Callable, Collection
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from PIL import Image

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

DEFAULT_NEWS_URL = "http://localhost:8000/api/news?asset=btc&limit=500"
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
NEWS_BUCKETS = 4  # 24h 창을 6시간씩 4구간으로 나눈다
VIDEO_LIMIT = 5
# 영상 창은 게시 시각 기준 48h. 24h 로 좁히면 my-youtube 가 요약을 늦게 끝낸 영상이
# 통째로 빠진다 — 게시 25h 뒤에 요약이 붙는 경우가 흔하다.
VIDEO_WINDOW_HOURS = 48
# 영상 일간 중복배제용 발행 이력 조회 기간. 영상 후보 창(48h) + 여유 하루.
RECENT_VIDEO_DAYS = 3

# 이미지 일간 중복배제. 카드뉴스 이미지가 며칠 간격으로 재탕되는데, 토큰포스트
# (f1.tokenpost.kr) 등 일부 매체가 같은 그림을 기사마다 새 랜덤 파일명으로
# 재업로드해 URL 대조로는 새어나간다(2026-08-19~23 발행 48장 md5 대조: 바이트
# 동일 4쌍 중 3쌍이 URL 이 서로 달랐다) — 그래서 실제로 이미지를 내려받아
# average hash 로 비교한다.
RECENT_IMAGE_DAYS = 7  # 발행 이력 조회 기간(일)
IMAGE_HASH_SIZE = 8  # average hash 그레이스케일 리사이즈 크기(8x8 = 64비트)
# 이 이하 해밍거리면 "같은 이미지"로 본다. 2026-08-23 실측으로 정했다: 발행분·후보
# 이미지 84종(3,486쌍)을 재보니 서로 다른 이미지의 최소 거리가 6이었고, 진짜 중복은
# — 바이트 동일이든 리사이즈 변형(_th_860x0, -560x305)이든 랜덤 파일명 재업로드든 —
# 전부 거리 0으로 나왔다. 그래서 0 쪽에 붙여 4로 잡는다(그 표본에서 오탐 0쌍).
# 처음에 12로 뒀더니 베이지색 서류함 일러스트와 네온 실루엣이 거리 11로 묶였다.
IMAGE_HASH_MAX_DISTANCE = 4
# 이미지 다운로드 타임아웃(초). 느린 CDN 하나가 배치를 물고 늘어지지 않게 짧게 잡는다.
IMAGE_FETCH_TIMEOUT = 10.0
IMAGE_HASH_CACHE_PATH = BACKEND_ROOT / ".cache" / "imghash" / "cache.json"


def _parse_dt(value: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))


# ---- 이미지 중복배제: average hash ----
#
# md5 같은 바이트 단위 대조는 리사이즈·재인코딩·랜덤 파일명 재업로드를 못 잡는다.
# average hash 는 이미지를 8x8 그레이스케일로 뭉갠 뒤 픽셀이 평균보다 밝은지만
# 비트로 남겨 그런 변형에 강하다 — 2026-08-19~23 발행 48장에서 해밍거리 12 이하
# 유사쌍이 6쌍 나왔다(바이트 동일 4쌍 + 리사이즈로 추정되는 2쌍).


def average_hash(image_bytes: bytes) -> int | None:
    """8x8(IMAGE_HASH_SIZE) 그레이스케일 average hash.

    디코딩 실패하면 None — 이미지 하나 때문에 호출자(배치)를 죽이지 않는다.
    """
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            small = img.convert("L").resize(
                (IMAGE_HASH_SIZE, IMAGE_HASH_SIZE), Image.Resampling.LANCZOS
            )
            pixels = list(small.getdata())
    except Exception as exc:  # Pillow 예외 유형이 다양해 넓게 잡는다
        print(f"경고: 이미지 해시 계산 실패, 건너뜀 ({exc!r})", file=sys.stderr)
        return None

    average = sum(pixels) / len(pixels)
    digest = 0
    for index, value in enumerate(pixels):
        if value > average:
            digest |= 1 << index
    return digest


def hamming_distance(a: int, b: int) -> int:
    """두 average hash 가 다른 비트 수 — 작을수록 같은 이미지에 가깝다."""
    return bin(a ^ b).count("1")


def _fetch_image_bytes(client: httpx.Client, url: str) -> bytes | None:
    """이미지를 내려받는다.

    실패(타임아웃/4xx/5xx)해도 예외를 올리지 않고 None — 이미지 하나의 네트워크
    실패로 전체 수집을 막지 않는다.
    """
    try:
        response = client.get(url, timeout=IMAGE_FETCH_TIMEOUT)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        print(f"경고: 이미지 다운로드 실패, 건너뜀 ({url}): {exc!r}", file=sys.stderr)
        return None
    return response.content


def _load_image_hash_cache() -> dict[str, int]:
    """url -> average hash 캐시. 없거나 손상됐으면 빈 캐시로 시작한다(치명적이지 않다)."""
    if not IMAGE_HASH_CACHE_PATH.exists():
        return {}
    try:
        raw = json.loads(IMAGE_HASH_CACHE_PATH.read_text(encoding="utf-8"))
        return {str(url): int(digest) for url, digest in raw.items()}
    except (OSError, json.JSONDecodeError, ValueError, AttributeError):
        return {}


def _save_image_hash_cache(cache: dict[str, int]) -> None:
    IMAGE_HASH_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        IMAGE_HASH_CACHE_PATH.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        print(f"경고: 이미지 해시 캐시 저장 실패 ({exc!r})", file=sys.stderr)


def get_image_hash(client: httpx.Client, url: str, cache: dict[str, int]) -> int | None:
    """url 이미지의 average hash. cache 에 있으면 그대로 쓰고, 없으면 내려받아 계산해

    cache 에 채운다(호출자가 들고 있는 dict를 in-place 로 채운다 — 여러 URL 을
    순회하고 마지막에 한 번만 파일로 저장하기 위해서다, 저장은 호출자 책임).
    다운로드/디코딩 실패는 캐시에 남기지 않는다 — 다음 실행에서 다시 시도되게.
    """
    if url in cache:
        return cache[url]
    image_bytes = _fetch_image_bytes(client, url)
    if image_bytes is None:
        return None
    digest = average_hash(image_bytes)
    if digest is None:
        return None
    cache[url] = digest
    return digest


def filter_news(
    items: list[dict[str, Any]],
    now: datetime.datetime,
    exclude_image_hashes: Collection[int] = (),
    hash_image: Callable[[str], int | None] | None = None,
) -> list[dict[str, Any]]:
    """중복을 배제하고 24h 창을 통과한 기사를, 시간대별로 고르게 뽑는다.

    예전에는 crawled_at 내림차순 단일 정렬로 상위 NEWS_LIMIT 건을 잘랐다(정렬
    보조키였던 dup_count 는 실측상 20건 중 19~20건이 0이라 사실상 상수였고,
    정렬 의도를 오독하게만 했다 — 제거). 크론이 06:00 KST 에 도는 탓에 그 직전
    몇 시간(=미국 장중)에 기사가 몰리면 그 시간대만 상위를 독차지해, 카드 후보
    20건이 하루 24시간 중 평균 27%(최악 9%)밖에 못 덮었다(2026-08-18 진단).

    24시간을 NEWS_BUCKETS 개 구간(각 6시간)으로 나눠 구간별로 최신순 정렬한 뒤
    라운드로빈으로 한 건씩 뽑으면, 특정 시간대가 없거나 얇아도 다른 구간이 그
    몫을 채우면서 하루 전체에서 소재가 나온다.

    exclude_image_hashes(recent_image_hashes)와 hash_image(url -> average hash,
    보통 get_image_hash 를 클라이언트/캐시에 바인딩한 클로저)가 둘 다 주어지면,
    최종 선정된 후보 중 이미지가 최근 발행분과 해밍거리 IMAGE_HASH_MAX_DISTANCE
    이하로 겹치는 것의 image_url 을 None 으로 뗀다(기사 자체는 남긴다) — 같은
    draft 안에서 후보끼리 겹쳐도 마찬가지다. 라운드로빈으로 뽑힌 20건에만
    적용한다 — 원본 최대 500건을 전부 내려받으면 느리고 낭비다. hash_image 를
    안 넘기면(기본값) 이미지 중복배제를 건너뛴다 — 예전과 동일하게 동작한다.

    items 와 그 안의 dict 를 변형하지 않는다(이미지가 떨어져 나간 항목은 새
    dict 로 돌려준다).
    """
    cutoff = now - datetime.timedelta(hours=24)
    fresh = [n for n in items if not n.get("is_duplicate") and _parse_dt(n["crawled_at"]) >= cutoff]

    bucket_hours = 24 / NEWS_BUCKETS
    buckets: list[list[dict[str, Any]]] = [[] for _ in range(NEWS_BUCKETS)]
    for n in fresh:
        age_h = (now - _parse_dt(n["crawled_at"])).total_seconds() / 3600
        # 클록 스큐 등으로 age_h 가 음수/24h 초과로 튀어도 유효 구간 안에 묶는다.
        index = min(max(int(age_h // bucket_hours), 0), NEWS_BUCKETS - 1)
        buckets[index].append(n)
    for bucket in buckets:
        bucket.sort(key=lambda n: _parse_dt(n["crawled_at"]), reverse=True)

    picked: list[dict[str, Any]] = []
    cursors = [0] * NEWS_BUCKETS
    while len(picked) < NEWS_LIMIT and any(
        cursors[i] < len(buckets[i]) for i in range(NEWS_BUCKETS)
    ):
        for i in range(NEWS_BUCKETS):
            if len(picked) >= NEWS_LIMIT:
                break
            if cursors[i] < len(buckets[i]):
                picked.append(buckets[i][cursors[i]])
                cursors[i] += 1

    # draft 를 사람이 읽을 땐 최신순이 자연스럽다 — 구간 배정과 무관하게 재정렬.
    picked.sort(key=lambda n: _parse_dt(n["crawled_at"]), reverse=True)

    if hash_image is not None:
        picked = _dedupe_image_urls(picked, exclude_image_hashes, hash_image)

    return picked


def _dedupe_image_urls(
    picked: list[dict[str, Any]],
    exclude_image_hashes: Collection[int],
    hash_image: Callable[[str], int | None],
) -> list[dict[str, Any]]:
    """최근 발행 이미지 또는 이 draft 안 앞선 후보와 겹치는 image_url 을 뗀다.

    같은 draft 안에서 겹치면 먼저 나온 쪽(picked 순서 기준)을 살리고 뒤에 오는
    쪽을 뗀다. hash_image 가 None 을 돌려주면(다운로드/디코딩 실패, 또는
    image_url 자체가 없음) 판정할 수 없으니 그대로 둔다.
    """
    seen_hashes: list[int] = []
    result: list[dict[str, Any]] = []
    dropped = 0
    for news in picked:
        url = news.get("image_url")
        digest = hash_image(url) if url else None
        if digest is None:
            result.append(news)
            continue
        match = _closest_image_match(digest, exclude_image_hashes, seen_hashes)
        if match is None:
            seen_hashes.append(digest)
            result.append(news)
            continue
        distance, source = match
        print(
            f"이미지 중복배제: {url} 의 image_url 을 뗀다 "
            f"({source}와 해밍거리 {distance} <= {IMAGE_HASH_MAX_DISTANCE})",
            file=sys.stderr,
        )
        result.append({**news, "image_url": None})
        dropped += 1
    if dropped:
        print(f"이미지 중복배제: {dropped}건의 image_url 을 뗐다", file=sys.stderr)
    return result


def _closest_image_match(
    digest: int, exclude_image_hashes: Collection[int], seen_hashes: list[int]
) -> tuple[int, str] | None:
    """digest 와 IMAGE_HASH_MAX_DISTANCE 이하로 가장 가까운 (해밍거리, 출처)를 찾는다."""
    best: tuple[int, str] | None = None
    for source, pool in (
        ("최근 발행 이미지", exclude_image_hashes),
        ("같은 draft 내 다른 후보", seen_hashes),
    ):
        for other in pool:
            distance = hamming_distance(digest, other)
            if distance <= IMAGE_HASH_MAX_DISTANCE and (best is None or distance < best[0]):
                best = (distance, source)
    return best


def filter_videos(
    items: list[dict[str, Any]],
    now: datetime.datetime,
    exclude_ids: Collection[str] = (),
) -> list[dict[str, Any]]:
    """Keep 비트코인-topic, summarized videos published within the window, by view_count desc.

    창을 published_at 으로 잡는 게 핵심이다. 큐 등록 시각(added_at)으로 잡으면
    my-youtube 가 과거 영상을 한꺼번에 백필한 날 몇 주 지난 영상이 "최근 24시간"으로
    딸려 들어오고, 조회수가 그만큼 누적돼 있어 상위 칸을 독차지한다.
    (2026-08-04: 6~7월 영상 5건이 8/3 게시분을 전부 밀어냄)

    published_at 이 없는 항목은 신선도를 판정할 수 없으므로 버린다.

    exclude_ids 는 최근 발행분에 이미 쓴 영상 id다(recent_video_ids). 48h 창 안에서
    조회수가 며칠째 쌓이는 인기 영상은 매일 상위권을 독차지하기 쉬운데, 그대로 두면
    같은 영상이 날짜를 넘겨 반복 게재된다 — 17개 날짜 전환 중 10회(59%)에서 전날
    영상이 재등장한 사례가 있었다(2026-08-18 진단). 기본값은 빈 컬렉션이라 호출부가
    안 넘기면 예전과 동일하게 동작한다.
    """
    excluded = set(exclude_ids)
    cutoff = now - datetime.timedelta(hours=VIDEO_WINDOW_HOURS)
    fresh = [
        v
        for v in items
        if v.get("topic") == "비트코인"
        and v.get("summary")
        and v.get("published_at")
        and _parse_dt(v["published_at"]) >= cutoff
        and v.get("id") not in excluded
    ]
    fresh.sort(key=lambda v: v.get("view_count", 0), reverse=True)
    return fresh[:VIDEO_LIMIT]


def trending_pool_news(items: list[dict[str, Any]], now: datetime.datetime) -> list[dict[str, Any]]:
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


def corpus_summary(news: list[dict[str, Any]], videos: list[dict[str, Any]]) -> dict[str, Any]:
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


def recent_quote_ids(client: httpx.Client, api: str, date: datetime.date, limit: int) -> list[str]:
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


def _youtube_id(url: str) -> str | None:
    """카드에 박히는 세 가지 유튜브 URL 형태에서 video id 를 뽑는다.

    발행 파이프라인이 만드는 형태는 이 셋뿐이다:
    - card.link.href  : `https://youtu.be/<id>` 또는 `https://www.youtube.com/watch?v=<id>`
    - card.media.image: `https://i.ytimg.com/vi/<id>/hqdefault.jpg`
    매치되지 않으면(형태가 바뀌었거나 유튜브 링크가 아니면) None — 조용히 건너뛴다.
    """
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return None
    host = parsed.netloc.removeprefix("www.")
    if host == "youtu.be":
        video_id = parsed.path.strip("/")
        return video_id or None
    if host in {"youtube.com", "m.youtube.com"}:
        video_id = urllib.parse.parse_qs(parsed.query).get("v", [None])[0]
        return video_id or None
    if host == "i.ytimg.com":
        parts = parsed.path.strip("/").split("/")
        if len(parts) >= 2 and parts[0] == "vi":
            return parts[1] or None
        return None
    return None


def recent_video_ids(client: httpx.Client, api: str, date: datetime.date, days: int) -> list[str]:
    """최근 `days`일 발행분에 이미 쓴 유튜브 영상 id 를 모은다 — 영상 일간 중복배제용.

    **실패해도 수집을 막지 않는다.** recent_quote_ids 와 같은 이유다 — 영상
    중복배제는 있으면 좋은 것이지, 발행 이력 조회 하나 때문에 06:00 배치가 죽으면
    손해가 훨씬 크다. 실패하면 빈 목록을 돌려주고, filter_videos 는 exclude_ids=()
    와 동일하게 동작한다(중복배제만 약해질 뿐 수집은 그대로 나간다).
    """
    try:
        # fetch_dates 는 응답이 에러면 SystemExit 을 낸다 — 여기서는 치명적이지 않다.
        dates = fetch_dates(client, api, date, days)
    except (httpx.HTTPError, SystemExit, TypeError, KeyError) as exc:
        print(f"경고: 발행 이력을 못 읽어 영상 중복 회피를 건너뛴다 ({exc!r})", file=sys.stderr)
        return []

    ids: list[str] = []
    for published in dates:
        try:
            edition = fetch_edition(client, api, published)
        except httpx.HTTPError:
            continue
        if not isinstance(edition, dict):
            continue
        for card in edition.get("cards") or []:
            if not isinstance(card, dict):
                continue
            # media: null 인 카드가 실제 데이터에 하루 0~3장 있다 — 방어적으로 접근.
            link = card.get("link")
            href = link.get("href") if isinstance(link, dict) else None
            media = card.get("media")
            image = media.get("image") if isinstance(media, dict) else None
            for url in (href, image):
                if isinstance(url, str):
                    video_id = _youtube_id(url)
                    if video_id is not None:
                        ids.append(video_id)
    return list(dict.fromkeys(ids))


def recent_image_hashes(
    client: httpx.Client, api: str, date: datetime.date, days: int, cache: dict[str, int]
) -> list[int]:
    """최근 `days`일 발행분 카드 이미지의 average hash 를 모은다 — 이미지 중복배제용.

    **실패해도 수집을 막지 않는다.** recent_video_ids 와 같은 이유다. 이미지가
    겹치는 건 아쉬운 일이지만, 발행 이력 조회나 CDN 하나가 느리다고 06:00 배치가
    죽으면 손해가 훨씬 크다. 실패하면 빈 목록을 돌려주고 filter_news 는
    exclude_image_hashes=() 와 동일하게 동작한다.

    유튜브 썸네일(i.ytimg.com)은 제외한다 — 영상 중복배제가 id 로 이미 막고 있고,
    썸네일은 그 영상의 고유 이미지라 여기서 또 걸 이유가 없다.
    """
    try:
        # fetch_dates 는 응답이 에러면 SystemExit 을 낸다 — 여기서는 치명적이지 않다.
        dates = fetch_dates(client, api, date, days)
    except (httpx.HTTPError, SystemExit, TypeError, KeyError) as exc:
        print(f"경고: 발행 이력을 못 읽어 이미지 중복 회피를 건너뛴다 ({exc!r})", file=sys.stderr)
        return []

    digests: list[int] = []
    for published in dates:
        try:
            edition = fetch_edition(client, api, published)
        except httpx.HTTPError:
            continue
        if not isinstance(edition, dict):
            continue
        for card in edition.get("cards") or []:
            if not isinstance(card, dict):
                continue
            # media: null 인 카드가 하루 0~3장 있다 — 방어적으로 접근.
            media = card.get("media")
            image = media.get("image") if isinstance(media, dict) else None
            if not isinstance(image, str) or _youtube_id(image) is not None:
                continue
            digest = get_image_hash(client, image, cache)
            if digest is not None:
                digests.append(digest)
    return digests


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
        # 트렌딩은 같은 소스를 더 넓게 봐야 한다. 기본값은 이제 둘 다 limit=500 이라
        # 아래 분기가 자동으로 news_raw 를 재사용해 호출 1회를 절약한다 — 사용자가
        # --news-url 을 이보다 좁게 오버라이드했을 때만 따로 다시 받는다.
        trending_news_raw = (
            news_raw
            if args.trending_news_url == args.news_url
            else fetch_json(client, args.trending_news_url, "my-news(trending)")
        )
        yt_raw = fetch_json(client, args.youtube_url, "my-youtube")["items"]
        quote_pool = load_pool()
        used_quote_ids = recent_quote_ids(client, args.edition_api, date, len(quote_pool))
        used_video_ids = recent_video_ids(client, args.edition_api, date, RECENT_VIDEO_DAYS)
        image_hash_cache = _load_image_hash_cache()
        used_image_hashes = recent_image_hashes(
            client, args.edition_api, date, RECENT_IMAGE_DAYS, image_hash_cache
        )
        # 후보 이미지 해시도 같은 클라이언트·캐시로 계산한다. filter_news 는 URL 만
        # 넘기므로 클로저로 묶어 둔다.
        news = filter_news(
            news_raw,
            window_end_utc,
            used_image_hashes,
            lambda url: get_image_hash(client, url, image_hash_cache),
        )
        _save_image_hash_cache(image_hash_cache)
    finally:
        if owns_client:
            client.close()
    videos = filter_videos(yt_raw, window_end_utc, used_video_ids)
    for video in videos:
        video["thumbnail_url"] = f"https://i.ytimg.com/vi/{video['id']}/hqdefault.jpg"

    # 후보 0건은 "그날 영상이 없었다"일 수도, 소스 응답이 바뀐 것일 수도 있다.
    # 조용히 넘어가면 뉴스만 10장인 에디션이 그대로 나가므로 이유를 구분해 알린다.
    if not videos:
        warn_video_drought(yt_raw)

    if not news and not videos:
        raise SystemExit(
            f"{date.isoformat()} 기준 24시간 내 후보가 없다 — 소스 응답이나 "
            "--news-url limit(과거 날짜는 500건으로 부족할 수 있다)을 확인하라."
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
    print(
        f"video candidates: {len(videos)} — 최근 {RECENT_VIDEO_DAYS}일 발행분 "
        f"{len(used_video_ids)}건 제외"
    )
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
