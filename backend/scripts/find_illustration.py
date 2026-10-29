"""이미지 없는 카드를 채울 **삽화** 후보를 키워드로 찾는다 (Unsplash).

기사에서 이미지가 안 나오는 카드가 매 발행 나온다 — 2026-09-21 btc 발행은 10장 중
5장이 그랬다. 그 카드는 `CardArtFallback` 이 문구를 조판해 채우는데, 절반이 그 경로로
가면 한 편이 통째로 글자판이 된다. 그래서 **내용을 떠올리게 하는 삽화**를 붙인다.

## 왜 Unsplash 인가

예전에는 Openverse(위키미디어·Flickr 모음)를 썼다. 2026-10-29 발행에서 Openverse 가
500·504 를 반복했고, 위키미디어 원본은 발행 서버에서 429 를 받아 삽화 6장 중 4장이
글자판으로 나갔다. Pexels 는 같은 날 신규 API 키 발급을 중단한 상태였다.
Unsplash 는 실사진 위주라 글자 그림이 거의 없고, 상업 이용·변형이 허용된다.

API 약관상 지킬 것: 이미지는 `images.unsplash.com` 주소를 그대로 건다(이 저장소는 원본
URL 을 저장하고 이미지 프록시가 받으므로 그대로 맞다). 사진가를 표기한다. 카드에 실제로
쓴 사진은 `--track <download_location>` 으로 다운로드 이벤트를 한 번 보낸다.
키는 `UNSPLASH_ACCESS_KEY` 를 환경 변수나 `backend/.env` 에 둔다. 데모 앱은 시간당
50회라 검색어를 한 카드에 서너 번 이상 바꾸지 마라.

## 삽화는 기사 사진이 아니다

`CONTENT_CONTRACT.md` 의 "이미지와 link 는 항상 같은 기사에서 나온다" 규칙은 그대로다.
**다른 매체의 기사 사진을 가져다 붙이는 것은 여전히 금지**다 — 그건 출처를 속이는 일이다.
여기서 찾는 것은 성격이 다르다: 사건을 찍은 사진이 아니라 주제를 떠올리게 하는 자료
사진이고, 카드에 출처를 적어 그 사실을 드러낸다.

## 반드시 지킬 것 둘

1. **출처 표기를 넣어라.** `media.credit` 에 이 스크립트가 만들어 주는 문자열을 그대로
   넣어라. `push_edition.py` 가 credit 없는 외부 삽화를 막는다. 독자가 "사건을 찍은
   사진이 아니라 자료 사진"임을 알게 하는 표기이기도 하다.
2. **인물 사진을 일반 삽화로 쓰지 마라.** 검색이 사람 사진을 섞어 준다. 기사와 무관한
   사람이 사건의 당사자처럼 읽힌다. 이 스크립트는 그런 후보에 `[인물?]` 표시를 붙이니,
   카드 주인공 본인이 아니면 고르지 마라.

Usage:
    python scripts/find_illustration.py "data center servers"
    python scripts/find_illustration.py "bitcoin mining" --n 8 --min-width 1200
    python scripts/find_illustration.py "bitcoin mining" --json
"""

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api.unsplash.com/search/photos"
ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
UA = "daily-cardnews/1.0 (illustration search)"
# 카드 최대 폭(800)과 미리보기(1200x630)에 충분한 크기로 Unsplash CDN 에서 줄여 받는다.
IMAGE_PARAMS = "fm=jpg&q=80&w=1600&fit=max"

# 사람이 주인공인 사진을 걸러내기 위한 표시. alt 문구에 이게 있으면 경고를 붙인다.
# 하드 제외가 아니라 경고인 이유는 카드 주인공 본인의 사진이면 오히려 맞기 때문이다.
_PERSON_HINTS = (
    "portrait", "portraits", "people", "person", "face", "faces", "man", "woman",
    "men", "women", "boy", "girl", "headshot", "selfie", "인물", "초상",
)

MIN_WIDTH_DEFAULT = 900


def load_api_key() -> str:
    key = os.environ.get("UNSPLASH_ACCESS_KEY", "").strip()
    if key:
        return key
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            name, _, value = line.strip().partition("=")
            if name.strip() == "UNSPLASH_ACCESS_KEY" and value.strip():
                return value.strip()
    raise SystemExit(
        f"UNSPLASH_ACCESS_KEY 가 없다 — 환경 변수나 {ENV_FILE} 에 넣어라 "
        "(https://unsplash.com/oauth/applications)"
    )


