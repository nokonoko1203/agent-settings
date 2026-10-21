#!/bin/bash
# Shared helpers for guardrail hooks.
# Logs record the rule that fired, not full commands, so secrets in arguments are not persisted.

HARNESS_LOG="${HARNESS_LOG:-$HOME/.claude/harness-log.jsonl}"

harness_log() {
  # $1: kind, $2: detail, $3: cwd
  jq -cn \
    --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg kind "$1" \
    --arg detail "$2" \
    --arg cwd "${3:-$PWD}" \
    '{ts: $ts, kind: $kind, cwd: $cwd, detail: $detail}' >>"$HARNESS_LOG" 2>/dev/null || true
}

# Block the tool call: stderr becomes Claude's feedback, exit 2 blocks PreToolUse.
harness_deny() {
  # $1: kind, $2: log detail, $3: cwd, $4: message for Claude
  harness_log "$1" "$2" "$3"
  echo "$4" >&2
  exit 2
}
