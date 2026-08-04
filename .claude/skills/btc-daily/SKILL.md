---
name: btc-daily
description: 최근 24시간 my-news + my-youtube 데이터로 오늘자 비트코인 카드뉴스 10장을 만들어 btc-daily-web에 발행한다. "btc daily", "오늘 카드뉴스", "카드뉴스 발행" 키워드로 트리거.
---

# btc-daily — 오늘자 카드뉴스 발행

명령 하나로 수집 → 카드 10장 작성 → 발행까지 끝낸다.
**문구를 쓰는 주체는 너(Claude)다.** 스크립트는 결정론적인 수집/조립/검증/발행만 한다.

프로젝트 루트: `/Users/nsw/Desktop/meeting_room/lab/btc-daily-web`

## 고정 포트 (이 머신 기준, 바꾸지 말 것)

| 대상 | 포트 |
|---|---|
| btc-daily-web backend | 8002 |
| btc-daily-web frontend | 5175 |
| my-news (소스) | 8000 |
| my-youtube (소스) | 23456 |

5173은 my-academy, 8000·8001은 my-news·exchange-fee가 이미 쓴다.

---

## 절차

### 1. 사전 확인

```bash
curl -s localhost:8002/health          # {"status":"ok"} 여야 함
curl -s -o /dev/null -w "%{http_code}" "http://localhost:8000/api/news?asset=btc&limit=1"
curl -s -o /dev/null -w "%{http_code}" "http://localhost:23456/api/queue"
```

백엔드가 안 떠 있으면 `bash scripts/dev.sh backend` 로 띄운다.
소스(8000/23456)가 죽어 있으면 **거기서 멈추고 사용자에게 알린다** — 더미 데이터로 대체 금지.

### 2. 수집

```bash
cd backend && source .venv/bin/activate && python scripts/collect_daily.py
```

→ `drafts/draft-<YYYY-MM-DD>.json` 생성. 구조:
- `skeleton` — `meta`/`theme`/`brand`/`cover`/`closing`이 이미 채워져 있다. **건드리지 마라.**
- `candidates.news[]` — 최근 24h 비트코인 기사 (중복 제외, 화제성 순)
- `candidates.videos[]` — 최근 24h 비트코인 유튜브 (조회수 순)
- `trending_candidates[]` — 트렌딩 토픽 후보 상위 15개 (5.1에서 쓴다)
- `trending_corpus` — 집계가 실제로 본 코퍼스 규모. `note` 문자열이 완성된 채로
  들어 있다. **5.1의 `note`는 이 값을 그대로 복사한다 — 직접 세거나 어림하지 마라.**

### 3. 카드 10장 선별

`draft-<date>.json`을 Read하고 후보에서 10건을 고른다.

- 기본 배분: **뉴스 8 + 유튜브 2**. 그날 물량에 따라 조정 가능.
- **주제 중복을 걷어낸다** — 같은 사건을 다룬 기사가 여러 건이면 가장 정보량 많은 하나만.
- 시황·온체인·규제·채굴·기관·보안 등 카테고리가 골고루 섞이게 한다.
- `num`은 1부터 10까지 순서대로. 중요도 높은 것을 앞에.

### 4. 문구 작성

`CONTENT_CONTRACT.md`의 톤 가이드를 따른다. 핵심 패턴:

| 필드 | 규칙 |
|---|---|
| `title` | 한국어 펀치라인. 사실 + 함의를 한 줄에. 예: `"연준 금리 동결에도 비트코인은 밀렸다"` |
| `subtitle` | 짧은 영문. 예: `"Fed Holds, BTC Slides"` |
| `chip.text` | 카테고리 한 단어 (시황/온체인/규제/채굴/기관/보안/레버리지/유튜브 화제) |
| `chip.emphasis` | `"primary"` \| `"secondary"` \| `null` 을 섞어 리듬을 준다 |
| `chips[]` | 해시태그 3개. 후보의 `tags`를 참고하되 그대로 베끼지 말 것 |
| `body` | **200자 내외** 한국어. 숫자와 고유명사를 살린다 |
| `quote` | 한 줄 촌철살인. 없으면 `null` (전부 채우지 말 것 — 8~9개 정도) |
| `link` | `{label: "<매체명> 원문", href: 후보의 url}` |
| `media` | `{image: 후보의 image_url 또는 유튜브 썸네일, href: null, cta: null}`. 이미지 없으면 `media: null` |

