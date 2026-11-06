#!/usr/bin/env python3
"""PreToolUse hook: block a Bash call that runs more than one git command.

Matcher: Bash
Permission rules in settings.json prompt once for a whole compound command, so chaining
`git switch main && git push origin --delete x` folds an `ask` operation into a single prompt with
the others. One git command per call keeps each operation's permission check separate.
`cd <dir> && git ...` with a single git passes. Read-only git commands count too.
git invocations are counted across `&&`, `||`, `;`, `|`, `&`, newlines, subshells, `$(...)`,
backticks and `bash -c`. Words inside quotes, redirection targets, heredoc bodies and
`command -v git` are not counted; a `$(...)` or backtick inside double quotes is, since the shell
runs it. A substitution nested inside a quoted substitution is not parsed.
This matches command text only and is not a security boundary.
"""

import json
import os
import re
import shlex
import subprocess
import sys

HOOK_DIR = os.path.dirname(os.path.abspath(__file__))
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
WRAPPERS = {"env", "time", "command", "nice", "nohup", "exec", "xargs", "sudo"}
# Wrapper options that take a separate value (nice -n 5, sudo -u bob, xargs -I {}).
WRAPPER_VALUE_OPTIONS = {"-n", "-u", "-g", "-C", "-I", "-L", "-P", "-s", "-E"}
KEYWORDS = {"if", "then", "else", "elif", "while", "until", "do", "{", "!"}
SHELLS = {"bash", "sh", "zsh"}
OPERATOR_CHARS = "();<>|&\n"
# Quoted operator characters and backticks are replaced so the lexer cannot read them as operators.
MASK = str.maketrans({c: chr(0xE000 + i) for i, c in enumerate(OPERATOR_CHARS + "`")})
UNMASK = str.maketrans({v: chr(k) for k, v in MASK.items()})
HEREDOC = re.compile(r"(?<!<)<<(-?)\s*\\?(['\"]?)([^\s'\"<>;&|()]+)\2")
SUBSTITUTION = re.compile(r"(?<!\\)\$\(([^()]*)\)|(?<!\\)`([^`]*)`")
# Fallback when quoting cannot be parsed: git at the start of a command.
GIT_AT_COMMAND = re.compile(r"(?:^|[;&|(\n`]|\$\()\s*(?:\S*/)?git(?:\s|$)")


def log(kind, detail, cwd):
    script = f'source "{HOOK_DIR}/lib-log.sh"; harness_log "$0" "$1" "$2"'
    subprocess.run(["bash", "-c", script, kind, detail, cwd], check=False)


def quoted_at(line, pos):
    """True when position pos of line is inside quotes."""
    quote = None
    i = 0
    while i < pos:
        c = line[i]
        if c == "\\" and quote != "'":
            i += 2
            continue
        if quote is None and c in ("'", '"'):
            quote = c
        elif c == quote:
            quote = None
        i += 1
    return quote is not None


def strip_heredocs(command):
    """Drop heredoc bodies so their text is not parsed as commands."""
    lines = command.split("\n")
    out = []
    i = 0
    while i < len(lines):
        out.append(lines[i])
        i += 1
        for marker in HEREDOC.finditer(out[-1]):
            if quoted_at(out[-1], marker.start()):
                continue
            strip_tabs, word = marker.group(1), marker.group(3)
            end = next(
                (j for j in range(i, len(lines))
                 if (lines[j].lstrip("\t") if strip_tabs else lines[j]) == word),
                None,
            )
            if end is not None:
                i = end + 1
    return "\n".join(out)


def tokenize(command):
    lexer = shlex.shlex(command, posix=True, punctuation_chars=OPERATOR_CHARS)
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    lexer.commenters = ""
    return list(lexer)


def scan(command):
    """Prepare a command for the lexer.

    Returns the command with comments removed, unquoted backticks turned into separators and quoted
    operator characters masked, plus the `$(...)`/backtick bodies inside double quotes.
    As in bash, `#` starts a comment only at the start of an unquoted word.
    """
    out = []
    bodies = []
    quote = None
    start = 0
    i = 0
    while i < len(command):
        c = command[i]
        if c == "\\" and quote != "'":
            text = command[i:i + 2]
            out.append(text.translate(MASK) if quote else text)
            i += 2
            continue
        if quote is None:
            if c == "#" and (i == 0 or command[i - 1] in " \t" + OPERATOR_CHARS):
                end = command.find("\n", i)
                i = len(command) if end == -1 else end
                continue
            if c == "`":
                out.append(" ; ")
                i += 1
                continue
            if c in ("'", '"'):
                quote, start = c, i + 1
            out.append(c)
        elif c == quote:
            if quote == '"':
                for m in SUBSTITUTION.finditer(command[start:i]):
                    bodies.append(m.group(1) if m.group(1) is not None else m.group(2))
            quote = None
            out.append(c)
        else:
            out.append(c.translate(MASK))
        i += 1
    return "".join(out), bodies


def count_git(command):
    command, bodies = scan(strip_heredocs(command.replace("\\\n", " ")))
    try:
        tokens = tokenize(command)
    except ValueError:
        return len(GIT_AT_COMMAND.findall(command))
    count = sum(count_git(body) for body in bodies)
    words = []
    skip_next = False
    for token in tokens:
        if skip_next:
            skip_next = False
            continue
        if not (token and all(c in OPERATOR_CHARS for c in token)):
            words.append(token)
            continue
        # Split a glued token such as `;>` into its separator and redirection parts.
        cut = next((k for k, c in enumerate(token) if c in "<>"), len(token))
        if token.startswith("&>"):
            cut = 0
        separator, redirect = token[:cut], token[cut:]
        if separator:
            count += count_simple(words)
            words = []
        if redirect:
            # A file descriptor number (2>) belongs to the redirection, not the command.
            if words and words[-1].isdigit():
                words.pop()
            # The target is the next word, unless the operator consumes it (>&1).
            skip_next = not redirect.endswith("&") or redirect in ("&>", "&>>")
    return count + count_simple(words)


def count_simple(words):
    i = 0
    wrapped = False
    while i < len(words):
        word = words[i]
        name = os.path.basename(word)
        if name in WRAPPERS:
            if name == "command" and i + 1 < len(words) and words[i + 1] in ("-v", "-V"):
                # `command -v git` looks git up without running it.
                return 0
            wrapped = True
        elif not (ASSIGNMENT.match(word) or word in KEYWORDS or (wrapped and word.startswith("-"))):
            break
        i += 1
        if wrapped and word in WRAPPER_VALUE_OPTIONS:
            i += 1
    words = words[i:]
    if not words:
        return 0
    program = os.path.basename(words[0])
    if program == "git":
        return 1
    if program in SHELLS:
        for index, word in enumerate(words[1:], start=1):
            if re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", word) and index + 1 < len(words):
                return count_git(words[index + 1].translate(UNMASK))
    return 0


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return 0
    tool_input = data.get("tool_input") if isinstance(data, dict) else None
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str) or "git" not in command or count_git(command) < 2:
        return 0
    cwd = data.get("cwd")
    log("block-git-chain", "multiple-git-commands", cwd if isinstance(cwd, str) else os.getcwd())
    print(
        "Blocked (git-chain): run one git command per Bash call. Split this into separate calls in "
        "order, so each operation gets its own permission check. `cd <dir> && git ...` with a single "
        "git is fine.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
