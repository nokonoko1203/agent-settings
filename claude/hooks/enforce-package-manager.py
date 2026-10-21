#!/usr/bin/env python3
"""PreToolUse hook: allow only the package manager the repository already uses.

Matcher: Bash
The manager is detected from the nearest lockfile above the working directory.
Without a lockfile, bun (JavaScript) and uv (Python) are required.
One-off runners (npx, bunx, bun x, pnpm dlx, yarn dlx, uvx) are not checked.
"""

import json
import os
import re
import shlex
import subprocess
import sys

HOOK_DIR = os.path.dirname(os.path.abspath(__file__))

JS_LOCKFILES = [
    ("bun.lock", "bun"),
    ("bun.lockb", "bun"),
    ("pnpm-lock.yaml", "pnpm"),
    ("yarn.lock", "yarn"),
    ("package-lock.json", "npm"),
]
PY_LOCKFILES = [
    ("uv.lock", "uv"),
    ("poetry.lock", "poetry"),
    ("Pipfile.lock", "pipenv"),
]
JS_DEFAULT = "bun"
PY_DEFAULT = "uv"

# Subcommands that install, change dependencies, or run project scripts.
JS_SUBCOMMANDS = {
    "install", "i", "add", "remove", "rm", "uninstall", "un", "update", "up",
    "upgrade", "ci", "run", "run-script", "test", "t", "exec", "link", "dedupe",
    "prune", "create",
}
YARN_READ_ONLY = {"info", "why", "config", "cache", "help", "list", "outdated", "audit", "npm"}
PY_SUBCOMMANDS = {
    "uv": {"add", "remove", "sync", "lock", "run", "pip", "init"},
    "poetry": {"add", "remove", "install", "update", "lock", "run", "init"},
    "pipenv": {"install", "uninstall", "sync", "update", "lock", "run"},
    "pip": {"install", "uninstall"},
}
WRAPPERS = {"env", "time", "command", "nice", "nohup"}
SEPARATORS = re.compile(r"&&|\|\||;|\||\n|&")


def log(kind, detail, cwd):
    script = f'source "{HOOK_DIR}/lib-log.sh"; harness_log "$0" "$1" "$2"'
    subprocess.run(["bash", "-c", script, kind, detail, cwd], check=False)


def find_manager(start, lockfiles):
    """Search upward, stopping at the git root. The home directory and above are never used."""
    home = os.path.expanduser("~")
    path = os.path.abspath(start)
    while path != home:
        found = [manager for name, manager in lockfiles if os.path.exists(os.path.join(path, name))]
        if found:
            return set(found), path
        parent = os.path.dirname(path)
        if os.path.exists(os.path.join(path, ".git")) or parent == path:
            break
        path = parent
    return None, None


def first_words(segment):
    try:
        words = shlex.split(segment)
    except ValueError:
        words = segment.split()
    while words and (re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", words[0]) or words[0] in WRAPPERS):
        words = words[1:]
    return words


def classify(words):
    """Return (ecosystem, manager) when the words invoke a checked subcommand."""
    if not words:
        return None
    program = os.path.basename(words[0])
    rest = words[1:]
    sub = next((w for w in rest if not w.startswith("-")), None)

    if program in ("npm", "pnpm", "bun"):
        return ("js", program) if sub in JS_SUBCOMMANDS else None
    if program == "yarn":
        # A bare `yarn` installs dependencies, and `yarn <script>` runs a script.
        if rest and rest[0] in ("--version", "-v", "--help", "-h"):
            return None
        return None if sub in YARN_READ_ONLY else ("js", "yarn")
    if program in ("pip", "pip3"):
        return ("py", "pip") if sub in PY_SUBCOMMANDS["pip"] else None
    if re.match(r"^python(3(\.\d+)?)?$", program) and rest[:2] == ["-m", "pip"]:
        sub = next((w for w in rest[2:] if not w.startswith("-")), None)
        return ("py", "pip") if sub in PY_SUBCOMMANDS["pip"] else None
    if program in ("uv", "poetry", "pipenv"):
        return ("py", program) if sub in PY_SUBCOMMANDS[program] else None
    return None


def main():
    data = json.load(sys.stdin)
    command = (data.get("tool_input") or {}).get("command") or ""
    cwd = data.get("cwd") or os.getcwd()
    if not command:
        return 0

    current = cwd
    variables = dict(os.environ)
    for segment in SEPARATORS.split(command):
        segment = segment.strip()
        for name, value in re.findall(r"^([A-Za-z_][A-Za-z0-9_]*)=(\S+)$", segment):
            variables[name] = value.strip("'\"")
        words = first_words(segment)
        if not words:
            continue
        if words[0] == "cd" and len(words) > 1:
            target = re.sub(
                r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?",
                lambda m: variables.get(m.group(1), m.group(0)),
                os.path.expanduser(words[1]),
            )
            current = os.path.normpath(os.path.join(current, target))
            continue

        result = classify(words)
        if result is None:
            continue
        ecosystem, manager = result
        lockfiles, default = (JS_LOCKFILES, JS_DEFAULT) if ecosystem == "js" else (PY_LOCKFILES, PY_DEFAULT)
        allowed, root = find_manager(current, lockfiles)

        if allowed is None:
            if manager == default:
                continue
            reason = f"No lockfile found; new projects use {default}. Use {default} instead of {manager}."
        elif manager in allowed:
            continue
        else:
            names = ", ".join(sorted(allowed))
            reason = f"This repository uses {names} (lockfile in {root}). Use {names} instead of {manager}."

        log("enforce-package-manager", f"{manager} -> {sorted(allowed) if allowed else default}", cwd)
        print(f"Blocked: {reason}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
