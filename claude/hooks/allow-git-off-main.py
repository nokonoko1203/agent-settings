#!/usr/bin/env python3
"""PreToolUse hook: auto-approve git commands that do not touch the protected branch.

Matcher: Bash
Returns "allow" when the whole command is git invocations (optionally `cd <dir>`) joined by `&&`,
`;` or newlines, HEAD is not a protected branch, and every invocation matches an allowlisted form:
read-only subcommands, or a mutating subcommand whose options are all listed in SPECS and whose
arguments pass its check. Returns "deny" when a push writes a protected branch, "ask" when a push
may write one (mirror remote, configured push refspecs, push.default=matching), and "ask" when
rebase/rm runs while HEAD is protected. `worktree remove` without --force and `branch -d` of
an unprotected branch are also allowed while HEAD is protected; git refuses to drop tracked,
untracked or unmerged work in those forms, though ignored files in the worktree are deleted. A
command may continue after `worktree remove` only if every later separator is `&&`.
Everything else gets no decision and falls through to the normal permission flow: shell expansion,
pipes, redirects, non-git commands, aliases, unlisted options (including abbreviations), and forms
that create, move or check out a protected branch or discard uncommitted work.
Destructive commands (reset --hard, clean, branch -D) also stay `ask` rules in settings.json,
which a hook "allow" cannot override.
This matches command text only and is not a security boundary.
"""

import json
import os
import re
import shlex
import subprocess
import sys

PROTECTED = {"main", "master"}
ASK_ON_PROTECTED = {"rebase", "rm"}
# A higher rank wins when segments disagree.
RANK = {"allow": 0, "ask": 1, "deny": 2}
READ_ONLY = {
    "status", "log", "diff", "show", "blame", "shortlog", "rev-parse", "rev-list", "ls-files",
    "ls-tree", "show-ref", "describe", "merge-base", "cherry", "range-diff",
}
# Long options of read-only subcommands that write files or run programs (also matched as prefixes,
# since git accepts unique abbreviations).
READ_ONLY_UNSAFE = ("--output", "--ext-diff", "--textconv", "--open-files-in-pager")
UPSTREAM_OPTIONS = {"-u", "--set-upstream", "--set-upstream-to", "--unset-upstream", "--track"}
# Characters bash/zsh treat specially outside quotes and inside double quotes.
UNQUOTED_META = set("$`{}*?[]~|<>()\\")
DOUBLE_QUOTED_META = set("$`\\")
OPERATORS = {"&&", ";"}


class Undecided(Exception):
    pass


def git(args, cwd):
    try:
        result = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, check=False, timeout=5
        )
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def current_branch(cwd):
    """Return HEAD's branch, or the branch being rebased while HEAD is detached."""
    branch = git(["symbolic-ref", "--short", "-q", "HEAD"], cwd)
    if branch is not None:
        return branch
    for state in ("rebase-merge/head-name", "rebase-apply/head-name"):
        path = git(["rev-parse", "--path-format=absolute", "--git-path", state], cwd)
        try:
            with open(path) as f:
                return f.read().strip().removeprefix("refs/heads/")
        except (OSError, TypeError):
            continue
    return None


def has_shell_meta(command):
    quote = None
    for c in command:
        if quote == "'":
            if c == "'":
                quote = None
        elif quote == '"':
            if c == '"':
                quote = None
            elif c in DOUBLE_QUOTED_META:
                return True
        elif c in ("'", '"'):
            quote = c
        elif c in UNQUOTED_META:
            return True
    return quote is not None


def is_protected_ref(ref):
    # git resolves heads/main, refs/heads/main and origin/main by suffix; macOS refs are
    # case-insensitive.
    ref = ref.lstrip("+").lower()
    return ref in PROTECTED or any(ref.endswith("/" + name) for name in PROTECTED)


def refspec_writes_protected(spec, branch):
    if "*" in spec or spec in (":", "+:"):
        return True
    dst = spec.rsplit(":", 1)[-1]
    if ":" not in spec and dst.lstrip("+") in ("HEAD", "@"):
        # `push origin HEAD` writes the branch of the same name as HEAD's; detached HEAD is unknown.
        return branch is None or is_protected_ref(branch)
    return dst == "" or is_protected_ref(dst)


