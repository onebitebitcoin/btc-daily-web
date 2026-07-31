"""Fill each card's `qa` (3 예상 질문 + Google Search 그라운딩 답변) via Gemini.

카드 하나당 1콜 — Gemini Interactions API에 google_search 툴 + JSON 스키마 강제
(response_format)를 함께 요청해, 검색까지 마친 뒤 스키마에 맞는 질문/답변/출처를 한 번에
받는다. 실패한 카드는 qa=None으로 두고 계속 진행한다(발행 전체를 막지 않음) — 이미 qa가
있는 카드는 --force 없이는 건너뛴다(재발행 시 불필요한 과금 방지).

429(rate limit)와 5xx는 재시도하면 풀리는 일시적 오류로 보고 지수 백오프로 재시도한다
(Retry-After 헤더가 있으면 그 값을 우선한다). 그 외 오류(400/401, JSON 스키마 이탈 등)는
영구적인 오류로 보고 대기 없이 짧게만 재시도한다. 카드 사이에는 --delay 초만큼 쉬어가서
한꺼번에 몰아치지 않는다.

thinking_level=low — 실사용 비교(기본 vs low, 같은 카드) 결과 답변 품질 차이 없이 토큰
소모만 78% 줄어(thought 토큰이 대부분이라 output 토큰은 거의 그대로) 기본값으로 채택.

Usage: python scripts/generate_qa.py drafts/edition-2026-07-31.json
       python scripts/generate_qa.py drafts/edition-2026-07-31.json --force
       python scripts/generate_qa.py drafts/edition-2026-07-31.json --delay 5
"""

import argparse
import json
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = BACKEND_ROOT / ".env"
API_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
MODEL = "gemini-3.6-flash"

QUESTIONS_PER_CARD = 3

# 카드 사이 기본 대기시간(초) — 짧은 시간에 콜을 몰아 429를 유발하지 않도록. --delay로 조정.
CARD_DELAY_SECONDS = 3.0

# Retry-After 헤더가 없을 때 쓰는 429/5xx 재시도 간격(초). 길이 3 = 최초 시도 포함 총 4번 시도.
RETRYABLE_BACKOFF_SECONDS = (5.0, 15.0, 45.0)
# 400/401, JSON 스키마 이탈 등 영구적 오류는 대기 없이 이 횟수만큼만 빠르게 재시도한다.
NON_RETRYABLE_ATTEMPTS = 2

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "minItems": QUESTIONS_PER_CARD,
            "maxItems": QUESTIONS_PER_CARD,
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "answer": {"type": "string"},
                    "sources": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["question", "answer", "sources"],
            },
        }
    },
    "required": ["questions"],
}


def load_env_value(key: str) -> str:
    if not ENV_FILE.exists():
        raise SystemExit(f"{ENV_FILE} 없음 — {key}를 설정하라.")
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        if name.strip() == key and value.strip():
            return value.strip()
    raise SystemExit(f"{ENV_FILE}에 {key} 없음.")


def build_prompt(card: dict[str, Any]) -> str:
    return (
        "다음은 비트코인 데일리 카드뉴스 한 장의 내용이다.\n\n"
        f"제목: {card['title']}\n"
        f"부제: {card.get('subtitle') or ''}\n"
        f"본문: {card['body']}\n\n"
        "독자가 이 카드를 읽고 궁금해할 만한 질문 3개를 한국어로 만들고, 각 질문을 "
        "구글 검색으로 최신 정보를 찾아 답하라. 답은 사실에 근거해 2~3문장으로, "
        "추측이나 과장 없이 작성하라."
    )


def fetch_qa(client: httpx.Client, api_key: str, card: dict[str, Any]) -> list[dict[str, Any]]:
    response = client.post(
        API_URL,
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        json={
            "model": MODEL,
            "input": build_prompt(card),
            "tools": [{"type": "google_search"}],
            "response_format": {
                "type": "text",
                "mime_type": "application/json",
                "schema": RESPONSE_SCHEMA,
            },
            "generation_config": {"thinking_level": "low"},
        },
    )
    response.raise_for_status()
    data = response.json()

    for step in data.get("steps", []):
        if step.get("type") != "model_output":
            continue
        for block in step.get("content", []):
            if block.get("type") == "text":
                parsed = json.loads(_strip_code_fence(block["text"]))
                questions = parsed["questions"]
                if len(questions) != QUESTIONS_PER_CARD:
                    raise ValueError(f"질문 {len(questions)}개 반환 (기대: {QUESTIONS_PER_CARD})")
                return questions

    raise ValueError("응답에서 model_output 텍스트를 찾지 못함")


