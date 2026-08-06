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
| | `quote` | object \| null | | **선택 블록.** 표지 하단에 나가는 그날의 오스트리아학파 인용구. 07-27~08-07 발행분에는 없다. `collect_daily.py`가 자동으로 채우니 손으로 쓰지 마라 |
| | `quote.id` | str | quote 있으면 ✓ | `austrian_quotes.json`의 id. 렌더에 쓰이지 않지만 **다음 날 중복 회피가 이 값을 되읽는다** |
| | `quote.text` | str | quote 있으면 ✓ | 한국어 번역. 인용문이라 [2.1절](#21-어미--body와-quote는-했습니다체-2026-08-07-발행분부터)의 했습니다체 규칙에서 제외 |
| | `quote.author` | str | quote 있으면 ✓ | 예: `"루트비히 폰 미제스"` |
| | `quote.portrait` | str \| null | | 번들 초상 stem. null이면 이름을 조판한 아바타, [4장](#4-이미지-규칙) 참고 |
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
| | `links` | list[Link] | ✓ | 각 원소 `label`/`href` 모두 필수 |
| | `stamp` | str | ✓ | |
| | `restart` | str | ✓ | |
| | `sources` | list[str] | ✓ | 실제 수집된 `source_ref` 유니크 목록 |
| | `disclaimer` | str | ✓ | 면책 문구 |
| `trending` | — | object \| null | | **선택 블록.** 없으면 슬라이드 12장(표지+카드10+클로징), 있으면 클로징 앞에 트렌딩 슬라이드가 끼어 13장. 기존 발행분 9편에는 없다 |
| | `eyebrow` | str | trending 있으면 ✓ | |
| | `title` | str | trending 있으면 ✓ | |
| | `note` | str \| null | | 40자 이내 한 줄. draft의 `trending_corpus.note`를 그대로 복사한다 (예: `"뉴스 205건 12매체 · 유튜브 18건 17채널 집계"`) |
| | `items` | list[TrendingItem] | trending 있으면 ✓ | **정확히 10개, `rank`는 1~10 오름차순** — 아니면 422 |
| | `items[].rank` | int | ✓ | 1~10 |
| | `items[].topic` | str | ✓ | 사람이 읽을 라벨 (후보 태그를 그대로 쓰지 않고 다듬는다) |
| | `items[].heat` | int (0~100) | ✓ | 1위가 100이 되도록 정규화. 카드에서 막대 길이로 렌더 |
| | `items[].mentions` | int | ✓ | 그 토픽을 다룬 후보 기사/영상 수 |
| | `items[].sources` | int | ✓ | 서로 다른 매체 수 |
| | `items[].links` | list[TrendingLink] \| null | | 펼침 목록(새 탭 원문). 없으면 그 줄은 안 눌린다. draft의 `trending_candidates[].articles`에서 옮긴다 |
| | `items[].links[].title` | str | ✓ | 기사 원제 그대로. **카드의 `link`와 달리 label이 아니다** — 목록에서는 무슨 기사인지가 먼저 보여야 한다 |
| | `items[].links[].href` | str | ✓ | 원문 URL |
| | `items[].links[].source` | str \| null | | 매체명. 제목 아래 작게 붙는다 |

`trending`은 **단순 언급 빈도가 아니라 "무엇이 진짜 핫했는가"**를 보여주는 게
목적이다. `backend/app/trending.py`의 `rank_topics`가 매체 다양성에 지수를 줘
계산하고(같은 매체가 5번 쓴 것보다 매체 5곳이 한 번씩 다룬 게 더 핫하다),
`collect_daily.py`가 상위 15개를 draft의 `trending_candidates`에 남기면
`.claude/skills/btc-daily/SKILL.md` 5.1단계에서 사람(Claude)이 겹치는 토픽을
10개로 병합·라벨링해 이 블록을 만든다.

`note`에 들어갈 집계 규모는 같은 스크립트가 `trending_corpus`로 함께 남긴다.
문구는 Claude가 쓰지만 **이 숫자만은 세는 것이지 쓰는 게 아니라서**, draft에
없으면 무인 발행이 "N건 집계"를 지어내게 된다.

## 2. 톤 가이드

`reference/content.json`의 실제 카드 패턴을 따른다:

- **`quote`**: 12자 내외 임팩트 한 줄. ("금리는 멈췄는데, 시장은 안 멈췄습니다.")
- **`title`**: 펀치라인형 헤드라인, 한 문장. ("연준 금리 동결에도 비트코인은 밀렸다")
- **`subtitle`**: 영문 요약, `title`의 짧은 재진술. ("Fed Holds, BTC Slides")
- **`chips`**: 정확히 3개, `#`로 시작하는 키워드.
- **`body`**: 200자 내외. 무슨 일이 있었는지 → 왜 중요한지 순서로 2~3문장.
- **`link`**: 원문 기사/영상 URL. 후보에 없으면 카드 자체를 스킵.

### 2.1. 어미 — `body`와 `quote`는 했습니다체 (2026-08-07 발행분부터)

읽는 사람에게 말을 거는 자리라 평서체("~했다", "~이다")는 딱딱하다. **`body`와
`quote`는 `-습니다`/`-ㅂ니다`로 끝낸다.** 이미 습니다체인 `qa[].answer`와도 톤이 맞는다.

| 필드 | 어미 | 예 |
|---|---|---|
| `body` | 했습니다체 | "…분수령입니다." / "…봤습니다." |
| `quote` | 했습니다체 | "지지선이 버티는 동안은 아직 하락장이 아닙니다." |
| `qa[].answer` | 했습니다체 | (Gemini가 이미 이렇게 생성한다) |
| `title` | **평서체 유지** | "비트코인, 박스권 상단을 다시 두드린다" |
| `subtitle` | 영문 | "Bitcoin Retests the Range Top" |

`title`은 헤드라인이라 예외다 — 습니다체로 늘이면 카드뉴스 제목 관례에서 벗어나고
줄이 길어진다.

### 2.2. 표기 용어집

번역·음차가 갈리는 고유명사는 여기 적힌 쪽으로 통일한다. 후보 데이터(`summary`)의
표기가 달라도 이 표를 따른다 — 수집원마다 제각각이라 그대로 쓰면 날마다 흔들린다.

| 원문 | 쓸 표기 | 쓰지 말 것 |
|---|---|---|
| Galaxy / Galaxy Digital | 갤럭시 / 갤럭시디지털 | 갈럭시 |
| BTC (한국어 문장 안에서) | 비트코인 | BTC |

`BTC` 금지는 프로젝트 `CLAUDE.md`의 규칙이다. 전체가 영문인 `subtitle`은 예외.

> 새 표기 분쟁이 생기면 고친 뒤 이 표에 한 줄 추가한다. 표에 없으면 다음 발행 때
> 같은 실수가 반복된다.

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
2. `check_cover_matches_date`로 `cover.mark`/`cover.meta[2]`가 `meta.date`에서
   파생된 값인지 확인 — stale draft가 DB의 올바른 cover를 되돌리는 사고를 막는다.
   여기서 걸리면 draft를 최신 코드로 재생성해야 하며, **가드를 우회하지 않는다**.
3. `check_wording`(`app/wording.py`)으로 **문구 게이트** — 2.1(어미)·2.2(표기
   용어집) 위반이면 어느 카드 어느 필드인지 찍고 POST 없이 종료. `meta.date`가
   계약 발효일(2026-08-07) 이전이면 건너뛴다(과거 발행분은 평서체·`BTC` 표기가
   섞여 있어, 소급 적용하면 오타 수정 재발행이 막힌다). 이 가드도 우회 옵션이 없다.
4. `backend/.env`(절대경로로 탐색)에서 `ADMIN_API_KEY` 로드. 없으면 실패.
5. `POST {api}/api/editions` (`--api` 기본값 `http://localhost:8002`).

> 게이트는 **표에 적힌 것만** 잡는다. 오역이나 어색한 음차처럼 판단이 필요한 문제는
> 걸러내지 못하므로, 새 사례가 나오면 고친 뒤 2.2절 표에 한 줄 추가한다.

### 프로덕션 발행

수집 소스(my-news `:8000`, my-youtube `:23456`)는 개발 머신에만 있으므로,
수집·문구작성·Q&A 생성은 로컬에서 하고 **마지막 발행만 프로덕션을 향한다**:

```bash
python scripts/push_edition.py ../drafts/edition-<date>.json \
  --api https://daily.onebitebitcoin.com
```

- `backend/.env`의 `ADMIN_API_KEY`가 **서버 `.env`의 값과 같아야** 한다. 다르면 401.
- 같은 `meta.date`로 다시 보내면 upsert다 — 오타 수정 후 재발행이 안전하다.
- 발행 확인: `curl -s https://daily.onebitebitcoin.com/api/editions`

## 4. 이미지 규칙

`media.image`는 **stem(번들 asset 파일명)과 절대 URL 둘 다 허용**된다
(`frontend/src/imageUrl.ts`의 `cardImageSrc`가 둘 다 해석). 시드 fixture 9장은
전부 stem(`fed-macro` 등, `frontend/src/assets/media/`에 실물 파일 존재).
자동 발행 파이프라인(`scripts/collect_daily.py` → 이 계약)은 **원본 썸네일
URL을 그대로 쓴다** — 발행 시점에는 다운로드/재호스팅을 하지 않는다.
대신 프론트가 절대 URL을 `/api/img/{date}/{num}` 프록시로 돌려 WebP로 줄여
받는다(원본 평균 380KB → 약 35KB). 계약에는 원본 URL을 그대로 넣으면 된다:
- 뉴스: 후보의 `image_url` 그대로.
- 유튜브: `https://i.ytimg.com/vi/{video_id}/hqdefault.jpg`.

이미지가 없는 후보는 `media: null`로 둔다 — 가짜 URL이나 플레이스홀더로
채우지 않는다. 개발자 포럼·레딧처럼 대표 이미지를 주지 않는 소스, 그리고 썸네일이
본문과 어긋나 일부러 뺀 카드까지 합쳐 하루 10장 중 0~3장이 여기 해당한다.

`media: null`인 카드는 프론트가 이미지 자리를 비우지 않고 **카드가 이미 가진 문구를
조판해 채운다**(`CardArtFallback`). 고르는 순서는 `quote` → `subtitle` → `chip.text`
→ 카드 번호다. `quote`가 1순위인 이유는 카드 표면에 나오지 않는 유일한 필드라
중복 없이 정보가 하나 늘기 때문이다. 부제가 아트로 올라간 카드는 본문에서 같은 줄을
빼 메아리를 없앤다. 따라서 **`quote`를 채워 두면 이미지 없는 카드의 완성도가 올라간다.**

### 4.1. 표지 인용구의 화자 초상 (`cover.quote.portrait`)

뉴스 이미지와 규칙이 다르다. 원격 URL을 쓰지 않고 **저장소에 번들한 파일**
(`frontend/src/assets/portraits/<stem>.jpg`)만 참조한다 — 매일 같은 몇 장이
반복되므로 프록시를 태울 이유가 없다.

**퍼블릭 도메인 사진만 담는다.** 공개 사이트라 CC BY-SA 사진은 저작자·라이선스
표기 줄이 따라붙어야 하는데, 그 줄이 인용구보다 길어져 표지가 지저분해진다.

2026-08-07 기준 위키미디어 공용을 확인한 결과:

| 인물 | 초상 | 근거 |
|---|---|---|
| 카를 멩거 | O | Public domain |
| 오이겐 폰 뵘바베르크 | O | Public domain |
| 루트비히 폰 미제스 | X | CC BY-SA 3.0뿐 |
| 프리드리히 하이에크 | X | CC BY-SA 3.0뿐 |
| 머리 로스바드 | X | CC BY 3.0뿐 |
| 헨리 해즐릿 | X | PD 사진 없음(1951년 방송 영상만 PD) |

그래서 **인용구 27개 중 3개만 사진이고 24개는 `portrait: null`**이다. null이면
프론트가 이름을 조판한 원형 아바타를 그린다(`SpeakerAvatar`) — 이미지 없는 카드를
`CardArtFallback`이 다루는 방식과 같은 태도다.

초상을 추가할 때는 `austrian_quotes.json`의 `portrait_source`(위키미디어 파일
페이지 URL)와 `portrait_license`를 반드시 함께 채운다. 빈 값이면 테스트가 막는다.
**라이선스가 애매하면 사진을 넣지 않고 아바타로 간다.**
