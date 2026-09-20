"""발행 직전 링크·이미지 검증 — 손으로 하던 눈검사를 기계가 먼저 훑는다.

2026-08-26 발행분에서 실제로 새어 나간 것들이 이 스크립트의 이유다.

- 링크가 매체 **홈페이지**였다(카드 4장). googlenews 경유 후보의 리디렉션 주소를
  쓸 수 없으니 도메인만 남겨둔 것이다.
- 링크가 **404** 였다(코인텔레그래프). my-news 가 준 주소가 죽어 있었다.
- 링크한 기사가 **다른 매체 것**이었다(라벨은 알파경제, 기사는 TechCrunch).
- 카드 1번과 3번이 **같은 이미지**를 썼다(토큰포스트가 브랜드 렌더를 돌려 쓴다).
  표지가 1번을 쓰므로 한 화면에 같은 그림이 세 번 나왔다.

기계가 가릴 수 있는 것만 본다. **이미지가 기사에 맞는지는 여전히 사람이 봐야 한다** —
`og:image` 는 매체가 붙인 것이라 출처는 맞지만 재탕 표지나 무관한 삽화일 수 있다.
그건 SKILL.md 7절의 눈검사 항목으로 남겨 뒀다.

FAIL 과 WARN 을 나눈 건 매체가 봇을 403 으로 막는 일이 흔해서다. 확실히 틀린 것만
FAIL 로 막고(죽은 링크·홈페이지·리디렉션·중복 이미지), 확인 불가는 WARN 으로 띄운다 —
확인 불가로 06:00 배치를 죽이면 손해가 더 크다.

Usage: python scripts/verify_edition.py ../drafts/edition-2026-08-26.json
       python scripts/verify_edition.py --api http://localhost:8003 --date 2026-08-26
"""

import argparse
import json
import re
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

BACKEND_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.collect_daily import (  # noqa: E402  (sys.path 조정 후여야 함)
    _SOURCE_REQUEST,
    GOOGLE_NEWS_ARTICLE,
    IMAGE_HASH_MAX_DISTANCE,
    SOURCE_ENRICH_WORKERS,
    average_hash,
    hamming_distance,
)

# ai-daily-web 에서 이식했다(2026-09-21) — 이 저장소엔 verify_edition 자체가
# 없어서 push_edition 이 링크·이미지를 하나도 검증하지 않고 있었다. 그날 카드
# 4장이 이미지 프록시 502로 깨진 채 발행됐는데, 검증이 있었어도 그 사고 자체는
# (원본은 살아 있고 서버의 fetch_source 만 막힌 경우라) 여기서는 못 잡았을 것이다
# — 그건 push_edition.verify_published_images 가 잡는 자리다. 이 스크립트는
# "원본 자체가 죽었거나 링크가 어긋난" 사고를 잡는다.
#
# 이 프로젝트는 프로덕션이 도메인 루트를 그대로 쓴다(서브패스 전환 대상이 아니다).
DEFAULT_API = "http://localhost:8002"
# 매체가 봇을 막아 확인만 못 한 경우. 링크가 진짜 죽은 것과 구분해 WARN 으로 둔다.
BLOCKED_STATUSES = frozenset({401, 403, 405, 429})
_TITLE_TAG = re.compile(
    r"""<meta[^>]+property=["']og:title["'][^>]*content=["']([^"']+)""", re.IGNORECASE
)
_TITLE_FALLBACK = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_WORD = re.compile(r"[가-힣]{2,}|[a-z]{3,}")
_HANGUL = re.compile(r"[가-힣]")


@dataclass
class Report:
    """카드별 점검 결과 모음. fails 가 비어 있어야 발행한다."""

    fails: list[str] = field(default_factory=list)
    warns: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.fails

    def merge(self, other: "Report") -> None:
        self.fails.extend(other.fails)
        self.warns.extend(other.warns)
        self.notes.extend(other.notes)


