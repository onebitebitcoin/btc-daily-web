"""Validate a finished edition JSON locally, then POST it to /api/editions.

Local validation reuses the same pydantic schema the API enforces, so a bad
field fails here with a clear message instead of round-tripping a 422.

Usage: python scripts/push_edition.py drafts/edition-2026-07-30.json
       python scripts/push_edition.py drafts/edition-2026-07-30.json --date 2026-07-30
"""

import argparse
import json
import sys
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
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, client: httpx.Client | None = None) -> dict[str, Any]:
    args = parse_args(argv)
    content = load_and_validate(args.edition_path)
    check_cover_matches_date(content)
    check_wording(content)

    if args.date and content.meta.date.isoformat() != args.date:
        raise SystemExit(
            f"meta.date({content.meta.date.isoformat()})가 --date({args.date})와 다름"
        )

    api_key = load_admin_api_key()
    body = content.model_dump(mode="json")

    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=10.0)
    try:
        result = push(client, args.api, api_key, body)
    finally:
        if owns_client:
            client.close()

    print(f"발행 완료: {result['meta']['date']} — {result['meta']['title']}")
    return result


if __name__ == "__main__":
    main()
