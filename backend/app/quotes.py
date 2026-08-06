"""표지에 매일 한 줄씩 나가는 오스트리아학파 인용구 풀과 선택 로직.

**인용구를 LLM이 매일 생성하지 않는 이유**: 인용구는 오귀속이 흔한 장르다. "미제스
인용구 하나 써줘"라고 하면 미제스가 하지 않은 말이 미제스 이름으로 발행되고, 그건
되돌릴 수 없다. 그래서 출처가 확인된 고정 풀에서 고른다.

`en`/`work`/`year`는 카드에 렌더하지 않지만 "이거 진짜 그 사람 말 맞나"를 나중에
확인할 근거로 파일에 남긴다. `portrait_*`도 같은 이유 — 초상 라이선스의 근거다.
"""

import datetime
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent / "data" / "austrian_quotes.json"


@dataclass(frozen=True)
class Quote:
    id: str
    ko: str
    en: str
    author: str
    work: str
    year: int
    #  번들 asset stem. None 이면 프론트가 이름을 조판한 아바타를 그린다.
    portrait: str | None = None
    #  초상을 넣었다면 어디서 왔고 어떤 라이선스인지 — 공개 사이트라 근거가 남아야 한다.
    portrait_source: str | None = None
    portrait_license: str | None = None


def load_pool(path: Path = DATA_FILE) -> tuple[Quote, ...]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    pool = tuple(Quote(**item) for item in raw)
    ids = [q.id for q in pool]
    if len(set(ids)) != len(ids):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        raise ValueError(f"인용구 id가 중복됐다: {dupes}")
    return pool


def pick_quote(
    pool: Sequence[Quote],
    recent_ids: Iterable[str],
    date: datetime.date,
) -> Quote:
    """아직 안 쓴 인용구 중 하나를 결정론적으로 고른다.

    `recent_ids`는 **최신 발행분부터** 나열한 id 목록이다(발행 목록 API가 주는 순서).
    같은 날 다시 돌려도 같은 결과가 나와야 재발행이 인용구를 바꾸지 않는다.

    중복 회피는 "안 쓴 것만 남긴다"에서 나오지, 인덱스 계산에서 나오지 않는다 —
    후보가 하루하루 줄어도 이미 쓴 id가 다시 뽑힐 일이 없다.
    """
    if not pool:
        raise ValueError("인용구 풀이 비었다")

    used = set(recent_ids)
    unused = [q for q in pool if q.id not in used]
    if unused:
        return unused[date.toordinal() % len(unused)]

    # 풀이 전부 소진됐다. 가장 오래전에 쓴 것부터 다시 쓴다 — 호출자가 로그를 남긴다.
    by_id = {q.id: q for q in pool}
    for quote_id in reversed(list(recent_ids)):
        if quote_id in by_id:
            return by_id[quote_id]
    return pool[date.toordinal() % len(pool)]


def is_exhausted(pool: Sequence[Quote], recent_ids: Iterable[str]) -> bool:
    """풀을 한 바퀴 다 돌았는가 — 호출자가 사용자에게 알릴지 판단한다."""
    used = set(recent_ids)
    return all(q.id in used for q in pool)


def as_cover_quote(quote: Quote) -> dict[str, str | None]:
    """에디션 콘텐츠에 실리는 형태. 렌더에 필요한 것만 남긴다.

    `id`는 렌더에 쓰이지 않지만 반드시 실어야 한다 — 다음 날 중복 회피가 발행된
    에디션에서 이 값을 되읽는다.
    """
    return {
        "id": quote.id,
        "text": quote.ko,
        "author": quote.author,
        "portrait": quote.portrait,
    }
