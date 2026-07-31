# CONTENT_CONTRACT — 에디션 JSON 계약

`btc-daily-web`이 `POST /api/editions`로 받는 JSON의 실제 계약이다. 원본
카드뉴스 템플릿 문서(`reference/template-field-reference.md`)를 베이스로 하되,
이 프로젝트의 `backend/app/schemas.py`(pydantic, `extra="forbid"`)가 강제하는
실제 델타를 반영한다. **스키마와 이 문서가 다르면 스키마가 맞다** —
`backend/app/schemas.py`를 최종 소스로 본다.

## 1. 필드 표 (실제 스키마 기준)

전 모델이 `extra="forbid"`다 — 표에 없는 키를 보내면 `POST /api/editions`가
422를 반환한다. 오타 하나로 조용히 무시되는 필드는 없다.

| 블록 | 필드 | 타입 | 필수 | 비고 |
|---|---|---|---|---|
| `meta` | `title` | str | ✓ | `<title>` |
| | `slug` | str | ✓ | 출력용 식별자 |
| | `date` | str(`YYYY-MM-DD`) | ✓ | **템플릿 원본에 없던 필드 — 라우팅 키(`GET /api/editions/{date}`)로 신규 추가됨** |
| `theme` | `bg`,`bg2`,`bg_light`,`bg2_light`,`paper`,`paper2`,`ink`,`ink_dim`,`accent`,`accent_strong`,`glow`,`accent2`,`accent2_light`,`line`,`chip_bg`,`seg_off` | str | ✓ (16개 전부) | 템플릿 문서는 "4~6쌍"이라 썼지만 실제 스키마는 **16개 키 전부 필수** — 하나라도 빠지면 422 |
| `brand` | — | str | ✓ | 좌상단 라벨 |
| `cover` | `eyebrow` | str | ✓ | |
| | `mark` | list[str] | ✓ | 줄바꿈 배열 |
| | `meta` | list[str] | ✓ | 관례상 3개(수집기간/소스/날짜) |
| | `hint` | str | ✓ | |
| `cards` | `num` | int | ✓ | |
| | `chip.text` | str | ✓ | |
| | `chip.emphasis` | `"primary"` \| `"secondary"` \| null | | |
| | `title` | str | ✓ | |
| | `subtitle` | str | ✓ | |
| | `chips_label` | str | ✓ | |
| | `chips` | list[str] | ✓ | |
| | `body` | str | ✓ | |
| | `quote` | str \| null | | |
| | `link.label`, `link.href` | str | link 있으면 둘 다 ✓ | 없으면 `link: null` |
| | `media.image` | str | media 있으면 ✓ | stem 또는 URL, [4장](#4-이미지-규칙) 참고 |
| | `media.href`, `media.cta` | str \| null | | 없으면 `media: null` |
| `closing` | `eyebrow` | str | ✓ | |
| | `mark_lines` | list[str] | ✓ | 마지막 줄만 강조색 |
| | `rows` | list[[str, str]] | ✓ | **각 원소는 정확히 2개짜리 쌍이어야 함** — `["k"]`나 `["k","v","w"]`는 422 |
| | `stamp` | str | ✓ | |
| | `restart` | str | ✓ | |
| | `sources` | list[str] | ✓ | 실제 수집된 `source_ref` 유니크 목록 |

## 2. 톤 가이드

`reference/content.json`의 실제 카드 패턴을 따른다:

- **`quote`**: 12자 내외 임팩트 한 줄. ("금리는 멈췄는데, 시장은 안 멈췄다.")
- **`title`**: 펀치라인형 헤드라인, 한 문장. ("연준 금리 동결에도 비트코인은 밀렸다")
- **`subtitle`**: 영문 요약, `title`의 짧은 재진술. ("Fed Holds, BTC Slides")
- **`chips`**: 정확히 3개, `#`로 시작하는 키워드.
- **`body`**: 200자 내외. 무슨 일이 있었는지 → 왜 중요한지 순서로 2~3문장.
- **`link`**: 원문 기사/영상 URL. 후보에 없으면 카드 자체를 스킵.

## 3. 발행 방법

```bash
cd backend
source .venv/bin/activate
python scripts/push_edition.py drafts/edition-<date>.json
# 또는 meta.date와 교차검증하며:
python scripts/push_edition.py drafts/edition-<date>.json --date <date>
```

내부 동작:
1. `app.schemas.EditionContent`로 **로컬 선검증** — 여기서 실패하면 서버에
   아무것도 보내지 않고 어떤 필드가 왜 틀렸는지 출력 후 종료.
2. `backend/.env`(절대경로로 탐색)에서 `ADMIN_API_KEY` 로드. 없으면 실패.
3. `POST {api}/api/editions` (`--api` 기본값 `http://localhost:8002`).

## 4. 이미지 규칙

`media.image`는 **stem(번들 asset 파일명)과 절대 URL 둘 다 허용**된다
(`frontend/src/CardDeck.tsx`의 `CardArt`가 둘 다 해석). 시드 fixture 9장은
전부 stem(`fed-macro` 등, `frontend/src/assets/media/`에 실물 파일 존재).
자동 발행 파이프라인(`scripts/collect_daily.py` → 이 계약)은 **원본 썸네일
URL을 그대로 쓴다** — 다운로드/재호스팅 없음:
- 뉴스: 후보의 `image_url` 그대로.
- 유튜브: `https://i.ytimg.com/vi/{video_id}/hqdefault.jpg`.

이미지가 없는 후보는 `media: null`로 둔다 — 가짜 URL이나 플레이스홀더로
채우지 않는다.
