#!/usr/bin/env python3
"""Stop hook: keep Claude working when the final reply is in English instead of Japanese.

Matcher: (none)
The reply counts as English when, after removing fenced code blocks, inline code, URLs and
Markdown link targets, it has no hiragana or katakana and at least MIN_ASCII_LETTERS ASCII letters.
Short replies ("OK", a lone command) and kanji-only replies are not reported.
Each reply is reported once per session, so a reply the user asked to be in English cannot loop.
"""

import hashlib
import json
import os
import re
import subprocess
import sys

HOOK_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.expanduser("~/.claude/state/language-check")
MIN_ASCII_LETTERS = 40

FENCE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")
INLINE_CODE = re.compile(r"(`+)((?:(?!\1).)+?)\1")
LINK_TARGET = re.compile(r"\]\([^)]*\)")
URL = re.compile(r"\b[A-Za-z][A-Za-z0-9+.-]*://[!-~]+")
KANA = re.compile(r"[぀-ヿｦ-ﾟ]")
ASCII_LETTER = re.compile(r"[A-Za-z]")


def log(kind, detail, cwd):
    script = f'source "{HOOK_DIR}/lib-log.sh"; harness_log "$0" "$1" "$2"'
    subprocess.run(["bash", "-c", script, kind, detail, cwd], check=False)


def prose(text):
    """The reply without code, URLs and link targets."""
    lines = []
    in_fence = None
    for line in text.splitlines():
        fence = FENCE.match(line)
        if fence:
            run, info = fence.groups()
            if in_fence is None:
                in_fence = run
                continue
            # A closing fence repeats the opening character at least as many times, with no info.
            if run[0] == in_fence[0] and len(run) >= len(in_fence) and not info.strip():
                in_fence = None
                continue
        if in_fence:
            continue
        line = INLINE_CODE.sub(" ", line)
        line = LINK_TARGET.sub("]", line)
        lines.append(URL.sub(" ", line))
    return "\n".join(lines)


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(data, dict):
        return 0
    message = data.get("last_assistant_message")
    session_id = data.get("session_id")
    if not isinstance(message, str) or not message or not isinstance(session_id, str):
        return 0

    text = prose(message)
    letters = len(ASCII_LETTER.findall(text))
    if KANA.search(text) or letters < MIN_ASCII_LETTERS:
        return 0

    # Key the state by a hash so session_id never acts as a path.
    state_file = os.path.join(STATE_DIR, hashlib.sha256(session_id.encode()).hexdigest()[:16])
    digest = hashlib.sha256(message.encode()).hexdigest()
    try:
        with open(state_file) as f:
            if digest in f.read().split():
                return 0
    except FileNotFoundError:
        pass
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(state_file, "a") as f:
        f.write(digest + "\n")

    cwd = data.get("cwd") if isinstance(data.get("cwd"), str) else os.getcwd()
    log("english-reply", f"{letters} ASCII letters, no kana", cwd)
    reason = (
        "直前の返答がほぼ英語でした。ユーザーは日本語を使います。"
        "同じ内容を日本語で書き直してください（コード、コマンド、識別子、引用はそのまま）。"
        "ユーザーが英語での返答を明示的に求めていた場合は、その旨を日本語で1行書くだけでよい。"
    )
    print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
