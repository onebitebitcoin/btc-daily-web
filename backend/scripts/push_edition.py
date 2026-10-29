"""Validate a finished edition JSON locally, then POST it to /api/editions.

Local validation reuses the same pydantic schema the API enforces, so a bad
field fails here with a clear message instead of round-tripping a 422. 그 뒤
verify_edition 이 카드마다 원문 링크와 이미지를 실제로 두드려 본다 — 죽은 링크,
매체 홈페이지, 구글 리디렉션, 중복 이미지는 여기서 막힌다.

Usage: python scripts/push_edition.py drafts/edition-2026-07-30.json
       python scripts/push_edition.py drafts/edition-2026-07-30.json --date 2026-07-30
"""

import argparse
import json
import sys
import urllib.parse
from pathlib import Path
from typing import Any

import httpx
from pydantic import ValidationError

BACKEND_ROOT = Path(__file__).resolve().parents[1]

# 직접 실행하면 sys.path[0] 이 scripts/ 라 app 을 못 찾는다.
# pytest 는 pyproject 의 pythonpath=["."] 로 이미 해결되지만, 문서화된 실행 방식은
# `python scripts/push_edition.py ...` 라서 여기서도 backend/ 를 붙여줘야 한다.
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.schemas import EditionContent  # noqa: E402  (sys.path 조정 후여야 함)
from app.wording import find_problems  # noqa: E402
from scripts.collect_daily import (  # noqa: E402
    IMAGE_HASH_MAX_DISTANCE,
    apply_date_to_cover,
    get_image_hash,
    hamming_distance,
)
from scripts.recent_editions import fetch_dates, fetch_edition  # noqa: E402
from scripts.verify_edition import check_edition, print_report  # noqa: E402

ENV_FILE = BACKEND_ROOT / ".env"
DEFAULT_API = "http://localhost:8002"


def load_admin_api_key() -> str:
    if not ENV_FILE.exists():
        raise SystemExit(f"{ENV_FILE} 없음 — ADMIN_API_KEY를 설정하라.")
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() == "ADMIN_API_KEY" and value.strip():
            return value.strip()
    raise SystemExit(f"{ENV_FILE}에 ADMIN_API_KEY 없음.")


def load_and_validate(path: Path) -> EditionContent:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SystemExit(f"{path} 읽기 실패: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path} JSON 파싱 실패: {exc}") from exc
    try:
        return EditionContent.model_validate(raw)
    except ValidationError as exc:
        raise SystemExit(f"스키마 검증 실패 — 서버로 전송하지 않음:\n{exc}") from exc


# 뉴스 카드 장수. 이 뒤에 붙는 카드(지식 한입·활용팁 같은 고정 꼭지)는 정렬하지 않고
# 맨 끝에 그대로 둔다.
NEWS_CARD_COUNT = 10


def order_cards_by_trend(content: EditionContent) -> EditionContent:
    """뉴스 카드를 지정 뉴스 → 트렌딩 순위 오름차순 → 카드 화제성 내림차순 → 나머지
    순으로 다시 매긴다.

    순서를 스킬 지시로만 맡겼더니 시황 카드를 1번에 고정하는 등 발행분이 트렌딩
    순위와 어긋났다(2026-10-28 실측). 발행 직전에 코드로 강제한다. 트렌딩 순위에
    안 걸린 카드는 `heat.score`(card_heat.py)로 줄 세운다. 같은 묶음 안에서는 draft 에
    적힌 순서를 유지한다(지정 뉴스는 파일 순서).
    """
    news = [card for card in content.cards if card.num <= NEWS_CARD_COUNT]
    extras = [card for card in content.cards if card.num > NEWS_CARD_COUNT]

    def sort_key(card: Any) -> tuple[int, int]:
        if card.pinned:
            return (0, 0)
        if card.trend_rank is not None:
            return (1, card.trend_rank)
        if card.heat is not None:
            return (2, -card.heat.score)
        return (3, 0)

    ordered = sorted(news, key=sort_key) + extras
    renumbered = [card.model_copy(update={"num": i}) for i, card in enumerate(ordered, 1)]
    if [card.num for card in ordered] != [card.num for card in renumbered]:
        moves = ", ".join(f"{card.num}→{i}" for i, card in enumerate(ordered, 1) if card.num != i)
        print(f"카드 순서를 트렌딩 순위대로 바꿈: {moves}")
    return content.model_copy(update={"cards": renumbered})


