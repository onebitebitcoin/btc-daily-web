import io

import httpx
from PIL import Image
from test_routes import reference_payload, seed_edition

from app.config import Settings, get_settings


def _fake_source_image_bytes(size: tuple[int, int] = (300, 200)) -> bytes:
    img = Image.new("RGB", size, color=(200, 50, 50))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _payload_with_image_url(date: str, url: str | None = "https://example.com/thumb.jpg"):
    payload = reference_payload(date)
    if url is None:
        payload["cards"][0]["media"] = None
    else:
        payload["cards"][0]["media"]["image"] = url
    return payload


def override_og_cache_dir(client, cache_dir) -> None:
    client.app.dependency_overrides[get_settings] = lambda: Settings(og_cache_dir=str(cache_dir))


# ---- GET /api/og/{date}/image.jpg ----


def test_og_image_generates_and_crops_to_1200x630(client, tmp_path, monkeypatch) -> None:
    override_og_cache_dir(client, tmp_path)
    seed_edition(client.session_factory, _payload_with_image_url("2026-07-30"))

    calls = []

    def fake_get(url, timeout=None, follow_redirects=None):
        calls.append(url)
        fake_request = httpx.Request("GET", url)
        return httpx.Response(200, content=_fake_source_image_bytes(), request=fake_request)

    monkeypatch.setattr("app.routes.httpx.get", fake_get)

    response = client.get("/api/og/2026-07-30/image.jpg")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    img = Image.open(io.BytesIO(response.content))
    assert img.size == (1200, 630)
    assert img.format == "JPEG"
    assert calls == ["https://example.com/thumb.jpg"]


def test_og_image_second_request_hits_cache(client, tmp_path, monkeypatch) -> None:
    override_og_cache_dir(client, tmp_path)
    seed_edition(client.session_factory, _payload_with_image_url("2026-07-30"))

    calls = []

    def fake_get(url, timeout=None, follow_redirects=None):
        calls.append(url)
        fake_request = httpx.Request("GET", url)
        return httpx.Response(200, content=_fake_source_image_bytes(), request=fake_request)

    monkeypatch.setattr("app.routes.httpx.get", fake_get)

    first = client.get("/api/og/2026-07-30/image.jpg")
    second = client.get("/api/og/2026-07-30/image.jpg")

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(calls) == 1


def test_og_image_missing_media_returns_404(client, tmp_path) -> None:
    override_og_cache_dir(client, tmp_path)
    seed_edition(client.session_factory, _payload_with_image_url("2026-07-30", url=None))

    response = client.get("/api/og/2026-07-30/image.jpg")

    assert response.status_code == 404


def test_og_image_missing_edition_returns_404(client, tmp_path) -> None:
    override_og_cache_dir(client, tmp_path)

    response = client.get("/api/og/2026-01-01/image.jpg")

    assert response.status_code == 404


# ---- GET /api/og/{date} and /api/og/latest ----


def test_og_html_contains_meta_tags(client) -> None:
    seed_edition(client.session_factory, _payload_with_image_url("2026-07-30"))

    response = client.get("/api/og/2026-07-30")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    body = response.text
    assert 'property="og:title" content="비트코인 하이라이트' in body
    assert '데일리 비트코인" />' in body
    assert 'property="og:description"' in body
    assert 'property="og:image" content="http://testserver/api/og/2026-07-30/image.jpg"' in body
    assert 'property="og:url" content="http://testserver/d/2026-07-30"' in body


def test_og_html_missing_date_returns_404(client) -> None:
    response = client.get("/api/og/2026-01-01")

    assert response.status_code == 404


def test_og_html_latest_picks_max_date(client) -> None:
    seed_edition(client.session_factory, _payload_with_image_url("2026-07-30"))
    later = _payload_with_image_url("2026-08-01")
    later["meta"]["slug"] = "btc-daily-0801"
    seed_edition(client.session_factory, later)

    response = client.get("/api/og/latest")

    assert response.status_code == 200
    assert 'property="og:url" content="http://testserver/d/2026-08-01"' in response.text


def test_og_html_latest_returns_404_when_empty(client) -> None:
    response = client.get("/api/og/latest")

    assert response.status_code == 404
