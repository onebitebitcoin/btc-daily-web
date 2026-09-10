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
import html
import io
import json
import re
import sys
import urllib.parse
from collections.abc import Callable, Collection
from concurrent.futures import ThreadPoolExecutor
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

# limit 이 500 이면 국내 소스가 컷에서 잘린다. my-news 는 published_at 순으로
# 자르는데 구글 뉴스 경유 기사는 게시 시각이 며칠 전인 경우가 흔해서, 방금
# 수집한 기사도 뒤로 밀린다(2026-09-10 실측: krmarket 이 limit 500 에서 7건,
# 1000 에서 12건). 창 필터는 crawled_at 기준이라 창은 통과하는데 API 컷에서
# 사라지는 것이라, limit 을 올리는 것 말고 방법이 없다.
DEFAULT_NEWS_URL = "http://localhost:8000/api/news?asset=btc&limit=1000"
# 트렌딩 집계는 카드 후보와 목적이 다르다 — 카드는 "쓸 만한 10건"을 고르지만
# 집계는 24시간에 무슨 일이 있었는지 전부 봐야 한다. 같은 소스를 따로, 넓게 받는다
# (2026-08-05 실측: 24h 코퍼스 205건인데 카드 후보 필터를 거치면 20건만 남았다).
DEFAULT_TRENDING_NEWS_URL = "http://localhost:8000/api/news?asset=btc&limit=1000"
# 매크로 보강 풀. my-news 의 asset=btc 는 달러·금리·연준 기사를 상당수 놓친다
# (2026-08-24 실측: 워시 첫 잭슨홀 연설, 연준의 10년 초과 국채 1.62조달러 보유,
# 빅테크 회사채가 국채금리를 밀어올린 건이 전부 asset=btc 밖에 있었다).
# 그래서 asset 필터 없이 한 번 더 받되 **macro 등급만** 취한다 — 이 피드는 AI·일반
# 뉴스가 대부분이고, 그중 일부는 내용과 무관한 tags:['bitcoin'] 이 붙어 있어
# 그대로 두면 야구 기사가 btc 등급으로 샌다(실측). 등급 제한이 그 방어선이다.
DEFAULT_MACRO_NEWS_URL = "http://localhost:8000/api/news?limit=1000"
# X(트위터) 집계 풀. `/api/tweets` 는 limit 파라미터가 없어 4만9천건 38MB 를 통째로
# 주므로 쓰지 않는다. `/api/feed` 는 limit 으로 자를 수 있고, 2000 이면 24시간 창을
# 덮고도 남는다(2026-09-10 실측: 2000건 중 24h 이내 683건 313계정).
DEFAULT_TWEETS_URL = "http://localhost:8000/api/feed?asset=btc&limit=2000&sort=time"
# full=1 없으면 my-youtube 가 summary/highlights/description 을 뺀 경량 응답을 준다.
# 그러면 filter_videos 의 `summary` 조건에 전부 걸려 후보가 조용히 0건이 된다(2026-08-05).
DEFAULT_YOUTUBE_URL = "http://localhost:23456/api/queue?full=1"
# 표지 인용구 중복 회피는 "실제로 발행된 것"을 봐야 한다 — 로컬 DB는 리허설 발행까지
# 섞여 있어 기준이 안 된다. 그래서 다른 소스와 달리 기본값이 프로덕션이다.
DEFAULT_EDITION_API = "https://daily.onebitebitcoin.com"
# 카드 후보 뉴스 창. 트렌딩 집계 창(24h)과 다르다 — 집계는 "그날 무슨 일이
# 있었나"라서 하루로 잘라야 맞지만, 카드 후보는 고를 게 많을수록 좋다.
# 2026-08-24 실측: 24h 는 btc 등급 69건인데 36h 로 늘리면 108건이 된다.
# 영상 창(VIDEO_WINDOW_HOURS)이 이미 48h 인 것과 같은 취지다.
NEWS_WINDOW_HOURS = 36
# 기사 자체의 나이 상한. **데일리 카드뉴스는 24시간 안에 나온 소식으로 만든다** —
# 편집 원칙이지 튜닝값이 아니므로 후보를 늘리려고 올리지 마라.
#
# 창(NEWS_WINDOW_HOURS)만으로는 이걸 보장하지 못한다. 창은 crawled_at 기준이라
# "우리가 언제 봤나"만 재는데, 구글 뉴스 검색 피드는 질의에 맞으면 몇 주 전 기사도
# 같이 준다. 그래서 8월 기사가 오늘 수집되면 36h 창을 그대로 통과해 오늘자 카드
# 후보가 됐다(2026-09-10 사고: 9월 3일자 김치프리미엄 기사가 그날 카드로 나갔다).
#
# 24h 로 잘라도 물량은 충분하다 — 그날 후보 100건 중 74건이 남았다
# (btc 54 / policy 11 / macro 9). 카드는 뉴스 8장이면 되므로 여유가 크다.
NEWS_MAX_AGE_HOURS = 24
# 후보 수. 2026-08-24 실측으로 20에서 올렸다 — 그날 24h 코퍼스 108건 중 20건만
# 후보가 됐고, 잘려나간 88건 안에 그날 트렌딩 1위였던 CFTC 비트코인 무기한선물
# 승인, 비트코인 코어 암호화 라우팅 재검토, 채굴사 IPO 가 전부 들어 있었다.
# 창을 36h 로 넓히면 btc 등급이 108건이라 60 으로는 다시 꼬리가 잘린다 — 창을
# 넓힌 의미가 없어지므로 같이 올린다. 비용은 후보당 이미지 1장 다운로드인데
# 디스크 캐시가 있어 배치가 몇십 초 길어지는 정도다.
NEWS_LIMIT = 100
NEWS_BUCKETS = 4  # 창을 4등분해 시간대별로 고르게 뽑는다
# 매크로 등급에 떼어두는 자리. 등급 순서대로만 채우면 btc 가 NEWS_LIMIT 을 그대로
# 다 먹어(2026-08-24: 36h btc 등급 108건) 매크로가 한 건도 못 올라온다 — 카드가
# 매크로를 쓸 수 있으려면 후보에 보이기부터 해야 한다.
MACRO_RESERVE = 12
# 정책 등급에 떼어두는 자리. MACRO_RESERVE 와 같은 취지다 — btc 등급이 상한을
# 다 먹으면 세제·규제 기사가 후보에 아예 안 보인다.
POLICY_RESERVE = 12
# 등급별 예약량. filter_news 가 이 합을 btc 몫에서 떼어 뒷등급에 남긴다.
TIER_RESERVES = {"policy": POLICY_RESERVE, "macro": MACRO_RESERVE}

