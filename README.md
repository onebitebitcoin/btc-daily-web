# btc-daily-web

매일 한 편씩 쌓이는 비트코인 카드뉴스 웹사이트. 쇼츠처럼 세로로 스크롤해 카드
10장을 읽고, 마지막 카드 다음에 바로 지난 날짜가 이어진다(최대 7일). 특정 날짜는
상단 날짜 칩의 달력에서 고른다.

- 프로덕션: <https://daily.onebitebitcoin.com>
- 스펙: [SPEC.md](SPEC.md) · 콘텐츠 계약: [CONTENT_CONTRACT.md](CONTENT_CONTRACT.md)

## 구조

| 경로 | 내용 |
|---|---|
| `backend/` | FastAPI + SQLAlchemy + Alembic. 엔드포인트 5개(`/health`, 목록/단건/latest/POST) + OG 미리보기용 3개(`/api/og/{date}`, `/api/og/latest`, `/api/og/{date}/image.jpg`) + 이미지 프록시 1개(`/api/img/{date}/{num}`) |
| `backend/scripts/` | 수집·Q&A 생성·발행 스크립트(앱 코드 아님) |
| `frontend/` | React + Vite + Tailwind. 세로 스냅 피드(`ShortsFeed`), 스타일은 `feed.css`·`chrome.css` |
| `deploy/` | 호스트 nginx vhost, DB 백업 스크립트 |

콘텐츠는 이 저장소가 만들지 않는다 — 다른 Claude 세션이 `/btc-daily` 스킬로 만들어
`POST /api/editions`로 밀어 넣는다.

## 로컬 개발

포트는 고정이다(다른 프로젝트와 충돌 방지): 백엔드 `8002`, 프론트 `5175`.

```bash
bash scripts/dev.sh            # 둘 다
bash scripts/dev.sh backend    # 하나씩
```

lint / test:

```bash
cd backend  && ruff check . && pytest      # 52 tests
cd frontend && npm run lint && npm run test && npm run build   # 27 tests
```

> 저장소 루트가 체크아웃돼 있어야 한다. `backend/tests`가 `../reference/content.json`을
> 읽으므로 `backend/`만 떼어내면 테스트가 깨진다.

## 배포 (자체 VPS + Docker Compose)

서비스 3개: `db`(Postgres 16) · `backend`(uvicorn, 기동 시 `alembic upgrade head`) ·
`web`(nginx가 `dist`를 서빙 + `/api` → backend 프록시 + SPA fallback).

`/`, `/d/{date}`는 User-Agent가 SNS 미리보기 봇(Twitterbot, Slackbot, KakaoTalk 등,
`frontend/nginx.conf`의 `is_social_bot` 목록)일 때만 백엔드가 렌더링한 OG 메타 HTML로
넘어간다 — 사람은 그대로 SPA를 받는다. og:image는 카드 1 썸네일을 1200×630으로 크롭해
`og_cache` 볼륨(`/data/og`)에 캐시한다.

### 1. 환경 변수

```bash
cp .env.example .env
```

`POSTGRES_PASSWORD`와 `ADMIN_API_KEY`를 실제 값으로 채운다(`openssl rand -hex 32`).
**`DATABASE_URL` 안의 비밀번호도 같이 바꿔야 한다** — 두 값이 어긋나면 백엔드가 붙지 못한다.
Postgres는 최초 init 때만 비밀번호를 반영하므로, 볼륨을 만든 뒤 바꾸려면
`docker compose down -v`로 지우고 다시 올려야 한다.

```bash
docker compose up -d --build
curl -s localhost:8020/health     # {"status":"ok"}
```

`web`은 `127.0.0.1:8020`에만 바인딩된다 — 외부 노출은 호스트 nginx가 전담한다.

### 2. 인그레스 + TLS

