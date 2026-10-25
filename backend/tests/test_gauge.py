import datetime
import io

import pytest
from PIL import Image

from app.gauge import classify, render_fear_greed_png


@pytest.mark.parametrize(
    ("value", "name"),
    [(0, "EXTREME FEAR"), (24, "EXTREME FEAR"), (25, "FEAR"), (46, "NEUTRAL"),
     (55, "NEUTRAL"), (56, "GREED"), (76, "EXTREME GREED"), (100, "EXTREME GREED")],
)
def test_classify_follows_alternative_me_bands(value: int, name: str) -> None:
    assert classify(value)[0] == name


def test_same_value_renders_same_picture() -> None:
    """지난 에디션의 그림이 그날 값에 고정돼야 한다."""
    day = datetime.date(2026, 10, 24)

    assert render_fear_greed_png(46, day) == render_fear_greed_png(46, day)
    assert render_fear_greed_png(46, day) != render_fear_greed_png(47, day)


def test_gauge_endpoint_returns_png(client) -> None:
    response = client.get("/api/gauge/fear-greed.png?value=46&date=2026-10-24")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert "immutable" in response.headers["cache-control"]
    assert Image.open(io.BytesIO(response.content)).size == (1200, 800)


@pytest.mark.parametrize("query", ["value=-1", "value=101", "value=abc", ""])
def test_gauge_endpoint_rejects_out_of_range(client, query: str) -> None:
    assert client.get(f"/api/gauge/fear-greed.png?{query}").status_code == 422