# 후보의 비트코인 관련도 등급. 앞에 올수록 먼저 후보 자리를 가져간다.
# 카드는 비트코인 온리가 1순위이고, 물량이 모자라면 알트·크립토 일반 소재 대신
# 정책(가상자산 세제·규제·입법)과 매크로(달러·금리·연준·국채)로 채운다.
# 정책이 매크로보다 앞인 이유는 가상자산 과세·입법이 달러·금리보다 이 카드뉴스의
# 주제에 가깝기 때문이다 — 2026-09-09 편집 방침.
RELEVANCE_TIERS = ("btc", "policy", "macro", "other")

# 관련도 판정 키워드. title 은 가중치 3, summary+tags 는 1로 센다(_relevance_score).
# ASCII 항목은 단어 경계로, 한글 항목은 부분 문자열로 맞춘다.
BTC_TERMS = (
    "비트코인",
    "btc",
    "bitcoin",
    "사토시",
    "satoshi",
    "반감기",
    "halving",
    "해시레이트",
    "hashrate",
    "해시프라이스",
    "hashprice",
    "채굴",
    "mining",
    "miner",
    "난이도",
    "라이트닝",
    "lightning",
    "utxo",
    "탭루트",
    "taproot",
    "세그윗",
    "segwit",
    "코인베이스 프리미엄",
    "퓨엘 멀티플",
    "puell",
    "mvrv",
    "단기 보유자",
    "장기 보유자",
    "제네시스 블록",
)
# "온체인"은 체인 중립 용어라 넣지 않는다 — 넣으면 이더리움 온체인 기사가 btc 로 샌다.
ALT_TERMS = (
    "이더리움",
    "ethereum",
    "eth",
    "이더 ",
    "xrp",
    "리플",
    "ripple",
    "솔라나",
    "solana",
    "알트코인",
    "altcoin",
    "스테이블코인",
    "stablecoin",
    "usdt",
    "usdc",
    "테더",
    "tether",
    "서클",
    "지캐시",
    "zcash",
    "스택스",
    "stacks",
    "체인링크",
    "chainlink",
    "도지",
    "doge",
    "밈코인",
    "memecoin",
    "nft",
    "디파이",
    "defi",
    "이캐시",
    "부테린",
    "buterin",
    "하이퍼리퀴드",
    "hyperliquid",
    "토큰화",
    "layer 1",
    "레이어1",
)
# "달러"는 단독으로 쓰지 않는다 — 코인 시세 헤드라인이 전부 "N달러"라 매크로가 오염된다.
MACRO_TERMS = (
    "달러인덱스",
    "dxy",
    "달러 약세",
    "달러 강세",
    "금리",
    "국채",
    "treasury",
    "t-bill",
    "채권",
    "연준",
    "fed",
    "fomc",
    "파월",
    "잭슨홀",
    "jackson hole",
    "인플레이션",
    "inflation",
    "cpi",
    "pce",
    "물가",
    "고용지표",
    "실업률",
    "금값",
    "골드",
    "gold",
    "나스닥",
    "nasdaq",
    "s&p",
    "증시",
    "바이백",
    "buyback",
    "양적완화",
    "수익률 곡선",
    "yield curve",
    "환율",
    "엔화",
    "관세",
    "tariff",
)
# 가상자산 세제·규제 판정 키워드. classify_relevance 가 CRYPTO_DOMAIN_TERMS 와
# 함께 **제목에서만** 본다 — 둘 다 제목에 있어야 policy 다. 본문·태그까지 보면
# 소스가 기계적으로 붙인 tags:['bitcoin'] 때문에 무관한 기사가 샌다(2026-09-09
# 실측: 대학 스포츠 기사 "SEC Schedules Vote About Whether to Expel LSU" 가
# 'sec' 매칭으로 올라왔다).
POLICY_TERMS = (
    "과세",
    "세금",
    "세제",
    "세율",
    "국세",
    "소득세",
    "양도소득",
    "비과세",
    "상속세",
    "tax",
    "irs",
    "금융위",
    "금감원",
    "특금법",
    "자금세탁",
    "트래블룰",
    "aml",
    "규제",
    "입법",
    "법안",
    "개정안",
    "시행령",
    "가이드라인",
    "제도화",
    "국회",
    "의회",
    "상원",
    "하원",
    "congress",
    "senate",
    "sec",
    "cftc",
    "mica",
    "클래리티",
    "clarity act",
    "legislation",
    "regulation",
    "regulatory",
    "판결",
    "소송",
    "기소",
    "압수",
    "몰수",
    "제재",
    "sanction",
    "lawsuit",
    "ruling",
    "라이선스",
    "인가",
    "감독",
    "당국",
    "백악관",
    "white house",
    "행정명령",
    "executive order",
)
# 크립토 도메인 용어. 정책 기사가 "무엇에 대한 정책인가"를 가른다. ALT_TERMS 와
# 일부러 겹친다 — 스테이블코인 과세처럼 알트 용어가 들어간 정책 기사를 살리는 게
# 이 등급의 목적이다. 알트 시세·기술 기사는 제목에 POLICY_TERMS 가 없어서 걸러진다.
CRYPTO_DOMAIN_TERMS = (
    "가상자산",
    "암호화폐",
    "디지털자산",
    "크립토",
    "crypto",
    "코인",
    "거래소",
    "블록체인",
    "blockchain",
    "스테이블코인",
    "stablecoin",
    "비트코인",
    "bitcoin",
    "btc",
    "etf",
    "토큰",
    "token",
)
# 국내 기사 판별 지표어. **등급(RELEVANCE_TIERS)과 직교하는 축이다** — "업비트
# 비트코인 거래량"은 btc 등급이면서 국내 기사다. 등급을 하나 더 만들어 옮기면
# 비트코인 온리 순서가 오히려 꼬인다.
#
# 오탐 검사를 거쳐 좁게 잡았다(2026-09-10, 36h 코퍼스 260건 실측).
# - "거래소" 제외: "비트코인 7일 평균 거래소 유입"처럼 해외 온체인 기사에 걸린다
# - "정부"·"당국" 제외: 해외 기사 번역에 흔하다
# - "의회" 제외: 미국 의회 기사에 걸린다
DOMESTIC_TERMS = (
    "한국",
    "韓",
    "국내",
    "원화",
    #  매체마다 붙여 쓰기도 하고 띄어 쓰기도 한다. 붙인 표기만 두면 절반을 놓친다
    #  (2026-09-10 실측: 국내 시장 소스 15건 중 4건이 "김치 프리미엄" 표기였다).
    "김치프리미엄",
    "김치 프리미엄",
    "업비트",
    "빗썸",
    "코인원",
    "코빗",
    "금융위",
    "금감원",
    "기재부",
    "국세청",
    "특금법",
    "가상자산이용자보호",
    "국회",
    "한국은행",
    "코스피",
)
# 국내 기사에 떼어두는 후보 자리. TIER_RESERVES 와 같은 취지지만 등급 축과
# 직교하므로 따로 계산한다 — 국내 기사는 등급이 무엇이든 후보에 보이기부터 해야
# 카드 선별에서 검토된다.
DOMESTIC_RESERVE = 8

