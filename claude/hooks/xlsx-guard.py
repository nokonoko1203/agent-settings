#!/usr/bin/env python3
"""Hook: validate .xlsx files written by a Bash command.

Events: PreToolUse, PostToolUse and PostToolUseFailure, all with matcher Bash.
The searched directories are the working directory and the directories of the absolute paths
that appear anywhere in the command text, quoted or not. PreToolUse records when the command
started and the (inode, mtime, size) of every .xlsx there. After the command, whether it
succeeded or failed, a .xlsx counts as changed by the command when it is new or any of those
three values changed. Reading a cloud-only file (which downloads it and touches only ctime)
therefore does not count, while files moved or copied into a directory scanned beforehand do.
Changed files are checked with xlsx_validate.py, smallest first; cloud-only files are never read.
Errors exit 2 so Claude sees them next to the tool result and repairs the file. The hook never
modifies workbooks.

Not covered: commands run in the background (they may still be writing when the hook runs),
commands interrupted with Esc (no post event fires), and files whose location appears nowhere
in the command and lies outside the working directory.
"""

import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time

HOOK_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HOOK_DIR)
import xlsx_validate  # noqa: E402

STATE_DIR = os.path.join(tempfile.gettempdir(), "claude-xlsx-guard")
STALE_MARKER_SECONDS = 24 * 3600
# Hook timeout is 60s; leave room for scanning and reporting.
VALIDATION_BUDGET_SECONDS = 40
MIN_FILE_SECONDS = 5
MAX_DEPTH = 4
MAX_DIRS = 20000
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".cache"}
SF_DATALESS = 0x40000000  # macOS: cloud-only placeholder; reading it downloads the file
HOME = os.path.realpath(os.path.expanduser("~"))
# Never scanned themselves: scanning them would walk huge trees. Their subdirectories are fine.
# Compared in lower case because the default APFS volume is case-insensitive.
BROAD_DIRS = {
    p.lower()
    for p in ("/tmp", "/private/tmp", "/var", "/Volumes", "/Users",
              os.path.join(HOME, "Library"), os.path.join(HOME, "Library", "CloudStorage"))
}
# Never scanned, including everything below them: system locations hold no user workbooks.
SYSTEM_PREFIXES = tuple(
    p.lower() for p in ("/System", "/Library", "/Applications", "/usr", "/bin", "/sbin", "/opt", "/private/var", "/dev", "/cores")
)

# Absolute or ~/ paths anywhere in the command, including inside quotes and -c strings.
# "\ " (an escaped space) stays part of the path.
PATH_TOKEN_RE = re.compile(r"(?<![\w.~/-])(~?/(?:\\ |[^\s\"'`;|&<>()\\])+)")
# Quoted strings that are a path by themselves, so paths with spaces are kept whole.
QUOTED_PATH_RE = re.compile(r"\"(~?/[^\"]*)\"|'(~?/[^']*)'")


def log(kind, detail, cwd):
    script = f'source "{HOOK_DIR}/lib-log.sh"; harness_log "$0" "$1" "$2"'
    subprocess.run(["bash", "-c", script, kind, detail, cwd], check=False)


def safe_id(value):
    return re.sub(r"[^A-Za-z0-9_-]", "_", value or "")


def marker_path(data):
    # One flat file per call, so concurrent sessions never remove each other's directories.
    return os.path.join(STATE_DIR, f"{safe_id(data.get('session_id'))}__{safe_id(data.get('tool_use_id'))}")


def remove_stale_markers(now):
    try:
        entries = list(os.scandir(STATE_DIR))
    except OSError:
        return
    for entry in entries:
        try:
            if now - entry.stat().st_mtime > STALE_MARKER_SECONDS:
                os.remove(entry.path)
        except OSError:
            pass


def record_start(data):
    now = time.time()
    remove_stale_markers(now)
    roots = roots_from(data)
    files, truncated = snapshot(roots)
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(marker_path(data), "w") as f:
        json.dump({"start": now, "roots": sorted(roots), "files": files, "truncated": truncated}, f)


def take_start(data):
    path = marker_path(data)
    try:
        with open(path) as f:
            before = json.load(f)
        os.remove(path)
        return before
    except (OSError, ValueError):
        return None


def too_broad(path):
    """Reject roots whose scan would cover home, a system location, or another huge tree."""
    p, home = path.lower(), HOME.lower()
    if p == "/" or p in BROAD_DIRS or p.count("/") < 2:
        return True
    if any(p == s or p.startswith(s + "/") for s in SYSTEM_PREFIXES):
        return True
    return home == p or home.startswith(p.rstrip("/") + "/")


def path_candidates(command):
    found = [m.group(1) or m.group(2) for m in QUOTED_PATH_RE.finditer(command)]
    found += [m.group(1).replace("\\ ", " ") for m in PATH_TOKEN_RE.finditer(command)]
    return found


def roots_from(data):
    command = (data.get("tool_input") or {}).get("command") or ""
    candidates = [data.get("cwd") or ""]
    for text in path_candidates(command):
        candidates.append(re.split(r"[$*?]", text, maxsplit=1)[0])
    roots = set()
    for raw in candidates:
        if not raw:
            continue
        path = os.path.expanduser(raw).rstrip("/")
        if not os.path.isdir(path):
            path = os.path.dirname(path)
        if not path or not os.path.isdir(path):
            continue
        path = os.path.realpath(path)
        if not too_broad(path):
            roots.add(path)
    return roots


def written_since(mtime_ns, since):
    # Filesystems with whole-second timestamps round the write time down, so compare
    # in whole seconds there; elsewhere a file written just before the command is excluded.
    if mtime_ns % 1_000_000_000 == 0:
        return mtime_ns / 1e9 >= math.floor(since)
    return mtime_ns / 1e9 >= since