def _headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Client-ID {api_key}", "Accept-Version": "v1", "User-Agent": UA}


def search(query: str, n: int, min_width: int, api_key: str) -> list[dict]:
    params = {
        "query": query,
        # 걸러낸 뒤에도 n 개가 남도록 넉넉히 받는다. Unsplash 상한은 30 이다.
        "per_page": min(max(n * 3, 15), 30),
        "orientation": "landscape",
        "content_filter": "high",
    }
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=_headers(api_key))
    with urllib.request.urlopen(req, timeout=25) as r:
        data = json.load(r)
    return pick(data.get("results") or [], n, min_width)


def track_download(download_location: str, api_key: str) -> None:
    """카드에 쓴 사진의 다운로드 이벤트를 보낸다(Unsplash API 약관)."""
    if not download_location.startswith("https://api.unsplash.com/"):
        raise SystemExit(f"Unsplash download_location 이 아니다: {download_location}")
    req = urllib.request.Request(download_location, headers=_headers(api_key))
    with urllib.request.urlopen(req, timeout=25) as r:
        r.read()


def pick(photos: list[dict], n: int, min_width: int) -> list[dict]:
    out = []
    for photo in photos:
        width, height = photo.get("width") or 0, photo.get("height") or 0
        raw = (photo.get("urls") or {}).get("raw")
        if width < min_width or not raw:
            continue
        joiner = "&" if "?" in raw else "?"
        out.append(
            {
                "url": f"{raw}{joiner}{IMAGE_PARAMS}",
                "width": width,
                "height": height,
                "landscape": width >= height,
                "license": "Unsplash License",
                "credit": build_credit(photo),
                "source_page": (photo.get("links") or {}).get("html"),
                "download_location": (photo.get("links") or {}).get("download_location"),
                "title": photo.get("alt_description") or photo.get("description") or "",
                "looks_like_person": looks_like_person(photo),
            }
        )
        if len(out) >= n:
            break
    return out


def build_credit(photo: dict) -> str:
    """카드에 그대로 넣을 출처 문자열."""
    who = ((photo.get("user") or {}).get("name") or "").strip() or "작자 미상"
    return f"{who} · Unsplash"


def looks_like_person(photo: dict) -> bool:
    """사람이 주인공인 사진으로 보이는가. 보수적으로 넓게 잡는다 —
    놓쳐서 남의 얼굴을 엉뚱한 기사에 붙이는 쪽이 훨씬 비싸다."""
    blob = " ".join(
        [photo.get("alt_description") or "", photo.get("description") or ""]
    ).lower()
    words = blob.replace(",", " ").replace(".", " ").split()
    return any(h in words or (not h.isascii() and h in blob) for h in _PERSON_HINTS)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="카드 삽화 후보를 키워드로 찾는다")
    p.add_argument("query", nargs="?", help="검색어. 영문이 결과가 훨씬 많다")
    p.add_argument("--track", metavar="DOWNLOAD_LOCATION",
                   help="카드에 고른 사진의 download_location 으로 다운로드 이벤트를 보낸다")
    p.add_argument("--n", type=int, default=5, help="받을 후보 수 (기본 5)")
    p.add_argument("--min-width", type=int, default=MIN_WIDTH_DEFAULT,
                   help=f"최소 가로 픽셀 (기본 {MIN_WIDTH_DEFAULT})")
    p.add_argument("--json", action="store_true", help="JSON 으로 출력")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    api_key = load_api_key()
    if args.track:
        track_download(args.track, api_key)
        print("다운로드 이벤트를 보냈다.")
        return 0
    if not args.query:
        print("검색어나 --track 중 하나가 필요하다.", file=sys.stderr)
        return 2
    try:
        results = search(args.query, args.n, args.min_width, api_key)
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
        print(f"{i}. {r['width']}x{r['height']} {shape} · {r['title']}{flag}")
        print(f"   image : {r['url']}")
        print(f"   credit: {r['credit']}")
        print(f"   출처  : {r['source_page']}")
        print(f"   track : {r['download_location']}")
        print()
    print("카드에 넣을 때: media.image = image, media.credit = credit 를 그대로 쓴다.")
    print("고른 사진은 --track <track 주소> 로 한 번 알린다(Unsplash API 약관).")
    print("[인물?] 표시가 붙은 후보는 카드 주인공 본인이 아니면 고르지 마라.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
