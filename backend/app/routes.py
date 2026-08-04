import datetime
import hashlib
import hmac
import json
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import imgproxy
from app.config import Settings, get_settings
from app.db import get_db
from app.models import Edition
from app.og import og_cache_path, og_image_bytes_to_jpeg, render_og_html, resolve_og_image_url
from app.schemas import EditionContent

router = APIRouter(prefix="/api")

# 발행분은 재발행(upsert)으로 바뀔 수 있으니 영구 캐시는 못 쓴다. 5분 뒤부터는
# 조건부 요청이 나가지만 내용이 그대로면 304 — 본문 0바이트다.
EDITION_CACHE_CONTROL = "public, max-age=300, stale-while-revalidate=86400"
# 변환 이미지는 원본 URL 해시가 캐시 키에 들어가므로 내용이 바뀌면 경로가 바뀐다.
IMAGE_CACHE_CONTROL = "public, max-age=86400, stale-while-revalidate=604800"


def json_with_etag(request: Request, payload: Any, cache_control: str) -> Response:
    """ETag를 붙이고, 클라이언트가 같은 값을 들고 있으면 304로 끊는다.

    세로 무한 피드는 같은 날짜를 재방문할 일이 잦다(뒤로가기, 캘린더 점프).
    ETag가 없으면 그때마다 50KB를 다시 받는다.
    """
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    etag = f'"{hashlib.sha256(canonical.encode()).hexdigest()[:32]}"'
    headers = {"ETag": etag, "Cache-Control": cache_control}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return JSONResponse(payload, headers=headers)


def require_admin(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    expected = f"Bearer {settings.admin_api_key}"
    if not settings.admin_api_key or not authorization:
        raise HTTPException(status_code=401, detail="invalid or missing API key")
    if not hmac.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="invalid or missing API key")


@router.get("/editions/latest")
def get_latest_edition(request: Request, db: Session = Depends(get_db)) -> Response:
    edition = db.scalars(select(Edition).order_by(Edition.date.desc())).first()
    if edition is None:
        raise HTTPException(status_code=404, detail="no editions found")
    return json_with_etag(request, edition.content, EDITION_CACHE_CONTROL)


@router.get("/editions")
def list_editions(request: Request, db: Session = Depends(get_db)) -> Response:
    editions = db.scalars(select(Edition).order_by(Edition.date.asc())).all()
    payload = [{"date": e.date.isoformat(), "slug": e.slug, "title": e.title} for e in editions]
    return json_with_etag(request, payload, EDITION_CACHE_CONTROL)


@router.get("/editions/{date}")
def get_edition(
    date: datetime.date, request: Request, db: Session = Depends(get_db)
) -> Response:
    edition = db.get(Edition, date)
    if edition is None:
        raise HTTPException(status_code=404, detail=f"no edition for date {date.isoformat()}")
    return json_with_etag(request, edition.content, EDITION_CACHE_CONTROL)


@router.get("/img/{date}/{num}")
def get_card_image(
    date: datetime.date,
    num: int,
    w: int | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    """카드 이미지를 WebP로 줄여 돌려준다 — 원본 URL은 받지 않는다(imgproxy 참고)."""
    edition = db.get(Edition, date)
    if edition is None:
        raise HTTPException(status_code=404, detail=f"no edition for date {date.isoformat()}")

    source_url = imgproxy.resolve_card_image_url(edition.content, num)
    if source_url is None:
        raise HTTPException(status_code=404, detail=f"no remote image for card {num}")

    width = imgproxy.normalize_width(w)
    path = imgproxy.cache_path(settings.img_cache_dir, date.isoformat(), num, width, source_url)

    if not path.exists():
        try:
            raw = imgproxy.fetch_source(source_url)
        except (httpx.HTTPError, imgproxy.ImageTooLargeError) as exc:
            raise HTTPException(status_code=502, detail="failed to fetch source image") from exc
        try:
            payload = imgproxy.to_webp(raw, width)
        except (
            OSError,
            ValueError,
            Image.DecompressionBombError,
            imgproxy.ImageTooLargeError,
        ) as exc:
            raise HTTPException(status_code=502, detail="failed to convert source image") from exc
        imgproxy.write_cache_atomically(path, payload)

    return FileResponse(
        path, media_type="image/webp", headers={"Cache-Control": IMAGE_CACHE_CONTROL}
    )


@router.post("/editions", dependencies=[Depends(require_admin)])
def upsert_edition(body: EditionContent, db: Session = Depends(get_db)) -> dict[str, Any]:
    content = body.model_dump(mode="json")
    edition = db.get(Edition, body.meta.date)
    if edition is None:
        edition = Edition(
            date=body.meta.date, slug=body.meta.slug, title=body.meta.title, content=content
        )
        db.add(edition)
    else:
        edition.slug = body.meta.slug
        edition.title = body.meta.title
        edition.content = content
    db.commit()
    db.refresh(edition)
    return edition.content


@router.get("/og/{date}/image.jpg")
def get_og_image(
    date: datetime.date,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    cache_path = og_cache_path(settings.og_cache_dir, date.isoformat())
    if cache_path.exists():
        return FileResponse(cache_path, media_type="image/jpeg")

    edition = db.get(Edition, date)
    if edition is None:
        raise HTTPException(status_code=404, detail=f"no edition for date {date.isoformat()}")

    image_url = resolve_og_image_url(edition.content)
    if image_url is None:
        raise HTTPException(status_code=404, detail="no source image for this edition")

    try:
        resp = httpx.get(image_url, timeout=10, follow_redirects=True)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="failed to fetch source image") from exc

    jpeg_bytes = og_image_bytes_to_jpeg(resp.content)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(jpeg_bytes)
    return FileResponse(cache_path, media_type="image/jpeg")


@router.get("/og/latest", response_class=HTMLResponse)
def get_og_html_latest(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    edition = db.scalars(select(Edition).order_by(Edition.date.desc())).first()
    if edition is None:
        raise HTTPException(status_code=404, detail="no editions found")
    return HTMLResponse(render_og_html(edition.content, edition.date.isoformat(), request))


@router.get("/og/{date}", response_class=HTMLResponse)
def get_og_html(
    date: datetime.date, request: Request, db: Session = Depends(get_db)
) -> HTMLResponse:
    edition = db.get(Edition, date)
    if edition is None:
        raise HTTPException(status_code=404, detail=f"no edition for date {date.isoformat()}")
    return HTMLResponse(render_og_html(edition.content, date.isoformat(), request))
