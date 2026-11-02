#!/bin/bash
# Run a global hook unless the project carries its own copy of the harness (see bin/harness-install).
# Usage in settings.json: ~/.claude/hooks/run-global.sh <hook file name>
# Claude Code reads .claude/settings.json only from the directory it was started in, not from the
# git root, so only a copy there registers the project hooks. A copy higher up does not count.
if [ -n "${CLAUDE_PROJECT_DIR:-}" ] && [ -f "$CLAUDE_PROJECT_DIR/.claude/harness-version" ]; then
  exit 0
fi
exec "$(dirname "$0")/$1"
