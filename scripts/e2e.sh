#!/usr/bin/env bash
# Browser E2E of the whole stack (item 14.2), fully isolated from the real one: own project
# name, volumes, env file, port and credentials. The user's stack and its volumes
# (fincontrol_pgdata / fincontrol_redisdata) are never touched.
#
#   scripts/e2e.sh                 # build, start, journey, restart, persistence, tear down
#   KEEP_STACK=1 scripts/e2e.sh    # leave the e2e stack running for inspection
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PROJECT="fincontrol-e2e"
WEB_PORT="${E2E_WEB_PORT:-18090}"
WORKDIR="$(mktemp -d)"
ENV_FILE="$WORKDIR/e2e.env"
BASE="http://localhost:${WEB_PORT}"

native_path() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else echo "$1"; fi; }

PASSWORD="$(uv run --quiet python -I -c "import secrets; print(secrets.token_urlsafe(16))")"
HASH="$(uv run --quiet python -I -c "import sys; from fincontrol_api.auth import hash_password; print(hash_password(sys.argv[1]))" "$PASSWORD")"
SECRET="$(uv run --quiet python -I -c "import secrets; print(secrets.token_hex(32))")"
sed -e "s|^PGDATA_VOLUME=.*|PGDATA_VOLUME=fincontrol_e2e_pgdata|" \
    -e "s|^REDISDATA_VOLUME=.*|REDISDATA_VOLUME=fincontrol_e2e_redisdata|" \
    -e "s|^WEB_PORT=.*|WEB_PORT=${WEB_PORT}|" \
    -e "s|^APP_ENV_FILE=.*|APP_ENV_FILE=$(native_path "$ENV_FILE")|" \
    -e "s|^AUTH_USERNAME=.*|AUTH_USERNAME=e2e|" \
    -e "s|^AUTH_PASSWORD_HASH=.*|AUTH_PASSWORD_HASH='${HASH}'|" \
    -e "s|^AUTH_JWT_SECRET=.*|AUTH_JWT_SECRET=${SECRET}|" \
    .env.example > "$ENV_FILE"

COMPOSE=(docker compose -p "$PROJECT" -f docker-compose.prod.yml --env-file "$(native_path "$ENV_FILE")")

if grep -qE "^PGDATA_VOLUME=fincontrol_pgdata$|^REDISDATA_VOLUME=fincontrol_redisdata$" "$ENV_FILE"; then
  echo "refusing to run: e2e env points at the real data volumes" >&2
  exit 1
fi

cleanup() {
  if [[ "${KEEP_STACK:-0}" != "1" ]]; then
    "${COMPOSE[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
  else
    echo "e2e stack kept at $BASE (user e2e, password in $ENV_FILE is hashed; rerun to reset)"
  fi
  [[ "${KEEP_STACK:-0}" == "1" ]] || rm -rf "$WORKDIR"
}
trap cleanup EXIT

fail() { echo "E2E FAILED: $*" >&2; "${COMPOSE[@]}" logs --tail 80 >&2 || true; exit 1; }

wait_ready() {
  for _ in $(seq 1 90); do
    if curl -s "$BASE/api/v1/ready" | grep -q '"status":"ready"'; then return 0; fi
    sleep 2
  done
  fail "API not ready at $BASE"
}

echo "==> building and starting $PROJECT"
"${COMPOSE[@]}" up -d --build --wait --wait-timeout 300 || fail "stack did not become healthy"
wait_ready

export E2E_BASE_URL="$BASE" E2E_USERNAME="e2e" E2E_PASSWORD="$PASSWORD"
echo "==> journey"
(cd apps/web && npx playwright test e2e/journey.spec.ts) || fail "journey"

echo "==> restarting containers"
"${COMPOSE[@]}" restart >/dev/null
"${COMPOSE[@]}" up -d --wait --wait-timeout 300 >/dev/null || fail "stack did not come back"
wait_ready

echo "==> persistence"
(cd apps/web && npx playwright test e2e/persistence.spec.ts) || fail "persistence"

echo "E2E OK"