def _words(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def article_title(html: str) -> str | None:
    """기사 페이지에서 사람이 눈으로 대조할 제목을 뽑는다."""
    found = _TITLE_TAG.search(html) or _TITLE_FALLBACK.search(html)
    if not found:
        return None
    return re.sub(r"\s+", " ", found.group(1)).strip() or None


def check_link(client: httpx.Client, num: int, card: dict[str, Any]) -> Report:
    """카드의 원문 링크가 살아 있고, 그 기사가 이 카드의 기사인지 본다."""
    report = Report()
    link = card.get("link") or {}
    href = str(link.get("href") or "")
    label = str(link.get("label") or "")
    if not href:
        report.fails.append(f"[{num:02d}] link.href 가 비었다")
        return report

    if href.startswith(GOOGLE_NEWS_ARTICLE):
        report.fails.append(
            f"[{num:02d}] 링크가 구글 뉴스 리디렉션이다 — 후보의 복원된 url 을 써라: {href[:60]}"
        )
        return report

    if not href.startswith(("http://", "https://")):
        report.fails.append(f"[{num:02d}] 링크가 절대 URL 이 아니다: {href[:60]}")
        return report

    parsed = urllib.parse.urlparse(href)
    if parsed.path.strip("/") == "" and not parsed.query:
        report.fails.append(
            f"[{num:02d}] 링크가 매체 홈페이지다 — 기사 주소를 넣어라: {href}"
        )
        return report

    try:
        response = client.get(href, **_SOURCE_REQUEST)
    except httpx.HTTPError as exc:
        report.warns.append(
            f"[{num:02d}] 링크 확인 불가({type(exc).__name__}) — 눈으로 열어봐라: {href}"
        )
        return report

    if response.status_code in BLOCKED_STATUSES:
        report.warns.append(
            f"[{num:02d}] 매체가 확인을 막았다({response.status_code}) — "
            f"브라우저로 열어 확인해라: {href}"
        )
        return report
    if response.is_error:
        report.fails.append(f"[{num:02d}] 링크가 죽었다({response.status_code}): {href}")
        return report

    title = article_title(response.text)
    if title is None:
        report.warns.append(f"[{num:02d}] 원문 제목을 못 읽었다 — 눈으로 대조해라: {href}")
        return report

    report.notes.append(f"[{num:02d}] {label} → {title[:70]}")
    card_words = _words(str(card.get("title") or "")) | _words(" ".join(card.get("chips") or []))
    title_words = _words(title)
    # 카드는 한국어, 원문이 영문이면 낱말이 겹칠 리가 없다 — 표기 사전 없이는 못 재니
    # 아예 묻지 않는다. 대신 위 notes 줄에 원문 제목을 적어 사람이 대조하게 한다.
    cross_language = _HANGUL.search(" ".join(card_words)) and not _HANGUL.search(title)
    if card_words and not cross_language and not (card_words & title_words):
        report.warns.append(
            f"[{num:02d}] 카드 제목과 원문 제목에 겹치는 낱말이 없다 — 다른 기사를 링크한 건 "
            f"아닌지 확인해라.\n        카드: {card.get('title')}\n        원문: {title[:70]}"
        )
    return report


def check_image(client: httpx.Client, num: int, card: dict[str, Any]) -> tuple[Report, int | None]:
    """이미지가 실제로 이미지로 내려오는지 보고, 중복 판정용 해시를 같이 돌려준다."""
    report = Report()
    media = card.get("media")
    if not media or not media.get("image"):
        report.warns.append(f"[{num:02d}] 이미지가 없다 — 기본 아트로 나간다")
        return report, None

    url = str(media["image"])
    if not url.startswith(("http://", "https://")):
        # 프론트 번들 asset stem(레퍼런스 fixture 가 쓰는 'fed-macro' 같은 것)이다.
        # 발행분에는 매체 원문 이미지의 절대 URL 이 들어가야 한다.
        report.warns.append(
            f"[{num:02d}] 이미지가 절대 URL 이 아니다 — 번들 asset stem?: {url[:40]}"
        )
        return report, None

    try:
        response = client.get(url, **_SOURCE_REQUEST)
    except httpx.HTTPError as exc:
        report.warns.append(f"[{num:02d}] 이미지 확인 불가({type(exc).__name__}): {url[:70]}")
        return report, None

    if response.status_code in BLOCKED_STATUSES:
        report.warns.append(
            f"[{num:02d}] 매체가 이미지 확인을 막았다({response.status_code}) — "
            f"카드가 뜨는지 브라우저로 봐라: {url[:70]}"
        )
        return report, None
    if response.is_error:
        report.fails.append(f"[{num:02d}] 이미지가 죽었다({response.status_code}): {url[:70]}")
        return report, None
    if not response.headers.get("content-type", "").startswith("image/"):
        report.fails.append(
            f"[{num:02d}] 이미지 주소가 이미지를 안 준다"
            f"({response.headers.get('content-type')}): {url[:70]}"
        )
        return report, None

    return report, average_hash(response.content)


def check_duplicate_images(
    hashes: dict[int, int | None], images: dict[int, str | None]
) -> Report:
    """한 에디션 안에서 같은 그림이 두 번 나가는 걸 막는다.

    표지가 1번 카드 이미지를 쓰므로, 1번과 겹치면 한 화면에 세 번 나온다.
    문자열이 달라도(같은 그림 다른 주소) 잡히도록 average hash 로 본다.
    """
    report = Report()
    nums = sorted(hashes)
    for i, left in enumerate(nums):
        for right in nums[i + 1 :]:
            same_url = images.get(left) and images[left] == images[right]
            a, b = hashes[left], hashes[right]
            same_image = a is not None and b is not None and (
                hamming_distance(a, b) <= IMAGE_HASH_MAX_DISTANCE
            )
            if same_url or same_image:
                report.fails.append(
                    f"[{left:02d}]·[{right:02d}] 두 카드가 같은 이미지를 쓴다 — "
                    "한쪽을 사건 클러스터의 다른 매체 사진으로 바꿔라"
                )
    return report


def check_sources(content: dict[str, Any]) -> Report:
    """closing.sources 가 카드에 실제로 링크한 매체와 맞는지 본다.

    사람이 손으로 유지하는 목록(수집기는 후보 전체 매체를 넣어 주고, 카드를 고른
    뒤 쓴 것만 남긴다)이라 카드 출처를 바꾸면 조용히 어긋난다 — 실측: 카드 10번
    링크를 알파경제에서 TechCrunch 로 고쳤는데 sources 는 알파경제 그대로였다.

    라벨은 "<매체명> 원문"/"<채널명> 영상" 처럼 접미사가 붙으므로 포함 관계로 본다.
    """
    report = Report()
    sources = [str(name) for name in (content.get("closing") or {}).get("sources") or []]
    labels = [
        str((card.get("link") or {}).get("label") or "")
        for card in content.get("cards") or []
    ]
    labels = [label for label in labels if label]
    if not sources or not labels:
        return report

    for name in sources:
        if not any(name in label for label in labels):
            report.fails.append(
                f"closing.sources 의 '{name}' 을(를) 링크한 카드가 없다 — "
                "카드 출처를 바꾸고 목록을 안 고쳤는지 확인해라"
            )
    for label in labels:
        if not any(name in label for name in sources):
            report.fails.append(
                f"'{label}' 이 closing.sources 에 없다 — 출처 목록에 추가해라"
            )
    return report


def check_edition(content: dict[str, Any], client: httpx.Client) -> Report:
    """에디션 하나를 통째로 점검한다. 반환 Report 의 fails 가 비어야 발행한다."""
    cards = content.get("cards") or []
    report = Report()
    hashes: dict[int, int | None] = {}
    images: dict[int, str | None] = {}

    def one(card: dict[str, Any]) -> tuple[int, Report, int | None, str | None]:
        num = int(card.get("num") or 0)
        card_report = check_link(client, num, card)
        image_report, digest = check_image(client, num, card)
        card_report.merge(image_report)
        media = card.get("media") or {}
        return num, card_report, digest, media.get("image")

    with ThreadPoolExecutor(max_workers=max(1, SOURCE_ENRICH_WORKERS)) as pool:
        results = sorted(pool.map(one, cards), key=lambda row: row[0])

    for num, card_report, digest, image in results:
        report.merge(card_report)
        if image:
            hashes[num] = digest
            images[num] = image

    report.merge(check_duplicate_images(hashes, images))
    report.merge(check_sources(content))
    return report


def print_report(report: Report) -> None:
    for note in report.notes:
        print(f"  {note}")
    for warn in report.warns:
        print(f"  WARN {warn}")
    for fail in report.fails:
        print(f"  FAIL {fail}")
    print(
        f"검증: FAIL {len(report.fails)}건 · WARN {len(report.warns)}건 "
        f"({len(report.notes)}개 카드의 원문 제목을 위에 적었다 — 눈으로 대조해라)"
    )


def load_content(args: argparse.Namespace, client: httpx.Client) -> dict[str, Any]:
    if args.edition_path:
        try:
            return json.loads(args.edition_path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise SystemExit(f"{args.edition_path} 읽기 실패: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{args.edition_path} JSON 파싱 실패: {exc}") from exc
    if not args.date:
        raise SystemExit("파일 경로나 --date 중 하나는 있어야 한다.")
    response = client.get(f"{args.api}/api/editions/{args.date}")
    if response.is_error:
        raise SystemExit(f"{args.date} 에디션 조회 실패 ({response.status_code})")
    return response.json()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("edition_path", type=Path, nargs="?")
    parser.add_argument("--api", default=DEFAULT_API)
    parser.add_argument("--date", help="파일 대신 발행된 에디션을 검증한다")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, client: httpx.Client | None = None) -> Report:
    args = parse_args(argv)
    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=15.0)
    try:
        content = load_content(args, client)
        report = check_edition(content, client)
    finally:
        if owns_client:
            client.close()
    print_report(report)
    if not report.ok:
        raise SystemExit(1)
    return report


if __name__ == "__main__":
    main()
