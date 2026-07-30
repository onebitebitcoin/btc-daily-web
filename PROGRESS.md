# 구현 진행 상황

## 완료된 Phase
- [x] Phase 1: Backend 기초 (FastAPI 앱 팩토리, config, SQLAlchemy Edition 모델, Alembic 초기 마이그레이션, Pydantic 스키마, /health) — commit 다음 참조. architect 리뷰(sonnet) 통과, JSON→JSONB(Postgres variant) 수정 반영, pytest 9 passed 100% coverage, ruff clean.

## 현재 진행 중
- [ ] Phase 2: Backend API (목록/단건/latest/POST 엔드포인트, Bearer 인증, 에러 처리, pytest 80%+)

## 남은 Phase
- [ ] Phase 3: 콘텐츠 계약 + push 스크립트 (CONTENT_CONTRACT.md, push_edition.py, 시드 데이터)
- [ ] Phase 4: Frontend 스캐폴드 + 디자인 이식 (Vite+React+Tailwind, deck.css, useSwipeDeck, CardDeck)
- [ ] Phase 5: 라우팅 + 날짜 스트립 (React Router, DateStrip, API 연동, vitest)
- [ ] Phase 6: Dockerization (Dockerfile, docker-compose.yml, nginx.conf, .env.example)
- [ ] Phase 7: 최종 통합 검증 (lint/test, docker compose 스모크 테스트, 시각적 비교, README, VERSION, git tag)
