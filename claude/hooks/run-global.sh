#!/bin/bash
# Run a global hook unless the project carries its own copy of the harness (see bin/harness-install).
# Usage in settings.json: ~/.claude/hooks/run-global.sh <hook file name>
if [ -n "${CLAUDE_PROJECT_DIR:-}" ]; then
  root=$(git -C "$CLAUDE_PROJECT_DIR" rev-parse --show-toplevel 2>/dev/null || echo "$CLAUDE_PROJECT_DIR")
  if [ -f "$CLAUDE_PROJECT_DIR/.claude/harness-version" ] || [ -f "$root/.claude/harness-version" ]; then
    exit 0
  fi
fi
exec "$(dirname "$0")/$1"
