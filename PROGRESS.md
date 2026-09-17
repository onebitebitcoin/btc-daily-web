# 구현 진행 상황

카드 공유 · 좋아요 기능 (계획: ~/.claude/plans/deep-forging-hippo.md)

## 완료된 Phase
- [x] Phase 1: 백엔드 — 좋아요 저장소와 API (c4284ba)
  - `CardLike` 모델 + 마이그레이션 `a44f83ab724b`
  - `GET /api/editions/{date}/likes`, `POST`/`DELETE /api/editions/{date}/cards/{num}/like`
- [x] Phase 2: 백엔드 + nginx — 카드별 링크 미리보기 (백엔드 301 테스트 통과)
  - `og.py` 에 `pick_card` 추가, 제목·설명·이미지·og:url 이 카드별로 갈린다
  - `GET /api/og/{date}/{index}`, `GET /api/og/{date}/{index}/image.jpg`
  - `frontend/nginx.conf` 의 `/d/` location 을 카드용·날짜용 둘로 분리

## 현재 진행 중
- [ ] Phase 3: 프론트엔드 — 공유·좋아요 UI

## 남은 Phase
- [ ] Phase 4: 통합 검증과 배포(버전 0.22.0)
