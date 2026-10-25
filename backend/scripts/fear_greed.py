"""공포·탐욕 지수 카드에 붙일 계기판 그림 URL 을 만든다.

지수 카드에는 기사 사진이 없거나 무관한 사진(모형 동전 등)이 붙는다. 그래서 백엔드
`/api/gauge/fear-greed.png` 가 값을 받아 계기판을 그린다(`app/gauge.py`). 이 스크립트는
그날 값을 alternative.me 에서 조회해 그 URL 을 찍어 준다.

**카드 본문이 인용한 값과 그림의 값이 같아야 한다.** 매체마다 산출처가 다르다
(2026-10-24: EBN 기사는 46, 같은 날 alternative.me 는 51). 기사 값을 인용했으면
`--value` 로 그 값을 넣고, 본문에 값이 없으면 조회값을 쓰되 본문에도 그 값을 적어라.

Usage:
    python scripts/fear_greed.py --date 2026-10-24
    python scripts/fear_greed.py --value 46 --date 2026-10-24
"""

import argparse
import datetime
import json
import sys
import urllib.parse
import urllib.request

API = "https://api.alternative.me/fng/"
SITE = "https://daily.onebitebitcoin.com"
UA = "daily-cardnews/1.0 (fear-greed gauge)"
LOOKBACK_DAYS = 30


def fetch_value(date: datetime.date) -> int:
    """alternative.me 에서 `date` 의 지수 값을 찾는다. 없으면 LookupError."""
    url = f"{API}?limit={LOOKBACK_DAYS}&date_format=kr"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=10) as resp:
        payload = json.load(resp)
    for row in payload.get("data") or []:
        if row.get("timestamp") == date.isoformat():
            return int(row["value"])
    raise LookupError(f"alternative.me 에 {date.isoformat()} 값이 없다")


def gauge_url(value: int, date: datetime.date, site: str = SITE) -> str:
    query = urllib.parse.urlencode({"value": value, "date": date.isoformat()})
    return f"{site}/api/gauge/fear-greed.png?{query}"


def credit(source: str) -> str:
    return f"공포·탐욕 지수 계기판 · 자체 제작 (값 출처: {source})"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="공포·탐욕 지수 계기판 그림 URL 을 만든다")
    p.add_argument("--date", type=datetime.date.fromisoformat, required=True,
                   help="지수 기준일 (YYYY-MM-DD). 카드가 인용한 날짜")
    p.add_argument("--value", type=int, help="기사가 인용한 값. 없으면 alternative.me 조회")
    p.add_argument("--source", help="--value 를 준 경우 그 값을 낸 매체 이름")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.value is not None:
        if not 0 <= args.value <= 100:
            print("값은 0~100 이어야 한다", file=sys.stderr)
            return 1
        value, source = args.value, args.source or "기사 인용"
    else:
        try:
            value, source = fetch_value(args.date), "alternative.me"
        except Exception as e:  # noqa: BLE001 — 네트워크 실패를 그대로 사람에게 보인다
            print(f"조회 실패: {e}", file=sys.stderr)
            return 1

    print(f"value : {value}")
    print(f"image : {gauge_url(value, args.date)}")
    print(f"credit: {credit(source)}")
    print("카드 본문의 지수 값이 위 value 와 같은지 확인해라.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
