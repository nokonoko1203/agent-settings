#!/usr/bin/env python3
"""Stop hook: keep Claude working when the final reply points to files that do not exist.

Matcher: (none)
Two kinds of targets are checked, both outside fenced code blocks:
- Markdown links, `[name](path)`. URLs and anchors are not checked.
- Paths written in inline code, because the desktop app makes those clickable too and opens them
  against the session's directory. A code span counts as a path only when it has no spaces or
  shell / placeholder characters and either ends in a known file extension, starts with `~/`, `./`
  or `../`, or is an absolute path whose first directory exists. Values like `fx.bgSwitch`,
  `1577/24`, `origin/main`, `/clear` or `.env` are not paths.
Relative targets resolve against CLAUDE_PROJECT_DIR (the directory the session started in),
not the hook input `cwd`, which follows `cd`. When `cwd` differs from CLAUDE_PROJECT_DIR, the app may
resolve relative links against `cwd` instead, so every relative target is reported and the reply must
use absolute paths. Absolute paths resolve the same way from any working directory.
A relative target that leaves CLAUDE_PROJECT_DIR (for example `../x`) is reported even when it exists:
files outside the session's folder are written as absolute paths.
Line suffixes (:42, :42-50, #L42) are ignored.
Fragments (#section) and queries (?x) are ignored too, and backslash escapes are undone.
Each set of reported paths is reported once per session, so an intentional link cannot loop.
"""

import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from urllib.parse import unquote

HOOK_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.expanduser("~/.claude/state/link-check")

FENCE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")
INLINE_CODE = re.compile(r"(`+)((?:(?!\1).)+?)\1")
LINK = re.compile(r"\]\(\s*(?:<([^>]+)>|((?:[^()\s]|\([^()\s]*\))+))(?:\s+\"[^\"]*\")?\s*\)")
SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
LINE_SUFFIX = re.compile(r"(?::L?\d+)+(?:-L?\d+)?$")
ESCAPE = re.compile(r"\\([!-/:-@\[-`{-~])")

# Inline code is a path only when it looks like one: no spaces, no shell, placeholder or code syntax.
CODE_NOT_PATH = re.compile(r"[\s<>*{}$|=\"'`,;()\[\]!?&^%]")
NUMERIC = re.compile(r"^[\d.:/×x+-]+$")
EXTENSIONS = frozenset("""
md markdown txt rst json jsonl yaml yml toml ini cfg conf env tpl lock
py pyi ipynb ts tsx js jsx mjs cjs sh bash zsh fish rb go rs java kt swift c h cc cpp hpp cs php lua r
html htm css scss sass vue svelte svg xml sql graphql proto
png jpg jpeg gif webp avif bmp ico tif tiff heic psd
mp4 mov webm mkv avi mp3 wav m4a aac flac ogg srt vtt lrc
csv tsv xlsx xls docx doc pptx ppt pdf
log zip tar gz tgz glb gltf fbx obj blend usdz
geojson topojson gpkg pmtiles mbtiles fgb kml kmz shp gpx parquet tif qgs qgz
mid midi diff patch woff woff2 ttf otf jsonc json5 mdx mts cts tf hcl
""".split())


def log(kind, detail, cwd):
    script = f'source "{HOOK_DIR}/lib-log.sh"; harness_log "$0" "$1" "$2"'
    subprocess.run(["bash", "-c", script, kind, detail, cwd], check=False)


def code_is_path(code):
    if CODE_NOT_PATH.search(code) or SCHEME.match(code) or NUMERIC.match(code) or code.startswith(("-", "#")):
        return False
    if "..." in code:  # an abbreviated path such as src/.../foo.ts
        return False
    if code.startswith(("~/", "./", "../")):
        return True
    if code.startswith("/"):
        # Match the top directory's exact case: macOS ignores case, so /users would match /Users.
        top = code.split("/")[1]
        try:
            return bool(top) and top in os.listdir("/") and os.path.isdir("/" + top)
        except (OSError, ValueError):
            return False
    name = LINE_SUFFIX.sub("", code).rsplit("/", 1)[-1]
    stem, dot, ext = name.rpartition(".")
    return bool(dot) and stem != "" and ext.lower() in EXTENSIONS


def targets(text):
    """Yield (kind, target) for every Markdown link ("link") and path-like inline code ("code")."""
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
        for match in INLINE_CODE.finditer(line):
            code = match.group(2).strip()
            if code_is_path(code):
                yield "code", code
        for match in LINK.finditer(INLINE_CODE.sub("", line)):
            yield "link", match.group(1) or match.group(2)


def file_part(target):
    if target.startswith("#") or SCHEME.match(target):
        return None
    path = re.split(r"[#?]", ESCAPE.sub(r"\1", target), maxsplit=1)[0]
    path = unquote(LINE_SUFFIX.sub("", path))
    return os.path.expanduser(path) or None


