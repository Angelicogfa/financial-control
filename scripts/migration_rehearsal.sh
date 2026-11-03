#!/usr/bin/env bash
# Migration rehearsal on a copy of the real database (Phase 48.R0). Run before merging any
# migration. The real data is only READ (pg_dump); the dump is restored into a throwaway
# Postgres container with no named volume, the migrations run there and everything is
# removed at the end.
#
#   scripts/migration_rehearsal.sh                   # dump the running stack's postgres
#   DUMP_FILE=backup.dump scripts/migration_rehearsal.sh   # use an existing pg_dump -Fc file
#   SOURCE_CONTAINER=other-postgres-1 scripts/migration_rehearsal.sh
#   KEEP_DUMP=1 scripts/migration_rehearsal.sh       # keep the dump (it holds personal data)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SOURCE_CONTAINER="${SOURCE_CONTAINER:-financial-control-postgres-1}"
IMAGE="${REHEARSAL_IMAGE:-postgres:16-alpine}"
PORT="${REHEARSAL_PORT:-55499}"
NAME="fincontrol-rehearsal-$$"
WORKDIR="$(mktemp -d)"
PASSWORD="$(uv run --quiet python -I -c "import secrets; print(secrets.token_urlsafe(16))")"

cleanup() {
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  if [[ "${KEEP_DUMP:-0}" == "1" && -z "${DUMP_FILE:-}" ]]; then
    echo "dump kept at $WORKDIR/copy.dump"
  else
    rm -rf "$WORKDIR"
  fi
}
trap cleanup EXIT

if [[ -n "${DUMP_FILE:-}" ]]; then
  DUMP="$DUMP_FILE"
else
  DUMP="$WORKDIR/copy.dump"
  echo "==> dumping $SOURCE_CONTAINER (read only)"
  docker exec "$SOURCE_CONTAINER" sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$DUMP"
fi
echo "    dump: $(wc -c < "$DUMP") bytes"

echo "==> starting throwaway postgres $NAME on 127.0.0.1:$PORT"
docker run -d --rm --name "$NAME" \
  -e POSTGRES_USER=rehearsal -e POSTGRES_PASSWORD="$PASSWORD" -e POSTGRES_DB=rehearsal \
  -p "127.0.0.1:${PORT}:5432" "$IMAGE" >/dev/null
for _ in $(seq 1 60); do
  # The entrypoint restarts the server once after init; wait for the TCP listener.
  if docker exec "$NAME" pg_isready -h 127.0.0.1 -U rehearsal -d rehearsal >/dev/null 2>&1; then break; fi
  sleep 1
done

echo "==> restoring the copy"
docker exec -i "$NAME" pg_restore -U rehearsal -d rehearsal --no-owner --no-privileges < "$DUMP"

echo "==> rehearsing the migrations"
(
  cd apps/api
  uv run python -m infra.data.migration_rehearsal \
    --url "postgresql+psycopg://rehearsal:${PASSWORD}@127.0.0.1:${PORT}/rehearsal"
)