# 영상 후보 수. 5 는 실측상 너무 좁았다 — 2026-08-24 에 48h 안에서 요약까지
# 끝난 비트코인 영상이 21건이었는데 상위 5건만 후보가 됐다.
VIDEO_LIMIT = 15
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


def _as_utc(value: str) -> datetime.datetime | None:
    """문자열을 UTC aware datetime 으로. 못 읽으면 None.

    my-news 의 published_at 은 tz 표기가 없는 경우가 많다(RSS 의 pubDate 를 파싱한
    뒤 tzinfo 를 떼어 저장한다). 그런 값은 UTC 로 간주한다 — 대부분의 피드가 GMT 로
    쓰기 때문이다. +0900 으로 쓰는 피드가 섞이면 최대 9시간 어긋나는데, 비트코인
    후보에서는 실측으로 그런 항목이 없었다(2026-09-10: 후보 100건 중 published_at 이
    crawled_at 보다 뒤인 건이 0건 — 뒤로 나오면 타임존을 잘못 붙였다는 뜻이다).
    어긋난 소스가 생기면 그 소스의 기사가 하루 일찍 잘려나가므로, 후보가 갑자기
    줄면 여기부터 확인한다.
    """
    if not value:
        return None
    try:
        parsed = _parse_dt(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=datetime.UTC)
    return parsed.astimezone(datetime.UTC)


def is_stale(news: dict[str, Any], now: datetime.datetime) -> bool:
    """기사가 NEWS_MAX_AGE_HOURS 보다 오래됐는가.

    published_at 이 없거나 못 읽으면 **오래되지 않은 것으로 본다** — 판정 근거가
    없다고 후보에서 빼면, 시각 표기가 특이한 소스가 통째로 사라진다. 이 함수는
    창(crawled_at)을 이미 통과한 항목에만 걸리는 추가 게이트다.

    미래로 찍힌 값도 통과시킨다. 타임존을 잘못 붙인 것이지 오래된 기사가 아니다.
    """
    published = _as_utc(str(news.get("published_at") or ""))
    if published is None:
        return False
    return (now - published) > datetime.timedelta(hours=NEWS_MAX_AGE_HOURS)


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


# ---- 원문 URL 복원 · 대표 이미지 보강 ----
#
# my-news 의 가상자산 정책 소스(cryptopolicy)는 구글 뉴스 경유라 url 이
# news.google.com 리디렉션이고 image_url 이 비어 있다. 그대로 두면 카드의 "원문"
# 링크가 리디렉션 주소가 되고 이미지는 채울 방법이 없다. ai-daily-web 이 같은
# 문제를 먼저 겪었고(2026-08-26 발행분 카드 4장이 매체 홈페이지 링크에 기본
# 아트로 나갔다), 아래는 거기서 검증된 구현을 그대로 옮긴 것이다.
#
# 그래서 최종 후보에 한해 둘을 채운다.
#   1. 구글 뉴스 리디렉션 -> 매체 원문 URL
#   2. image_url 이 빈 후보 -> 원문 <head> 의 og:image
# 둘 다 실패하면 원래 값을 그대로 남긴다. 있으면 좋은 보강이지 06:00 배치를
# 죽일 이유가 아니다. 최종 후보(NEWS_LIMIT)에만 거는 건 원본 500건을 전부
# 두드리면 느리고 낭비라서다 — 이미지 해시와 같은 이유다.

GOOGLE_NEWS_ARTICLE = "https://news.google.com/rss/articles/"
GOOGLE_NEWS_RPC = "https://news.google.com/_/DotsSplashUi/data/batchexecute"
# 구글은 브라우저 UA 가 아니면 인터스티셜에 서명을 심어주지 않는다.
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
SOURCE_FETCH_TIMEOUT = 12.0
# 동시 요청 수. 5 면 이미지 없는 후보 59건이 실측 15초 안쪽이고 매체 한 곳에
# 몰아치지도 않는다.
SOURCE_ENRICH_WORKERS = 5
# og:image 는 <head> 에 있다. 본문까지 읽을 이유가 없다.
OG_HEAD_BYTES = 200_000
# 수집 본체는 my-news/my-youtube 만 보므로 리디렉션을 안 따라가지만, 매체 원문은
# 거의 항상 리디렉션을 탄다. 클라이언트를 따로 만들지 않고 요청 단위로 얹는다 —
# 그래야 호출자가 넘긴 클라이언트를 그대로 쓴다(테스트가 MockTransport 로 가로챈다).
_SOURCE_REQUEST: dict[str, Any] = {
    "headers": {"User-Agent": BROWSER_UA},
    "follow_redirects": True,
    "timeout": SOURCE_FETCH_TIMEOUT,
}
SOURCE_URL_CACHE_PATH = BACKEND_ROOT / ".cache" / "source-url" / "cache.json"
OG_IMAGE_CACHE_PATH = BACKEND_ROOT / ".cache" / "og-image" / "cache.json"

_GNEWS_SIGNATURE = re.compile(r'data-n-a-sg="([^"]+)"')
_GNEWS_TIMESTAMP = re.compile(r'data-n-a-ts="(\d+)"')
_OG_IMAGE_TAG = re.compile(
    r"""<meta[^>]+(?:property|name)=["'](?:og:image|twitter:image)(?::src)?["'][^>]*>""",
    re.IGNORECASE,
)
_OG_CONTENT = re.compile(r"""content=["']([^"']+)["']""", re.IGNORECASE)