작성 규칙:
- 이모지 금지 (프로젝트 CLAUDE.md 규칙)
- 사실만. 후보 데이터에 없는 숫자를 지어내지 마라
- `body`에 인용구를 반복하지 마라
- **유튜브 썸네일 주의**: 썸네일은 채널이 만든 마케팅 그래픽이라 숫자가 크게 박혀 있고
  영상 내용·실제 사실과 어긋나는 경우가 있다. 썸네일에 숫자/단정 문구가 보이면 본문과
  충돌하지 않는지 확인하고, **충돌하면 그 카드는 `media: null`로 둔다.**
  (예: 2026-07-31 일본 세제 카드 — 썸네일 "22%" vs 정부안 실제 20% 분리과세)
- **숫자가 소스마다 다르면 지어내 맞추지 말고 웹으로 검증**한 뒤 검증된 값을 쓴다.
  `summary`는 my-youtube의 LLM이 생성한 것이라 그 자체가 틀릴 수 있다.

### 5. 조립

`skeleton`에 `cards` 배열을 넣는다. 이때 **`closing.sources`를 반드시 갱신한다** —
collector가 채워둔 값은 *후보 전체*의 매체 목록이라, 실제로 카드에 쓰지 않은 매체가
출처로 남는다. 선별한 10장의 `link.label`에 실제 등장한 매체만 남길 것.

`drafts/edition-<date>.json`으로 저장한다.

### 5.1. 트렌딩 토픽 정리 (24시간 트렌딩 카드) — **필수 단계**

이 카드는 12번째 슬라이드로 매일 나간다. 건너뛰지 마라.

draft의 `trending_candidates`(상위 15개, `backend/app/trending.py`의 `rank_topics`가
매체 다양성·최신성·유튜브 반응까지 반영해 계산한 점수순 후보)를 읽고 **의미가
겹치는 토픽을 하나로 묶어** 정확히 10개로 정리한다.

**이 병합 판단이 "단순 빈도가 아니라 무엇이 진짜 핫했는가"를 가리는 핵심이다.**
집계기는 태그 단위로 기계적으로 나누므로, 예를 들어 `SEC` · `클래리티 법안` ·
`암호화폐규제`처럼 사실상 한 사건(규제 입법)을 가리키는 태그가 후보에 따로 올라올
수 있다. 이런 항목은 사람이 읽었을 때 자연스러운 라벨 하나("규제·클래리티 법안")로
합친다 — 이건 스크립트가 할 수 없는 일이라 이 단계에서 네가 해야 한다.

병합·정리 후 각 항목에 채울 것:
- `topic`: 사람이 읽을 라벨 (후보의 원 태그를 그대로 쓰지 말고 다듬는다. 여러
  토픽을 합쳤으면 그중 가장 대표적인 이름이나 새 이름을 쓴다)
- `rank`: 1~10, 합친 뒤의 화제성(heat) 기준 내림차순
- `heat`/`mentions`/`sources`: 병합했다면 합쳐진 원소들의 값을 더해서 다시 계산
  (같은 기사가 두 후보 태그에 동시에 걸려 있었다면 중복으로 세지 않는다).
  병합하지 않았다면 후보 값 그대로 두되, `heat`는 최종 10개 중 1위가 100이 되도록
  다시 정규화한다.

`trending` 블록으로 조립해 `skeleton`에 얹는다(`cards`/`closing`과 같은 레벨의
최상위 키 — `CONTENT_CONTRACT.md` 1절 참고):

```json
"trending": {
  "eyebrow": "24H TRENDING",
  "title": "지난 24시간 가장 뜨거웠던 토픽",
  "note": "<draft의 trending_corpus.note 를 그대로>",
  "items": [
    {"rank": 1, "topic": "규제·클래리티 법안", "heat": 100, "mentions": 6, "sources": 4}
  ]
}
```