def to_path(target, base):
    path = file_part(target)
    return os.path.join(base, path) if path else None


def is_relative(target):
    path = file_part(target)
    return bool(path) and not os.path.isabs(path)


def leaves(target, base):
    """A relative target that resolves outside base. Compared as strings, so a symlink inside
    base that points elsewhere still counts as inside, and no filesystem call can raise."""
    if not is_relative(target):
        return False
    path = os.path.normpath(to_path(target, base))
    root = os.path.normpath(os.path.abspath(base))
    return path != root and not path.startswith(root + os.sep)


def exists(path):
    try:
        return os.path.exists(path)
    except ValueError:  # an embedded null byte, e.g. from %00
        return False


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(data, dict):
        return 0
    base = os.environ.get("CLAUDE_PROJECT_DIR")
    message = data.get("last_assistant_message")
    session_id = data.get("session_id")
    if not base or not isinstance(message, str) or not message or not isinstance(session_id, str):
        return 0

    found = set(targets(message))
    all_targets = {t for _, t in found}
    broken = sorted({t for k, t in found if k == "link" and (p := to_path(t, base)) and not exists(p)})
    broken_code = sorted({t for k, t in found if k == "code" and (p := to_path(t, base)) and not exists(p)} - set(broken))
    outside = sorted({t for t in all_targets if leaves(t, base)} - set(broken) - set(broken_code))
    cwd = data.get("cwd")
    moved = isinstance(cwd, str) and os.path.realpath(cwd) != os.path.realpath(base)
    reported = set(broken) | set(broken_code) | set(outside)
    ambiguous = sorted({t for t in all_targets if is_relative(t)} - reported) if moved else []
    # Key the state by a hash so session_id never acts as a path.
    state_file = os.path.join(STATE_DIR, hashlib.sha256(session_id.encode()).hexdigest()[:16])
    if not broken and not broken_code and not outside and not ambiguous:
        if os.path.exists(state_file):
            os.remove(state_file)
        return 0

    digest = hashlib.sha256(
        "\0".join(["broken", *broken, "\1code", *broken_code, "\1outside", *outside, "\1ambiguous", *ambiguous]).encode()
    ).hexdigest()
    try:
        with open(state_file) as f:
            if digest in f.read().split():
                return 0
    except FileNotFoundError:
        pass
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(state_file, "a") as f:
        f.write(digest + "\n")

    absolute_hint = (
        "Files outside the session's folder are written as absolute paths; send videos or images the "
        "user should watch or view with SendUserFile as well. Write the absolute path as the link "
        "target as is, as `[name](/abs/path)`: do not wrap it in angle brackets like `[name](</abs/path>)`, "
        "which the app does not render as a link."
    )
    parts = []
    if broken:
        log("broken-link", f"{len(broken)} broken link(s)", base)
        listing = "\n".join(f"- {t}" for t in broken)
        parts.append(
            f"Your reply links to files that do not exist (relative links resolve against {base}):\n"
            f"{listing}\n"
            "Check the correct paths and post a short correction with fixed links. "
            "If a link is intentional (for example a file deleted in this reply), say so in one line."
        )
    if broken_code:
        log("broken-code-path", f"{len(broken_code)} broken inline-code path(s)", base)
        listing = "\n".join(f"- {t}" for t in broken_code)
        parts.append(
            "Your reply writes paths in inline code that do not exist. The app makes inline-code paths "
            f"clickable and opens them against {base}, so these fail for the user:\n"
            f"{listing}\n"
            "Post a short correction that gives each file as a Markdown link with its correct path "
            f"(absolute when it is outside {base}). "
            "If a span is not meant as a path (an example or a name inside another folder you already "
            "linked), say so in one line."
        )
    if outside:
        log("outside-relative-link", f"{len(outside)} relative path(s) leaving the project", base)
        listing = "\n".join(f"- {t}" for t in outside)
        parts.append(
            f"These relative paths point outside {base}:\n{listing}\n"
            "Post a short correction that gives them as absolute paths."
        )
    if ambiguous:
        log("cwd-moved-link", f"{len(ambiguous)} relative link(s) while cwd={cwd}", base)
        listing = "\n".join(f"- {t}" for t in ambiguous)
        parts.append(
            f"The working directory moved from {base} to {cwd}, so these relative links may open "
            f"against the wrong directory:\n{listing}\n"
            f"Post a short correction that links them by absolute path, and run `cd {shlex.quote(base)}` "
            "so later links resolve from the session's starting directory again."
        )
    if broken_code or outside:
        parts.append(absolute_hint)
    reason = "\n\n".join(parts)
    print(json.dumps({"decision": "block", "reason": reason}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
