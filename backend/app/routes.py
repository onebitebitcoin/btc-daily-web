import datetime
import hmac
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.models import Edition
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