def check_cover_matches_date(content: EditionContent) -> None:
    """cover.mark/meta[2]는 meta.date에서 파생돼야 한다 — 드리프트를 발행 전에 잡는다.

    이 체크가 없으면 날짜 이전에 만들어진 stale draft(구버전 cover)를 재발행할 때
    DB의 올바른 cover를 조용히 되돌려버린다(실제로 있었던 사고).
    """
    expected = apply_date_to_cover(content.cover.model_dump(), content.meta.date)
    actual_meta2 = content.cover.meta[2] if len(content.cover.meta) > 2 else None
    if content.cover.mark != expected["mark"] or actual_meta2 != expected["meta"][2]:
        raise SystemExit(
            "cover가 meta.date와 불일치 — 발행 취소 (draft가 최신 날짜 코드로 재생성되지 않음).\n"
            f"  기대 cover.mark = {expected['mark']} / 실제 = {content.cover.mark}\n"
            f"  기대 cover.meta[2] = {expected['meta'][2]!r} / 실제 = {actual_meta2!r}"
        )


def check_wording(content: EditionContent) -> None:
    """CONTENT_CONTRACT.md 2.1·2.2 위반이면 POST 전에 멈춘다.

    `check_cover_matches_date`와 같은 이유로 우회 옵션을 두지 않는다 — 끌 수 있는
    가드는 바쁜 날 꺼지고, 그날 틀린 표기가 그대로 나간다.
    """
    problems = find_problems(content)
    if problems:
        joined = "\n".join(f"  - {p}" for p in problems)
        raise SystemExit(
            f"문구 게이트 실패 — 발행하지 않음 ({len(problems)}건). "
            f"CONTENT_CONTRACT.md 2.1(어미)·2.2(표기 용어집) 참고:\n{joined}"
        )


# 삽화(기사 사진이 아닌 자료 사진)가 올라오는 호스트. 여기서 온 그림은 출처 표기가
# 라이선스 조건이라 credit 없이 내보내면 안 된다.
#
# 호스트로 판정하는 이유: 기사 URL 과 이미지 URL 의 도메인 비교로는 못 가른다 —
# 매체가 이미지를 별도 CDN 에 두는 게 흔하다(tokenpost.kr 기사 / f1.tokenpost.kr 그림,
# daum 기사 / img1.daumcdn.net 그림). 그래서 삽화가 실제로 오는 곳만 적어 둔다.
# `scripts/find_illustration.py` 가 쓰는 Openverse 가 돌려주는 제공처가 이 둘이다.
ILLUSTRATION_HOSTS = (
    "staticflickr.com",
    "upload.wikimedia.org",
    # rawpixel 은 CC0 를 많이 주는데, CC0 는 저작자 표시가 법적 의무는 아니다.
    # 그래도 목록에 넣는다 — 독자가 "사건을 찍은 사진이 아니라 자료 사진"임을
    # 아는 것이 이 표기의 두 번째 일이고, 그건 라이선스와 무관하게 필요하다.
    "images.rawpixel.com",
    # find_illustration.py 가 2026-10-29 부터 쓰는 출처.
    "images.unsplash.com",
)


def check_illustration_credit(content: EditionContent) -> None:
    """삽화 호스트에서 온 그림은 `media.credit` 이 있어야 한다.

    CC BY·BY-SA 는 저작자 표시가 라이선스 조건이다. 표기를 빠뜨리면 라이선스를
    어긴 채로 발행물이 나가고, 독자도 그 그림이 사건을 찍은 사진인 줄 알게 된다.
    `find_illustration.py` 가 만들어 주는 문자열을 그대로 넣으면 된다.
    """
    problems: list[str] = []
    for card in content.cards:
        media = card.media
        if media is None:
            continue
        host = urllib.parse.urlparse(media.image).netloc.lower()
        if not any(host.endswith(h) or h in host for h in ILLUSTRATION_HOSTS):
            continue
        if not (media.credit or "").strip():
            problems.append(
                f"카드 {card.num}: 삽화({host})인데 media.credit 이 없다 — "
                f"scripts/find_illustration.py 가 준 credit 을 그대로 넣어라"
            )
    if problems:
        joined = "\n".join(f"  - {p}" for p in problems)
        raise SystemExit(f"삽화 출처 게이트 실패 — 발행하지 않음 ({len(problems)}건):\n{joined}")


