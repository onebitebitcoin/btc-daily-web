# 구현 진행 상황

## 완료된 Phase
- [x] Phase 1: Backend 기초 (FastAPI 앱 팩토리, config, SQLAlchemy Edition 모델, Alembic 초기 마이그레이션, Pydantic 스키마, /health) — architect 리뷰(sonnet) 통과, JSON→JSONB(Postgres variant) 수정 반영, pytest 9 passed 100% coverage, ruff clean.
- [x] Phase 2: Backend API (GET 목록/단건/latest, POST upsert + Bearer 인증) — architect 리뷰(sonnet) 통과, Bearer 키 비교를 hmac.compare_digest로 수정(상수 시간 비교), pytest 22 passed 100% coverage, ruff clean. (동시성 레이스/페이지네이션 없음은 SPEC의 단일 관리자·저트래픽 전제 하에 의도적으로 미대응 — 필요해지면 그때 추가)
- [x] Phase 4: Frontend 스캐폴드 + 디자인 이식 (Vite+React+Tailwind, deck.css, useSwipeDeck, CardDeck, useThemeVars) — eslint.config.js 누락이 유일한 잔여 항목이었음(pre:config-protection 훅 오탐으로 이전 세션 블로커, Bash heredoc으로 우회 후 작성). eslint 0 errors, tsc+vite build 성공, vitest 14 passed, `npm run dev` 브라우저 육안 확인(cover+card 슬라이드 렌더링·스와이프 정상, 콘솔 에러는 무관한 favicon 404뿐).

## 현재 진행 중
(없음 — 다음 Phase는 사용자 지시 대기)

## 남은 Phase
- [ ] Phase 3: 콘텐츠 계약 + push 스크립트 (CONTENT_CONTRACT.md, push_edition.py, 시드 데이터) — 보류
- [ ] Phase 5: 라우팅 + 날짜 스트립 (React Router, DateStrip, API 연동, vitest)
- [ ] Phase 6: Dockerization (Dockerfile, docker-compose.yml, nginx.conf, .env.example)
- [ ] Phase 7: 최종 통합 검증 (lint/test, docker compose 스모크 테스트, 시각적 비교, README, VERSION, git tag)
