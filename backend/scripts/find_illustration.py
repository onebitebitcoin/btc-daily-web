"""이미지 없는 카드를 채울 **삽화** 후보를 키워드로 찾는다 (Openverse).

기사에서 이미지가 안 나오는 카드가 매 발행 나온다 — 2026-09-21 btc 발행은 10장 중
5장이 그랬다. 그 카드는 `CardArtFallback` 이 문구를 조판해 채우는데, 절반이 그 경로로
가면 한 편이 통째로 글자판이 된다. 그래서 **내용을 떠올리게 하는 삽화**를 붙인다.

## 삽화는 기사 사진이 아니다

`CONTENT_CONTRACT.md` 의 "이미지와 link 는 항상 같은 기사에서 나온다" 규칙은 그대로다.
**다른 매체의 기사 사진을 가져다 붙이는 것은 여전히 금지**다 — 그건 출처를 속이는 일이다.
여기서 찾는 것은 성격이 다르다: 사건을 찍은 사진이 아니라 주제를 떠올리게 하는 자료
사진이고, 카드에 출처를 적어 그 사실을 드러낸다.

## 반드시 지킬 것 둘

1. **출처 표기는 의무다.** `by`·`by-sa` 는 저작자 표시가 라이선스 조건이다.
   `media.credit` 에 이 스크립트가 만들어 주는 문자열을 그대로 넣어라.
   `push_edition.py` 가 credit 없는 외부 삽화를 막는다.
2. **인물 사진을 일반 삽화로 쓰지 마라.** 검색이 사람 사진을 섞어 준다 — 실측:
   "data center servers" 질의에 `Shaku Atre in 2016`(실존 인물 초상)이 올라왔다.
   기사와 무관한 사람이 사건의 당사자처럼 읽힌다. 이 스크립트는 그런 후보에
   `[인물?]` 표시를 붙이니, 카드 주인공 본인이 아니면 고르지 마라.

Usage:
    python scripts/find_illustration.py "data center servers"
    python scripts/find_illustration.py "양자컴퓨터" --n 8 --min-width 1200
    python scripts/find_illustration.py "bitcoin mining" --json
"""

import argparse
import json
import sys
import urllib.parse
import urllib.request

API = "https://api.openverse.org/v1/images/"
UA = "daily-cardnews/1.0 (illustration search)"

# 상업적 이용과 변형이 모두 허용되는 것만 쓴다. 카드뉴스는 발행물이라 nc(비상업)·
# nd(변형금지) 는 쓸 수 없다 — 이미지 프록시가 크기를 줄이는 것 자체가 변형이다.
ALLOWED_LICENSES = ("cc0", "pdm", "by", "by-sa")

# 사람이 주인공인 사진을 걸러내기 위한 표시. 태그·제목에 이게 있으면 경고를 붙인다.
# 하드 제외가 아니라 경고인 이유는 카드 주인공 본인의 사진이면 오히려 맞기 때문이다.
_PERSON_HINTS = (
    "portrait", "portraits", "people", "person", "face", "faces", "man", "woman",
    "men", "women", "boy", "girl", "headshot", "selfie", "인물", "초상",
)

MIN_WIDTH_DEFAULT = 900


def search(query: str, n: int, min_width: int) -> list[dict]:
    params = {
        "q": query,
        # 걸러낸 뒤에도 n 개가 남도록 넉넉히 받는다.
        "page_size": min(max(n * 4, 12), 40),
        "license_type": "commercial,modification",
        "mature": "false",
    }
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        data = json.load(r)

    out = []
    for it in data.get("results", []):
        if it.get("license") not in ALLOWED_LICENSES:
            continue
        if it.get("mature"):
            continue
        width, height = it.get("width") or 0, it.get("height") or 0
        if width < min_width:
            continue
        out.append(
            {
                "url": it.get("url"),
                "width": width,
                "height": height,
                "landscape": width >= height,
                "license": _license_label(it),
                "credit": build_credit(it),
                "source_page": it.get("foreign_landing_url"),
                "title": it.get("title") or "",
                "looks_like_person": looks_like_person(it),
            }
        )
        if len(out) >= n:
            break
    return out


def _license_label(item: dict) -> str:
    lic = (item.get("license") or "").upper()
    ver = item.get("license_version") or ""
    if lic in ("CC0", "PDM"):
        return lic
    return f"CC {lic} {ver}".strip()


def build_credit(item: dict) -> str:
    """카드에 그대로 넣을 한국어 출처 문자열.

    Openverse 가 주는 영문 `attribution` 을 쓰지 않는 이유는 카드가 한국어라서다.
    라이선스 이름은 고유명사라 원문을 유지한다.
    """
    title = (item.get("title") or "").strip() or "무제"
    creator = (item.get("creator") or "").strip()
    who = f" · {creator}" if creator else ""
    return f"{title}{who} ({_license_label(item)})"


def looks_like_person(item: dict) -> bool:
    """사람이 주인공인 사진으로 보이는가. 보수적으로 넓게 잡는다 —
    놓쳐서 남의 얼굴을 엉뚱한 기사에 붙이는 쪽이 훨씬 비싸다."""
    haystack = [(item.get("title") or "").lower()]
    haystack += [str(t.get("name", "")).lower() for t in (item.get("tags") or [])]
    blob = " ".join(haystack)
    return any(h in blob.split() or h in blob for h in _PERSON_HINTS)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="카드 삽화 후보를 키워드로 찾는다")
    p.add_argument("query", help="검색어. 영문이 결과가 훨씬 많다")
    p.add_argument("--n", type=int, default=5, help="받을 후보 수 (기본 5)")
    p.add_argument("--min-width", type=int, default=MIN_WIDTH_DEFAULT,
                   help=f"최소 가로 픽셀 (기본 {MIN_WIDTH_DEFAULT})")
    p.add_argument("--json", action="store_true", help="JSON 으로 출력")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        results = search(args.query, args.n, args.min_width)
    except Exception as e:  # noqa: BLE001 — 네트워크 실패를 그대로 사람에게 보인다
        print(f"검색 실패: {e}", file=sys.stderr)
        return 1

    if not results:
        print(f"'{args.query}' 로 쓸 만한 후보가 없다. 검색어를 영문으로 바꾸거나 "
              f"--min-width 를 낮춰라.", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0

    for i, r in enumerate(results, 1):
        flag = " [인물?]" if r["looks_like_person"] else ""
        shape = "가로" if r["landscape"] else "세로"
        print(f"{i}. {r['width']}x{r['height']} {shape} · {r['license']}{flag}")
        print(f"   image : {r['url']}")
        print(f"   credit: {r['credit']}")
        print(f"   출처  : {r['source_page']}")
        print()
    print("카드에 넣을 때: media.image = image, media.credit = credit 를 그대로 쓴다.")
    print("[인물?] 표시가 붙은 후보는 카드 주인공 본인이 아니면 고르지 마라.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