def known_absent_before(path, roots, start):
    """Whether `path` could not have existed before the command.

    True when the PreToolUse scan covered its directory (same depth limit and skips), or when the
    directory itself was created during the command (for example `mkdir -p a/b && cp -p x a/b/`).
    """
    directory = os.path.dirname(path)
    try:
        if os.stat(directory).st_birthtime >= start:
            return True
    except (OSError, AttributeError):
        pass
    for root in roots:
        rel = os.path.relpath(directory, root)
        if rel == ".":
            return True
        if rel.startswith(".."):
            continue
        parts = rel.split(os.sep)
        if len(parts) <= MAX_DEPTH and not SKIP_DIRS.intersection(parts):
            return True
    return False


def changed_by_command(before, after):
    """Return (path, how) for .xlsx files the command wrote or brought in.

    "written": new with a modification time inside the command, or its inode, mtime or size changed.
    "brought in": new with an older modification time where it cannot have been before the command
    (a directory the PreToolUse scan covered, or one created during the command), i.e. moved or
    copied in with its metadata. A file found only because the PostToolUse scan starts elsewhere
    (a removed directory, a changed cwd) is not "brought in": it was simply not looked at before.
    Files whose three values are unchanged (only read, or downloaded from the cloud) are left out.
    """
    changed = []
    for path, state in after.items():
        previous = before["files"].get(path)
        if previous is not None:
            if previous != state:
                changed.append((path, "written"))
        elif written_since(state[1], before["start"]):
            changed.append((path, "written"))
        elif not before.get("truncated") and known_absent_before(path, before.get("roots", []), before["start"]):
            changed.append((path, "brought in"))
    return changed


def snapshot(roots):
    """Return ({path: [inode, mtime_ns, size]} for .xlsx files under roots, whether the scan hit its limit)."""
    found = {}
    visited = set()
    stack = [(root, 0) for root in sorted(roots)]
    while stack:
        directory, depth = stack.pop()
        if directory in visited:
            continue
        visited.add(directory)
        if len(visited) > MAX_DIRS:
            return found, True
        try:
            entries = list(os.scandir(directory))
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    if depth < MAX_DEPTH and entry.name not in SKIP_DIRS:
                        stack.append((entry.path, depth + 1))
                elif entry.name.lower().endswith(".xlsx") and not entry.name.startswith("~$"):
                    st = entry.stat()
                    found[os.path.realpath(entry.path)] = [st.st_ino, st.st_mtime_ns, st.st_size]
            except OSError:
                continue
    return found, False


def emit_context(event, text):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}))


def check_after(data):
    event = data.get("hook_event_name")
    before = take_start(data)
    if before is None or (data.get("tool_input") or {}).get("run_in_background"):
        return 0
    cwd = data.get("cwd") or os.getcwd()
    roots = roots_from(data)
    after, truncated = snapshot(roots)
    if truncated or before.get("truncated"):
        log("xlsx-guard-scan-limit", f"stopped after {MAX_DIRS} directories under {len(roots)} root(s)", cwd)

    broken, warned, skipped = [], [], []
    budget_end = time.monotonic() + VALIDATION_BUDGET_SECONDS
    # Smallest first, so one huge workbook cannot use up the budget before small broken ones.
    for path, how in sorted(changed_by_command(before, after), key=lambda item: (after[item[0]][2], item[0])):
        try:
            if os.stat(path).st_flags & SF_DATALESS:
                continue  # cloud-only: the command did not write its content, and reading it would download it
        except OSError:
            continue
        remaining = budget_end - time.monotonic()
        if remaining < MIN_FILE_SECONDS:
            skipped.append(path)
            continue
        report = xlsx_validate.validate(path, time_limit=remaining)
        if report.errors:
            broken.append((path, how, report))
        elif report.warnings:
            warned.append((path, how, report))

    notes = [
        f"xlsx-guard warning (not a known Excel repair trigger): {path} ({how})\n" + "\n".join(f"  warning: {w}" for w in report.warnings)
        for path, how, report in warned
    ]
    if skipped:
        notes.append("xlsx-guard: not checked within the time budget: " + ", ".join(skipped))
    if broken:
        lines = [
            "xlsx-guard: .xlsx files changed by this command contain structures that make Excel offer to repair the workbook (the repair can drop data), or could not be checked.",
        ]
        for path, how, report in broken:
            lines.append(f"{path} ({how})")
            lines += [f"  error: {e}" for e in report.errors]
            lines += [f"  warning: {w}" for w in report.warnings]
        lines.append(
            "Fix each file, or restore it from the backup taken before the edit, then re-run "
            f"`python3 -I {HOOK_DIR}/xlsx_validate.py <file>` until it reports no errors. "
            "Do not treat the task as done, and do not have the user open the file in Excel, while errors remain. "
            "If the errors were already in the file before the edit, follow ~/.claude/references/xlsx-repair.md."
        )
        if any(how == "brought in" for _, how, _ in broken):
            lines.append(
                "A file marked 'brought in' was moved or copied here with its older content. If it is a backup "
                "of a file that was already broken, keep the backup unchanged and fix the original instead."
            )
        lines += notes
        detail = "; ".join(os.path.basename(path) + ": " + ",".join(r.error_kinds) for path, _, r in broken)
        log("xlsx-validate", detail[:500], cwd)
        print("\n".join(lines), file=sys.stderr)
        return 2
    if notes:
        emit_context(event, "\n".join(notes))
    return 0


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return 0
    if data.get("tool_name") != "Bash":
        return 0
    event = data.get("hook_event_name")
    if event == "PreToolUse":
        record_start(data)
        return 0
    if event in ("PostToolUse", "PostToolUseFailure"):
        return check_after(data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
