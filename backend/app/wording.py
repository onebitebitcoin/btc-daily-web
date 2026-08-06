"""발행 직전 문구 게이트 — `CONTENT_CONTRACT.md` 2.1(어미)·2.2(표기 용어집)를 코드로 강제한다.

같은 실수가 매일 재발하는 걸 막는 게 목적이다. 사람이 쓴 문구를 사람이 검토하면
"오늘은 통과"가 반복되지만, 표에 한 줄 적어두면 다음 발행부터 자동으로 걸린다.
(계기: 2026-08-07 발행분이 Galaxy를 "갈럭시"로 내보냈다.)

여기서 잡는 건 **표에 적힌 것뿐이다.** 오역이나 어색한 음차처럼 판단이 필요한 문제는
잡지 못한다 — 그건 리뷰 에이전트(2층)의 몫이다.

계약 발효일 이전 발행분은 검사하지 않는다. 07-27~08-06 에디션은 평서체로 나갔고
제목에 "BTC"를 쓴 것도 있어서, 소급 적용하면 오타 하나 고치려는 재발행이 막힌다.
"""

import datetime
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # 런타임 임포트는 순환을 만든다 (schemas -> wording 방향이 열려 있어야 함)
    from app.schemas import EditionContent

# CONTENT_CONTRACT.md 2.1·2.2가 발효된 날. 이 날짜 이전 meta.date는 통과시킨다.
EFFECTIVE_DATE = datetime.date(2026, 8, 7)

# 쓰면 안 되는 표기 -> 써야 하는 표기. CONTENT_CONTRACT.md 2.2와 같은 내용을 유지한다.
BANNED_TERMS: dict[str, str] = {
    "갈럭시": "갤럭시",
}

# 한국어 문장 안의 "BTC" 금지 (프로젝트 CLAUDE.md 규칙). 단어 경계를 봐야
# "BTCUSD" 같은 티커나 소문자 slug("btc-daily-0807")를 오탐하지 않는다.
BTC_TOKEN = re.compile(r"(?<![A-Za-z])BTC(?![A-Za-z])")

# 했습니다체 판정. "니다로 끝나는가"만 보면 **평서체 "아니다"가 통과한다** — 아/니/다도
# "니다"로 끝나기 때문이다. 진짜 구분점은 "니다" 앞 음절의 종성이 ㅂ인지다:
#   입니다(입) · 습니다(습) · 탑니다(탑) · 아닙니다(닙) · 기댑니다(댑)  -> 종성 ㅂ
#   아니다(아)                                                        -> 종성 없음
_HANGUL_FIRST, _HANGUL_LAST = "가", "힣"
_JONGSEONG_COUNT = 28
_JONGSEONG_BIEUP = 17
_TRAILING_PUNCT = ".!?…\"'”’)"


def is_polite_ending(text: str) -> bool:
    stripped = text.strip().rstrip(_TRAILING_PUNCT)
    if len(stripped) < 3 or not stripped.endswith("니다"):
        return False
    stem = stripped[-3]
    if not (_HANGUL_FIRST <= stem <= _HANGUL_LAST):
        return False
    return (ord(stem) - ord(_HANGUL_FIRST)) % _JONGSEONG_COUNT == _JONGSEONG_BIEUP


def _check_text(where: str, text: str | None, problems: list[str]) -> None:
    """한국어로 노출되는 문구 하나를 용어집에 걸어본다."""
    if not text:
        return
    for banned, correct in BANNED_TERMS.items():
        if banned in text:
            problems.append(f"{where}: '{banned}' -> '{correct}' 로 고쳐라 ({text.strip()!r})")
    if BTC_TOKEN.search(text):
        problems.append(f"{where}: 한국어 문구에 'BTC' 금지 -> '비트코인' ({text.strip()!r})")


def _check_ending(where: str, text: str | None, problems: list[str]) -> None:
    if text and not is_polite_ending(text):
        problems.append(f"{where}: 했습니다체가 아니다 (…{text.strip()[-16:]!r})")


def find_problems(content: "EditionContent") -> list[str]:
    """문구 규칙 위반 목록. 비어 있으면 통과다.

    검사 대상은 **Claude가 쓴 한국어 문구**로 한정한다. 전부가 영문인 `subtitle`,
    매체명인 `link.label`, 기사 원제를 그대로 옮기는 `trending.items[].links[].title`
    은 제외한다 — 원제를 다듬는 건 계약이 금지한 행위라 여기서 걸면 안 된다.
    """
    if content.meta.date < EFFECTIVE_DATE:
        return []

    problems: list[str] = []
    for card in content.cards:
        at = f"카드 {card.num}"
        _check_text(f"{at} title", card.title, problems)
        _check_text(f"{at} body", card.body, problems)
        _check_text(f"{at} quote", card.quote, problems)
        _check_text(f"{at} chip.text", card.chip.text, problems)
        for i, chip in enumerate(card.chips, 1):
            _check_text(f"{at} chips[{i}]", chip, problems)
        _check_ending(f"{at} body", card.body, problems)
        _check_ending(f"{at} quote", card.quote, problems)
        for i, qa in enumerate(card.qa or [], 1):
            _check_text(f"{at} qa[{i}].answer", qa.answer, problems)
            _check_ending(f"{at} qa[{i}].answer", qa.answer, problems)

    for item in (content.trending.items if content.trending else []):
        _check_text(f"트렌딩 {item.rank}위 topic", item.topic, problems)

    return problems
