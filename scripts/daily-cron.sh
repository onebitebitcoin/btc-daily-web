#!/bin/zsh
# btc-daily 무인 발행 러너. launchd(com.nsw.btc-daily)가 매일 06:00 KST 에 호출한다.
#
# 오늘자 에디션이 이미 프로덕션에 있으면 아무것도 하지 않는다 — 맥이 자다 깨서 늦게
# 발화하거나 수동으로 한 번 돌린 뒤에 또 발화해도 같은 날짜를 덮어쓰지 않게 한다.
set -u

ROOT=/Users/nsw/meeting_room/lab/btc-daily-web
API=https://daily.onebitebitcoin.com
LOG="$ROOT/logs/daily-cron-$(date +%F).log"
mkdir -p "$ROOT/logs"

cd "$ROOT" || exit 1

{
  today=$(date +%F)
  echo "=== $(date '+%F %T %Z') start ($today) ==="

  # 이미 발행됐으면 재발행하지 않는다
  if curl -s -m 15 -o /dev/null -w "%{http_code}" "$API/api/editions/$today" | grep -q '^200$'; then
    echo "SKIP: $today 에디션이 이미 있다"
    exit 0
  fi

  # 소스가 죽어 있으면 시작도 하지 않는다 (더미 발행 방지)
  news=$(curl -s -m 10 -o /dev/null -w "%{http_code}" "http://localhost:8000/api/news?asset=btc&limit=1")
  yt=$(curl -s -m 10 -o /dev/null -w "%{http_code}" "http://localhost:23456/api/queue")
  echo "source check: my-news=$news my-youtube=$yt"
  if [[ "$news" != "200" || "$yt" != "200" ]]; then
    echo "ABORT: 소스 서버 비정상 — 발행하지 않음"
    exit 1
  fi

  /Users/nsw/.local/bin/claude -p \
    'btc-daily 스킬을 사용해 오늘자(Asia/Seoul 기준) 비트코인 카드뉴스 10장을 만들어 프로덕션 https://daily.onebitebitcoin.com 에 발행하라. 스킬 SKILL.md의 1~7단계를 하나도 빼지 말고 순서대로 수행한다. 특히 3.1단계(최근 발행분 대비 중복 점검)는 필수다 — recent_editions.py 를 돌려 최근 7일에 무엇이 나갔는지 먼저 보고 카드를 골라라. 2~3일 안의 재등장은 새 숫자나 새 국면이 있으면 괜찮지만, 최근 7일에 4장 이상 나갔거나 4일 이상 연속 나간 토픽, 어제 카드와 사실상 같은 사건인데 새 내용이 없는 후보는 빼고 다른 후보로 채워라(시황 카드는 예외). 무엇을 왜 뺐고 무엇으로 채웠는지 마지막 보고에 적어라. 5.1단계(24시간 트렌딩 토픽 10개)도 필수다 — trending 블록 없이 발행하지 마라. trending.note 는 draft의 trending_corpus.note 를 그대로 복사하고 집계 건수를 직접 어림해서 쓰지 마라. trending_candidates 가 10개 미만이라 트렌딩을 뺐다면 그 사실과 이유를 출력에 명시하라. 수집 결과가 비었거나 소스가 죽어 있으면 더미 데이터로 대체하지 말고 그 자리에서 중단하라. 사실에 없는 숫자를 지어내지 마라. 유튜브 후보의 요약은 그 자체가 틀릴 수 있으니 소스끼리 숫자가 어긋나면 웹으로 검증한 값을 써라. 썸네일 문구가 본문과 충돌하면 그 카드는 media를 null로 둬라. 마지막에 발행된 날짜, 카드 10장의 제목, 트렌딩 10개의 순위와 토픽을 출력하라.' \
    --model claude-opus-5 \
    --dangerously-skip-permissions \
    --output-format text
  # zsh에서 status 는 $? 의 예약 별칭이라 대입하면 스크립트가 그 자리에서 죽는다.
  rc=$?

  echo "=== $(date '+%F %T %Z') claude exit=$rc ==="
} >> "$LOG" 2>&1
