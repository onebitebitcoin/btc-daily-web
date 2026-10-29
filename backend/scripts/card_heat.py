"""카드마다 24시간 화제성(`heat`)을 세어 에디션 JSON 에 써 넣는다.

`trend_rank` 는 태그 토픽 상위 10개에 걸린 카드만 받는다. 그런데 트렌딩 상위가 알트·
정책 태그로 채워지는 날에는 비트코인 카드 대부분이 어느 토픽에도 안 걸린다
(2026-10-29: 10장 중 2장만 막대가 그려졌다). 그래서 카드 사건을 검색어로 정의해
트렌딩과 **같은 코퍼스·같은 공식**(`app.trending.score_terms`)으로 따로 잰다.

검색어 파일은 카드 번호 → 그 사건을 가리키는 말 목록이다. 한글·영문 표기를 함께
넣는다. "비트코인"처럼 모든 글에 나오는 말은 거부된다.

    {"1": ["FOMC", "연준", "금리 동결", "Fed"],
     "2": ["국부펀드", "sovereign", "헤지펀드"],
     ...}

Usage:
    python scripts/card_heat.py ../drafts/edition-2026-10-29.json \
        --terms ../drafts/heat-terms-2026-10-29.json
"""

import argparse
import datetime
import json
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.trending import KST, score_terms  # noqa: E402  (sys.path 조정 후여야 함)

# 뉴스 카드 장수. 이 뒤의 고정 꼭지(지식 한입)는 그날 사건이 아니라 화제성을 재지 않는다.
NEWS_CARD_COUNT = 10


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"{path} 읽기 실패: {exc}") from exc


def window_end(draft: dict[str, Any], date_iso: str) -> datetime.datetime:
    """코퍼스를 모은 시각 — 최근성 가중(6h·12h)의 기준. draft 에 없으면 발행일 06:00 KST."""
    stamp = (draft.get("trending_pool") or {}).get("window_end")
    if stamp:
        return datetime.datetime.fromisoformat(stamp)
    day = datetime.date.fromisoformat(date_iso)
    return datetime.datetime.combine(day, datetime.time(6, 0), tzinfo=KST)


def compute_heats(
    edition: dict[str, Any],
    draft: dict[str, Any],
    terms: dict[str, list[str]],
    now: datetime.datetime,
) -> dict[int, dict[str, Any]]:
    """카드 번호 → score_terms 결과 + 정규화한 heat(0~100)."""
    pool = draft.get("trending_pool")
    if not pool:
        raise SystemExit(
            "draft 에 trending_pool 이 없다 — 최신 collect_daily.py 로 draft 를 다시 만들어라"
        )
    candidates = draft.get("trending_candidates") or []
    if not candidates:
        raise SystemExit("draft 에 trending_candidates 가 없어 기준(1위 점수)을 못 잡는다")
    top_score = float(candidates[0]["score"])

    news_nums = [c["num"] for c in edition["cards"] if c["num"] <= NEWS_CARD_COUNT]
    missing = [n for n in news_nums if not terms.get(str(n))]
    if missing:
        raise SystemExit(f"검색어가 없는 카드: {missing} — 모든 뉴스 카드에 검색어를 넣어라")

    result: dict[int, dict[str, Any]] = {}
    for num in news_nums:
        try:
            signal = score_terms(
                terms[str(num)], pool["news"], pool["videos"], now, pool.get("tweets")
            )
        except ValueError as exc:
            raise SystemExit(f"카드 {num}: {exc}") from exc
        heat = min(100, round(100 * signal["score"] / top_score)) if top_score > 0 else 0
        result[num] = {**signal, "heat": heat}
    return result


def apply_heats(edition: dict[str, Any], heats: dict[int, dict[str, Any]]) -> dict[str, Any]:
    cards = [
        {
            **card,
            "heat": {
                "score": heats[card["num"]]["heat"],
                "mentions": heats[card["num"]]["mentions"],
                "sources": heats[card["num"]]["sources"],
            },
        }
        if card["num"] in heats
        else card
        for card in edition["cards"]
    ]
    return {**edition, "cards": cards}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("edition", type=Path)
    parser.add_argument("--terms", type=Path, required=True)
    parser.add_argument("--draft", type=Path, help="기본값: drafts/draft-<meta.date>.json")
    args = parser.parse_args(argv)

    edition = load_json(args.edition)
    date_iso = edition["meta"]["date"]
    draft_path = args.draft or REPO_ROOT / "drafts" / f"draft-{date_iso}.json"
    draft = load_json(draft_path)
    heats = compute_heats(edition, draft, load_json(args.terms), window_end(draft, date_iso))

    for num, h in sorted(heats.items()):
        print(
            f"카드 {num}: heat {h['heat']} · {h['mentions']}건 {h['sources']}매체"
            f" · X {h['tweet_mentions']}"
        )
        for title in h["titles"][:3]:
            print(f"    - {title}")
    zero = [num for num, h in heats.items() if h["mentions"] == 0]
    if zero:
        print(
            f"경고: 코퍼스에서 한 건도 안 걸린 카드 {zero} — 검색어가 너무 좁지 않은지 보라",
            file=sys.stderr,
        )

    args.edition.write_text(
        json.dumps(apply_heats(edition, heats), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {args.edition}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
