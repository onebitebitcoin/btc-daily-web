"""공포·탐욕 지수 계기판 그림.

지수를 다루는 카드에 붙일 실사진이 없다. alternative.me 가 주는 그림은 매일 값이
바뀌어서, 카드가 인용한 값(매체마다 산출처가 다르다 — 2026-10-24 EBN 은 46, 같은 날
alternative.me 는 51)과 다른 숫자를 보여 준다. 그래서 값을 URL 로 받아 직접 그린다.
같은 값이면 같은 그림이므로 지난 에디션의 그림도 그날 값에 고정된다.
"""

import datetime
import io
import math

from PIL import Image, ImageDraw, ImageFont

SIZE = (1200, 800)
BACKGROUND = (250, 248, 243)
INK = (34, 34, 34)
INK_DIM = (120, 120, 120)

# alternative.me 의 구간 경계를 따른다. (상한, 이름, 색)
BANDS = (
    (24, "EXTREME FEAR", (214, 69, 65)),
    (44, "FEAR", (236, 138, 72)),
    (55, "NEUTRAL", (232, 196, 70)),
    (75, "GREED", (139, 190, 90)),
    (100, "EXTREME GREED", (52, 152, 92)),
)

CENTER = (600, 560)
RADIUS = 380
RING_WIDTH = 70


def classify(value: int) -> tuple[str, tuple[int, int, int]]:
    for upper, name, color in BANDS:
        if value <= upper:
            return name, color
    raise ValueError(f"value out of range: {value}")


def _angle(value: float) -> float:
    """0 은 왼쪽 끝(180도), 100 은 오른쪽 끝(360도). PIL 각도는 시계 방향이다."""
    return 180 + 180 * value / 100


def _point(angle_deg: float, radius: float) -> tuple[float, float]:
    rad = math.radians(angle_deg)
    return CENTER[0] + radius * math.cos(rad), CENTER[1] + radius * math.sin(rad)


def render_fear_greed_png(value: int, as_of: datetime.date | None = None) -> bytes:
    name, color = classify(value)
    img = Image.new("RGB", SIZE, BACKGROUND)
    draw = ImageDraw.Draw(img)
    box = (
        CENTER[0] - RADIUS,
        CENTER[1] - RADIUS,
        CENTER[0] + RADIUS,
        CENTER[1] + RADIUS,
    )

    lower = 0
    for upper, _, band_color in BANDS:
        draw.arc(box, _angle(lower), _angle(upper), fill=band_color, width=RING_WIDTH)
        lower = upper

    # 중심까지 긋지 않고 고리 안쪽에 짧게만 그린다 — 50 근처에서 숫자와 겹친다.
    inner = _point(_angle(value), RADIUS - RING_WIDTH - 90)
    tip = _point(_angle(value), RADIUS - RING_WIDTH - 12)
    draw.line([inner, tip], fill=INK, width=16)
    draw.ellipse((tip[0] - 14, tip[1] - 14, tip[0] + 14, tip[1] + 14), fill=INK)

    title_font = ImageFont.load_default(size=44)
    value_font = ImageFont.load_default(size=150)
    label_font = ImageFont.load_default(size=56)
    small_font = ImageFont.load_default(size=34)

    draw.text((600, 70), "FEAR & GREED INDEX", font=title_font, fill=INK_DIM, anchor="mm")
    draw.text((600, 450), str(value), font=value_font, fill=INK, anchor="mm")
    draw.text((600, 655), name, font=label_font, fill=color, anchor="mm")
    draw.text((CENTER[0] - RADIUS, 620), "0", font=small_font, fill=INK_DIM, anchor="mm")
    draw.text((CENTER[0] + RADIUS, 620), "100", font=small_font, fill=INK_DIM, anchor="mm")
    if as_of is not None:
        draw.text((600, 740), as_of.isoformat(), font=small_font, fill=INK_DIM, anchor="mm")

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