def _load_str_cache(path: Path) -> dict[str, str]:
    """url -> url 캐시. 없거나 손상됐으면 빈 캐시로 시작한다(치명적이지 않다)."""
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {str(key): str(value) for key, value in raw.items()}
    except (OSError, json.JSONDecodeError, ValueError, AttributeError):
        return {}


def _save_str_cache(path: Path, cache: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        print(f"경고: 캐시 저장 실패 ({path.name}): {exc!r}", file=sys.stderr)


def _cached(cache: dict[str, str], key: str, produce: Callable[[], str | None]) -> str | None:
    """성공한 결과만 캐시에 남긴다 — 실패는 다음 실행에서 다시 시도되게."""
    if key in cache:
        return cache[key]
    value = produce()
    if value:
        cache[key] = value
    return value


def resolve_google_news_url(client: httpx.Client, url: str) -> str | None:
    """구글 뉴스 리디렉션 주소를 매체 원문 URL 로 되돌린다.

    주소 안에 원문이 인코딩돼 있지 않다 — 예전 형식은 base64 였지만 지금은
    아니다. 인터스티셜 HTML 에 심긴 서명(`data-n-a-sg`)과 타임스탬프를 구글
    내부 RPC 에 되던져야 원문이 나온다. 구글이 이 흐름을 바꾸면 여기서 None 이
    나오고 호출자는 원래 주소를 그대로 쓴다 — 링크가 리디렉션으로 남을 뿐
    수집은 계속된다.
    """
    article_id = url.split("/articles/", 1)[-1].split("?", 1)[0]
    if not article_id or article_id == url:
        return None
    try:
        page = client.get(url, **_SOURCE_REQUEST)
        page.raise_for_status()
        signature = _GNEWS_SIGNATURE.search(page.text)
        timestamp = _GNEWS_TIMESTAMP.search(page.text)
        if not (signature and timestamp):
            return None
        request = [
            "Fbv4je",
            json.dumps(
                [
                    "garturlreq",
                    [
                        ["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1]
                        + [None, None, None, None, None, 0, 1],
                        "X",
                        "X",
                        1,
                        [1, 1, 1],
                        1,
                        1,
                        None,
                        0,
                        0,
                        None,
                        0,
                    ],
                    article_id,
                    int(timestamp.group(1)),
                    signature.group(1),
                ]
            ),
        ]
        response = client.post(
            GOOGLE_NEWS_RPC,
            data={"f.req": json.dumps([[request]])},
            headers={
                "User-Agent": BROWSER_UA,
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            },
            timeout=SOURCE_FETCH_TIMEOUT,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        print(f"경고: 구글 뉴스 원문 복원 실패, 건너뜀 ({exc!r})", file=sys.stderr)
        return None
    return _parse_garturlres(response.text)


def _parse_garturlres(body: str) -> str | None:
    """batchexecute 응답에서 원문 URL 을 꺼낸다.

    응답은 `)]}'` 로 시작하는 줄 뒤에 JSON 이 이어지는 구글 특유의 형식이고,
    원문 URL 은 그 안에 **문자열로 한 번 더 인코딩된** JSON 안에 들어 있다.
    정규식으로 한 번에 긁으면 `=` 가 `\u003d` 로 이스케이프된 자리에서 잘린다
    (실측: aitimes.com 주소가 `?idxno` 에서 끊겼다) — 그래서 두 겹 다 파싱한다.
    """
    for line in body.splitlines():
        if "garturlres" not in line:
            continue
        try:
            envelope = json.loads(line)
        except json.JSONDecodeError:
            continue
        for row in envelope:
            if isinstance(row, list) and len(row) > 2 and row[0] == "wrb.fr":
                try:
                    payload = json.loads(row[2])
                except (json.JSONDecodeError, TypeError):
                    continue
                if len(payload) > 1 and isinstance(payload[1], str):
                    return payload[1]
    return None


def og_image_url(client: httpx.Client, url: str) -> str | None:
    """기사 <head> 의 og:image(없으면 twitter:image)를 절대 URL 로 돌려준다.

    이게 "기사 본문 실사진"에 가장 가까운 자동 수단이다 — 매체가 그 기사의
    대표 이미지로 직접 지정한 것이라, 다른 기사 사진을 빌려 오는 사고가 없다.
    """
    try:
        response = client.get(url, **_SOURCE_REQUEST)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        print(f"경고: 원문 og:image 조회 실패, 건너뜀 ({url}): {exc!r}", file=sys.stderr)
        return None
    for tag in _OG_IMAGE_TAG.findall(response.text[:OG_HEAD_BYTES]):
        found = _OG_CONTENT.search(tag)
        if found and found.group(1).strip():
            # 속성값은 HTML 이스케이프된 채로 들어온다 — `&amp;` 를 그대로 두면
            # 쿼리스트링이 깨져 이미지 서버가 다른 것을 주거나 404 를 낸다.
            raw = html.unescape(found.group(1).strip())
            return urllib.parse.urljoin(str(response.url), raw)
    return None


def enrich_candidates(
    items: list[dict[str, Any]],
    resolve_url: Callable[[str], str | None],
    fetch_image: Callable[[str], str | None],
    workers: int = SOURCE_ENRICH_WORKERS,
) -> list[dict[str, Any]]:
    """후보의 url 을 매체 원문으로 되돌리고, 이미지가 빈 후보에 og:image 를 채운다.

    되돌린 주소는 `url` 에 넣고 원래 리디렉션 주소는 `google_url` 로 남긴다.
    items 와 그 안의 dict 를 변형하지 않는다.
    """
    redirects = sum(1 for n in items if str(n.get("url") or "").startswith(GOOGLE_NEWS_ARTICLE))
    missing = sum(1 for n in items if not n.get("image_url"))

    def enrich(news: dict[str, Any]) -> dict[str, Any]:
        url = str(news.get("url") or "")
        patch: dict[str, Any] = {}
        if url.startswith(GOOGLE_NEWS_ARTICLE):
            resolved = resolve_url(url)
            if resolved:
                patch["url"] = resolved
                patch["google_url"] = url
                url = resolved
        if url and not news.get("image_url"):
            image = fetch_image(url)
            if image:
                patch["image_url"] = image
        return {**news, **patch} if patch else news

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        enriched = list(pool.map(enrich, items))

    restored = sum(1 for n in enriched if n.get("google_url"))
    filled = sum(
        1
        for before, after in zip(items, enriched, strict=True)
        if not before.get("image_url") and after.get("image_url")
    )
    print(
        f"source enrich: 리디렉션 {redirects}건 중 {restored}건 복원 · "
        f"이미지 없던 {missing}건 중 {filled}건 보강"
    )
    return enriched


def enrich_with_network(
    items: list[dict[str, Any]],
    client: httpx.Client,
    url_cache: dict[str, str],
    image_cache: dict[str, str],
) -> list[dict[str, Any]]:
    """enrich_candidates 를 실제 네트워크와 디스크 캐시에 묶는다."""
    return enrich_candidates(
        items,
        lambda url: _cached(url_cache, url, lambda: resolve_google_news_url(client, url)),
        lambda url: _cached(image_cache, url, lambda: og_image_url(client, url)),
    )


# 화제성 우선권을 줄 트렌딩 토픽 수. rank_topics 는 상위 15개를 내는데, 그 꼬리는
# 매체 한 곳이 한 번 언급한 수준이라 "여러 매체가 동시에 다뤘다"는 신호가 약하다.
TRENDING_PRIORITY_TOPICS = 8


def trending_article_urls(topics: list[dict[str, Any]]) -> list[str]:
    """상위 TRENDING_PRIORITY_TOPICS 개 토픽에 걸린 기사 url — filter_news 의 우선권 목록."""
    urls: list[str] = []
    for topic in topics[:TRENDING_PRIORITY_TOPICS]:
        for article in topic.get("articles") or []:
            url = article.get("url")
            if isinstance(url, str):
                urls.append(url)
    return list(dict.fromkeys(urls))


def _term_hits(text: str, terms: tuple[str, ...]) -> int:
    """text 에 등장한 terms 의 종류 수. 같은 단어가 여러 번 나와도 1로 센다."""
    count = 0
    for term in terms:
        if term.isascii():
            # "eth" 가 "method" 에, "gold" 가 "goldman" 에 걸리지 않게 단어 경계로 맞춘다.
            if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text):
                count += 1
        elif term in text:
            count += 1
    return count


def _relevance_score(news: dict[str, Any], terms: tuple[str, ...]) -> int:
    """제목 가중치 3, summary+tags 가중치 1로 매긴 키워드 점수."""
    title = str(news.get("title") or "").lower()
    rest = " ".join(str(news.get(key) or "") for key in ("summary", "tags")).lower()
    return 3 * _term_hits(title, terms) + _term_hits(rest, terms)


def _title_hits(news: dict[str, Any], terms: tuple[str, ...]) -> int:
    """제목에만 걸린 terms 의 종류 수. 본문·태그는 안 본다.

    policy 판정 전용이다. _relevance_score 는 제목에 가중치 3 을 주긴 하지만
    본문·태그만으로도 점수가 나므로, 소스가 기사 내용과 무관하게 붙인 태그
    (tags: ['bitcoin'])로 등급이 뒤집힌다. 정책 등급은 오탐 비용이 커서
    (카드 10장 중 한 자리를 무관한 기사에 내준다) 제목만 본다.
    """
    return _term_hits(str(news.get("title") or "").lower(), terms)


def classify_relevance(news: dict[str, Any]) -> str:
    """기사를 RELEVANCE_TIERS 중 하나로 분류한다 — "btc" / "macro" / "other".

    비트코인 점수가 알트 점수 이상이면 btc, 아니면 매크로 점수가 알트 이상일 때
    macro, 나머지는 other. 동점을 btc·macro 쪽에 주는 건 의도한 것이다 — 이 등급은
    후보를 자르는 게이트가 아니라 **후보 자리를 누가 먼저 가져가느냐**를 정하는
    우선순위라서, 카드 10장을 고르는 사람이 한 번 더 거른다. 애매한 건을 빼서
    아예 안 보이게 만드는 쪽이 훨씬 비싸다(2026-08-24: 그날 트렌딩 1위 기사가
    후보에 없었다).

    2026-08-24 코퍼스 108건 실측: btc 71 / macro 3 / other 34 로 갈렸고, other 에는
    스택스·잭엑스비티·XRP 시황·이더리움·스테이블코인처럼 그날 카드에서 빼고 싶었던
    소재가 모여 있었다.

    policy 는 그 other 안에 섞여 있던 **가상자산 세제·규제·입법** 기사를 건져내려고
    2026-09-09 에 넣었다. 제목에 알트·스테이블코인 용어가 들어갔다는 이유만으로
    국내 정책 보도가 통째로 other 로 밀려나 카드에 못 갔다(실측: "국회예산정책처
    원화 스테이블코인 준비자산 규제는 필요", "최대 5조1500억원 절감…원화
    스테이블코인 준비자산 규제 제언"). 판정은 **정책 용어와 크립토 용어가 둘 다
    제목에 있을 것**을 요구한다 — 알트코인 시세·기술·프로젝트 소식은 제목에 정책
    용어가 없어서 그대로 other 에 남는다(실측으로 비자 스테이블코인 카드, 로빈후드
    예측시장, 비트마인 이더리움 매입이 other 를 유지했다).

    btc 를 policy 보다 먼저 보는 것도 의도한 것이다 — 비트코인 규제 기사는 policy
    가 아니라 btc 로 남아야 후보 상단을 지킨다.
    """
    btc = _relevance_score(news, BTC_TERMS)
    alt = _relevance_score(news, ALT_TERMS)
    if btc and btc >= alt:
        return "btc"
    if _title_hits(news, POLICY_TERMS) and _title_hits(news, CRYPTO_DOMAIN_TERMS):
        return "policy"
    if _relevance_score(news, MACRO_TERMS) >= max(alt, 1):
        return "macro"
    return "other"


def _dedupe_key(news: dict[str, Any]) -> tuple[Any, Any]:
    """후보 하나를 가리키는 키. url 이 비어 있는 항목이 있어 id 를 같이 쓴다."""
    return (news.get("url"), news.get("id"))


def classify_domestic(news: dict[str, Any]) -> bool:
    """국내 기사인가. **제목만** 본다.

    `_title_hits` 와 같은 이유로 제목만 본다 — 태그·요약까지 보면 소스가 기사
    내용과 무관하게 붙인 태그로 오탐이 난다(policy 등급에서 이미 겪었다).

    매체 국적이 아니라 기사 내용 기준이다. 토큰포스트·블록미디어는 한국 매체지만
    실제로 내보내는 기사 대부분이 해외 시황 번역이라(2026-09-10: 후보 51건 중 국내
    취재물 0건), 매체로 판정하면 해외 기사가 통째로 국내로 분류된다.
    """
    return _title_hits(news, DOMESTIC_TERMS) > 0


def _round_robin_by_bucket(
    items: list[dict[str, Any]],
    now: datetime.datetime,
    limit: int,
    priority_urls: Collection[str] = (),
) -> list[dict[str, Any]]:
    """창을 NEWS_BUCKETS 구간으로 나눠 구간별 라운드로빈으로 limit 건 뽑는다.

    구간 안에서는 국내 기사를 먼저, 그 다음 priority_urls 에 든 기사를, 그 다음
    최신순으로 정렬한다. 국내가 화제성보다 앞인 건 물량 차이 때문이다 — 국내
    기사는 하루 5건 안팎이라(2026-09-10 실측) 화제성 큰 사건을 밀어내는 폭이 작다.
    """
    if limit <= 0:
        return []
    priority = set(priority_urls)
    bucket_hours = NEWS_WINDOW_HOURS / NEWS_BUCKETS
    buckets: list[list[dict[str, Any]]] = [[] for _ in range(NEWS_BUCKETS)]
    for n in items:
        age_h = (now - _parse_dt(n["crawled_at"])).total_seconds() / 3600
        # 클록 스큐 등으로 age_h 가 음수/창 초과로 튀어도 유효 구간 안에 묶는다.
        index = min(max(int(age_h // bucket_hours), 0), NEWS_BUCKETS - 1)
        buckets[index].append(n)
    for bucket in buckets:
        bucket.sort(
            key=lambda n: (
                not n.get("domestic"),
                n.get("url") not in priority,
                -_parse_dt(n["crawled_at"]).timestamp(),
            )
        )

    picked: list[dict[str, Any]] = []
    cursors = [0] * NEWS_BUCKETS
    while len(picked) < limit and any(cursors[i] < len(buckets[i]) for i in range(NEWS_BUCKETS)):
        for i in range(NEWS_BUCKETS):
            if len(picked) >= limit:
                break
            if cursors[i] < len(buckets[i]):
                picked.append(buckets[i][cursors[i]])
                cursors[i] += 1
    return picked


# 무필터 피드에서 주워올 등급. btc 는 일부러 뺀다(broad_topups docstring 참고).
BROAD_TOPUP_TIERS = ("policy", "macro")


def broad_topups(
    items: list[dict[str, Any]],
    now: datetime.datetime,
    exclude_urls: Collection[str] = (),
) -> list[dict[str, Any]]:
    """asset 필터 없는 피드에서 **BROAD_TOPUP_TIERS 등급만** 골라낸다 — 보강 풀.

    btc 등급은 일부러 버린다. 이 피드는 AI·일반 뉴스가 대부분이고 그중 일부에
    내용과 무관한 `tags: ['bitcoin']` 이 붙어 있어(2026-08-24 실측: KBO 야구 기사
    3건이 그렇게 btc 로 분류됐다) 그대로 받으면 후보 상단이 오염된다. 비트코인
    기사는 my-news 가 이미 asset=btc 로 걸러 주므로 여기서 또 주울 이유도 없다.

    policy 를 함께 받는 이유는, 가상자산 세제·규제 기사가 태그에 코인 이름을 안
    달아 asset 판정에서 새는 경우가 있어서다. policy 판정은 제목에 정책 용어와
    크립토 용어를 둘 다 요구하므로 야구 기사가 새던 경로로는 안 들어온다.

    exclude_urls 는 기본 피드에서 이미 받은 url 이다 — 두 피드가 겹치는 만큼
    중복으로 들어오는 걸 막는다.
    """
    seen = set(exclude_urls)
    cutoff = now - datetime.timedelta(hours=NEWS_WINDOW_HOURS)
    picked: list[dict[str, Any]] = []
    for news in items:
        url = news.get("url")
        if not url or url in seen or news.get("is_duplicate"):
            continue
        crawled = news.get("crawled_at")
        if not crawled or _parse_dt(crawled) < cutoff:
            continue
        if classify_relevance(news) not in BROAD_TOPUP_TIERS:
            continue
        seen.add(url)
        picked.append(news)
    return picked


def filter_news(
    items: list[dict[str, Any]],
    now: datetime.datetime,
    exclude_image_hashes: Collection[int] = (),
    hash_image: Callable[[str], int | None] | None = None,
    priority_urls: Collection[str] = (),
    enrich: Callable[[list[dict[str, Any]]], list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    """NEWS_WINDOW_HOURS 창을 통과한 기사를 관련도 순으로, 시간대별로 고르게 뽑는다.

    두 축이 겹쳐 있다.

    **관련도(바깥 축).** RELEVANCE_TIERS 순서대로 btc 를 먼저 채우고, 남으면
    policy, macro, 그래도 남으면 other 로 채운다. 카드가 비트코인 온리를 1순위로
    두고 물량이 모자랄 때 알트 대신 정책·매크로를 쓰기 때문이다. 다만 btc 만으로
    상한이 차버리면 뒷등급이 후보에 아예 안 보이므로, 각 등급 후보가 있는 만큼
    TIER_RESERVES 자리까지는 btc 몫에서 떼어 남겨둔다. 2026-08-24 진단: 코퍼스
    108건 중 20건만 후보가 됐는데 관련도 정렬이 없어, 그날 트렌딩 1위였던 CFTC
    비트코인 무기한선물 승인은 빠지고 이더리움 시세·지캐시 기사는 들어왔다.

    **시간대(안쪽 축).** 각 등급 안에서는 창을 NEWS_BUCKETS 개 구간으로 나눠
    구간별 라운드로빈으로 뽑는다. 크론이 06:00 KST 에 도는 탓에 그 직전 몇 시간
    (=미국 장중)에 기사가 몰리면 그 시간대가 상위를 독차지해, 카드 후보가 하루
    24시간 중 평균 27%(최악 9%)밖에 못 덮었다(2026-08-18 진단).

    **기사 나이(창과 별개의 게이트).** 창은 crawled_at 기준이라 "우리가 언제 봤나"만
    잰다. 구글 뉴스 검색 피드가 몇 주 전 기사를 같이 주므로, 게시 시각이
    NEWS_MAX_AGE_HOURS 를 넘긴 기사는 `is_stale` 로 따로 뗀다.

    **국내(등급과 직교하는 축).** 국내 기사는 등급 안에서 먼저 오고, DOMESTIC_RESERVE
    만큼은 등급별 몫과 별개로 자리를 확보한다. 판정은 `classify_domestic` — 매체
    국적이 아니라 제목 내용 기준이다. 2026-09-10 진단: 36h 코퍼스 260건 중 국내
    기사가 5건뿐인데 그마저 policy 등급이라 btc 기사 뒤에 묻혔고, 그날 발행분에
    국내 소식이 한 건도 못 들어갔다.

    **화제성(구간 안 정렬).** priority_urls 는 보통 rank_topics 상위 토픽에 걸린
    기사들의 url 이다. 구간 안에서 이들을 최신순보다 앞에 둔다 — 등급이 같아도
    여러 매체가 동시에 다룬 사건이 먼저 후보 자리를 가져가야 지엽적인 단발 기사에
    밀리지 않는다. 2026-08-24 에는 btc 등급만 71건이라 40 컷에서 그날 트렌딩 1위
    (CFTC 비트코인 무기한선물 승인)가 잘려나갔다. 안 넘기면 예전처럼 최신순이다.

    돌려주는 각 항목에는 `relevance` 와 `domestic` 키가 붙는다(카드 10장을 고를 때 쓴다).

    exclude_image_hashes(recent_image_hashes)와 hash_image(url -> average hash,
    보통 get_image_hash 를 클라이언트/캐시에 바인딩한 클로저)가 둘 다 주어지면,
    최종 선정된 후보 중 이미지가 최근 발행분과 해밍거리 IMAGE_HASH_MAX_DISTANCE
    이하로 겹치는 것의 image_url 을 None 으로 뗀다(기사 자체는 남긴다) — 같은
    draft 안에서 후보끼리 겹쳐도 마찬가지다. 최종 선정된 NEWS_LIMIT 건에만
    적용한다 — 원본 최대 500건을 전부 내려받으면 느리고 낭비다. hash_image 를
    안 넘기면(기본값) 이미지 중복배제를 건너뛴다 — 예전과 동일하게 동작한다.

    enrich 를 넘기면 최종 선정된 후보에만 적용한다(보통 enrich_with_network) —
    구글 뉴스 리디렉션을 매체 원문으로 되돌리고 빈 이미지를 og:image 로 채운다.
    이미지 중복배제보다 먼저 돌아가므로 새로 채운 이미지도 검사를 받는다.
    안 넘기면(기본값) 보강을 건너뛴다.

    items 와 그 안의 dict 를 변형하지 않는다(relevance 가 붙은 항목도, 이미지가
    떨어져 나간 항목도 새 dict 로 돌려준다).
    """
    cutoff = now - datetime.timedelta(hours=NEWS_WINDOW_HOURS)
    fresh = [
        {**n, "relevance": classify_relevance(n), "domestic": classify_domestic(n)}
        for n in items
        if not n.get("is_duplicate")
        and _parse_dt(n["crawled_at"]) >= cutoff
        and not is_stale(n, now)
    ]

    # 국내 기사부터 DOMESTIC_RESERVE 만큼 확보한다. 등급 축과 직교하므로 등급별
    # 몫에서 떼는 게 아니라 아예 먼저 집는다 — 국내 기사는 등급이 무엇이든 후보에
    # 보이기부터 해야 카드 선별에서 검토된다.
    picked: list[dict[str, Any]] = _round_robin_by_bucket(
        [n for n in fresh if n["domestic"]], now, DOMESTIC_RESERVE, priority_urls
    )
    taken = {_dedupe_key(n) for n in picked}

    by_tier = {
        tier: [n for n in fresh if n["relevance"] == tier and _dedupe_key(n) not in taken]
        for tier in RELEVANCE_TIERS
    }
    # btc 가 상한을 다 먹지 않도록, 실제로 있는 만큼만 뒷등급 자리를 떼어둔다.
    reserved = sum(min(quota, len(by_tier[tier])) for tier, quota in TIER_RESERVES.items())

    for tier in RELEVANCE_TIERS:
        room = NEWS_LIMIT - len(picked)
        if tier == "btc":
            room -= reserved
        if room <= 0:
            continue
        picked.extend(_round_robin_by_bucket(by_tier[tier], now, room, priority_urls))

    # draft 를 사람이 읽을 땐 등급 → 화제성 → 최신순이 자연스럽다. 위에서부터 읽으면
    # 비트코인 온리에 여러 매체가 동시에 다룬 사건이 먼저 나온다 — 카드 10장을 고를 때
    # 실제로 훑는 순서가 그거다.
    priority = set(priority_urls)
    picked.sort(
        key=lambda n: (
            RELEVANCE_TIERS.index(n["relevance"]),
            not n.get("domestic"),
            n.get("url") not in priority,
            -_parse_dt(n["crawled_at"]).timestamp(),
        )
    )

    # enrich 를 이미지 중복배제보다 먼저 돌린다 — og:image 로 새로 채운 이미지도
    # 중복 검사를 받아야 한다. 순서가 반대면 보강된 그림이 검사를 건너뛴다.
    if enrich is not None:
        picked = enrich(picked)

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
    return [
        n
        for n in items
        if n.get("crawled_at")
        and _parse_dt(n["crawled_at"]) >= cutoff
        and not is_stale(n, now)
    ]


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


def tweet_account(tweet: dict[str, Any]) -> str | None:
    """트윗의 계정 핸들. my-news 의 `user` 는 여러 줄이다.

    "₿ig Picture\n@BtcPicture\n·\n12분" 처럼 표시명·핸들·시간이 줄바꿈으로 붙어
    있어서, 그대로 세면 같은 계정이 시간 문구 때문에 여러 개로 갈린다.
    """
    raw = str(tweet.get("user") or "")
    for line in raw.split("\n"):
        line = line.strip()
        if line.startswith("@"):
            return line
    return raw.strip() or None


def trending_pool_tweets(
    items: list[dict[str, Any]], now: datetime.datetime
) -> list[dict[str, Any]]:
    """트렌딩 집계용 24시간 X 코퍼스. 창 필터만 한다.

    트윗에는 my-news 가 뉴스와 같은 모양의 `tags` 를 붙여 주므로(예:
    ['#거시경제', '#인플레이션', '#연준']) 별도 토픽 추출이 필요 없다.
    """
    cutoff = now - datetime.timedelta(hours=24)
    fresh = []
    for t in items:
        stamp = t.get("time") or t.get("crawled_at")
        if not stamp:
            continue
        try:
            when = _parse_dt(stamp)
        except ValueError:
            continue
        if when >= cutoff:
            fresh.append(t)
    return fresh


def corpus_summary(
    news: list[dict[str, Any]],
    videos: list[dict[str, Any]],
    tweets: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """트렌딩 집계가 실제로 무엇을 봤는지 — 건수와 매체/채널/계정 수.

    `note` 문자열까지 여기서 완성해 draft 에 굽는다. 발행 문구를 쓰는 주체는
    Claude 지만 **이 숫자만은 세는 것이지 쓰는 게 아니다.** draft 에 없으면 무인
    실행이 트렌딩 카드의 "N건 집계"를 지어내는 수밖에 없다(2026-08-05: 사람이
    수동으로 세어 넣었다). 세어서 넘겨주면 그대로 베끼면 된다.
    """
    outlets = {n.get("source_ref") for n in news if n.get("source_ref")}
    channels = {v.get("channel_title") for v in videos if v.get("channel_title")}
    tweets = tweets or []
    accounts = {a for a in (tweet_account(t) for t in tweets) if a}
    note = (
        f"뉴스 {len(news)}건 {len(outlets)}매체 · "
        f"유튜브 {len(videos)}건 {len(channels)}채널"
    )
    # X 를 못 읽은 날(피드 장애)에는 문구를 늘리지 않는다 — 카드에 "X 0건"이 찍히면
    # 집계가 X 를 봤는데 아무것도 없었다는 뜻으로 읽혀 사실과 어긋난다.
    if tweets:
        note += f" · X {len(tweets)}건 {len(accounts)}계정"
    return {
        "news": len(news),
        "outlets": len(outlets),
        "videos": len(videos),
        "channels": len(channels),
        "tweets": len(tweets),
        "accounts": len(accounts),
        "outlet_names": sorted(outlets),
        "channel_names": sorted(channels),
        "note": f"{note} 집계",
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

    filter_news/filter_videos 는 항상 "이 시각으로부터 각자의 창 길이만큼 전까지"만 본다 —
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
    parser.add_argument("--macro-news-url", default=DEFAULT_MACRO_NEWS_URL)
    parser.add_argument("--youtube-url", default=DEFAULT_YOUTUBE_URL)
    parser.add_argument("--tweets-url", default=DEFAULT_TWEETS_URL)
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
        source_url_cache = _load_str_cache(SOURCE_URL_CACHE_PATH)
        og_image_cache = _load_str_cache(OG_IMAGE_CACHE_PATH)
        used_image_hashes = recent_image_hashes(
            client, args.edition_api, date, RECENT_IMAGE_DAYS, image_hash_cache
        )
        # 트렌딩 집계를 카드 후보 선별보다 먼저 돌린다 — 그날 여러 매체가 동시에
        # 다룬 사건이 무엇인지 알아야 후보 40 자리를 그쪽에 먼저 줄 수 있다.
        # X 보강. macro 피드와 같은 취지로 실패해도 수집을 막지 않는다 — 피드 하나
        # 때문에 06:00 배치가 죽으면 손해가 훨씬 크다.
        try:
            tweets_payload = fetch_json(client, args.tweets_url, "my-news(tweets)")
            tweets_raw = (
                tweets_payload["items"]
                if isinstance(tweets_payload, dict)
                else tweets_payload
            )
        except (httpx.HTTPError, SystemExit, KeyError, TypeError) as exc:
            print(f"경고: X 피드를 못 읽어 건너뛴다 ({exc!r})", file=sys.stderr)
            tweets_raw = []
        trending_news = trending_pool_news(trending_news_raw, window_end_utc)
        trending_videos = trending_pool_videos(yt_raw, window_end_utc)
        trending_tweets = trending_pool_tweets(tweets_raw, window_end_utc)
        trending_candidates = rank_topics(
            trending_news, trending_videos, window_end_utc, trending_tweets
        )
        trending_corpus = corpus_summary(trending_news, trending_videos, trending_tweets)
        hot_urls = trending_article_urls(trending_candidates)
        # 후보 이미지 해시도 같은 클라이언트·캐시로 계산한다. filter_news 는 URL 만
        # 넘기므로 클로저로 묶어 둔다.
        # 정책·매크로 보강. 실패해도 수집을 막지 않는다 — 있으면 좋은 것이지, 피드
        # 하나 때문에 06:00 배치가 죽으면 손해가 훨씬 크다.
        try:
            macro_raw = fetch_json(client, args.macro_news_url, "my-news(broad)")
        except (httpx.HTTPError, SystemExit) as exc:
            print(f"경고: 정책·매크로 보강 피드를 못 읽어 건너뛴다 ({exc!r})", file=sys.stderr)
            macro_raw = []
        broad_extra = broad_topups(
            macro_raw, window_end_utc, {n.get("url") for n in news_raw if n.get("url")}
        )
        news = filter_news(
            news_raw + broad_extra,
            window_end_utc,
            used_image_hashes,
            lambda url: get_image_hash(client, url, image_hash_cache),
            hot_urls,
            lambda picked: enrich_with_network(
                picked, client, source_url_cache, og_image_cache
            ),
        )
        _save_image_hash_cache(image_hash_cache)
        _save_str_cache(SOURCE_URL_CACHE_PATH, source_url_cache)
        _save_str_cache(OG_IMAGE_CACHE_PATH, og_image_cache)
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
            f"{date.isoformat()} 기준 창 안에 후보가 없다 — 소스 응답이나 "
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
    # 집계는 카드 후보(NEWS_LIMIT · VIDEO_LIMIT)가 아니라 24시간 코퍼스 전체를 본다.

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

    tier_counts = {t: sum(1 for n in news if n.get("relevance") == t) for t in RELEVANCE_TIERS}
    print(
        f"news candidates: {len(news)} — "
        + " / ".join(f"{tier} {count}" for tier, count in tier_counts.items())
    )
    # 국내 기사는 등급 안에서 맨 앞으로 오지만, policy 등급 자체가 후보 80번대에서
    # 시작하는 날이 있어 위에서부터 읽으면 못 보고 지나친다. 제목까지 찍어서 카드를
    # 고르는 쪽이 draft 를 안 뒤져도 무엇이 있었는지 알게 한다.
    domestic = [n for n in news if n.get("domestic")]
    if domestic:
        print(f"domestic candidates: {len(domestic)}")
        for n in domestic:
            print(f"  [{n.get('relevance')}] {n.get('source_ref')} — {n.get('title')}")
    else:
        print("domestic candidates: 0 — 창 안에 국내 기사가 없었다")
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
