#!/usr/bin/env bash
# Local quality gate: the same checks the GitHub workflow runs, executable on any machine
# (GitHub Actions minutes are not available for this repository).
#
#   scripts/check.sh            # lint, tests, coverage floors, web build, Docker images
#   scripts/check.sh --fast     # skip Docker (used by the pre-push hook)
#   scripts/check.sh --smoke    # everything plus the isolated end-to-end stack test
#   scripts/check.sh --e2e      # everything plus smoke and the browser E2E journey
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MODE="${1:-}"
step() { echo; echo "==> $*"; }

step "Python: lock, lint and format"
uv sync --all-packages --frozen --quiet
uv run ruff check .
uv run ruff format --check .

step "Python: full unit and integration suite (coverage floor 80%)"
uv run pytest -q \
  --cov=apps/api --cov-report=term:skip-covered \
  --cov-fail-under=80

step "Web: install, lint, type-check, tests with coverage floor (70%) and build"
(
  cd apps/web
  npm ci --no-audit --no-fund --loglevel=error
  npm run lint
  npx tsc --noEmit
  npm run test:coverage
  npm run build
)

if [[ "$MODE" == "--fast" ]]; then
  echo; echo "CHECKS OK (fast mode: Docker skipped)"
  exit 0
fi

step "Docker: compose config (production and development) and image build"
docker compose -p fincontrol-check --env-file .env.example -f docker-compose.prod.yml config -q
docker compose -p fincontrol-check --env-file .env.example -f docker-compose.yml config -q
docker compose -p fincontrol-check --env-file .env.example -f docker-compose.prod.yml build

if [[ "$MODE" == "--smoke" || "$MODE" == "--e2e" ]]; then
  step "Docker: isolated end-to-end smoke test"
  scripts/smoke.sh
fi

if [[ "$MODE" == "--e2e" ]]; then
  step "Docker + browser: isolated E2E journey and persistence after restart"
  scripts/e2e.sh
fi

echo; echo "CHECKS OK"
