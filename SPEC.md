# btc-daily-web — SPEC

## 배경

`card-news/btc-daily-0730/`은 매일 사람(에이전트 세션)이 `content.json`을 손으로 채우고
`build.py`로 base64 내장 단일 정적 HTML을 구워 Claude Artifact로 발행하는 방식이었다.
이 프로젝트는 그 워크플로우를 실서비스 웹사이트로 승격한다: 데이터는 백엔드 DB에서
서빙되고, 매일 새 날짜의 카드 10장이 쌓이며, 상단에 날짜를 가로 스크롤로 탐색하는
네비게이션이 새로 생긴다. 디자인은 기존 정적 카드뉴스와 100% 동일해야 한다.

## 범위

- **BTC 데일리 시리즈 전용.** `card-news/`의 다른 시리즈(ai-daily, harness-engineering-101,
  kr-crypto-tax-timeline, dynamic-duo-album-1)는 이 프로젝트와 무관 — 손대지 않는다.
- 콘텐츠 큐레이션 파이프라인(뉴스/유튜브 수집 → 카드 10장 선별)은 이 프로젝트 범위 밖.
  **다른 Claude 에이전트 세션이 오늘처럼 수작업으로 만들고, 정해진 포맷으로 push한다.**
  이 저장소는 그 push를 받는 백엔드 + 그걸 보여주는 프론트만 만든다.

## 기술 스택 (고정)

| 영역 | 기술 |
|---|---|
| Frontend | React + Vite + TailwindCSS |
| Backend | Python + FastAPI + SQLAlchemy |
| DB | SQLite(개발) / PostgreSQL(프로덕션) |
| 배포 | Docker Compose, 자체 관리 VPS + Nginx(리버스프록시 + TLS) |

## 데이터 모델

테이블 1개, 정규화하지 않는다 — 항상 "그 날짜 통째로" 읽고 쓰지, 카드 단위 쿼리가
없어서 관계형으로 쪼갤 이유가 없다(YAGNI).

```
editions
  date        DATE PRIMARY KEY      -- ISO, 예: 2026-07-30
  slug        TEXT UNIQUE NOT NULL  -- 예: btc-daily-0730
  title       TEXT NOT NULL         -- content.meta.title
  content     JSONB NOT NULL        -- 아래 "콘텐츠 스키마" 전체
  created_at  TIMESTAMPTZ NOT NULL
  updated_at  TIMESTAMPTZ NOT NULL
```

`content` JSONB는 `reference/content.json`과 동일한 구조
(`meta/theme/brand/cover/cards[]/closing`, 필드 정의는
`reference/template-field-reference.md` 표 참고) + 새 필수 필드 `meta.date`(ISO,
DB 키와 반드시 일치) 하나만 추가.

## 백엔드 API

| 메서드/경로 | 인증 | 설명 |
|---|---|---|
| `GET /health` | 없음 | 헬스체크 |
| `GET /api/editions` | 없음 | 목록 `[{date, slug, title}]` (content 제외, 날짜 스트립용, 오름차순) |
| `GET /api/editions/latest` | 없음 | 가장 최근 날짜의 전체 편집본 (`GET /api/editions/{date}`와 동일 응답 모양) |
| `GET /api/editions/{date}` | 없음 | 그 날짜의 전체 `content` JSON. 없으면 404 |
| `POST /api/editions` | `Authorization: Bearer <API_KEY>` | upsert. body는 `content.json` 스키마 그대로 + `meta.date`. Pydantic 검증 실패 시 422, 키 불일치 401 |

로그인/유저 테이블 없음 — 발행 주체가 사람이 아니라 스크립트라서 정적 API 키 하나로
충분. 키는 백엔드 env(`ADMIN_API_KEY`)로 관리.

## 콘텐츠 계약 (다른 에이전트용)

`CONTENT_CONTRACT.md`를 루트에 작성한다. 내용:
- `reference/template-field-reference.md`의 필드 표를 그대로 가져오되 `meta.date` 필드 추가.
- 톤 가이드: 기존 `reference/content.json`의 카드들(짧은 인용구 `quote` + 헤드라인 `title` +
  태그 3개 `chips[]` + 200자 내외 `body`) 패턴을 예시로 명시.
- 발행 방법: `push_edition.py --date 2026-07-30 path/to/content.json` 사용법.
  스크립트는 로컬에서 스키마를 먼저 검증하고, `ADMIN_API_KEY` 환경변수로 `POST /api/editions` 호출.
- 이미지: 카드뉴스 정적 생성기(`build.py`)처럼 base64 내장은 안 한다 — 이미지가 있는 카드는
  `media.image`에 공개 URL을 넣는다(정적 생성기와 계약이 달라지는 유일한 지점, 계약서에
  명시적으로 적을 것).