def segments(command):
    """Yield (words, separator) pairs; separator is "&&", ";" (also for newlines) or None at the end."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&\n")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    lexer.commenters = ""
    current = []
    for token in lexer:
        if all(c in ";&\n" for c in token):
            if token.replace("\n", ";").strip(";") and token not in OPERATORS:
                raise ValueError(token)
            if current:
                yield current, "&&" if token == "&&" else ";"
            current = []
            continue
        current.append(token)
    if current:
        yield current, None


def parse(args, flags, values):
    """Split args into (options, positionals); raise Undecided on any unlisted option.

    options maps each option name to the list of its values (empty for flags).
    """
    options, positional = {}, []
    i = 0
    while i < len(args):
        arg = args[i]
        i += 1
        if arg == "--" and "--" in flags:
            positional.extend(args[i:])
            break
        if arg.startswith("--"):
            name, eq, value = arg.partition("=")
            if name in values:
                if not eq:
                    if i >= len(args):
                        raise Undecided
                    value = args[i]
                    i += 1
                options.setdefault(name, []).append(value)
            elif name in flags and not eq:
                options.setdefault(name, [])
            else:
                raise Undecided
        elif arg.startswith("-") and len(arg) > 1:
            j = 1
            while j < len(arg):
                name = "-" + arg[j]
                j += 1
                if name in values:
                    value = arg[j:]
                    if not value:
                        if i >= len(args):
                            raise Undecided
                        value = args[i]
                        i += 1
                    options.setdefault(name, []).append(value)
                    break
                if name not in flags:
                    raise Undecided
                options.setdefault(name, [])
        else:
            positional.append(arg)
    return options, positional


def deny_protected(*names):
    if any(is_protected_ref(n) for n in names):
        raise Undecided


def check_push(opts, pos, cwd):
    head = current_branch(cwd)
    branch = head or ""
    remote = pos[0] if pos else next(
        (r for r in (
            git(["config", "--get", f"branch.{branch}.pushRemote"], cwd),
            git(["config", "--get", "remote.pushDefault"], cwd),
            git(["config", "--get", f"branch.{branch}.remote"], cwd),
        ) if r),
        "origin",
    )
    # A mirror remote or configured push refspecs may map any push onto protected branches.
    if (git(["config", "--get", f"remote.{remote}.mirror"], cwd) or "").lower() in (
        "true", "yes", "on", "1", "fetch", "push",
    ) or git(["config", "--get-all", f"remote.{remote}.push"], cwd):
        return "ask"
    refspecs = pos[1:]
    if refspecs:
        return "deny" if any(refspec_writes_protected(s, head) for s in refspecs) else "allow"
    # No refspec: `matching` pushes every branch; otherwise the current branch's push target.
    if (git(["config", "--get", "push.default"], cwd) or "").lower() == "matching":
        return "ask"
    dest = git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{push}"], cwd)
    if dest is None:
        # No push target: push.autoSetupRemote or push.default=current would create one named after HEAD.
        dest = head
    return "deny" if dest is not None and is_protected_ref(dest) else "allow"


def check_fetch(opts, pos, cwd):
    # Plain remote/branch names only; refspecs with `:` or wildcards can write local branches.
    if any(":" in p or "*" in p for p in pos):
        raise Undecided


def check_switch(opts, pos, cwd):
    deny_protected(*pos, *opts.get("-c", []), *opts.get("--create", []))


def check_checkout(opts, pos, cwd):
    if "-b" in opts:
        deny_protected(*opts["-b"])
        if len(pos) > 1:
            raise Undecided
        return
    # Only `checkout <existing local branch>`; pathspec forms discard work.
    if len(pos) != 1 or pos[0].startswith(":"):
        raise Undecided
    deny_protected(pos[0])
    if git(["show-ref", "--verify", "--quiet", f"refs/heads/{pos[0]}"], cwd) is None:
        raise Undecided


def check_branch(opts, pos, cwd):
    deny_protected(*pos, *opts.get("-u", []), *opts.get("--set-upstream-to", []))


def check_rebase(opts, pos, cwd):
    # `rebase <upstream> <branch>` checks out <branch> first.
    if len(pos) > 1:
        raise Undecided


def check_stash(opts, pos, cwd):
    if pos and pos[0] not in ("push", "list", "show", "pop", "apply"):
        raise Undecided


def check_worktree(opts, pos, cwd):
    if not pos or pos[0] not in ("add", "list", "remove"):
        raise Undecided
    if pos[0] == "remove" and len(pos) != 2:
        raise Undecided
    deny_protected(*pos[2:], *opts.get("-b", []))
    if pos[0] == "add" and len(pos) == 2 and "-b" not in opts and "--detach" not in opts:
        # Without a branch, git checks out (or creates) the branch named after the path.
        deny_protected(os.path.basename(os.path.normpath(pos[1])))


def check_remote(opts, pos, cwd):
    if pos and pos[0] not in ("show", "get-url"):
        raise Undecided


def check_tag(opts, pos, cwd):
    deny_protected(*pos)


QUIET = {"-q", "--quiet"}
VERBOSE = {"-v", "--verbose"}
# subcommand: (flags, options taking a value, argument check)
SPECS = {
    "add": ({"-A", "--all", "-u", "--update", "-N", "--intent-to-add", "-n", "--dry-run", "--"}
            | VERBOSE, set(), None),
    "commit": ({"-a", "--all", "--amend", "--no-edit", "-s", "--signoff", "--allow-empty", "--"}
               | QUIET | VERBOSE,
               {"-m", "--message", "-F", "--file", "--fixup", "--author", "--date"}, None),
    "push": ({"-u", "--set-upstream", "-f", "--force", "--force-with-lease", "--force-if-includes",
              "-n", "--dry-run", "--follow-tags"} | QUIET | VERBOSE,
             {"-o", "--push-option"}, check_push),
    "fetch": ({"-p", "--prune", "--all", "--tags", "--no-tags"} | QUIET | VERBOSE, set(),
              check_fetch),
    "pull": ({"-r", "--rebase", "--no-rebase", "--ff", "--no-ff", "--ff-only", "--autostash"}
             | QUIET | VERBOSE, set(), check_fetch),
    "switch": ({"--track", "--no-track", "-d", "--detach"} | QUIET, {"-c", "--create"},
               check_switch),
    "checkout": ({"--track", "--no-track"} | QUIET, {"-b"}, check_checkout),
    "branch": ({"-a", "--all", "-r", "--remotes", "--list", "--show-current", "-d", "--delete",
                "-m", "--move", "--unset-upstream", "--merged", "--no-merged"} | QUIET | VERBOSE,
               {"-u", "--set-upstream-to", "--contains", "--sort", "--format"}, check_branch),
    "merge": ({"--no-ff", "--ff-only", "--ff", "--squash", "--no-edit", "--continue",
               "--no-commit"} | QUIET, {"-m", "--message"}, None),
    "rebase": ({"--continue", "--autostash"} | QUIET, {"--onto"}, check_rebase),
    "stash": ({"-u", "--include-untracked", "-k", "--keep-index"} | QUIET, {"-m", "--message"},
              check_stash),
    "rm": ({"--cached", "-r", "-n", "--dry-run", "--"} | QUIET, set(), None),
    "mv": ({"-k", "-n", "--dry-run"} | VERBOSE, set(), None),
    "tag": ({"-a", "--annotate", "-l", "--list", "-n"}, {"-m", "--message"}, check_tag),
    "worktree": ({"--detach", "--porcelain"} | QUIET, {"-b"}, check_worktree),
    "remote": (VERBOSE, set(), check_remote),
    "cherry-pick": ({"--continue", "-n", "--no-commit"}, set(), None),
    "revert": ({"--continue", "-n", "--no-commit", "--no-edit"}, set(), None),
}
# Subcommands that move HEAD or create a checkout, so later segments may run on another branch.
SWITCHERS = {"checkout", "switch", "worktree"}


def deletes_unprotected(sub, args):
    """True for `branch -d` and `worktree remove` forms that leave HEAD's branch alone."""
    if sub not in ("branch", "worktree"):
        return False
    flags, values, _ = SPECS[sub]
    opts, pos = parse(args, flags, values)
    if sub == "branch":
        delete = {"-d", "--delete"}
        return bool(pos) and bool(opts.keys() & delete) and opts.keys() <= delete | QUIET
    return bool(pos) and pos[0] == "remove" and not opts


