# 구현 진행 상황

## 완료된 Phase
- [x] Phase 1: Backend 기초 (FastAPI 앱 팩토리, config, SQLAlchemy Edition 모델, Alembic 초기 마이그레이션, Pydantic 스키마, /health) — architect 리뷰(sonnet) 통과, JSON→JSONB(Postgres variant) 수정 반영, pytest 9 passed 100% coverage, ruff clean.
- [x] Phase 2: Backend API (GET 목록/단건/latest, POST upsert + Bearer 인증) — architect 리뷰(sonnet) 통과, Bearer 키 비교를 hmac.compare_digest로 수정(상수 시간 비교), pytest 22 passed 100% coverage, ruff clean. (동시성 레이스/페이지네이션 없음은 SPEC의 단일 관리자·저트래픽 전제 하에 의도적으로 미대응 — 필요해지면 그때 추가)
- [x] Phase 4: Frontend 스캐폴드 + 디자인 이식 (Vite+React+Tailwind, deck.css, useSwipeDeck, CardDeck, useThemeVars) — eslint.config.js 누락이 유일한 잔여 항목이었음(pre:config-protection 훅 오탐으로 이전 세션 블로커, Bash heredoc으로 우회 후 작성). eslint 0 errors, tsc+vite build 성공, vitest 14 passed, `npm run dev` 브라우저 육안 확인(cover+card 슬라이드 렌더링·스와이프 정상, 콘솔 에러는 무관한 favicon 404뿐).

- [x] Phase 3: 콘텐츠 계약 + push 스크립트 (CONTENT_CONTRACT.md, backend/scripts/push_edition.py) — SPEC 원안대로 구현하되 시드 변환은 불필요했음(`frontend/src/fixtures/content.json`이 이미 `meta.date` 포함 변환본). `app.schemas.EditionContent` 재사용해 POST 전 로컬 선검증. 직접 실행 시 `sys.path[0]`이 `scripts/`가 되어 `app` import가 깨지는 버그를 발견·수정(pytest는 `pythonpath=["."]` 덕에 통과해서 안 잡혔음).
- [x] Phase 5: 라우팅 + 날짜 스트립 (react-router-dom 7.18.2, DateStrip, EditionPage, API 연동) — `/`→최신날짜 리다이렉트, `/d/:date`, 404 화면. `deck.css`는 한 줄도 안 고치고 `strip.css`의 `.shell > .app` 특정성 오버라이드로 `.app{height:100dvh}` + `body{overflow:hidden}` 제약 해결. `CardDeck`의 media 해석을 stem/URL 양쪽 지원으로 확장(1줄). eslint 0, tsc 0, vitest 18 passed(기존 14 + 신규 4), build 성공.
- [x] Phase 8(신규): 콘텐츠 자동 수집 파이프라인 — SPEC이 YAGNI로 제외했던 항목을 사용자 요청으로 추가. 앱 코드가 아닌 `backend/scripts/`에 두어 SPEC 범위는 유지. `collect_daily.py`가 my-news(:8000)·my-youtube(:23456)에서 최근 24h BTC 데이터를 결정론적으로 수집·랭킹하고 skeleton을 조립, 문구 작성은 `/btc-daily` 스킬로 Claude 세션이 담당(LLM API 미연동 — 사용자 결정). CORS 미들웨어 + `redirect_slashes=False` + `scripts/dev.sh`(포트 8002/5175 고정) 추가. 실제 2026-07-31자 카드 10장 발행 후 Playwright 육안 검증 완료. `collect_daily.py`에 `--date` 백필 버그 있었음(과거 날짜를 줘도 항상 "지금부터 24h"만 봄) — `window_end()` 추가해 과거 날짜는 그날 자정(KST) 기준 24h 창으로 전환, 07-27~07-30 4일치(40장) 백필 완료. `cover.mark`가 매일 고정("비트코인/하이라이트")이던 것도 `[N월 N일, 비트코인 카드뉴스]`로 날짜별 생성하게 수정 + 기발행 5일치 소급 갱신.
- [x] Phase 9(신규): 카드별 AI 예상 질문 3개 + Gemini 웹검색 답변 — 발행 시점에 미리 생성해 카드 JSON에 굽는 방식(실시간 호출 아님, 사용자 결정), `GEMINI_API_KEY`는 my-news 것 재사용. `schemas.py`에 `QA(_Strict)` 모델 + `Card.qa` 옵션 필드 추가. `backend/scripts/generate_qa.py` 신규 — 카드당 Gemini Interactions API 1콜(`tools:[google_search]` + `response_format` JSON 스키마 강제, 질문/답변/출처를 한 번에), 실패한 카드는 `qa:null`로 두고 전체 발행은 막지 않음, 이미 `qa` 있는 카드는 스킵(`--force`로 강제). 실사용 스모크 테스트 중 가끔 마크다운 코드펜스로 감싸 응답하는 것 발견 → 스트립 처리 + 카드당 1회 재시도 추가. 프론트는 `<details>/<summary>` 네이티브(React state 0)로 `qa-block` 렌더, `qa.css` 신규 파일(deck.css는 안 건드림). pytest 44 passed, vitest 20 passed, 2026-07-31 10장 전체 Q&A 생성+발행 후 Playwright로 펼치기 동작 육안 확인.

## 현재 진행 중
(없음 — 다음 Phase는 사용자 지시 대기)

## 남은 Phase
- [ ] Phase 6: Dockerization (Dockerfile, docker-compose.yml, nginx.conf, .env.example)
- [ ] Phase 7: 최종 통합 검증 (lint/test, docker compose 스모크 테스트, 시각적 비교, README, VERSION, git tag)
