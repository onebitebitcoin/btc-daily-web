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

# 실패는 조용히 지나가면 안 된다 — 하루치 발행이 통째로 빠져도 로그를 열어보기
# 전까지 아무도 모른다(2026-09-06 사고). 중단 지점마다 텔레그램으로 알린다.
NOTIFY="$HOME/.claude/scripts/launchd-notify-failure.sh"
notify_fail() {  # $1=사유  $2=종료코드
  [[ -x "$NOTIFY" ]] && "$NOTIFY" "com.nsw.btc-daily" "${2:-1}" "$1" "$LOG" >/dev/null 2>&1
}

{
  today=$(date +%F)
  echo "=== $(date '+%F %T %Z') start ($today) ==="

  # 이미 발행됐으면 재발행하지 않는다
  if curl -s -m 15 -o /dev/null -w "%{http_code}" "$API/api/editions/$today" | grep -q '^200$'; then
    echo "SKIP: $today 에디션이 이미 있다"
    exit 0
  fi

  # 소스가 죽어 있으면 시작도 하지 않는다 (더미 발행 방지)
  #
  # 2026-09-06 발행 누락: my-youtube(serve.py)가 스레드/커넥션 누수로 응답 불능이라
  # 헬스체크가 000 을 받고 abort 했다. 한 번의 000 으로 하루를 통째로 건너뛰지 않도록
  # 20초 간격으로 3회까지 재시도한다. 3회 모두 실패면 서버가 정말 죽은 것이다.
  check() {  # $1=url  → 마지막 http_code 를 echo
    local code=""
    for _ in 1 2 3; do
      code=$(curl -s -m 20 -o /dev/null -w "%{http_code}" "$1")
      [[ "$code" == "200" ]] && break
      sleep 20
    done
    echo "$code"
  }

  news=$(check "http://localhost:8000/api/news?asset=btc&limit=1")
  yt=$(check "http://localhost:23456/api/queue")
  echo "source check: my-news=$news my-youtube=$yt"
  if [[ "$news" != "200" || "$yt" != "200" ]]; then
    echo "ABORT: 소스 서버 비정상 — 발행하지 않음"
    notify_fail "소스 서버 비정상 (my-news=$news my-youtube=$yt)" 1
    exit 1
  fi

  # 137(=128+9)은 외부에서 보낸 SIGKILL 이다. 2026-09-17 에 syspolicyd 가 폭주해
  # Gatekeeper 가 claude 를 악성코드로 오판정했고, 8분쯤 돌던 발행이 그대로 끊겨
  # 하루치가 빠졌다. 메모리 압박(jetsam)으로도 같은 코드가 나온다. 어느 쪽이든
  # 발행 내용의 문제가 아니라 머신 사정이므로 한 번은 다시 시도한다.
  attempt=1
  while true; do
    /Users/nsw/.local/bin/claude -p \
      'btc-daily 스킬을 사용해 오늘자(Asia/Seoul 기준) 비트코인 카드뉴스 10장을 만들어 프로덕션 https://daily.onebitebitcoin.com 에 발행하라. 스킬 SKILL.md의 1~7단계를 하나도 빼지 말고 순서대로 수행한다. 3.0.1.1단계(국내 소식 1장 확보)는 필수다 — 뉴스 8장 중 1장은 국내 소식에 배정하라. 다만 domestic 플래그는 제목 키워드 판정이라 해외 사건이 섞이므로, 그 기사가 실제로 한국에서 벌어진 일인지 본문으로 확인하고 넣어라. 쓸 만한 국내 후보가 없으면 비우되 후보가 몇 건이었고 각각 왜 못 썼는지 건별로 보고에 적어라. 특히 3.1단계(최근 발행분 대비 중복 점검)는 필수다 — recent_editions.py 를 돌려 최근 7일에 무엇이 나갔는지 먼저 보고 카드를 골라라. 2~3일 안의 재등장은 새 숫자나 새 국면이 있으면 괜찮지만, 최근 7일에 4장 이상 나갔거나 4일 이상 연속 나간 토픽, 어제 카드와 사실상 같은 사건인데 새 내용이 없는 후보는 빼고 다른 후보로 채워라(시황 카드는 예외). 무엇을 왜 뺐고 무엇으로 채웠는지 마지막 보고에 적어라. 5.1단계(24시간 트렌딩 토픽 10개)도 필수다 — trending 블록 없이 발행하지 마라. trending.note 는 draft의 trending_corpus.note 를 그대로 복사하고 집계 건수를 직접 어림해서 쓰지 마라. trending_candidates 가 10개 미만이라 트렌딩을 뺐다면 그 사실과 이유를 출력에 명시하라. 수집 결과가 비었거나 소스가 죽어 있으면 더미 데이터로 대체하지 말고 그 자리에서 중단하라. 사실에 없는 숫자를 지어내지 마라. 4.1단계(사실관계 원문 대조)도 필수다 — 카드를 다 쓴 뒤 각 카드의 link.href 원문을 열어 다섯 가지를 확인하라: 한 문장에 서로 다른 기사의 수치를 섞지 않았는지, 기사 발행일과 사건 발생일이 어긋나지 않는지(9월 기사가 8월 데이터를 다루거나 유튜브 촬영일이 공개일보다 앞설 수 있다), 개인의 인터뷰·SNS 발언을 기관의 공식 발표로 격상하지 않았는지, 원문에 없는 최상급·비교급을 만들어 붙이지 않았는지, 큰 숫자의 성격(잔액인지 매각액인지, 누적인지 연간인지)과 영문 제목 표현의 뜻을 본문에서 확인했는지. 숫자가 들어간 카드와 기관·인물 발언을 인용한 카드는 반드시 원문을 열어라. 어긋나면 그 자리에서 고치고, 확인이 안 되는 수치는 빼고, 수치를 빼서 카드가 비면 다른 후보로 교체하라. 무엇을 어떻게 고쳤는지 마지막 보고에 적어라. 유튜브 후보의 요약은 그 자체가 틀릴 수 있으니 소스끼리 숫자가 어긋나면 웹으로 검증한 값을 써라. 썸네일 문구가 본문과 충돌하면 그 카드는 media를 null로 둬라. 마지막에 발행된 날짜, 카드 10장의 제목, 트렌딩 10개의 순위와 토픽을 출력하라.' \
      --model claude-sonnet-5 \
      --dangerously-skip-permissions \
      --output-format text
    # zsh에서 status 는 $? 의 예약 별칭이라 대입하면 스크립트가 그 자리에서 죽는다.
    rc=$?
    echo "=== $(date '+%F %T %Z') claude exit=$rc (시도 $attempt/2) ==="

    [[ "$rc" != "137" || "$attempt" -ge 2 ]] && break

    echo "--- SIGKILL 감지 — 120초 뒤 재시도한다 ---"
    sleep 120

    # 죽기 직전에 발행까지는 끝냈을 수 있다. 재시도 전에 확인해 같은 날짜를 두 번
    # 올리는 일을 막는다.
    if curl -s -m 15 -o /dev/null -w "%{http_code}" "$API/api/editions/$today" | grep -q '^200$'; then
      echo "재시도 생략: 다시 보니 $today 에디션이 이미 올라가 있다"
      rc=0
      break
    fi
    attempt=$((attempt + 1))
  done

  if [[ "$rc" != "0" ]]; then
    if [[ "$attempt" -ge 2 ]]; then
      notify_fail "claude 발행 실패 — SIGKILL 후 재시도까지 실패" "$rc"
    else
      notify_fail "claude 발행 실패" "$rc"
    fi
  fi

  # claude 가 0 을 반환해도 실제로 올라갔는지는 별개다 — 프로덕션에 오늘자
  # 에디션이 없으면 실패로 친다.
  final=$(curl -s -m 15 -o /dev/null -w "%{http_code}" "$API/api/editions/$today")
  if [[ "$final" != "200" ]]; then
    echo "VERIFY FAIL: 발행 후에도 $today 에디션이 없다 (http=$final)"
    notify_fail "발행 후 검증 실패 — $today 에디션 없음 (http=$final)" "$rc"
  else
    echo "VERIFY OK: $today 에디션 확인"
  fi
} >> "$LOG" 2>&1