def check_read_only(args):
    for arg in args:
        name = arg.partition("=")[0]
        if arg.startswith("-O") or (
            name.startswith("--") and len(name) > 2
            and any(unsafe.startswith(name) for unsafe in READ_ONLY_UNSAFE)
        ):
            raise Undecided


def decide(command, cwd):
    """Return "allow" or "ask", or raise Undecided."""
    if has_shell_meta(command):
        raise Undecided
    try:
        parts = list(segments(command))
    except ValueError:
        raise Undecided
    decision = "allow"
    saw_git = False
    upstream_changed = False
    removed = False
    for words, separator in parts:
        if removed and separator == ";":
            raise Undecided
        if words[0] == "cd" and len(words) == 2:
            cwd = os.path.normpath(os.path.join(cwd, words[1]))
            if not os.path.isdir(cwd):
                raise Undecided
            continue
        if words[0] != "git":
            raise Undecided
        saw_git = True
        target = cwd
        i = 1
        while i < len(words) and words[i].startswith("-"):
            if words[i] == "-C" and i + 1 < len(words):
                target = os.path.normpath(os.path.join(target, words[i + 1]))
                i += 2
            elif words[i] in ("--no-pager", "--no-optional-locks"):
                i += 1
            else:
                # -c, --git-dir, --work-tree, --exec-path etc. can redirect or run anything.
                raise Undecided
        if i >= len(words) or not os.path.isdir(target):
            raise Undecided
        sub, args = words[i], words[i + 1:]
        if sub not in READ_ONLY and sub not in SPECS:
            raise Undecided
        branch = current_branch(target)
        if branch is not None and is_protected_ref(branch) and sub != "push":
            if sub in ASK_ON_PROTECTED:
                if RANK["ask"] > RANK[decision]:
                    decision = "ask"
                continue
            if not deletes_unprotected(sub, args):
                # Keep the normal flow on the protected branch (block-main-commit.py blocks commits).
                raise Undecided
        if sub in READ_ONLY:
            check_read_only(args)
            continue
        flags, values, check = SPECS[sub]
        opts, pos = parse(args, flags, values)
        if sub == "push" and not pos[1:] and upstream_changed:
            # The push target was computed before this line changed the upstream.
            raise Undecided
        result = check(opts, pos, target) if check is not None else None
        if result is not None and RANK[result] > RANK[decision]:
            decision = result
        # After `worktree remove`, a later `cd` into the removed path fails; only `&&` stops there,
        # so every later separator must be `&&`.
        if sub == "worktree" and pos[:1] == ["remove"]:
            removed = True
        if sub in SWITCHERS and separator is not None and not (
            pos[:1] == ["list"] or (pos[:1] == ["remove"] and separator == "&&")
        ):
            raise Undecided
        if sub == "worktree" or UPSTREAM_OPTIONS & opts.keys():
            upstream_changed = True
    if not saw_git:
        raise Undecided
    return decision


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return 0
    tool_input = data.get("tool_input") if isinstance(data, dict) else None
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str) or not command.lstrip().startswith(("git", "cd")):
        return 0
    cwd = data.get("cwd")
    if not isinstance(cwd, str):
        cwd = os.getcwd()
    try:
        decision = decide(command, cwd)
    except Undecided:
        # Replaces the old `Bash(git push *)` ask rule for pushes this hook cannot parse.
        if not re.search(r"\bgit\b.*\bpush\b", command, re.S):
            return 0
        branch = current_branch(cwd) if os.path.isdir(cwd) else None
        if not (re.search(r"(?i)\b(main|master)\b", command) or (branch and is_protected_ref(branch))):
            return 0
        decision = "ask"
    reason = {
        "allow": "git operation off the protected branch",
        "ask": "git operation may target the protected branch (main/master)",
        "deny": "Blocked: pushing to main or master is not allowed. Push a work branch and open a PR.",
    }[decision]
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
