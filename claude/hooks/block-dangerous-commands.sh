#!/bin/bash
# PreToolUse hook: block irreversible commands
# Matcher: Bash
# History-rewriting git commands are not blocked here; they are `ask` rules in settings.json.
# This matches command text only and is not a security boundary.

source "$(dirname "$0")/lib-log.sh"

input=$(cat)
command=$(echo "$input" | jq -r '.tool_input.command // empty')
cwd=$(echo "$input" | jq -r '.cwd // empty')

[ -z "$command" ] && exit 0

deny() {
  harness_deny "block-dangerous" "$1" "$cwd" "Blocked ($1): irreversible command. Ask the user to run it manually if it is really needed."
}

# rm (or /bin/rm) with both recursive and force flags anywhere in its arguments
# (-rf, -fr, -Rf, -r -f, rm -r dir -f, --recursive --force).
# Subcommands named rm (git rm, docker rm, ...) are not the rm program and are skipped.
while IFS= read -r segment; do
  read -ra words <<<"$segment"
  for i in "${!words[@]}"; do
    [ "${words[$i]##*/}" = "rm" ] || continue
    if [ "$i" -gt 0 ]; then
      case "${words[$((i - 1))]}" in
        git | npm | pnpm | yarn | bun | docker | podman | cargo | kubectl | brew | uv | poetry) continue ;;
      esac
    fi
    recursive=0
    force=0
    for arg in "${words[@]:$((i + 1))}"; do
      case "$arg" in
        --recursive) recursive=1 ;;
        --force) force=1 ;;
        --*) ;;
        -*)
          [[ "$arg" == *[rR]* ]] && recursive=1
          [[ "$arg" == *f* ]] && force=1
          ;;
      esac
    done
    if [ "$recursive" = 1 ] && [ "$force" = 1 ]; then
      deny "rm-recursive-force"
    fi
  done
done < <(echo "$command" | tr ';&|()' '\n\n\n\n\n')

if echo "$command" | grep -qiE '(^|[^[:alnum:]_])mkfs(\.|[[:space:]])'; then deny "mkfs"; fi
if echo "$command" | grep -qiE '(^|[^[:alnum:]_])dd[[:space:]]+if='; then deny "dd"; fi
if echo "$command" | grep -qiE '>[[:space:]]*/dev/(sd|disk|nvme)'; then deny "raw-device-write"; fi
if echo "$command" | grep -qiE '(DROP[[:space:]]+(TABLE|DATABASE|SCHEMA)|TRUNCATE[[:space:]]+TABLE)'; then deny "sql-drop"; fi

exit 0
