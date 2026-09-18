"""유튜브 카드의 썸네일을 링크에서 되살린다.

영상 썸네일 주소는 영상 id 하나로 결정된다(`i.ytimg.com/vi/<id>/hqdefault.jpg`).
그런데 카드 JSON 을 쓰는 단계에서 이 값이 빠지는 일이 있다 — 2026-09-18 편 10번
카드가 `media: {}` 로 발행되어 유튜브 카드인데도 썸네일 자리가 비었다. 후보 수집은
`scripts/collect_daily.py` 가 thumbnail_url 을 붙여 주지만, 카드로 옮겨 적는 단계를
사람이 거치므로 같은 누락이 또 난다.

그래서 내보낼 때 채운다. 링크만 있으면 되살릴 수 있는 값이고, 읽는 쪽에서 채우면
이미 발행된 과거 편에도 그대로 적용된다. 저장된 내용은 건드리지 않는다.
"""

import urllib.parse
from typing import Any

THUMBNAIL_URL = "https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"


def video_id(url: str) -> str | None:
    """카드에 박히는 유튜브 URL 형태에서 video id 를 뽑는다.

    발행 파이프라인이 만드는 형태는 셋뿐이다(`scripts/collect_daily.py` 와 같은 규칙):
    - `https://youtu.be/<id>`
    - `https://www.youtube.com/watch?v=<id>`
    - `https://i.ytimg.com/vi/<id>/hqdefault.jpg`

    매치되지 않으면 None — 유튜브가 아니거나 형태가 바뀐 것이므로 조용히 건너뛴다.
    """
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return None
    host = parsed.netloc.removeprefix("www.")
    if host == "youtu.be":
        return parsed.path.strip("/") or None
    if host in {"youtube.com", "m.youtube.com"}:
        return urllib.parse.parse_qs(parsed.query).get("v", [None])[0] or None
    if host == "i.ytimg.com":
        parts = parsed.path.strip("/").split("/")
        if len(parts) >= 2 and parts[0] == "vi":
            return parts[1] or None
    return None


def _card_with_thumbnail(card: dict[str, Any]) -> dict[str, Any]:
    media = card.get("media")
    if isinstance(media, dict) and isinstance(media.get("image"), str) and media["image"]:
        return card  # 이미 쓸 그림이 있다. 무엇이든 여기서 덮지 않는다.

    link = card.get("link")
    href = link.get("href") if isinstance(link, dict) else None
    if not isinstance(href, str):
        return card
    found = video_id(href)
    if found is None:
        return card

    # 기존 media 의 다른 키(href·cta)는 살린다. media 가 null 이면 새로 만든다.
    filled = dict(media) if isinstance(media, dict) else {}
    filled["image"] = THUMBNAIL_URL.format(video_id=found)
    return {**card, "media": filled}


def fill_card_thumbnails(content: dict[str, Any]) -> dict[str, Any]:
    """유튜브 링크를 가진 카드에 썸네일이 없으면 채워 넣은 사본을 돌려준다.

    바뀐 카드가 없으면 원본을 그대로 돌려준다 — 대부분의 편이 여기 해당하므로
    쓸데없는 사본을 만들지 않는다.
    """
    cards = content.get("cards")
    if not isinstance(cards, list):
        return content

    filled = [_card_with_thumbnail(c) if isinstance(c, dict) else c for c in cards]
    if all(a is b for a, b in zip(filled, cards, strict=True)):
        return content
    return {**content, "cards": filled}