`note`는 draft의 `trending_corpus.note`를 **문자 그대로 복사한다**(예:
`"뉴스 205건 12매체 · 유튜브 19건 18채널 집계"`). 집계 규모를 눈대중으로 쓰면
카드에 틀린 숫자가 박힌다 — 스크립트가 세어서 넘겨주는 값이 있으니 그걸 쓴다.

프론트엔드가 이 블록이 있으면 클로징 바로 앞에 트렌딩 슬라이드를 자동으로 끼운다
(슬라이드 12장 → 13장, 트렌딩이 12번째).

**생략은 후보가 10개를 못 채울 때만이다.** `trending_candidates`가 10개 미만이면
(소스가 죽었거나 물량이 극단적으로 적었던 날) `trending`을 빼고 발행한다 —
optional 필드라 없으면 예전처럼 슬라이드 12장으로 나간다. 그 경우 **왜 뺐는지
사용자에게 반드시 보고한다.** 후보가 10개 이상인데 생략하는 것은 실패로 친다.

### 5.5. Q&A 생성

카드마다 예상 질문 3개 + Gemini의 Google Search 그라운딩 답변을 미리 만들어 굽는다
(방문자가 볼 때는 이미 완성된 정적 데이터 — 실시간 호출 없음):

```bash
cd backend && source .venv/bin/activate && python scripts/generate_qa.py ../drafts/edition-<date>.json
```

카드별로 1콜. 실패한 카드는 `qa: null`로 남고 스크립트는 계속 진행한다(전체 발행을
막지 않음) — stderr에 실패한 카드 번호가 찍힌다. 이미 `qa`가 있는 카드는 재호출하지
않는다(재발행 시 과금 방지); 전부 다시 만들려면 `--force`.

`GEMINI_API_KEY`가 `backend/.env`에 없으면 여기서 멈춘다 — 지어내지 말고 사용자에게 알린다.

### 6. 발행

**프로덕션으로 발행한다.** 수집·문구작성·Q&A는 로컬에서 했지만 결과물이 사는 곳은 서버다.

```bash
cd backend && source .venv/bin/activate && \
python scripts/push_edition.py ../drafts/edition-<date>.json --api https://daily.onebitebitcoin.com
```

`--api`를 빼면 로컬(`localhost:8002`)로 간다 — 리허설용으로만 쓴다.

스키마 위반이면 POST 전에 로컬에서 잡아준다. 어떤 필드가 틀렸는지 출력되니 고쳐서 재실행.

> `extra="forbid"`라 오타 키 하나만 있어도 실패한다. `theme` 16키 전부 필수,
> `closing.links`의 각 항목은 `label`/`href` 모두 필수.
>
> `cover가 meta.date와 불일치`가 뜨면 stale draft다. **가드를 우회하지 말고**
> 2단계부터 다시 해서 draft를 최신 코드로 재생성한다.

### 7. 검증 후 보고

```bash
curl -s "https://daily.onebitebitcoin.com/api/editions/<date>" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['meta']); print(len(d['cards']), '장')"
curl -s https://daily.onebitebitcoin.com/api/editions
```

사용자에게 보고할 것: 발행된 날짜, 카드 10장의 제목 목록,
사이트 URL(`https://daily.onebitebitcoin.com/d/<date>`).

---

## 실패 시

| 증상 | 원인 / 대응 |
|---|---|
| collect가 0건 반환 | 소스 서버가 죽었거나 24h 내 비트코인 데이터가 없음. 소스 상태부터 확인 |
| push 422 | 로컬 검증을 건너뛴 것. `push_edition.py`가 출력한 필드 경로를 보고 수정 |
| push 401 | `backend/.env`의 `ADMIN_API_KEY` 누락 |
| push 401 (프로덕션) | `backend/.env`의 `ADMIN_API_KEY`가 서버 `.env` 값과 달라졌다. 서버에서 `grep '^ADMIN_API_KEY=' ~/btc-daily-web/.env`로 대조 |
| 사이트에 안 뜸 | 프론트가 8002를 프록시하는지(`frontend/vite.config.ts`), 백엔드가 떠 있는지 확인 |
| Q&A 다 실패 | `backend/.env`의 `GEMINI_API_KEY` 확인. 일부만 실패는 정상 범위(카드별 독립) |
