#!/bin/bash
# Stop hook: keep Claude working until behavior-changing edits have evidence that they were run
# Matcher: (none)
#
# A change counts as behavior-changing when an uncommitted file (or the source path of a
# rename) matches a pattern in <repo>/.claude/evidence-paths (one glob per line, # for
# comments), or the default Svelte/SvelteKit patterns when that file is absent. An existing file
# with no patterns turns the check off for that repository and records
# evidence-check-disabled once per session. Paths inside any .tmp/ directory never count.
# Evidence is a .tmp/evidence/*/evidence.md at least as new as the newest changed file.
# A deleted file has no mtime, so the mtime of its parent directory stands in for it.
# After MAX_BLOCKS consecutive blocks, Claude may stop and the same set of behavior files
# is not blocked again, like stop-check.sh.
# It also records untriaged-change once per session and repository when behavior-changing
# edits exist but the repository has no triage record in the last 24 hours. That record
# never blocks.
# Known gap: changes inside a submodule are invisible from the parent repository.

source "$(dirname "$0")/lib-log.sh"

MAX_BLOCKS=3
STATE_DIR="${HARNESS_STATE_DIR:-$HOME/.claude/state}"
# Svelte components and rune modules, SvelteKit route modules (+page.ts etc., not their co-located tests),
# hooks, param matchers, the instrumentation entry, the service worker, remote functions,
# the HTML shells, and styles.
DEFAULT_PATTERNS=(
  '*.svelte' '*.svelte.[jt]s'
  '*/+page.[jt]s' '*/+page.server.[jt]s' '*/+layout.[jt]s' '*/+layout.server.[jt]s' '*/+server.[jt]s'
  'src/hooks.[jt]s' '*/src/hooks.[jt]s' '*/hooks.server.[jt]s' '*/hooks.client.[jt]s'
  'src/params/*.[jt]s' '*/src/params/*.[jt]s' 'src/params.[jt]s' '*/src/params.[jt]s'
  '*/instrumentation.server.[jt]s'
  '*/service-worker.[jt]s' '*/service-worker/*.[jt]s'
  '*.remote.[jt]s'
  '*/app.html' 'src/error.html' '*/src/error.html'
  '*.css'
)

input=$(cat)
cwd=$(echo "$input" | jq -r '.cwd // empty')
session_id=$(echo "$input" | jq -r '.session_id // "unknown"')
[ -z "$cwd" ] && cwd=$PWD

root=$(git -C "$cwd" rev-parse --show-toplevel 2>/dev/null) || exit 0
root_key=$(printf '%s' "$root" | shasum -a 256 | cut -c1-16)
counter_file="$STATE_DIR/evidence-blocks/$session_id-$root_key"
give_up_file="$STATE_DIR/evidence-give-up/$root_key"
untriaged_file="$STATE_DIR/untriaged/$session_id-$root_key"
disabled_file="$STATE_DIR/evidence-disabled/$session_id-$root_key"
mkdir -p "$STATE_DIR/evidence-blocks" "$STATE_DIR/evidence-give-up" "$STATE_DIR/untriaged" "$STATE_DIR/evidence-disabled"

allow_stop() {
  rm -f "$counter_file"
  exit 0
}

