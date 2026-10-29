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
      'btc-daily 스킬을 사용해 오늘자(Asia/Seoul 기준) 비트코인 카드뉴스 10장을 만들어 프로덕션 https://daily.onebitebitcoin.com 에 발행하라. 스킬 SKILL.md의 1~7단계를 하나도 빼지 말고 순서대로 수행한다. 이 세션은 비대화형(-p)이라 턴을 끝내면 그대로 종료되고 완료 알림을 받을 다음 턴이 없다 — 수집·Q&A 생성·발행 등 모든 스크립트는 백그라운드로 돌리지 말고 포그라운드에서 끝날 때까지 기다려라. "알림이 오면 진행하겠다"며 턴을 끝내지 말고 7단계 검증까지 마친 뒤에만 종료하라. 2.1단계(사용자 지정 뉴스)도 필수다 — pinned/오늘날짜.md 가 있으면 그 안의 항목을 하나도 빼지 말고 카드로 실어라. 지정 뉴스는 파일에 적힌 순서대로 1번 카드부터 맨 앞에 배치하고, 섬네일도 첫 번째 지정 뉴스를 기준으로 골라라. 시황 카드는 고정 번호 없이 트렌딩 순위대로 놓고, 시황 카드 시세 대조 규칙은 번호와 상관없이 그 카드에 적용한다. 24시간 게이트나 중복 점검으로 빼지 말되 원문 대조는 그대로 하고, 각 항목이 몇 번 카드로 나갔는지 마지막 보고에 적어라. 3.0.1.1단계(국내 소식 1장 확보)는 필수다 — 뉴스 8장 중 1장은 국내 소식에 배정하라. 다만 domestic 플래그는 제목 키워드 판정이라 해외 사건이 섞이므로, 그 기사가 실제로 한국에서 벌어진 일인지 본문으로 확인하고 넣어라. 쓸 만한 국내 후보가 없으면 비우되 후보가 몇 건이었고 각각 왜 못 썼는지 건별로 보고에 적어라. 특히 3.1단계(최근 발행분 대비 중복 점검)는 필수다 — recent_editions.py 를 돌려 최근 7일에 무엇이 나갔는지 먼저 보고 카드를 골라라. 2~3일 안의 재등장은 새 숫자나 새 국면이 있으면 괜찮지만, 최근 7일에 4장 이상 나갔거나 4일 이상 연속 나간 토픽, 어제 카드와 사실상 같은 사건인데 새 내용이 없는 후보는 빼고 다른 후보로 채워라(시황 카드는 예외). 무엇을 왜 뺐고 무엇으로 채웠는지 마지막 보고에 적어라. 5.1단계(24시간 트렌딩 토픽 10개)도 필수다 — trending 블록 없이 발행하지 마라. trending.note 는 draft의 trending_corpus.note 를 그대로 복사하고 집계 건수를 직접 어림해서 쓰지 마라. trending_candidates 가 10개 미만이라 트렌딩을 뺐다면 그 사실과 이유를 출력에 명시하라. 5.2단계(카드 순서 확정)도 필수다 — 트렌딩 10개가 정해지면 카드 순서를 지정 뉴스(파일 순서) → 나머지(시황 카드 포함)는 그 카드 사건이 걸린 트렌딩 토픽의 최고 순위 오름차순으로 다시 매기고, 같은 토픽끼리는 cluster_size 큰 것을 앞에, 트렌딩 어디에도 안 걸리는 카드는 뒤로 보내라. 지식 한입 카드는 11번째 맨 끝 그대로다. 중요도 눈대중으로 순서를 바꾸지 말고, 마지막 보고에 카드마다 어떤 트렌딩 순위·토픽에 걸려 그 자리에 놓였는지 적어라. 같은 단계에서 각 카드의 trend_rank 에 그 트렌딩 순위(1~10)를, 지정 뉴스 카드에 pinned: true 를 넣어라 — 카드 화제성 막대가 이 값으로 그려진다. 트렌딩에 안 걸린 카드는 trend_rank 를 넣지 말고, trending 블록을 뺀 날은 trend_rank 도 모두 빼라. 그와 별개로 뉴스 카드 10장 모두에 카드 화제성(heat)을 넣어라 — 카드마다 그 사건에만 걸리는 한글·영문 검색어를 drafts/heat-terms-오늘날짜.json 에 적고 scripts/card_heat.py 를 돌려라. 출력에 걸린 기사 제목을 보고 엉뚱한 기사가 걸렸으면 검색어를 좁히고 0건이면 표기를 더해 다시 돌려라. heat 가 없는 뉴스 카드가 있으면 push_edition.py 가 발행을 막는다. 수집 결과가 비었거나 소스가 죽어 있으면 더미 데이터로 대체하지 말고 그 자리에서 중단하라. 사실에 없는 숫자를 지어내지 마라. 4.1단계(사실관계 원문 대조)도 필수다 — 카드를 다 쓴 뒤 각 카드의 link.href 원문을 열어 다섯 가지를 확인하라: 한 문장에 서로 다른 기사의 수치를 섞지 않았는지, 기사 발행일과 사건 발생일이 어긋나지 않는지(9월 기사가 8월 데이터를 다루거나 유튜브 촬영일이 공개일보다 앞설 수 있다), 개인의 인터뷰·SNS 발언을 기관의 공식 발표로 격상하지 않았는지, 원문에 없는 최상급·비교급을 만들어 붙이지 않았는지, 큰 숫자의 성격(잔액인지 매각액인지, 누적인지 연간인지)과 영문 제목 표현의 뜻을 본문에서 확인했는지. 숫자가 들어간 카드와 기관·인물 발언을 인용한 카드는 반드시 원문을 열어라. 어긋나면 그 자리에서 고치고, 확인이 안 되는 수치는 빼고, 수치를 빼서 카드가 비면 다른 후보로 교체하라. 무엇을 어떻게 고쳤는지 마지막 보고에 적어라. 유튜브 후보의 요약은 그 자체가 틀릴 수 있으니 소스끼리 숫자가 어긋나면 웹으로 검증한 값을 써라. 유튜브 섬네일(i.ytimg.com)은 글자 그림이라 카드 그림으로 쓰지 말고, 영상의 핵심 낱말로 find_illustration.py 삽화를 찾아 붙여라. 섬네일(meta.og_image)은 5.9단계와 CONTENT_CONTRACT.md 4.2절대로 직접 골라 넣어라 — 카드 그림 중 한국 기사의 실사진을 카드 번호 순으로 먼저 보고, AI 생성 그림·알트코인(이더리움·솔라나·리플 등)이 보이는 그림·최근 발행분이 이미 쓴 섬네일은 건너뛰어라. 실사진이 그날 주제와 상관없는 범용 그림(모형 비트코인 동전 등)뿐이면 1번 카드 소재를 연상시키는 삽화를 find_illustration.py 로 찾아 섬네일로 쓰고, 같은 그림을 그 카드 media 에도 credit 과 함께 넣어라. 후보 그림은 반드시 열어서 눈으로 확인하라. 카드 그림에도 AI 생성 그림(토큰포스트 본문 그림, 매끈한 3D 렌더, 만화풍 콜라주)과 글자가 주인 그림(기사 제목 배너, 시리즈 템플릿, 매체 로고뿐인 기본 이미지, 인포그래픽)은 쓰지 말고 실사진이나 핵심 낱말 삽화로 바꿔라. 카드 그림이 없거나 아무 비트코인 사진(동전·키체인 등)뿐인 카드는 media: null 로 두지 말고, 그 기사의 핵심 낱말(예: 엔비디아 → 본사 사진, 계절성 통계 → 차트, 선거 → 투표 스티커)로 find_illustration.py 를 검색해 붙여라. 공포·탐욕 지수 카드는 scripts/fear_greed.py 가 주는 계기판 그림을 쓰되 본문이 인용한 값과 그림 값을 맞춰라. media: null 은 쓰지 마라 — 그림 없는 카드는 글자판으로 나가고 push_edition.py 가 막는다. 검색어가 안 맞으면 더 넓은 핵심 낱말로 다시 찾아라. 삽화는 find_illustration.py(Unsplash)로만 찾고, 카드에 고른 사진은 출력의 track 주소로 --track 을 한 번 돌리고 위키미디어 그림은 쓰지 마라(발행 서버가 429 를 받는다, push_edition.py 가 막는다). 이미지 프록시가 발행 직후 일시적으로 502 를 줘도 그림을 빼지 마라. ETF 자금 흐름 카드는 하루 1장으로 합치고, 트렌딩 상위에 국내 규제·과세 소재가 있으면 우선 실어라. 시황 카드의 가격은 발행 직전 시세(curl -s https://api.coinbase.com/v2/prices/BTC-USD/spot)와 대조하라. 마지막에 발행된 날짜, 섬네일로 고른 카드 번호와 이유, 카드 10장의 제목, 트렌딩 10개의 순위와 토픽을 출력하라.' \
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
