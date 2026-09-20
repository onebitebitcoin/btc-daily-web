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
from scripts.collect_daily import apply_date_to_cover  # noqa: E402
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
        raise SystemExit(
            f"삽화 출처 게이트 실패 — 발행하지 않음 ({len(problems)}건):\n{joined}"
        )


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
    content = load_and_validate(args.edition_path)
    check_cover_matches_date(content)
    check_wording(content)
    check_illustration_credit(content)

    if args.date and content.meta.date.isoformat() != args.date:
        raise SystemExit(
            f"meta.date({content.meta.date.isoformat()})가 --date({args.date})와 다름"
        )

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
        result = push(client, args.api, api_key, body)
        verify_published_images(client, args.api, result)
    finally:
        if owns_client:
            client.close()

    print(f"발행 완료: {result['meta']['date']} — {result['meta']['title']}")
    return result


if __name__ == "__main__":
    main()
