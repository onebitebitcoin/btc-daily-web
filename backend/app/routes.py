import datetime
import hmac
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.models import Edition
from app.og import og_cache_path, og_image_bytes_to_jpeg, render_og_html, resolve_og_image_url
from app.schemas import EditionContent

router = APIRouter(prefix="/api")


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
def get_latest_edition(db: Session = Depends(get_db)) -> dict[str, Any]:
    edition = db.scalars(select(Edition).order_by(Edition.date.desc())).first()
    if edition is None:
        raise HTTPException(status_code=404, detail="no editions found")
    return edition.content


@router.get("/editions")
def list_editions(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    editions = db.scalars(select(Edition).order_by(Edition.date.asc())).all()
    return [{"date": e.date.isoformat(), "slug": e.slug, "title": e.title} for e in editions]


@router.get("/editions/{date}")
def get_edition(date: datetime.date, db: Session = Depends(get_db)) -> dict[str, Any]:
    edition = db.get(Edition, date)
    if edition is None:
        raise HTTPException(status_code=404, detail=f"no edition for date {date.isoformat()}")
    return edition.content


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
