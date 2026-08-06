"""최근 발행분의 카드 목록을 한 화면짜리 요약으로 뽑는다 — 중복 편성 점검용.

카드 10장을 고르기 전에 "이 토픽이 최근에 몇 번 나갔나"를 봐야 하는데, 에디션
JSON을 통째로 읽으면 본문·Q&A까지 딸려와 컨텍스트만 잡아먹는다. 여기서는 날짜별
`num / chip / title / 매체`만 남긴다. 어떤 카드가 같은 사건인지 묶는 판단은
스크립트가 아니라 사람(Claude)이 SKILL.md 3.1의 기준으로 한다.

Usage: python scripts/recent_editions.py --api https://daily.onebitebitcoin.com
       python scripts/recent_editions.py --days 10 --before 2026-08-07
"""

import argparse
import datetime
import sys
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

BACKEND_ROOT = Path(__file__).resolve().parents[1]

# push_edition.py 와 같은 이유 — 직접 실행하면 sys.path[0] 이 scripts/ 다.
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

KST = ZoneInfo("Asia/Seoul")
DEFAULT_API = "http://localhost:8002"
DEFAULT_DAYS = 7


def fetch_dates(client: httpx.Client, api: str, before: datetime.date, days: int) -> list[str]:
    """발행 목록에서 `before` 직전 `days`일치 날짜를 최신순으로 고른다."""
    response = client.get(f"{api}/api/editions")
    if response.is_error:
        raise SystemExit(f"발행 목록 조회 실패 ({response.status_code}): {response.text}")
    dates = sorted(item["date"] for item in response.json() if item["date"] < before.isoformat())
    return list(reversed(dates[-days:]))


def fetch_edition(client: httpx.Client, api: str, date: str) -> dict[str, Any] | None:
    response = client.get(f"{api}/api/editions/{date}")
    if response.is_error:
        return None
    return response.json()


def outlet_of(card: dict[str, Any]) -> str:
    """link.label 에서 매체명만 남긴다 ("Cointelegraph 원문" -> "Cointelegraph")."""
    label = (card.get("link") or {}).get("label") or "-"
    for suffix in (" 원문", " 토론 보기", " 영상"):
        label = label.removesuffix(suffix)
    return label


def render(editions: list[tuple[str, dict[str, Any]]]) -> str:
    lines: list[str] = []
    chip_days: dict[str, set[str]] = {}
    chip_cards: dict[str, int] = {}

    for date, edition in editions:
        lines.append(f"--- {date} ---")
        for card in edition.get("cards") or []:
            chip = (card.get("chip") or {}).get("text") or "-"
            lines.append(
                f"  {card.get('num'):>2}. [{chip}] {card.get('title')}  ({outlet_of(card)})"
            )
            chip_days.setdefault(chip, set()).add(date)
            chip_cards[chip] = chip_cards.get(chip, 0) + 1

    lines.append("")
    lines.append(f"카테고리 빈도 ({len(editions)}일 / 카드 {sum(chip_cards.values())}장)")
    for chip, count in sorted(chip_cards.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"  {chip}: {count}장 / {len(chip_days[chip])}일")
    lines.append("")
    lines.append(
        "카테고리는 기계 집계다. 같은 사건인지는 제목을 읽고 판단해라 — SKILL.md 3.1 기준."
    )
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default=DEFAULT_API)
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument("--before", help="이 날짜 이전만 본다. 기본값: 오늘(Asia/Seoul)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, client: httpx.Client | None = None) -> str:
    args = parse_args(argv)
    before = (
        datetime.date.fromisoformat(args.before)
        if args.before
        else datetime.datetime.now(KST).date()
    )

    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=15.0)
    try:
        editions = [
            (date, edition)
            for date in fetch_dates(client, args.api, before, args.days)
            if (edition := fetch_edition(client, args.api, date)) is not None
        ]
    finally:
        if owns_client:
            client.close()

    if not editions:
        raise SystemExit(f"{before} 이전 발행분이 없다 — 중복 점검을 건너뛴다.")

    output = render(editions)
    print(output)
    return output


if __name__ == "__main__":
    main()
