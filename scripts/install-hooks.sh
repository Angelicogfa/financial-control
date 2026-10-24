#!/usr/bin/env bash
# Install a git pre-push hook that runs the fast local quality gate before every push.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOK="$ROOT/.git/hooks/pre-push"

cat > "$HOOK" <<'HOOK'
#!/usr/bin/env bash
# Installed by scripts/install-hooks.sh — runs the local quality gate before pushing.
exec "$(git rev-parse --show-toplevel)/scripts/check.sh" --fast
HOOK
chmod +x "$HOOK"
echo "pre-push hook installed at $HOOK"
