import pytest

from app.youtube import fill_card_thumbnails, video_id


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://youtu.be/zsL6sABQ_Ec", "zsL6sABQ_Ec"),
        ("https://www.youtube.com/watch?v=zsL6sABQ_Ec", "zsL6sABQ_Ec"),
        ("https://m.youtube.com/watch?v=zsL6sABQ_Ec", "zsL6sABQ_Ec"),
        ("https://i.ytimg.com/vi/zsL6sABQ_Ec/hqdefault.jpg", "zsL6sABQ_Ec"),
        ("https://www.tokenpost.kr/news/blockchain/409563", None),
        ("https://youtu.be/", None),
        ("not a url at all", None),
    ],
)
def test_video_id_reads_the_forms_the_pipeline_makes(url: str, expected: str | None) -> None:
    assert video_id(url) == expected


def card(num: int, href: str | None = None, media: dict | None = None) -> dict:
    return {
        "num": num,
        "title": f"카드 {num}",
        "link": {"href": href} if href else None,
        "media": media,
    }


def test_fills_thumbnail_for_a_youtube_card_with_no_media() -> None:
    """2026-09-18 편 10번 카드가 media: {} 로 발행돼 썸네일 자리가 비었다."""
    content = {"cards": [card(1, "https://youtu.be/zsL6sABQ_Ec", {})]}

    filled = fill_card_thumbnails(content)

    assert filled["cards"][0]["media"]["image"] == (
        "https://i.ytimg.com/vi/zsL6sABQ_Ec/hqdefault.jpg"
    )


def test_fills_thumbnail_when_media_is_null() -> None:
    content = {"cards": [card(1, "https://www.youtube.com/watch?v=abc123", None)]}

    filled = fill_card_thumbnails(content)

    assert filled["cards"][0]["media"]["image"] == "https://i.ytimg.com/vi/abc123/hqdefault.jpg"


def test_keeps_other_media_keys() -> None:
    # href·cta 는 카드가 쓰던 값이다. 썸네일을 채우면서 지우면 안 된다.
    content = {"cards": [card(1, "https://youtu.be/abc123", {"href": "x", "cta": "보기"})]}

    media = fill_card_thumbnails(content)["cards"][0]["media"]

    assert media["href"] == "x"
    assert media["cta"] == "보기"


def test_never_overwrites_an_existing_image() -> None:
    """발행자가 썸네일 대신 다른 그림을 고른 카드가 있다. 그 선택을 덮지 않는다."""
    chosen = "https://cdn.example/chosen.jpg"
    content = {"cards": [card(1, "https://youtu.be/abc123", {"image": chosen})]}

    assert fill_card_thumbnails(content)["cards"][0]["media"]["image"] == chosen


def test_leaves_non_youtube_cards_alone() -> None:
    content = {"cards": [card(1, "https://www.tokenpost.kr/news/blockchain/409563", {})]}

    assert fill_card_thumbnails(content)["cards"][0]["media"] == {}


def test_returns_the_original_when_nothing_changes() -> None:
    # 대부분의 편은 손댈 카드가 없다. 쓸데없는 사본을 만들지 않는다.
    content = {"cards": [card(1, "https://example.com/news", None)]}

    assert fill_card_thumbnails(content) is content


def test_tolerates_broken_shapes() -> None:
    # 저장된 내용이 계약과 어긋나도 500 을 내면 안 된다.
    assert fill_card_thumbnails({}) == {}
    assert fill_card_thumbnails({"cards": None}) == {"cards": None}
    assert fill_card_thumbnails({"cards": ["문자열"]}) == {"cards": ["문자열"]}
