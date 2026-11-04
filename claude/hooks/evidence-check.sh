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
# When the newest evidence.md belongs to a task (its directory name) whose latest triage or
# triage-override record says level 1 or 2, it also has to carry an abnormal-case row
# ("異常系" at the start of a table row, or "異常系: 該当なし") and a "## 確かめていないこと"
# section, unless it is only the "動作確認なし" line. Otherwise it does not count as evidence.
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

# mtime has one-second resolution, so every evidence.md tied for the newest one is checked.
newest_evidence=0
newest_files=()
if [ -d "$root/.tmp/evidence" ]; then
  while IFS= read -r -d '' ev; do
    m=$(mtime "$ev")
    [ -n "$m" ] || continue
    if [ "$m" -gt "$newest_evidence" ]; then
      newest_evidence=$m
      newest_files=("$ev")
    elif [ "$m" -eq "$newest_evidence" ]; then
      newest_files+=("$ev")
    fi
  done < <(find "$root/.tmp/evidence" -mindepth 2 -maxdepth 2 -name evidence.md -print0 2>/dev/null)
fi

# Print what a level 1 or 2 evidence.md lacks, one item per line; print nothing when it is enough.
content_gaps() {
  local ev="$1" task level
  task=$(basename "$(dirname "$ev")")
  level=$(jq -Rr --arg task "$task" --arg root "$root" '
    fromjson? // empty
    | select(.kind == "triage" or .kind == "triage-override")
    | select(.task == $task)
    | select(.cwd == $root or (.cwd | startswith($root + "/")))
    | (.detail | capture("level=(?<l>[^;[:space:]]+)").l) // empty' "$HARNESS_LOG" 2>/dev/null | tail -1)
  case "$level" in 1 | 2) ;; *) return 0 ;; esac
  if [ "$(grep -cv '^[[:space:]]*$' "$ev")" -le 1 ] && grep -Eq '^[[:space:]]*動作確認なし: ?[^[:space:]]' "$ev"; then
    return 0
  fi
  # A table row whose first cell starts with 異常系, or a line (or first cell) that is 異常系: 該当なし: <reason>.
  grep -Eq '^\|[[:space:]]*異常系|^([-*|][[:space:]]*)?異常系: ?該当なし: ?[^[:space:]]' "$ev" ||
    echo "- ${ev}: 受け入れ条件と証拠の表に、異常系の行（当たる観点がなければ「異常系: 該当なし: <理由>」）"
  grep -Eq '^## 確かめていないこと[[:space:]]*$' "$ev" ||
    echo "- ${ev}: 「## 確かめていないこと」の節（なければ「なし」と書く）"
}

gaps=""
if [ "$newest_evidence" -gt 0 ] && [ "$newest_evidence" -ge "$newest_change" ]; then
  gaps=$(for ev in "${newest_files[@]}"; do content_gaps "$ev"; done)
  [ -z "$gaps" ] && allow_stop
fi

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

files=$(printf '%s\n' "${changed[@]}" | head -10)
if [ -n "$gaps" ]; then
  harness_log "evidence-incomplete" "block $count/$MAX_BLOCKS" "$root"
  reason="レベル1・2の作業の証拠に、次が足りません。
${gaps}

spec の確認範囲表で確かめないとした観点は「確かめていないこと」に写してください。形式は ~/.claude/references/evidence.md にあります。"
  jq -cn --arg reason "$reason" '{decision: "block", reason: $reason}'
  exit 0
fi
harness_log "evidence-missing" "block $count/$MAX_BLOCKS" "$root"
reason="振る舞いに関わるファイルが変わっていますが、それより新しい動作確認の証拠がありません。
変更したファイル（最大10件）:
${files}

実際に動かして、${root}/.tmp/evidence/<task>/evidence.md に受け入れ条件と証拠を書いてください。形式は ~/.claude/references/evidence.md にあります。
振る舞いが変わらない変更なら、evidence.md に「動作確認なし: <理由>」の1行を書けば終了できます。"
jq -cn --arg reason "$reason" '{decision: "block", reason: $reason}'
exit 0