# 섬네일로 내보내면 안 되는 호스트. 토큰포스트 본문 그림은 `/ TokenPost.ai` 크레딧이
# 붙는 자체 AI 생성물이다.
AI_IMAGE_HOSTS = ("tokenpost.kr",)


def _matches_host(host: str, hosts: tuple[str, ...]) -> bool:
    return any(host.endswith(h) or h in host for h in hosts)


def check_card_images_not_ai(content: EditionContent) -> None:
    """카드 그림에도 AI 생성물 호스트를 쓰지 않는다.

    AI 그림은 사건을 찍은 사진처럼 보이지만 실재하지 않는 장면이고, 글자가 깨진 채
    나가기도 한다. 매체 CDN 에 섞인 AI 그림은 호스트로 다 못 거르므로 나머지는
    CONTENT_CONTRACT.md 이미지 규칙의 "거르는 것" 목록을 보고 눈으로 거른다.
    """
    problems = [
        f"카드 {card.num}: {urllib.parse.urlparse(card.media.image).netloc} 는 AI 생성물이다"
        for card in content.cards
        if card.media is not None
        and _matches_host(urllib.parse.urlparse(card.media.image).netloc.lower(), AI_IMAGE_HOSTS)
    ]
    if problems:
        joined = "\n".join(f"  - {p}" for p in problems)
        raise SystemExit(
            f"카드 그림 게이트 실패 — 발행하지 않음 ({len(problems)}건). "
            f"기사 실사진이나 핵심 낱말 삽화로 바꿔라:\n{joined}"
        )


# 유튜브 섬네일 호스트. 섬네일은 클릭을 끌려고 제목·숫자·트윗 캡처를 크게 얹어 만들어서
# 거의 다 "글자가 주인 그림"이다(2026-10-28 ai-daily 5번 "AI CRISIS IN MATH", 10번
# "1.5T tokens"). 눈으로 거르라는 규칙만으로는 계속 새어 나가서 호스트째 막는다.
YOUTUBE_THUMBNAIL_HOSTS = ("ytimg.com",)


def check_no_youtube_thumbnails(content: EditionContent) -> None:
    """카드 그림과 섬네일(`meta.og_image`)에 유튜브 섬네일을 쓰지 않는다.

    유튜브 카드는 영상의 핵심 낱말로 `find_illustration.py` 삽화를 찾아 붙인다.
    """
    images = [(f"카드 {card.num}", card.media.image) for card in content.cards if card.media]
    if content.meta.og_image:
        images.append(("meta.og_image", content.meta.og_image))
    problems = [
        f"{where}: {url}"
        for where, url in images
        if _matches_host(urllib.parse.urlparse(url).netloc.lower(), YOUTUBE_THUMBNAIL_HOSTS)
    ]
    if problems:
        joined = "\n".join(f"  - {p}" for p in problems)
        raise SystemExit(
            f"유튜브 섬네일 게이트 실패 — 발행하지 않음 ({len(problems)}건). "
            "섬네일은 글자가 주인 그림이다. 핵심 낱말 삽화(find_illustration.py)로 바꿔라:\n"
            f"{joined}"
        )


# 새 발행에 쓰지 않는 삽화 호스트. 위키미디어는 발행 서버(데이터센터 IP)에서 원본을
# 받으면 429 를 연달아 줘서 2026-10-29 삽화 6장 중 4장이 글자판으로 나갔다. 운영자
# 지시로 Unsplash(find_illustration.py)로 바꿨다. 과거 발행분은 이미지 프록시가 계속 받는다.
BLOCKED_ILLUSTRATION_HOSTS = ("wikimedia.org",)


