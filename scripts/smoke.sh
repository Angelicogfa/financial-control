#!/usr/bin/env bash
# End-to-end smoke test of the Docker Compose stack, fully isolated from the real one:
# separate project name, volumes, env file and web port. Nothing of the user's stack or
# data (fincontrol_pgdata / fincontrol_redisdata) is touched.
#
#   scripts/smoke.sh            # build, start, check, tear down
#   KEEP_STACK=1 scripts/smoke.sh   # leave the smoke stack running for inspection
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PROJECT="fincontrol-smoke"
WEB_PORT="${SMOKE_WEB_PORT:-18080}"
PASSWORD="smoke-test-password"
WORKDIR="$(mktemp -d)"
ENV_FILE="$WORKDIR/smoke.env"
COOKIES="$WORKDIR/cookies.txt"
BASE="http://localhost:${WEB_PORT}"

# Docker Desktop on Windows needs a native path for env files.
native_path() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else echo "$1"; fi; }

HASH="$(uv run --quiet python -I -c "from fincontrol_api.auth import hash_password; print(hash_password('$PASSWORD'))")"
SECRET="$(uv run --quiet python -I -c "import secrets; print(secrets.token_hex(32))")"
sed -e "s|^PGDATA_VOLUME=.*|PGDATA_VOLUME=fincontrol_smoke_pgdata|" \
    -e "s|^REDISDATA_VOLUME=.*|REDISDATA_VOLUME=fincontrol_smoke_redisdata|" \
    -e "s|^WEB_PORT=.*|WEB_PORT=${WEB_PORT}|" \
    -e "s|^APP_ENV_FILE=.*|APP_ENV_FILE=$(native_path "$ENV_FILE")|" \
    -e "s|^AUTH_USERNAME=.*|AUTH_USERNAME=smoke|" \
    -e "s|^AUTH_PASSWORD_HASH=.*|AUTH_PASSWORD_HASH='${HASH}'|" \
    -e "s|^AUTH_JWT_SECRET=.*|AUTH_JWT_SECRET=${SECRET}|" \
    .env.example > "$ENV_FILE"

COMPOSE=(docker compose -p "$PROJECT" --env-file "$(native_path "$ENV_FILE")")

# Safety net: never run `down -v` against the real data volumes.
if grep -qE "^PGDATA_VOLUME=fincontrol_pgdata$|^REDISDATA_VOLUME=fincontrol_redisdata$" "$ENV_FILE"; then
  echo "refusing to run: smoke env points at the real data volumes" >&2
  exit 1
fi

cleanup() {
  if [[ "${KEEP_STACK:-0}" != "1" ]]; then
    "${COMPOSE[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
  fi
  rm -rf "$WORKDIR"
}
trap cleanup EXIT

fail() { echo "SMOKE FAILED: $*" >&2; "${COMPOSE[@]}" logs --tail 50 >&2 || true; exit 1; }
expect_status() {
  local expected="$1"; shift
  local got
  got="$(curl -s -o /dev/null -w "%{http_code}" "$@")"
  [[ "$got" == "$expected" ]] || fail "expected HTTP $expected, got $got for: $*"
}

echo "==> building and starting $PROJECT"
if ! "${COMPOSE[@]}" up -d --build --wait --wait-timeout 300; then
  fail "stack did not become healthy"
fi

echo "==> readiness"
READY="$(curl -s "$BASE/api/v1/ready")"
echo "$READY"
[[ "$READY" == *'"status":"ready"'* ]] || fail "API not ready"

echo "==> authentication"
expect_status 401 "$BASE/api/v1/assets"
expect_status 401 -H "Content-Type: application/json" \
  -d '{"username":"smoke","password":"wrong"}' "$BASE/api/v1/auth/login"
expect_status 200 -c "$COOKIES" -H "Content-Type: application/json" \
  -d "{\"username\":\"smoke\",\"password\":\"$PASSWORD\"}" "$BASE/api/v1/auth/login"

echo "==> ledger round trip"
expect_status 201 -b "$COOKIES" -H "Content-Type: application/json" \
  -d '{"ticker":"CDB-SMOKE","name":"CDB Smoke","asset_type":"FIXED_INCOME","fixed_income_term":{"instrument_kind":"CDB","indexer":"CDI","contracted_rate":"1.10","issue_date":"2025-01-02"}}' \
  "$BASE/api/v1/assets"
expect_status 201 -b "$COOKIES" -H "Content-Type: application/json" \
  -d '{"asset_id":1,"kind":"BUY","trade_date":"2025-01-02","quantity":"1","unit_price":"10000"}' \
  "$BASE/api/v1/transactions"
expect_status 200 -b "$COOKIES" "$BASE/api/v1/portfolio"
expect_status 200 -b "$COOKIES" "$BASE/api/v1/market/job-runs"

echo "==> web app and hardening"
expect_status 200 "$BASE/"
curl -s -D - -o /dev/null "$BASE/" | grep -qi "x-frame-options: deny" || fail "missing security headers"
for service in api worker; do
  uid="$("${COMPOSE[@]}" exec -T "$service" id -u | tr -d '\r')"
  [[ "$uid" != "0" ]] || fail "$service runs as root"
done
"${COMPOSE[@]}" exec -T -e REDISCLI_AUTH= redis redis-cli ping 2>&1 | grep -q NOAUTH \
  || fail "redis accepts unauthenticated clients"
published="$("${COMPOSE[@]}" ps --format '{{.Service}} {{.Publishers}}' | grep -vE '^web ' | grep -c 'PublishedPort:[1-9]' || true)"
[[ "$published" == "0" ]] || fail "only the web service may publish ports"

echo "SMOKE OK"
