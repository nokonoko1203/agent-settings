#!/bin/bash
# Stop hook: keep Claude working until the repository check passes
# Matcher: (none)
#
# The check command is per repository: `make check` if a Makefile has a check target,
# otherwise an executable .claude/check.sh. Repositories with neither are skipped.
# The check runs only in git repositories with uncommitted changes, and is skipped when
# the working tree is unchanged since the last passing run.
# After MAX_BLOCKS consecutive blocks, Claude may stop and the user is told why; the same
# working tree is then not blocked again, so an existing failure does not stall every turn.

source "$(dirname "$0")/lib-log.sh"

MAX_BLOCKS=3
STATE_DIR="$HOME/.claude/state"

input=$(cat)
cwd=$(echo "$input" | jq -r '.cwd // empty')
session_id=$(echo "$input" | jq -r '.session_id // "unknown"')
[ -z "$cwd" ] && cwd=$PWD

root=$(git -C "$cwd" rev-parse --show-toplevel 2>/dev/null) || exit 0
root_key=$(printf '%s' "$root" | shasum -a 256 | cut -c1-16)
counter_file="$STATE_DIR/stop-blocks/$session_id"
pass_file="$STATE_DIR/check-pass/$root_key"
give_up_file="$STATE_DIR/give-up/$root_key"
mkdir -p "$STATE_DIR/stop-blocks" "$STATE_DIR/check-pass" "$STATE_DIR/give-up"

status=$(git -C "$root" status --porcelain=v1 -uall 2>/dev/null)
tree_hash=""

# Hashing untracked files can be slow, so compute only when a decision needs it.
compute_tree_hash() {
  [ -n "$tree_hash" ] && return
  tree_hash=$({
    echo "$status"
    git -C "$root" diff HEAD 2>/dev/null
    git -C "$root" ls-files --others --exclude-standard -z 2>/dev/null | xargs -0 -I{} shasum "$root/{}" 2>/dev/null
  } | shasum -a 256 | cut -d' ' -f1)
}

allow_stop() {
  rm -f "$counter_file"
  exit 0
}

block() {
  # $1: kind, $2: reason for Claude
  count=$(($(cat "$counter_file" 2>/dev/null || echo 0) + 1))
  if [ "$count" -gt "$MAX_BLOCKS" ]; then
    rm -f "$counter_file"
    compute_tree_hash
    echo "$tree_hash" >"$give_up_file"
    harness_log "$1-gave-up" "stopped after $MAX_BLOCKS blocks" "$root"
    jq -cn --arg msg "stop-check: $1 still failing after $MAX_BLOCKS attempts. Not blocking again until the working tree changes. Check the repository manually." \
      '{systemMessage: $msg}'
    exit 0
  fi
  echo "$count" >"$counter_file"
  harness_log "$1" "block $count/$MAX_BLOCKS" "$root"
  jq -cn --arg reason "$2" '{decision: "block", reason: $reason}'
  exit 0
}

if [ -f "$give_up_file" ]; then
  compute_tree_hash
  [ "$(cat "$give_up_file")" = "$tree_hash" ] && allow_stop
fi

check_cmd=()
for makefile in GNUmakefile makefile Makefile; do
  if [ -f "$root/$makefile" ] && grep -qE '^check:' "$root/$makefile"; then
    check_cmd=(make -C "$root" check)
    break
  fi
done
if [ ${#check_cmd[@]} -eq 0 ] && [ -x "$root/.claude/check.sh" ]; then
  check_cmd=("$root/.claude/check.sh")
fi
[ ${#check_cmd[@]} -eq 0 ] && allow_stop

[ -z "$status" ] && allow_stop
compute_tree_hash
[ "$(cat "$pass_file" 2>/dev/null)" = "$tree_hash" ] && allow_stop

output=$(cd "$root" && "${check_cmd[@]}" 2>&1)
if [ $? -eq 0 ]; then
  echo "$tree_hash" >"$pass_file"
  allow_stop
fi

block "check-failed" "Repository check failed (${check_cmd[*]}). Fix the failures before finishing:
$(echo "$output" | tail -40)"