def check_no_blocked_illustration_hosts(content: EditionContent) -> None:
    """카드 그림과 섬네일에 위키미디어를 쓰지 않는다."""
    images = [(f"카드 {card.num}", card.media.image) for card in content.cards if card.media]
    if content.meta.og_image:
        images.append(("meta.og_image", content.meta.og_image))
    problems = [
        f"{where}: {url}"
        for where, url in images
        if _matches_host(urllib.parse.urlparse(url).netloc.lower(), BLOCKED_ILLUSTRATION_HOSTS)
    ]
    if problems:
        joined = "\n".join(f"  - {p}" for p in problems)
        raise SystemExit(
            f"위키미디어 그림 게이트 실패 — 발행하지 않음 ({len(problems)}건). "
            "발행 서버가 위키미디어에서 429 를 받는다. find_illustration.py(Unsplash)로 바꿔라:\n"
            f"{joined}"
        )


def check_cards_have_media(content: EditionContent) -> None:
    """모든 카드에 그림이 있어야 한다.

    `media: null` 카드는 프론트가 문구를 조판해 채우는 글자판(`CardArtFallback`)이 된다.
    "최후 수단"으로 열어 뒀더니 무인 발행이 삽화를 못 받을 때마다 그 출구로 빠졌다
    (2026-10-29: 11장 중 5장이 글자판). 사건을 특정하는 카드도 발표 주체의 건물·로고는
    있으니 그림이 없는 카드는 없다.
    """
    missing = [card.num for card in content.cards if card.media is None]
    if missing:
        raise SystemExit(
            f"카드 그림 누락 게이트 실패 — 발행하지 않음 (카드 {missing}). "
            "그림 없는 카드는 글자판으로 나간다. 핵심 낱말 삽화(find_illustration.py)나 "
            "발표 주체의 건물·로고 사진을 붙여라."
        )


def check_news_cards_have_heat(content: EditionContent) -> None:
    """뉴스 카드마다 화제성(`heat`)이 있어야 한다 — 카드 화제성 막대가 이 값으로 그려진다.

    `trend_rank` 만으로는 트렌딩 상위 토픽에 걸린 카드만 막대를 받는다(2026-10-29:
    10장 중 2장). `scripts/card_heat.py` 로 카드마다 센다.
    """
    missing = [
        card.num for card in content.cards if card.num <= NEWS_CARD_COUNT and card.heat is None
    ]
    if missing:
        raise SystemExit(
            f"카드 화제성 게이트 실패 — 발행하지 않음 (카드 {missing}). "
            "scripts/card_heat.py 로 카드마다 heat 를 넣어라."
        )


def check_og_image(content: EditionContent) -> None:
    """`meta.og_image` 를 직접 골라 넣었는지 본다.

    비워 두면 1번 카드 그림이 그대로 링크 미리보기가 된다 — 2026-10-24 에 블록미디어가
    돌려쓰는 AI 만화가 그렇게 나갔다. 매체 CDN 의 AI 그림은 호스트로 다 못 거르므로,
    고르는 기준(주제와 맞는 실사진 우선, 없으면 주제를 떠올리게 하는 삽화)은
    CONTENT_CONTRACT.md 4.2절이 맡고 여기서는 비어 있는 것과 AI 호스트를 막는다.

    삽화는 섬네일에 credit 을 표시할 자리가 없으므로, 같은 그림을 카드에도 싣고
    그 카드의 `media.credit` 으로 저작자를 밝힌 경우에만 허용한다.
    """
    url = (content.meta.og_image or "").strip()
    if not url.startswith("http"):
        raise SystemExit(
            "섬네일 게이트 실패 — meta.og_image 가 비어 있다. "
            "CONTENT_CONTRACT.md 4.2절대로 골라 넣어라"
        )
    host = urllib.parse.urlparse(url).netloc.lower()
    if _matches_host(host, AI_IMAGE_HOSTS):
        raise SystemExit(
            f"섬네일 게이트 실패 — meta.og_image({host})는 AI 생성물이다. "
            f"기사 실사진이나 주제를 떠올리게 하는 삽화로 바꿔라"
        )
    if _matches_host(host, ILLUSTRATION_HOSTS):
        credited = any(
            card.media is not None
            and card.media.image == url
            and (card.media.credit or "").strip()
            for card in content.cards
        )
        if not credited:
            raise SystemExit(
                f"섬네일 게이트 실패 — meta.og_image({host})는 삽화인데 같은 그림을 "
                f"credit 과 함께 실은 카드가 없다. 그 삽화를 카드 media 에도 넣어라"
            )


OG_REUSE_LOOKBACK_DAYS = 30


