#!/bin/bash
# PreToolUse hook: block .env file edits
# Matcher: Edit|Write|NotebookEdit
# .env.tpl and .env.example hold only secret references, so they stay editable.

source "$(dirname "$0")/lib-log.sh"

input=$(cat)
file_path=$(echo "$input" | jq -r '.tool_input.file_path // .tool_input.notebook_path // empty')
cwd=$(echo "$input" | jq -r '.cwd // empty')

[ -z "$file_path" ] && exit 0

name=$(basename "$file_path")

case "$name" in
  .env.tpl | .env.example) exit 0 ;;
esac

if [[ "$name" == ".env" || "$name" == .env.* ]]; then
  harness_deny "block-env-edit" "$file_path" "$cwd" ".env file editing is blocked. Ask the user to edit ${name} manually."
fi

exit 0