def _strip_code_fence(text: str) -> str:
    """response_format 을 줬는데도 가끔 ```json 코드펜스로 감싸서 돌아온다."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.removesuffix("```").strip()
        if text.startswith("json"):
            text = text[len("json") :].strip()
    return text


def _is_retryable_status(status_code: int) -> bool:
    """429(rate limit) 또는 5xx — 시간을 두면 풀리는 일시적 오류."""
    return status_code == 429 or status_code >= 500


def _retry_after_seconds(exc: httpx.HTTPStatusError) -> float | None:
    value = exc.response.headers.get("Retry-After")
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _fetch_qa_with_retry(
    client: httpx.Client,
    api_key: str,
    card: dict[str, Any],
    sleep: Callable[[float], None],
) -> tuple[list[dict[str, Any]] | None, Exception | None, bool]:
    """카드 하나에 대해 재시도(+백오프)까지 포함해 fetch_qa를 실행한다.

    반환값은 (qa, error, rate_limited) — 성공하면 error가 None, 실패하면 qa가 None이다.
    rate_limited는 실패 원인이 429/5xx 재시도 소진인지를 나타낸다.
    """
    retryable_attempts = 0
    non_retryable_attempts = 0
    was_rate_limited = False
    while True:
        try:
            return fetch_qa(client, api_key, card), None, was_rate_limited
        except httpx.HTTPStatusError as exc:
            if _is_retryable_status(exc.response.status_code):
                was_rate_limited = True
                retryable_attempts += 1
                if retryable_attempts >= len(RETRYABLE_BACKOFF_SECONDS) + 1:
                    return None, exc, was_rate_limited
                retry_after = _retry_after_seconds(exc)
                wait = (
                    retry_after
                    if retry_after is not None
                    else RETRYABLE_BACKOFF_SECONDS[retryable_attempts - 1]
                )
                sleep(wait)
                continue
            # 400/401 등 영구적 오류 — 대기 없이 빠르게만 재시도
            non_retryable_attempts += 1
            if non_retryable_attempts >= NON_RETRYABLE_ATTEMPTS:
                return None, exc, was_rate_limited
        except (httpx.HTTPError, ValueError, KeyError, json.JSONDecodeError) as exc:
            # 코드펜스/스키마 이탈, 연결 오류 등 — 대기 없이 빠르게만 재시도
            non_retryable_attempts += 1
            if non_retryable_attempts >= NON_RETRYABLE_ATTEMPTS:
                return None, exc, was_rate_limited


def fill_edition(
    edition: dict[str, Any],
    client: httpx.Client,
    api_key: str,
    force: bool,
    *,
    card_delay: float = CARD_DELAY_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[int, int, int]:
    """Returns (성공 수, 실패 수, 실패 중 rate-limit 재시도 소진으로 인한 수)."""
    ok = 0
    failed = 0
    rate_limited = 0
    cards_to_fill = [card for card in edition["cards"] if force or not card.get("qa")]
    for i, card in enumerate(cards_to_fill):
        if i > 0:
            sleep(card_delay)
        qa, exc, was_rate_limited = _fetch_qa_with_retry(client, api_key, card, sleep)
        if exc is None:
            card["qa"] = qa
            ok += 1
        else:
            card["qa"] = None
            failed += 1
            if was_rate_limited:
                rate_limited += 1
            print(f"  카드 {card.get('num')} 실패: {exc}", file=sys.stderr)
    return ok, failed, rate_limited


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("edition_path", type=Path)
    parser.add_argument("--force", action="store_true", help="이미 qa 있는 카드도 재생성")
    parser.add_argument(
        "--delay",
        type=float,
        default=CARD_DELAY_SECONDS,
        help=f"카드 사이 대기시간(초, 기본 {CARD_DELAY_SECONDS})",
    )
    return parser.parse_args(argv)


def main(
    argv: list[str] | None = None,
    client: httpx.Client | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> Path:
    args = parse_args(argv)
    api_key = load_env_value("GEMINI_API_KEY")
    edition = json.loads(args.edition_path.read_text(encoding="utf-8"))

    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=60.0)
    try:
        ok, failed, rate_limited = fill_edition(
            edition, client, api_key, args.force, card_delay=args.delay, sleep=sleep
        )
    finally:
        if owns_client:
            client.close()

    args.edition_path.write_text(
        json.dumps(edition, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Q&A 생성: 성공 {ok} / 실패 {failed} (전체 {len(edition['cards'])}장)")
    if rate_limited:
        print(
            f"  참고: 실패 {rate_limited}건은 API 레이트 리밋(429) 재시도 소진 — "
            "시간을 두고 재실행 권장"
        )
    return args.edition_path


if __name__ == "__main__":
    main()