호스트 nginx가 80/443과 인증서를 소유한다. 인증서가 없는 상태로 `:443` 블록을 넣으면
`nginx -t`가 깨지므로 **2단계**로 올린다.

```bash
# (1) :80 전용 vhost 먼저
sudo cp deploy/nginx/daily.onebitebitcoin.com.bootstrap.conf \
        /etc/nginx/sites-available/daily.onebitebitcoin.com
sudo ln -sf /etc/nginx/sites-available/daily.onebitebitcoin.com \
            /etc/nginx/sites-enabled/daily.onebitebitcoin.com
sudo nginx -t && sudo systemctl reload nginx

# (2) 인증서 — daily 전용. 기존 공용 인증서에 --expand 하지 않는다
#     (SAN 목록을 잘못 넘기면 기존 도메인이 갱신에서 조용히 빠진다)
sudo certbot certonly --webroot -w /var/www/letsencrypt \
     --cert-name daily.onebitebitcoin.com -d daily.onebitebitcoin.com

# (3) TLS 포함 최종 vhost로 교체
sudo cp deploy/nginx/daily.onebitebitcoin.com.conf \
        /etc/nginx/sites-available/daily.onebitebitcoin.com
sudo nginx -t && sudo systemctl reload nginx
```

DNS는 Cloudflare 프록시 뒤에 있다. HTTP-01 챌린지는 CF를 통과한다(확인함).
갱신은 certbot이 등록한 스케줄 작업이 처리한다.

### 3. 갱신 배포

```bash
git pull && docker compose up -d --build
```

마이그레이션은 backend 컨테이너가 기동하면서 `alembic upgrade head`로 적용한다.
실패하면 컨테이너가 뜨지 않는다(의도된 설계) — `docker compose logs backend`를 본다.

## 발행

수집 소스(my-news `:8000`, my-youtube `:23456`)는 개발 머신에만 있다. 수집·문구작성·
Q&A 생성은 로컬에서, 발행만 프로덕션을 향한다:

```bash
cd backend
python scripts/push_edition.py ../drafts/edition-<date>.json \
  --api https://daily.onebitebitcoin.com
```

`backend/.env`의 `ADMIN_API_KEY`가 서버 `.env`의 값과 같아야 한다(다르면 401).
같은 `meta.date`는 upsert이므로 재발행이 안전하다. 자세한 계약은
[CONTENT_CONTRACT.md](CONTENT_CONTRACT.md).

## 백업 / 복구

발행 데이터는 재생성이 불가능하다 — 수집 소스는 24시간 창만 보여주고, Q&A는 유료
호출 결과다. 일 1회 덤프하고 14일 보관한다.

```bash
bash deploy/backup.sh          # 수동 1회
crontab -l | grep btc-daily    # 등록 확인
```

복구:

```bash
gunzip -c ~/backups/btc-daily/btc-daily-<YYYY-MM-DD>.sql.gz \
  | docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"
```

## 트러블슈팅

| 증상 | 원인 / 대응 |
|---|---|
| `docker compose`가 `client version ... is too old` | 구버전 compose 플러그인(`/usr/lib/docker/cli-plugins`)이 탐색 순서에서 앞선다. `ln -sf /usr/libexec/docker/cli-plugins/docker-compose ~/.docker/cli-plugins/docker-compose` |
| `/d/<date>` 새로고침이 404 | 컨테이너 nginx의 `try_files` SPA fallback 확인(`frontend/nginx.conf`). 백엔드에는 catch-all이 없다 |
| 발행이 401 | `backend/.env`와 서버 `.env`의 `ADMIN_API_KEY` 불일치. 서버가 빈 값이면 항상 401(fail closed) |
| 발행이 "cover가 meta.date와 불일치" | stale draft다. 가드를 우회하지 말고 draft를 최신 코드로 재생성할 것 |
| `/`가 에러 화면 | DB에 편집본이 0건이면 `latest`가 404다. 한 건이라도 발행하면 해소된다 |
