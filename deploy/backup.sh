#!/usr/bin/env bash
# btc-daily-web DB 일일 백업.
#
# 발행 데이터는 재생성이 불가능하다 — 수집 소스(my-news/my-youtube)는 24시간 창만
# 보여주고, Q&A는 Gemini 유료 호출 결과다. 볼륨 하나에만 있는 상태로 두지 않는다.
#
# crontab 등록 (기존 stackhealth 스크립트와 같은 형식):
#   30 4 * * * /bin/bash /home/measly/btc-daily-web/deploy/backup.sh >> /home/measly/.claude/logs/btc-daily-backup.log 2>&1
#
# 복구:
#   gunzip -c ~/backups/btc-daily/btc-daily-2026-07-31.sql.gz \
#     | docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${BTC_DAILY_BACKUP_DIR:-$HOME/backups/btc-daily}"
RETENTION_DAYS=14

# cron은 PATH가 빈약하다. compose 플러그인이 붙은 CLI를 절대경로로 잡는다.
DOCKER_BIN="${DOCKER_BIN:-/usr/bin/docker}"
[ -x "$DOCKER_BIN" ] || DOCKER_BIN="$(command -v docker)"

# POSTGRES_USER / POSTGRES_DB 를 가져온다. 값은 출력하지 않는다.
ENV_FILE="$REPO_ROOT/.env"
if [ ! -f "$ENV_FILE" ]; then
  echo "$(date -Is) ERROR: $ENV_FILE 없음 — 백업 중단" >&2
  exit 1
fi
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

: "${POSTGRES_USER:?.env에 POSTGRES_USER 없음}"
: "${POSTGRES_DB:?.env에 POSTGRES_DB 없음}"

mkdir -p "$BACKUP_DIR"
target="$BACKUP_DIR/btc-daily-$(date +%F).sql.gz"

# 부분 파일이 정상 백업으로 남지 않도록 임시 파일에 받고 성공 시에만 옮긴다.
tmp="$(mktemp "$target.XXXXXX")"
trap 'rm -f "$tmp"' EXIT

cd "$REPO_ROOT"
# pg_dump가 실패해도 gzip은 0을 뱉는다 — PIPESTATUS로 파이프 앞단을 직접 확인한다.
set +e
"$DOCKER_BIN" compose exec -T db pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" | gzip > "$tmp"
dump_status="${PIPESTATUS[0]}"
set -e

if [ "$dump_status" -ne 0 ]; then
  echo "$(date -Is) ERROR: pg_dump 실패(exit $dump_status) — 기존 백업을 덮어쓰지 않는다" >&2
  exit 1
fi
if [ ! -s "$tmp" ]; then
  echo "$(date -Is) ERROR: 덤프가 비어 있음 — 기존 백업을 덮어쓰지 않는다" >&2
  exit 1
fi

mv "$tmp" "$target"
trap - EXIT

find "$BACKUP_DIR" -name 'btc-daily-*.sql.gz' -mtime "+$RETENTION_DAYS" -delete

echo "$(date -Is) OK: $target ($(du -h "$target" | cut -f1))"
