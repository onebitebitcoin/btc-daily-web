# 구현 진행 상황 — 표지 오스트리아학파 인용구 + 초상

계획: `~/.claude/plans/crispy-meandering-panda.md`

## 완료된 Phase

- [x] Phase 1: 인용구 풀 27개 + 선택 로직 + 테스트 13건 (b9ebea0)
      하이에크 10 · 미제스 8 · 로스바드 3 · 해즐릿 3 · 멩거 2 · 뵘바베르크 1
- [x] Phase 2: `CoverQuote` 스키마(optional) + `collect_daily` 배선 (a889cd4)
- [x] Phase 3: PD 초상 2장 + `SpeakerAvatar`/`CoverSlide`/CSS (dd9c886)
      **라이선스 결과: PD는 멩거·뵘바베르크뿐** — 미제스/하이에크/로스바드는 CC BY(-SA),
      해즐릿은 PD 사진 없음. 27개 중 3개만 사진, 24개는 조판 아바타.
- [x] Phase 4: `CONTENT_CONTRACT.md` 1절·4.1절 + `SKILL.md` 2단계 + 버전 0.16.0

## 남은 일 — 배포 (사용자 작업)

**프로덕션 서버가 아직 옛 스키마라 `cover.quote`를 422로 거부한다.** 코드는 다 됐고
로컬 발행은 되지만, 배포 전까지 프로덕션에는 인용구가 실리지 않는다.

```bash
git push                                        # 8개 커밋 + 0.16.0
ssh <VPS> 'cd ~/btc-daily-web && git pull && docker compose up -d --build'
```

배포 후 8/7 재발행 (draft에 인용구가 이미 들어 있다):

```bash
cd backend && source .venv/bin/activate
python scripts/push_edition.py ../drafts/edition-2026-08-07.json \
  --api https://daily.onebitebitcoin.com
```

> **경고**: 배포 전에 내일 06:00 배치가 돌면 `collect_daily`가 draft에 `cover.quote`를
> 넣고 `push_edition`이 422로 실패해 **그날 발행이 통째로 안 나간다.** 배포를 06:00
> 전에 끝내거나, 미룰 거면 알려달라 — 서버가 거부하면 인용구만 빼고 재시도하는
> 안전망을 넣겠다.
