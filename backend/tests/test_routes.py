import datetime
import io
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from PIL import Image

from app import imgproxy
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


def override_img_cache_dir(client, path: Path) -> None:
    client.app.dependency_overrides[get_settings] = lambda: Settings(img_cache_dir=str(path))


def seed_edition_with_remote_image(session_factory, url: str, num: int = 1) -> None:
    payload = reference_payload("2026-07-30")
    payload["cards"][num - 1]["num"] = num
    payload["cards"][num - 1]["media"] = {"image": url, "href": None, "cta": None}
    seed_edition(session_factory, payload)


def png_bytes(size: tuple[int, int] = (1600, 900)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (10, 120, 200)).save(buf, format="PNG")
    return buf.getvalue()


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


# ---- 전송량 절감: ETag / 조건부 요청 ----


def test_edition_response_carries_etag_and_cache_control(client) -> None:
    seed_edition(client.session_factory, reference_payload("2026-07-30"))

    response = client.get("/api/editions/2026-07-30")

    assert response.headers["etag"].startswith('"')
    assert "max-age" in response.headers["cache-control"]


def test_matching_if_none_match_returns_304_with_empty_body(client) -> None:
    """재방문 시 50KB를 다시 받지 않는다는 것이 이 엔드포인트의 요점이다."""
    seed_edition(client.session_factory, reference_payload("2026-07-30"))
    etag = client.get("/api/editions/2026-07-30").headers["etag"]

    response = client.get("/api/editions/2026-07-30", headers={"If-None-Match": etag})

    assert response.status_code == 304
    assert response.content == b""


def test_weak_etag_from_gzipping_proxy_still_matches(client) -> None:
    """앞단 nginx가 gzip을 걸면 ETag에 W/ 접두사를 붙여 내보내고, 클라이언트는
    그 값을 그대로 돌려준다. 강하게 비교하면 304가 영원히 안 나간다."""
    seed_edition(client.session_factory, reference_payload("2026-07-30"))
    etag = client.get("/api/editions/2026-07-30").headers["etag"]

    response = client.get("/api/editions/2026-07-30", headers={"If-None-Match": f"W/{etag}"})

    assert response.status_code == 304


def test_if_none_match_accepts_a_list_of_tags(client) -> None:
    seed_edition(client.session_factory, reference_payload("2026-07-30"))
    etag = client.get("/api/editions/2026-07-30").headers["etag"]

    response = client.get(
        "/api/editions/2026-07-30", headers={"If-None-Match": f'"stale", {etag}'}
    )

    assert response.status_code == 304


def test_non_matching_if_none_match_returns_the_body(client) -> None:
    seed_edition(client.session_factory, reference_payload("2026-07-30"))

    response = client.get("/api/editions/2026-07-30", headers={"If-None-Match": '"nope"'})

    assert response.status_code == 200
    assert response.json()["meta"]["date"] == "2026-07-30"


def test_etag_changes_after_republish(client) -> None:
    override_admin_key(client, "secret")
    headers = {"Authorization": "Bearer secret"}
    client.post("/api/editions", json=reference_payload("2026-07-30"), headers=headers)
    before = client.get("/api/editions/2026-07-30").headers["etag"]

    updated = reference_payload("2026-07-30")
    updated["cards"][0]["title"] = "바뀐 헤드라인"
    client.post("/api/editions", json=updated, headers=headers)

    assert client.get("/api/editions/2026-07-30").headers["etag"] != before


def test_editions_list_also_supports_conditional_requests(client) -> None:
    seed_edition(client.session_factory, reference_payload("2026-07-30"))
    etag = client.get("/api/editions").headers["etag"]

    response = client.get("/api/editions", headers={"If-None-Match": etag})

    assert response.status_code == 304


def test_latest_edition_also_supports_conditional_requests(client) -> None:
    seed_edition(client.session_factory, reference_payload("2026-07-30"))
    etag = client.get("/api/editions/latest").headers["etag"]

    response = client.get("/api/editions/latest", headers={"If-None-Match": etag})

    assert response.status_code == 304