patterns=()
if [ -f "$root/.claude/evidence-paths" ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%%#*}"
    line=$(printf '%s' "$line" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
    [ -n "$line" ] && patterns+=("$line")
  done <"$root/.claude/evidence-paths"
  if [ ${#patterns[@]} -eq 0 ]; then
    if [ ! -f "$disabled_file" ]; then
      harness_log "evidence-check-disabled" ".claude/evidence-paths has no patterns" "$root"
      touch "$disabled_file"
    fi
    allow_stop
  fi
else
  patterns=("${DEFAULT_PATTERNS[@]}")
fi

mtime() {
  stat -f %m "$1" 2>/dev/null || stat -c %Y "$1" 2>/dev/null
}

matches() {
  case "$1" in .tmp/* | */.tmp/*) return 1 ;; esac
  local pattern
  for pattern in "${patterns[@]}"; do
    # shellcheck disable=SC2053
    [[ "$1" == $pattern ]] && return 0
  done
  return 1
}

changed=()
newest_change=0
note_change() {
  # $1: path relative to root
  changed+=("$1")
  local target="$root/$1" m
  [ -e "$target" ] || target=$(dirname "$target")
  while [ ! -e "$target" ] && [ "$target" != "$root" ]; do target=$(dirname "$target"); done
  m=$(mtime "$target")
  [ -n "$m" ] && [ "$m" -gt "$newest_change" ] && newest_change=$m
}

# -z keeps non-ASCII and special characters unquoted; a rename is "XY to\0from\0".
while IFS= read -r -d '' entry; do
  xy="${entry:0:2}"
  path="${entry:3}"
  from=""
  case "$xy" in R* | C* | ?R | ?C) IFS= read -r -d '' from ;; esac
  if matches "$path"; then
    note_change "$path"
  elif [ -n "$from" ] && matches "$from"; then
    note_change "$from"
  fi
done < <(git -C "$root" status --porcelain=v1 -z -uall 2>/dev/null)

[ ${#changed[@]} -eq 0 ] && allow_stop

if [ ! -f "$untriaged_file" ]; then
  triaged=$(jq -Rr --arg root "$root" '
    fromjson? // empty
    | select(.kind == "triage" or .kind == "triage-override")
    | select(.cwd == $root or (.cwd | startswith($root + "/")))
    | select(.ts >= (now - 86400 | todate))
    | .ts' "$HARNESS_LOG" 2>/dev/null | head -1)
  if [ -z "$triaged" ]; then
    harness_log "untriaged-change" "${#changed[@]} behavior file(s) changed without a triage record in 24h" "$root"
  fi
  touch "$untriaged_file"
fi

newest_evidence=0
if [ -d "$root/.tmp/evidence" ]; then
  while IFS= read -r -d '' ev; do
    m=$(mtime "$ev")
    [ -n "$m" ] && [ "$m" -gt "$newest_evidence" ] && newest_evidence=$m
  done < <(find "$root/.tmp/evidence" -mindepth 2 -maxdepth 2 -name evidence.md -print0 2>/dev/null)
fi

[ "$newest_evidence" -gt 0 ] && [ "$newest_evidence" -ge "$newest_change" ] && allow_stop

# Key the give-up on the behavior files only, so writes elsewhere (.tmp/, docs) do not re-arm it.
tree_hash=$(for f in "${changed[@]}"; do
  printf '%s\0' "$f"
  [ -f "$root/$f" ] && shasum "$root/$f" 2>/dev/null
done | shasum -a 256 | cut -d' ' -f1)
[ -f "$give_up_file" ] && [ "$(cat "$give_up_file")" = "$tree_hash" ] && allow_stop

count=$(($(cat "$counter_file" 2>/dev/null || echo 0) + 1))
if [ "$count" -gt "$MAX_BLOCKS" ]; then
  rm -f "$counter_file"
  echo "$tree_hash" >"$give_up_file"
  harness_log "evidence-missing-gave-up" "stopped after $MAX_BLOCKS blocks" "$root"
  jq -cn --arg msg "evidence-check: 動作確認の証拠がないまま${MAX_BLOCKS}回止めたので、今回は終了を許可します。対象のファイルが変わるまで再び止めません。" \
    '{systemMessage: $msg}'
  exit 0
fi
echo "$count" >"$counter_file"
harness_log "evidence-missing" "block $count/$MAX_BLOCKS" "$root"

files=$(printf '%s\n' "${changed[@]}" | head -10)
reason="振る舞いに関わるファイルが変わっていますが、それより新しい動作確認の証拠がありません。
変更したファイル（最大10件）:
${files}

実際に動かして、${root}/.tmp/evidence/<task>/evidence.md に受け入れ条件と証拠を書いてください。形式は ~/.claude/references/evidence.md にあります。
振る舞いが変わらない変更なら、evidence.md に「動作確認なし: <理由>」の1行を書けば終了できます。"
jq -cn --arg reason "$reason" '{decision: "block", reason: $reason}'
exit 0
