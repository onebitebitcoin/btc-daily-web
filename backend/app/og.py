"""OG(Open Graph) 이미지·메타 HTML 생성 — 링크 공유 미리보기용.

SNS 크롤러는 JS를 실행하지 않으므로 SPA의 정적 index.html로는 날짜별 메타를
줄 수 없다. 이 모듈이 만드는 값은 컨테이너 nginx가 크롤러 User-Agent만 골라
백엔드로 라우팅했을 때 쓰인다(frontend/nginx.conf 참고).
"""

import html
import io
from pathlib import Path
from typing import Any

from fastapi import Request
from PIL import Image, ImageDraw

OG_IMAGE_SIZE = (1200, 630)
DESCRIPTION_MAX_LEN = 160

LOGO_PATH = Path(__file__).parent / "assets" / "hanip-logo.jpg"
LOGO_BADGE_SIZE = 88
LOGO_BADGE_MARGIN = 28
LOGO_RING_PADDING = 8


def resolve_og_image_url(content: dict[str, Any]) -> str | None:
    """카드 1(첫 뉴스 카드)의 이미지 URL을 반환한다. stem(번들 asset)이나
    이미지 자체가 없으면 None — CONTENT_CONTRACT.md 4장에 따르면 배포본은
    항상 절대 URL을 쓰므로, stem은 로컬 시드 fixture에서만 나온다."""
    cards = content.get("cards") or []
    if not cards:
        return None
    media = cards[0].get("media")
    if not media:
        return None
    image = media.get("image")
    if not image or not image.startswith("http"):
        return None
    return image


def crop_to_fill(img: Image.Image, size: tuple[int, int] = OG_IMAGE_SIZE) -> Image.Image:
    """비율을 유지한 채 리사이즈한 뒤 중앙을 기준으로 target 크기에 맞춰 자른다."""
    target_w, target_h = size
    src_w, src_h = img.size
    scale = max(target_w / src_w, target_h / src_h)
    resized = img.resize((round(src_w * scale), round(src_h * scale)))
    left = (resized.width - target_w) // 2
    top = (resized.height - target_h) // 2
    return resized.crop((left, top, left + target_w, top + target_h))


def add_logo_badge(img: Image.Image) -> Image.Image:
    """우하단에 한입비트코인 원형 배지를 합성한다 — 링크 미리보기에도 출처가 남도록."""
    badge = Image.open(LOGO_PATH).convert("RGB").resize(
        (LOGO_BADGE_SIZE, LOGO_BADGE_SIZE), Image.LANCZOS
    )
    badge_mask = Image.new("L", (LOGO_BADGE_SIZE, LOGO_BADGE_SIZE), 0)
    ImageDraw.Draw(badge_mask).ellipse((0, 0, LOGO_BADGE_SIZE, LOGO_BADGE_SIZE), fill=255)

    ring_size = LOGO_BADGE_SIZE + LOGO_RING_PADDING
    ring = Image.new("RGBA", (ring_size, ring_size), (0, 0, 0, 0))
    ImageDraw.Draw(ring).ellipse((0, 0, ring_size, ring_size), fill=(255, 255, 255, 235))

    out = img.convert("RGB").copy()
    x = out.width - LOGO_BADGE_MARGIN - ring_size
    y = out.height - LOGO_BADGE_MARGIN - ring_size
    inset = LOGO_RING_PADDING // 2
    out.paste(ring, (x, y), ring)
    out.paste(badge, (x + inset, y + inset), badge_mask)
    return out


def og_image_bytes_to_jpeg(raw: bytes) -> bytes:
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    cropped = crop_to_fill(img)
    branded = add_logo_badge(cropped)
    buf = io.BytesIO()
    branded.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def og_cache_path(cache_dir: str, date_iso: str) -> Path:
    return Path(cache_dir) / f"{date_iso}.jpg"


def build_og_description(content: dict[str, Any], max_len: int = DESCRIPTION_MAX_LEN) -> str:
    cards = content.get("cards") or []
    if not cards:
        return content.get("cover", {}).get("hint", "")
    first = cards[0]
    text = f"{first.get('title', '')} — {first.get('body', '')}".strip()
    if len(text) <= max_len:
        return text
    return text[:max_len].rstrip() + "…"


def _request_origin(request: Request) -> str:
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("host", request.url.netloc)
    return f"{scheme}://{host}"


def render_og_html(content: dict[str, Any], date_iso: str, request: Request) -> str:
    origin = _request_origin(request)
    title = html.escape(f"{content['meta']['title']} · 데일리 비트코인")
    description = html.escape(build_og_description(content))
    image_url = html.escape(f"{origin}/api/og/{date_iso}/image.jpg")
    page_url = html.escape(f"{origin}/d/{date_iso}")

    return f"""<!doctype html>
<html lang="ko">
  <head>
    <meta charset="utf-8" />
    <title>{title}</title>
    <meta name="description" content="{description}" />
    <meta property="og:type" content="article" />
    <meta property="og:site_name" content="데일리 비트코인" />
    <meta property="og:title" content="{title}" />
    <meta property="og:description" content="{description}" />
    <meta property="og:image" content="{image_url}" />
    <meta property="og:url" content="{page_url}" />
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:title" content="{title}" />
    <meta name="twitter:description" content="{description}" />
    <meta name="twitter:image" content="{image_url}" />
  </head>
  <body></body>
</html>
"""