def published_thumbnail(edition: dict[str, Any]) -> str | None:
    """그 에디션이 실제로 내보낸 섬네일 URL — `app/og.py` 의 에디션 기준 선택과 같다."""
    og_image = (edition.get("meta") or {}).get("og_image")
    if og_image:
        return og_image
    cards = edition.get("cards") or []
    media = (cards[0].get("media") or {}) if cards else {}
    return media.get("image")


def check_og_image_not_reused(client: httpx.Client, api: str, content: EditionContent) -> None:
    """최근 발행분이 이미 쓴 섬네일을 다시 쓰지 않았는지 본다.

    URL 이 같은 경우와, 매체가 같은 그림을 다른 URL 로 다시 올린 경우(average hash
    해밍거리 `IMAGE_HASH_MAX_DISTANCE` 이하)를 둘 다 막는다. 발행 이력을 못 읽으면
    경고만 하고 넘어간다 — 조회 실패로 06:00 무인 발행을 막을 일은 아니다.
    """
    url = content.meta.og_image or ""
    try:
        dates = fetch_dates(client, api, content.meta.date, OG_REUSE_LOOKBACK_DAYS)
    except (httpx.HTTPError, SystemExit) as exc:
        print(f"경고: 발행 이력을 못 읽어 섬네일 재사용 점검을 건너뛴다 ({exc!r})", file=sys.stderr)
        return

    hashes: dict[str, int] = {}
    digest: int | None = None
    for date in dates:
        try:
            edition = fetch_edition(client, api, date)
        except httpx.HTTPError:
            continue
        previous = published_thumbnail(edition) if isinstance(edition, dict) else None
        if not previous:
            continue
        if previous == url:
            raise SystemExit(f"섬네일 게이트 실패 — {date} 에 이미 쓴 섬네일이다: {url}")
        if digest is None:
            digest = get_image_hash(client, url, hashes)
            if digest is None:
                return  # 새 섬네일을 못 내려받으면 그림 비교는 할 수 없다
        old = get_image_hash(client, previous, hashes)
        if old is not None and hamming_distance(digest, old) <= IMAGE_HASH_MAX_DISTANCE:
            raise SystemExit(f"섬네일 게이트 실패 — {date} 섬네일과 같은 그림이다 ({previous})")


def check_links_and_images(client: httpx.Client, body: dict[str, Any]) -> None:
    """링크·이미지 검증(verify_edition). FAIL 이 하나라도 있으면 POST 하지 않는다.

    스키마·커버·문구 게이트와 달리 이건 바깥 네트워크를 두드리므로 `--skip-link-check`
    를 둔다 — 네트워크가 없는 자리에서 발행해야 할 때뿐이고, 켜 두는 게 기본이다.
    확인이 안 되는 것(매체가 봇을 403 으로 막는 등)은 WARN 이라 발행을 막지 않는다.

    2026-09-21까지 이 저장소엔 이 호출 자체가 없었다 — push_edition 이 스키마만
    보고 그대로 POST 했다. 그날 카드 여러 장이 죽은 이미지·링크인 채로 발행됐다.
    """
    print("링크·이미지 검증:")
    report = check_edition(body, client)
    print_report(report)
    if not report.ok:
        raise SystemExit(
            f"링크·이미지 검증 실패 — 발행하지 않음 ({len(report.fails)}건). "
            "위 FAIL 을 고치고 다시 돌려라."
        )