## 프론트엔드

- 라우팅: `/` → `/d/<최신 날짜>` 리다이렉트, `/d/:date` → 그 날짜의 카드덱. 없는 날짜면 404 페이지.
- **디자인 이식 원칙**: `reference/template.html`의 `<style>` 블록을 선택자/클래스명 그대로
  `deck.css`로 옮긴다(디자인 100% 동일 보장의 핵심). 같은 파일의 ~270줄 바닐라 JS 스와이프
  컨트롤러(scroll-snap 기반 + IntersectionObserver로 현재 카드 추적 + 키보드 nav + 진행 세그먼트
  + prev/next 버튼)는 `useSwipeDeck` 훅으로 그대로 포팅한다. DOM 구조/클래스명을 바꾸지 않아야
  CSS를 안 건드리고 그대로 쓸 수 있다.
- 테마: `content.theme`를 오늘처럼 CSS 변수로 매핑하되, 날짜마다 다를 수 있으므로 빌드타임이
  아니라 **런타임**에 선택된 편집본의 값으로 `:root` 변수를 주입한다.
- **새 기능 — 날짜 스트립**: `GET /api/editions` 목록을 상단에 가로 스크롤 pill 리스트로
  렌더링. `overflow-x:auto; scroll-snap-type:x proximity` 네이티브 스크롤만 쓰고 캐러셀
  라이브러리는 안 쓴다. pill 클릭 → `/d/:date`로 라우트 전환(아래 카드덱 전체 리로드) →
  선택된 pill을 `scrollIntoView({inline:'center'})`로 자동 중앙 정렬.
- 라이트/다크 테마 토글은 기존 정적 버전과 동일하게 유지(`data-theme` 속성 방식).

## 배포

`docker-compose.yml`:
- `postgres` (named volume, healthcheck)
- `backend` (uvicorn, 컨테이너 시작 시 `alembic upgrade head`)
- `frontend` (멀티스테이지: `vite build` → 정적 파일만 남김)
- `nginx` (frontend 정적 서빙 + `/api/*` → backend 리버스프록시 + TLS. 도메인/인증서는
  `.env`의 `DOMAIN`/`CERTBOT_EMAIL`로 설정 — 실제 발급은 배포 시점에 수행, 지금은
  플레이스홀더로 구조만 갖춘다)

WebSocket/SSE 없음 — 데일리 데이터지 실시간이 아니다. 필요해지면 그때 추가.

## 테스트

- 백엔드: pytest — POST 스키마 검증/401/404, GET 목록·단건·latest, 커버리지 80%+.
- 프론트: vitest — DateStrip 렌더/스크롤 정렬, CardDeck 스와이프·키보드 네비게이션.

## Phase 분할 (대규모 작업 — PROGRESS.md로 추적)

1. **Backend 기초** — FastAPI 앱 팩토리, config(env), SQLAlchemy `Edition` 모델,
   Alembic 초기 마이그레이션, Pydantic 스키마(콘텐츠 계약 그대로 + `meta.date`), `/health`.
2. **Backend API** — 4개 엔드포인트 구현(목록/단건/latest/POST), Bearer 인증, 에러 처리,
   pytest 80%+.
3. **콘텐츠 계약 + push 스크립트** — `CONTENT_CONTRACT.md`, `push_edition.py`,
   `reference/content.json`을 `meta.date` 붙여 시드 데이터로 변환.
4. **Frontend 스캐폴드 + 디자인 이식** — Vite+React+Tailwind 스켈레톤, `deck.css` 포팅,
   `useSwipeDeck` 훅 포팅, CardDeck 컴포넌트(cover/cards/closing 렌더), 런타임 테마 주입.
5. **라우팅 + 날짜 스트립** — React Router, DateStrip 컴포넌트, API 연동, 로딩/404 처리,
   vitest.
6. **Dockerization** — Dockerfile(backend/frontend), docker-compose.yml, nginx.conf,
   `.env.example`.
7. **최종 통합 검증** — 전체 lint/test, `docker compose up` 로컬 스모크 테스트, seed
   데이터로 원본 정적 btc-daily-0730과 시각적 비교, README, VERSION(0.1.0), git tag v0.1.0.

## 명시적으로 안 하는 것 (YAGNI)

- 콘텐츠 자동 생성/수집 파이프라인 (다른 에이전트가 수작업으로 push)
- 로그인/유저 관리 (API 키만)
- 카드 단위 정규화 스키마
- WebSocket/SSE 실시간 갱신
- 다른 카드뉴스 시리즈 지원