# ---- 이미지 프록시 GET /api/img/{date}/{num} ----


def test_img_returns_webp_smaller_than_source(client, tmp_path, monkeypatch) -> None:
    source = png_bytes((1600, 900))
    seed_edition_with_remote_image(client.session_factory, "https://cdn.example/a.png")
    override_img_cache_dir(client, tmp_path)
    monkeypatch.setattr(imgproxy, "fetch_source", lambda url: source)

    response = client.get("/api/img/2026-07-30/1")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"
    assert len(response.content) < len(source)
    assert Image.open(io.BytesIO(response.content)).size == (800, 450)


def test_img_honours_width_parameter(client, tmp_path, monkeypatch) -> None:
    seed_edition_with_remote_image(client.session_factory, "https://cdn.example/a.png")
    override_img_cache_dir(client, tmp_path)
    monkeypatch.setattr(imgproxy, "fetch_source", lambda url: png_bytes((1600, 900)))

    response = client.get("/api/img/2026-07-30/1?w=480")

    assert Image.open(io.BytesIO(response.content)).size == (480, 270)


def test_img_second_request_is_served_from_cache_without_refetch(
    client, tmp_path, monkeypatch
) -> None:
    calls: list[str] = []

    def counting_fetch(url: str) -> bytes:
        calls.append(url)
        return png_bytes()

    seed_edition_with_remote_image(client.session_factory, "https://cdn.example/a.png")
    override_img_cache_dir(client, tmp_path)
    monkeypatch.setattr(imgproxy, "fetch_source", counting_fetch)

    client.get("/api/img/2026-07-30/1")
    client.get("/api/img/2026-07-30/1")

    assert len(calls) == 1


def test_img_sets_long_cache_control(client, tmp_path, monkeypatch) -> None:
    seed_edition_with_remote_image(client.session_factory, "https://cdn.example/a.png")
    override_img_cache_dir(client, tmp_path)
    monkeypatch.setattr(imgproxy, "fetch_source", lambda url: png_bytes())

    response = client.get("/api/img/2026-07-30/1")

    assert "max-age=86400" in response.headers["cache-control"]


def test_img_404_for_unknown_date(client, tmp_path) -> None:
    override_img_cache_dir(client, tmp_path)

    response = client.get("/api/img/2026-01-01/1")

    assert response.status_code == 404


def test_img_404_when_card_uses_bundled_stem(client, tmp_path) -> None:
    """stem 이미지는 프론트가 번들에서 직접 쓴다 — 프록시할 원본이 없다."""
    seed_edition(client.session_factory, reference_payload("2026-07-30"))
    override_img_cache_dir(client, tmp_path)

    response = client.get("/api/img/2026-07-30/1")

    assert response.status_code == 404


def test_img_502_when_source_fetch_fails(client, tmp_path, monkeypatch) -> None:
    def failing_fetch(url: str) -> bytes:
        raise httpx.ConnectError("boom")

    seed_edition_with_remote_image(client.session_factory, "https://cdn.example/a.png")
    override_img_cache_dir(client, tmp_path)
    monkeypatch.setattr(imgproxy, "fetch_source", failing_fetch)

    response = client.get("/api/img/2026-07-30/1")

    assert response.status_code == 502


def test_img_502_when_source_is_not_an_image(client, tmp_path, monkeypatch) -> None:
    seed_edition_with_remote_image(client.session_factory, "https://cdn.example/a.png")
    override_img_cache_dir(client, tmp_path)
    monkeypatch.setattr(imgproxy, "fetch_source", lambda url: b"<html>404</html>")

    response = client.get("/api/img/2026-07-30/1")

    assert response.status_code == 502


@pytest.mark.parametrize("path", ["/api/img/2026-07-30/0", "/api/img/2026-07-30/99"])
def test_img_404_for_out_of_range_card_numbers(client, tmp_path, path: str) -> None:
    seed_edition_with_remote_image(client.session_factory, "https://cdn.example/a.png")
    override_img_cache_dir(client, tmp_path)

    assert client.get(path).status_code == 404
