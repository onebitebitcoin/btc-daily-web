#!/bin/zsh
# btc-daily 무인 발행 러너. launchd(com.nsw.btc-daily-oneshot)가 호출한다.
# ponytail: 원샷 전용 — 실행 후 스스로 launchd에서 내려간다. 매일 돌리려면 아래 self-unload 블록을 지우고
#           plist의 StartCalendarInterval에서 Month/Day를 빼면 된다.
set -u

ROOT=/Users/nsw/Desktop/meeting_room/lab/btc-daily-web
LABEL=com.nsw.btc-daily-oneshot
LOG="$ROOT/logs/daily-cron-$(date +%F).log"
mkdir -p "$ROOT/logs"

cd "$ROOT" || exit 1

{
  echo "=== $(date '+%F %T %Z') start ==="

  # 소스가 죽어 있으면 시작도 하지 않는다 (더미 발행 방지)
  news=$(curl -s -m 10 -o /dev/null -w "%{http_code}" "http://localhost:8000/api/news?asset=btc&limit=1")
  yt=$(curl -s -m 10 -o /dev/null -w "%{http_code}" "http://localhost:23456/api/queue")
  echo "source check: my-news=$news my-youtube=$yt"
  if [[ "$news" != "200" || "$yt" != "200" ]]; then
    echo "ABORT: 소스 서버 비정상 — 발행하지 않음"
    exit 1
  fi

  /Users/nsw/.local/bin/claude -p \
    'btc-daily 스킬을 사용해 오늘자(Asia/Seoul 기준) 비트코인 카드뉴스 10장을 만들어 프로덕션 https://daily.onebitebitcoin.com 에 발행하라. 스킬 SKILL.md의 1~7단계를 하나도 빼지 말고 순서대로 수행한다. 수집 결과가 비었거나 소스가 죽어 있으면 더미 데이터로 대체하지 말고 그 자리에서 중단하라. 사실에 없는 숫자를 지어내지 마라. 마지막에 발행된 날짜와 카드 10장의 제목을 출력하라.' \
    --model claude-opus-5 \
    --dangerously-skip-permissions \
    --output-format text
  status=$?

  echo "=== $(date '+%F %T %Z') claude exit=$status ==="
} >> "$LOG" 2>&1

# 원샷: 발행 성패와 무관하게 스스로 내려간다 (내년 8/3 재발화 방지)
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
