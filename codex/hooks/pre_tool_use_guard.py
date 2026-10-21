#!/usr/bin/env python3
"""Minimal Codex shell guard to mirror key Claude Code safety rules."""

from __future__ import annotations

import json
import re
import sys


COMMAND_PATTERNS = [
    (
        re.compile(r"(^|[;&|]\s*)(sudo|su|doas)\b"),
        "Privileged commands are blocked. Run them manually outside Codex if truly needed.",
    ),
    (
        re.compile(r"(^|[;&|]\s*)(printenv|env)(\s|$)"),
        "Environment dumping commands are blocked.",
    ),
    (
        re.compile(r"(^|[;&|]\s*)(source|\.)\s+(\./)?\.env(\.[^\s;&|]+)?\b"),
        "Loading .env files in-shell is blocked.",
    ),
]

PATH_PATTERNS = [
    (re.compile(r"(^|[^A-Za-z0-9_./-])\./\.env($|[^A-Za-z0-9_.-])"), "Direct .env access is blocked."),
    (re.compile(r"(^|[^A-Za-z0-9_./-])\./\.env\.[^\s;&|]+"), "Direct .env.* access is blocked."),
    (re.compile(r"(^|[^A-Za-z0-9_./-])\./secrets/"), "Reading ./secrets is blocked."),
    (re.compile(r"~/.ssh/"), "Reading ~/.ssh is blocked."),
    (re.compile(r"~/.aws/"), "Reading ~/.aws is blocked."),
    (re.compile(r"~/.gnupg/"), "Reading ~/.gnupg is blocked."),
    (re.compile(r"~/.config/op/"), "Reading ~/.config/op is blocked."),
    (re.compile(r"~/.op/"), "Reading ~/.op is blocked."),
]


def deny(reason: str) -> None:
    payload = {
        "systemMessage": reason,
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        },
    }
    print(json.dumps(payload))


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0

    command = event.get("tool_input", {}).get("command", "")
    if not isinstance(command, str) or not command.strip():
        return 0

    for pattern, reason in COMMAND_PATTERNS:
        if pattern.search(command):
            deny(reason)
            return 0

    for pattern, reason in PATH_PATTERNS:
        if pattern.search(command):
            deny(reason)
            return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
