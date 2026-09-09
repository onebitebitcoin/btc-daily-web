import datetime
import io

import httpx
from PIL import Image
from test_routes import reference_payload, seed_edition

from app.config import Settings, get_settings
from app.models import Edition
from app.og import source_fingerprint


def _fake_source_image_bytes(size: tuple[int, int] = (300, 200)) -> bytes:
    img = Image.new("RGB", size, color=(200, 50, 50))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _republish(session_factory, content) -> None:
    """이미 있는 날짜의 내용을 갈아끼운다 — seed_edition은 새 행을 넣어 PK가 충돌한다."""
    with session_factory() as session:
        edition = session.get(Edition, datetime.date.fromisoformat(content["meta"]["date"]))
        edition.content = content
        session.commit()


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


def test_og_image_has_logo_badge_in_bottom_right(client, tmp_path, monkeypatch) -> None:
    override_og_cache_dir(client, tmp_path)
    seed_edition(client.session_factory, _payload_with_image_url("2026-07-30"))

    def fake_get(url, timeout=None, follow_redirects=None):
        fake_request = httpx.Request("GET", url)
        return httpx.Response(200, content=_fake_source_image_bytes(), request=fake_request)

    monkeypatch.setattr("app.routes.httpx.get", fake_get)

    response = client.get("/api/og/2026-07-30/image.jpg")

    img = Image.open(io.BytesIO(response.content))
    # source is a flat (200, 50, 50) fill — the badge/ring paste overwrites it near
    # the bottom-right corner, so that pixel should no longer be the background color.
    badge_center = (img.width - 76, img.height - 76)
    assert img.getpixel(badge_center) != (200, 50, 50)


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


def test_og_image_prefers_meta_og_image_over_card_one(client, tmp_path, monkeypatch) -> None:
    """meta.og_image가 있으면 카드 1의 그림 대신 그것을 가져온다."""
    override_og_cache_dir(client, tmp_path)
    payload = _payload_with_image_url("2026-07-30", url="https://example.com/card-one.jpg")
    payload["meta"]["og_image"] = "https://example.com/thumbnail.jpg"
    seed_edition(client.session_factory, payload)

    calls = []

    def fake_get(url, timeout=None, follow_redirects=None):
        calls.append(url)
        fake_request = httpx.Request("GET", url)
        return httpx.Response(200, content=_fake_source_image_bytes(), request=fake_request)

    monkeypatch.setattr("app.routes.httpx.get", fake_get)

    response = client.get("/api/og/2026-07-30/image.jpg")

    assert response.status_code == 200
    assert calls == ["https://example.com/thumbnail.jpg"]


def test_og_image_falls_back_to_card_one_when_override_absent(
    client, tmp_path, monkeypatch
) -> None:
    """meta.og_image가 없는 과거 에디션은 예전대로 카드 1의 그림을 쓴다."""
    override_og_cache_dir(client, tmp_path)
    payload = _payload_with_image_url("2026-07-30", url="https://example.com/card-one.jpg")
    payload["meta"].pop("og_image", None)
    seed_edition(client.session_factory, payload)

    calls = []

    def fake_get(url, timeout=None, follow_redirects=None):
        calls.append(url)
        fake_request = httpx.Request("GET", url)
        return httpx.Response(200, content=_fake_source_image_bytes(), request=fake_request)

    monkeypatch.setattr("app.routes.httpx.get", fake_get)

    response = client.get("/api/og/2026-07-30/image.jpg")

    assert response.status_code == 200
    assert calls == ["https://example.com/card-one.jpg"]


def test_og_image_rebuilds_when_source_changes(client, tmp_path, monkeypatch) -> None:
    """같은 날짜를 다른 썸네일로 재발행하면 캐시가 아니라 새 원본을 굽는다.

    지문 없이 날짜만으로 캐시하던 시절에는 여기서 옛 그림이 계속 나갔다.
    """
    override_og_cache_dir(client, tmp_path)
    payload = _payload_with_image_url("2026-07-30", url="https://example.com/old.jpg")
    seed_edition(client.session_factory, payload)

    calls = []

    def fake_get(url, timeout=None, follow_redirects=None):
        calls.append(url)
        fake_request = httpx.Request("GET", url)
        return httpx.Response(200, content=_fake_source_image_bytes(), request=fake_request)

    monkeypatch.setattr("app.routes.httpx.get", fake_get)

    assert client.get("/api/og/2026-07-30/image.jpg").status_code == 200

    republished = _payload_with_image_url("2026-07-30", url="https://example.com/old.jpg")
    republished["meta"]["og_image"] = "https://example.com/new.jpg"
    _republish(client.session_factory, republished)

    assert client.get("/api/og/2026-07-30/image.jpg").status_code == 200
    assert calls == ["https://example.com/old.jpg", "https://example.com/new.jpg"]


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
    expected_image = (
        "http://testserver/api/og/2026-07-30/image.jpg"
        f"?v={source_fingerprint('https://example.com/thumb.jpg')}"
    )
    assert f'property="og:image" content="{expected_image}"' in body
    assert f'name="twitter:image" content="{expected_image}"' in body
    assert 'property="og:url" content="http://testserver/d/2026-07-30"' in body


def test_og_html_image_url_changes_with_thumbnail(client) -> None:
    """썸네일을 바꾸면 og:image 주소도 달라진다 — 엣지/SNS 캐시가 새로 받도록."""
    before = _payload_with_image_url("2026-07-30")
    seed_edition(client.session_factory, before)
    first = client.get("/api/og/2026-07-30").text

    after = _payload_with_image_url("2026-07-30")
    after["meta"]["og_image"] = "https://example.com/other.jpg"
    _republish(client.session_factory, after)
    second = client.get("/api/og/2026-07-30").text

    assert source_fingerprint("https://example.com/thumb.jpg") in first
    assert source_fingerprint("https://example.com/other.jpg") in second
    assert first != second


def test_og_html_image_url_has_no_version_without_source(client) -> None:
    """카드에 이미지가 없는 날은 붙일 지문이 없으므로 쿼리 없이 나간다."""
    seed_edition(client.session_factory, _payload_with_image_url("2026-07-30", url=None))

    body = client.get("/api/og/2026-07-30").text

    assert 'property="og:image" content="http://testserver/api/og/2026-07-30/image.jpg"' in body


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
