import datetime
import json
from pathlib import Path
from typing import Any

from app.config import Settings, get_settings
from app.models import Edition

REFERENCE_CONTENT = Path(__file__).resolve().parents[2] / "reference" / "content.json"


def reference_payload(date: str = "2026-07-30") -> dict[str, Any]:
    payload = json.loads(REFERENCE_CONTENT.read_text(encoding="utf-8"))
    payload["meta"]["date"] = date
    return payload


def seed_edition(session_factory, content: dict[str, Any]) -> None:
    meta = content["meta"]
    with session_factory() as session:
        session.add(
            Edition(
                date=datetime.date.fromisoformat(meta["date"]),
                slug=meta["slug"],
                title=meta["title"],
                content=content,
            )
        )
        session.commit()


def override_admin_key(client, key: str) -> None:
    client.app.dependency_overrides[get_settings] = lambda: Settings(admin_api_key=key)


# ---- US-202: GET /api/editions (list) ----


def test_list_editions_empty(client) -> None:
    response = client.get("/api/editions")

    assert response.status_code == 200
    assert response.json() == []


def test_list_editions_ascending_excludes_content(client) -> None:
    later = reference_payload("2026-07-31")
    later["meta"]["slug"] = "btc-daily-0731"
    later["meta"]["title"] = "Title 31"
    seed_edition(client.session_factory, later)

    earlier = reference_payload("2026-07-30")
    earlier["meta"]["title"] = "Title 30"
    seed_edition(client.session_factory, earlier)

    response = client.get("/api/editions")

    assert response.status_code == 200
    body = response.json()
    assert body == [
        {"date": "2026-07-30", "slug": "btc-daily-0730", "title": "Title 30"},
        {"date": "2026-07-31", "slug": "btc-daily-0731", "title": "Title 31"},
    ]
    assert "content" not in body[0]


# ---- US-203: GET /api/editions/{date} ----


def test_get_edition_by_date_returns_full_content(client) -> None:
    payload = reference_payload("2026-07-30")
    seed_edition(client.session_factory, payload)

    response = client.get("/api/editions/2026-07-30")

    assert response.status_code == 200
    assert response.json() == payload


def test_get_edition_missing_date_returns_404(client) -> None:
    response = client.get("/api/editions/2026-01-01")

    assert response.status_code == 404
    assert "detail" in response.json()


def test_get_edition_malformed_date_returns_422(client) -> None:
    response = client.get("/api/editions/not-a-date")

    assert response.status_code == 422


# ---- US-204: GET /api/editions/latest ----


def test_latest_returns_max_date_not_insertion_order(client) -> None:
    seed_edition(client.session_factory, reference_payload("2026-07-30"))

    later = reference_payload("2026-08-01")
    later["meta"]["slug"] = "btc-daily-0801"
    later["meta"]["title"] = "Aug 1"
    seed_edition(client.session_factory, later)

    inserted_last_but_earliest = reference_payload("2026-07-15")
    inserted_last_but_earliest["meta"]["slug"] = "btc-daily-0715"
    inserted_last_but_earliest["meta"]["title"] = "Jul 15"
    seed_edition(client.session_factory, inserted_last_but_earliest)

    response = client.get("/api/editions/latest")

    assert response.status_code == 200
    assert response.json()["meta"]["date"] == "2026-08-01"


def test_latest_returns_404_when_empty(client) -> None:
    response = client.get("/api/editions/latest")

    assert response.status_code == 404
    assert "detail" in response.json()


# ---- US-205: POST /api/editions (auth + upsert) ----


def test_post_missing_auth_header_returns_401(client) -> None:
    override_admin_key(client, "secret")

    response = client.post("/api/editions", json=reference_payload())

    assert response.status_code == 401
    assert "detail" in response.json()


def test_post_wrong_key_returns_401(client) -> None:
    override_admin_key(client, "secret")

    response = client.post(
        "/api/editions",
        json=reference_payload(),
        headers={"Authorization": "Bearer wrong"},
    )

    assert response.status_code == 401


def test_post_fails_closed_when_admin_key_unset(client) -> None:
    override_admin_key(client, "")

    response = client.post(
        "/api/editions",
        json=reference_payload(),
        headers={"Authorization": "Bearer anything"},
    )

    assert response.status_code == 401


def test_post_invalid_body_returns_422(client) -> None:
    override_admin_key(client, "secret")
    payload = reference_payload()
    del payload["meta"]["date"]

    response = client.post(
        "/api/editions", json=payload, headers={"Authorization": "Bearer secret"}
    )

    assert response.status_code == 422


def test_post_creates_and_second_post_upserts_in_place(client) -> None:
    override_admin_key(client, "secret")
    headers = {"Authorization": "Bearer secret"}

    create_response = client.post(
        "/api/editions", json=reference_payload("2026-07-30"), headers=headers
    )
    assert create_response.status_code in (200, 201)
    assert create_response.json()["meta"]["date"] == "2026-07-30"

    updated_payload = reference_payload("2026-07-30")
    updated_payload["meta"]["title"] = "업데이트된 제목"
    updated_payload["cards"][0]["title"] = "새 헤드라인"

    update_response = client.post("/api/editions", json=updated_payload, headers=headers)
    assert update_response.status_code in (200, 201)

    get_response = client.get("/api/editions/2026-07-30")
    assert get_response.status_code == 200
    assert get_response.json()["meta"]["title"] == "업데이트된 제목"
    assert get_response.json()["cards"][0]["title"] == "새 헤드라인"

    list_response = client.get("/api/editions")
    assert len(list_response.json()) == 1