def verify_published_images(client: httpx.Client, api: str, body: dict[str, Any]) -> None:
    """발행 직후 **실제로 서비스되는 이미지 프록시**(`/api/img/{date}/{num}`)를
    하나씩 두드려 200 이 오는지 확인한다.

    `check_links_and_images`(verify_edition)는 push **전**에 원본 매체 URL 만
    본다. 원본이 살아 있어도 이 서버의 `imgproxy.fetch_source` 가 그 원본에서
    막힐 수 있다 — 2026-09-21 실측: live.staticflickr.com 이 httpx 기본
    User-Agent 를 차단해 프록시가 502 를 냈는데, verify_edition 은 브라우저 UA 로
    원본을 확인하므로 이 차이를 못 잡았다. 그리고 push 전에는 이 날짜 에디션이
    서버에 아직 없어 프록시 경로 자체가 404 이므로, 반드시 push **뒤에** 실제
    서빙 경로를 두드려야 한다.

    문제가 있어도 발행을 되돌리지는 않는다(POST 는 이미 끝났다) — 대신 non-zero
    exit 으로 끝내 daily-cron.sh 의 실패 알림을 그대로 태운다. 사람이 media 를
    다른 그림으로 바꿔 재발행해야 한다.
    """
    date = body["meta"]["date"]
    problems: list[str] = []
    checked = 0
    for card in body.get("cards", []):
        media = card.get("media")
        image = (media or {}).get("image") or ""
        # 번들 asset stem(레퍼런스 fixture 가 쓰는 'fed-macro' 같은 것)은 프록시를
        # 거치지 않고 프론트가 그대로 쓴다 — imgproxy.resolve_card_image_url 과
        # 같은 조건이다. 원격 URL 이 아니면 확인할 프록시 경로 자체가 없다.
        if not image.startswith("http"):
            continue
        num = card["num"]
        checked += 1
        url = f"{api}/api/img/{date}/{num}?w=800"
        try:
            response = client.get(url, timeout=20.0)
        except httpx.HTTPError as exc:
            problems.append(f"[{num:02d}] 이미지 프록시 확인 불가({type(exc).__name__}): {url}")
            continue
        if response.is_error:
            problems.append(
                f"[{num:02d}] 이미지 프록시가 {response.status_code} 를 준다"
                f"(카드 이미지가 브라우저에서 깨져 보인다): {url}"
            )
        elif not response.headers.get("content-type", "").startswith("image/"):
            problems.append(
                f"[{num:02d}] 이미지 프록시가 이미지가 아닌 걸 준다"
                f"({response.headers.get('content-type')}): {url}"
            )
    if problems:
        joined = "\n".join(f"  - {p}" for p in problems)
        raise SystemExit(
            f"발행 후 이미지 프록시 확인 실패 — 발행은 이미 됐지만 카드 이미지가 깨져 "
            f"보인다 ({len(problems)}/{checked}건). media 를 다른 그림으로 바꿔 "
            f"재발행해라:\n{joined}"
        )
    print(f"발행 후 이미지 프록시 확인: {checked}장 전부 정상")


def push(client: httpx.Client, api: str, api_key: str, body: dict[str, Any]) -> dict[str, Any]:
    response = client.post(
        f"{api}/api/editions",
        json=body,
        headers={"Authorization": f"Bearer {api_key}"},
    )
    if response.is_error:
        raise SystemExit(f"발행 실패 ({response.status_code}): {response.text}")
    return response.json()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("edition_path", type=Path)
    parser.add_argument("--api", default=DEFAULT_API)
    parser.add_argument("--date", help="검증용: 파일의 meta.date와 일치해야 함")
    parser.add_argument(
        "--skip-link-check",
        action="store_true",
        help="링크·이미지 검증을 건너뛴다. 네트워크가 없을 때만 쓴다",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, client: httpx.Client | None = None) -> dict[str, Any]:
    args = parse_args(argv)
    content = order_cards_by_trend(load_and_validate(args.edition_path))
    check_cover_matches_date(content)
    check_wording(content)
    check_illustration_credit(content)
    check_card_images_not_ai(content)
    check_no_youtube_thumbnails(content)
    check_no_blocked_illustration_hosts(content)
    check_cards_have_media(content)
    check_news_cards_have_heat(content)
    check_og_image(content)

    if args.date and content.meta.date.isoformat() != args.date:
        raise SystemExit(f"meta.date({content.meta.date.isoformat()})가 --date({args.date})와 다름")

    api_key = load_admin_api_key()
    body = content.model_dump(mode="json")

    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=15.0)
    try:
        if args.skip_link_check:
            print("경고: --skip-link-check — 링크·이미지 검증을 건너뛴다", file=sys.stderr)
        else:
            check_links_and_images(client, body)
            check_og_image_not_reused(client, args.api, content)
        result = push(client, args.api, api_key, body)
        verify_published_images(client, args.api, result)
    finally:
        if owns_client:
            client.close()

    print(f"발행 완료: {result['meta']['date']} — {result['meta']['title']}")
    return result


if __name__ == "__main__":
    main()
