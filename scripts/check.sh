#!/usr/bin/env bash
# Local quality gate: the same checks the GitHub workflow runs, executable on any machine
# (GitHub Actions minutes are not available for this repository).
#
#   scripts/check.sh            # lint, tests, coverage, web build, Docker images
#   scripts/check.sh --fast     # skip Docker (used by the pre-push hook)
#   scripts/check.sh --smoke    # everything plus the isolated end-to-end stack test
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MODE="${1:-}"
step() { echo; echo "==> $*"; }

step "Python: lock, lint and format"
uv sync --all-packages --frozen --quiet
uv run ruff check .
uv run ruff format --check .

step "Python: core domain tests with coverage floor (85%)"
uv run pytest packages/core/tests -q \
  --cov=fincontrol_core --cov-report=term:skip-covered --cov-fail-under=85

step "Python: full unit and integration suite"
uv run pytest -q \
  --cov=fincontrol_config --cov=fincontrol_core --cov=fincontrol_persistence \
  --cov=fincontrol_api --cov=fincontrol_worker --cov-report=term:skip-covered

step "Web: install, lint, type-check, tests and build"
(
  cd apps/web
  npm ci --no-audit --no-fund --loglevel=error
  npm run lint
  npx tsc --noEmit
  npm test
  npm run build
)

if [[ "$MODE" == "--fast" ]]; then
  echo; echo "CHECKS OK (fast mode: Docker skipped)"
  exit 0
fi

step "Docker: compose config and image build"
docker compose -p fincontrol-check --env-file .env.example config -q
docker compose -p fincontrol-check --env-file .env.example build

if [[ "$MODE" == "--smoke" ]]; then
  step "Docker: isolated end-to-end smoke test"
  scripts/smoke.sh
fi

echo; echo "CHECKS OK"
