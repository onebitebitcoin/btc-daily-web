"""카드 이미지를 화면 크기에 맞춰 WebP로 줄여 재전송한다.

뉴스사 CDN 원본은 실측 평균 380KB인데 카드의 이미지 영역은 모바일에서 400px가
채 안 된다. 세로 무한 피드는 하루 10장을 연속으로 소비하므로 원본을 그대로
흘리면 7일 스크롤에 20MB를 넘긴다.

**임의 URL을 받지 않는 것이 이 모듈의 보안 전제다.** 클라이언트는 (날짜, 카드
번호)만 넘기고 실제 URL은 서버가 DB에서 꺼낸다. 발행은 admin 키가 필요하므로
프록시가 어디로 나갈지 고를 수 있는 쪽은 발행자뿐이다 — 호스트 화이트리스트
없이 SSRF가 닫힌다. 화이트리스트를 쓰지 않는 실용적 이유도 있다: 매일 자동
발행이 새 뉴스 도메인을 물고 오면 목록에 없는 이미지가 조용히 깨진다.
"""

import hashlib
import io
from pathlib import Path
from typing import Any

import httpx
from PIL import Image

# 카드 이미지 영역은 뷰포트 폭의 100%, 높이의 40%다. 480은 Save-Data용,
# 800은 일반(고밀도 디스플레이의 2x까지 감당). 임의 폭을 허용하면 캐시가
# 폭발하므로 이 둘로 고정하고 나머지는 가까운 쪽으로 스냅한다.
ALLOWED_WIDTHS = (480, 800)
DEFAULT_WIDTH = 800

WEBP_QUALITY = 78
FETCH_TIMEOUT_SECONDS = 10
# 원본을 통째로 메모리에 올리므로 상한이 필요하다. 실측 최대가 700KB대라
# 16MB면 정상 이미지는 전부 통과하고 비정상만 걸린다.
MAX_SOURCE_BYTES = 16 * 1024 * 1024
# Pillow 기본 경고 임계치보다 낮게 잡아 decompression bomb을 일찍 끊는다.
MAX_SOURCE_PIXELS = 50_000_000


class ImageTooLargeError(Exception):
    """원본이 상한을 넘었다 — 정상 뉴스 썸네일이 아니다."""


def resolve_card_image_url(content: dict[str, Any], num: int) -> str | None:
    """에디션 content에서 카드 `num`의 원격 이미지 URL을 찾는다.

    번들 asset을 가리키는 stem(예: 'fed-macro')은 프록시 대상이 아니므로
    None을 반환한다 — 그 경우 프론트가 번들 이미지를 그대로 쓴다.
    """
    for card in content.get("cards") or []:
        if card.get("num") != num:
            continue
        media = card.get("media")
        if not media:
            return None
        image = media.get("image")
        if not image or not image.startswith("http"):
            return None
        return str(image)
    return None


def normalize_width(raw: int | None) -> int:
    """요청 폭을 허용 폭 중 하나로 스냅한다. 캐시 키가 무한히 늘지 않도록."""
    if raw is None:
        return DEFAULT_WIDTH
    return min(ALLOWED_WIDTHS, key=lambda allowed: abs(allowed - raw))


def source_fingerprint(url: str) -> str:
    """원본 URL의 짧은 해시. 재발행으로 이미지가 바뀌면 캐시 키도 바뀐다."""
    return hashlib.sha256(url.encode()).hexdigest()[:12]


def cache_path(cache_dir: str, date_iso: str, num: int, width: int, url: str) -> Path:
    return Path(cache_dir) / f"{date_iso}-{num:02d}-{width}-{source_fingerprint(url)}.webp"


def fetch_source(url: str) -> bytes:
    """원격 원본을 상한을 지키며 받아온다."""
    with httpx.stream("GET", url, timeout=FETCH_TIMEOUT_SECONDS, follow_redirects=True) as resp:
        resp.raise_for_status()
        declared = resp.headers.get("content-length")
        if declared and int(declared) > MAX_SOURCE_BYTES:
            raise ImageTooLargeError(f"content-length {declared} exceeds cap")
        chunks: list[bytes] = []
        total = 0
        for chunk in resp.iter_bytes():
            total += len(chunk)
            # Content-Length를 안 주거나 거짓말하는 CDN이 있으므로 실제로도 센다.
            if total > MAX_SOURCE_BYTES:
                raise ImageTooLargeError("streamed body exceeds cap")
            chunks.append(chunk)
    return b"".join(chunks)


def to_webp(raw: bytes, width: int) -> bytes:
    """원본 바이트를 지정 폭의 WebP로 변환한다. 원본이 더 좁으면 확대하지 않는다."""
    img = Image.open(io.BytesIO(raw))
    if img.width * img.height > MAX_SOURCE_PIXELS:
        raise ImageTooLargeError(f"{img.width}x{img.height} exceeds pixel cap")

    # 투명 배경(PNG·WebP)을 그냥 convert("RGB")하면 검게 깔린다. 카드 배경이
    # 밝은 쪽에 가까우므로 흰색 위에 합성한다.
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        canvas = Image.new("RGB", img.size, (255, 255, 255))
        canvas.paste(img, mask=img.split()[-1])
        img = canvas
    else:
        img = img.convert("RGB")

    if img.width > width:
        height = round(img.height * width / img.width)
        img = img.resize((width, height), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=WEBP_QUALITY, method=6)
    return buf.getvalue()


def write_cache_atomically(path: Path, payload: bytes) -> None:
    """같은 이미지를 동시에 요청해도 반쪽짜리 파일이 남지 않도록 rename으로 바꾼다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{source_fingerprint(str(path))}.tmp")
    tmp.write_bytes(payload)
    tmp.replace(path)
