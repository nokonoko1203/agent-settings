#!/usr/bin/env python3
"""PreToolUse hook: block git commit while the target repository is on main or master.

Matcher: Bash
Commits on other branches (and detached HEAD) pass without a prompt.
The target repository follows `cd`/`pushd`, subshells, `git -C`, `--git-dir`/`--work-tree`,
GIT_DIR/GIT_WORK_TREE, and `bash -c` within the command. A `git switch`/`git checkout` earlier
in the same command updates the branch used for later commits.
This matches command text only and is not a security boundary.
"""

import json
import os
import re
import shlex
import subprocess
import sys

HOOK_DIR = os.path.dirname(os.path.abspath(__file__))
PROTECTED = {"main", "master"}

ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
WRAPPERS = {"env", "time", "command", "nice", "nohup", "exec", "xargs"}
# Shell keywords that may precede a command (if ...; then git commit; fi).
KEYWORDS = {"if", "then", "else", "elif", "while", "until", "do", "{", "!"}
SHELLS = {"bash", "sh", "zsh"}
OPERATOR_CHARS = "();<>|&\n"
HEREDOC = re.compile(r"(?<!<)<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
# git global options that take a separate value.
GIT_VALUE_OPTIONS = {"--namespace", "--config-env", "--super-prefix", "--exec-path"}


def log(kind, detail, cwd):
    script = f'source "{HOOK_DIR}/lib-log.sh"; harness_log "$0" "$1" "$2"'
    subprocess.run(["bash", "-c", script, kind, detail, cwd], check=False)


def git(args, cwd, env=None):
    try:
        result = subprocess.run(
            ["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=False, timeout=5
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def strip_heredocs(command):
    """Drop heredoc bodies so their text is not parsed as commands.

    A marker without a terminating line (for example `<<EOF` inside quotes) is ignored.
    """
    lines = command.split("\n")
    out = []
    i = 0
    while i < len(lines):
        out.append(lines[i])
        i += 1
        for marker in HEREDOC.finditer(out[-1]):
            end = next((j for j in range(i, len(lines)) if lines[j].strip() == marker.group(2)), None)
            if end is not None:
                i = end + 1
    return "\n".join(out)


def tokenize(command):
    # A comment consumes its trailing newline, so double newlines to keep the command separator.
    lexer = shlex.shlex(command.replace("\n", "\n\n"), posix=True, punctuation_chars=OPERATOR_CHARS)
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    lexer.commenters = "#"
    return list(lexer)


class Checker:
    def __init__(self, cwd):
        self.cwd = cwd
        self.variables = dict(os.environ)
        # Branch set by an earlier switch/checkout in this command, keyed by absolute git dir.
        self.branches = {}
        self.dirstack = []

    def expand(self, word):
        word = os.path.expanduser(word)
        return re.sub(
            r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?",
            lambda m: self.variables.get(m.group(1), m.group(0)),
            word,
        )

    def resolve(self, base, path):
        return os.path.normpath(os.path.join(base, self.expand(path)))

    def run(self, command, cwd):
        """Return True when the command commits to the protected branch."""
        command = command.replace("\\\n", " ")
        try:
            tokens = tokenize(strip_heredocs(command))
        except ValueError:
            # Unparseable quoting: block when the working directory or any cd/-C target is on main.
            if not re.search(r"\bgit\b.*\bcommit\b", command):
                return False
            paths = re.findall(r"(?:\bcd|\bpushd|-C)\s+(['\"]?)([^'\"\s;&|)]+)\1", command)
            dirs = [cwd] + [self.resolve(cwd, path) for _, path in paths]
            return any(os.path.isdir(d) and self.branch_at(d, None) in PROTECTED for d in dirs)

        stack = [cwd]
        words = []
        skip_next = False
        for token in tokens:
            if skip_next:
                skip_next = False
                continue
            if token and all(c in OPERATOR_CHARS for c in token):
                # Split a glued token such as `)>` into its separator and redirection parts.
                cut = next((k for k, c in enumerate(token) if c in "<>"), len(token))
                if token.startswith("&>"):
                    cut = 0
                separator, redirect = token[:cut], token[cut:]
                if separator:
                    if words:
                        if self.simple_command(words, stack):
                            return True
                        words = []
                    for c in separator:
                        if c == "(":
                            stack.append(stack[-1])
                        elif c == ")" and len(stack) > 1:
                            stack.pop()
                # A redirection's target is the next word, unless the operator consumes it (>&1).
                skip_next = bool(redirect) and (not redirect.endswith("&") or redirect in ("&>", "&>>"))
                continue
            words.append(token)
        return bool(words) and self.simple_command(words, stack)

    def simple_command(self, words, stack):
        env = {}
        i = 0
        while i < len(words) and ASSIGNMENT.match(words[i]):
            name, value = words[i].split("=", 1)
            env[name] = self.expand(value)
            i += 1
        if i == len(words):
            self.variables.update(env)
            return False
        if words[i] == "export":
            for word in words[i + 1 :]:
                if ASSIGNMENT.match(word):
                    name, value = word.split("=", 1)
                    self.variables[name] = self.expand(value)
            return False

        # Skip keywords, wrappers and wrapper options (env -i, nice -n 5, time -p).
        while i < len(words) and (words[i] in WRAPPERS or words[i] in KEYWORDS):
            wrapper = words[i]
            i += 1
            while i < len(words) and (words[i].startswith("-") or (wrapper == "env" and ASSIGNMENT.match(words[i]))):
                if wrapper == "env" and ASSIGNMENT.match(words[i]):
                    name, value = words[i].split("=", 1)
                    env[name] = self.expand(value)
                elif wrapper == "nice" and words[i] == "-n":
                    i += 1
                i += 1
        words = words[i:]
        if not words:
            return False

        program = os.path.basename(words[0])
        if program in ("cd", "pushd"):
            args = [w for w in words[1:] if not w.startswith("-")]
            if program == "pushd":
                self.dirstack.append(stack[-1])
            stack[-1] = self.resolve(stack[-1], args[0]) if args else os.path.expanduser("~")
            return False
        if program == "popd":
            if self.dirstack:
                stack[-1] = self.dirstack.pop()
            return False
        if program in SHELLS:
            for index, word in enumerate(words[1:], start=1):
                if re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", word) and index + 1 < len(words):
                    return self.run(words[index + 1], stack[-1])
            return False
        if program == "git":
            return self.git_command(words[1:], stack[-1], env)
        return False

    def git_command(self, args, cwd, env):
        target = cwd
        git_env = dict(os.environ)
        for name in ("GIT_DIR", "GIT_WORK_TREE"):
            value = env.get(name) or self.variables.get(name)
            if value:
                git_env[name] = self.resolve(cwd, value)
        options = []
        i = 0
        while i < len(args):
            arg = args[i]
            if arg == "-C" and i + 1 < len(args):
                target = self.resolve(target, args[i + 1])
                i += 2
                continue
            if arg in ("--git-dir", "--work-tree") and i + 1 < len(args):
                options.append(f"{arg}={self.resolve(target, args[i + 1])}")
                i += 2
                continue
            if arg.startswith(("--git-dir=", "--work-tree=")):
                name, value = arg.split("=", 1)
                options.append(f"{name}={self.resolve(target, value)}")
            elif arg == "-c" and i + 1 < len(args):
                # Keep -c so aliases defined on the command line resolve.
                options.extend(["-c", args[i + 1]])
                i += 1
            elif arg in GIT_VALUE_OPTIONS:
                i += 1
            elif not arg.startswith("-"):
                break
            i += 1
        if i >= len(args):
            return False

        sub, rest = args[i], args[i + 1 :]
        if not os.path.isdir(target):
            return False
        context = (target, options, git_env)

        alias = git([*options, "config", "--get", f"alias.{sub}"], target, git_env)
        if alias and not alias.startswith("!"):
            try:
                alias_words = shlex.split(alias)
            except ValueError:
                alias_words = alias.split()
            if alias_words:
                sub, rest = alias_words[0], alias_words[1:] + rest

        if sub in ("switch", "checkout"):
            self.record_branch(sub, rest, context)
            return False
        if sub == "commit":
            return self.branch_at(target, context) in PROTECTED
        return False

    def git_dir(self, context):
        target, options, git_env = context
        return git([*options, "rev-parse", "--absolute-git-dir"], target, git_env)

    def branch_at(self, cwd, context):
        if not context:
            context = (cwd, [], dict(os.environ))
        key = self.git_dir(context)
        if key in self.branches:
            return self.branches[key]
        target, options, git_env = context
        return git([*options, "symbolic-ref", "--short", "-q", "HEAD"], target, git_env)

    def record_branch(self, sub, rest, context):
        key = self.git_dir(context)
        if key is None:
            return
        create = ("-c", "-C", "--create", "--force-create") if sub == "switch" else ("-b", "-B", "--orphan")
        positional = []
        i = 0
        while i < len(rest):
            arg = rest[i]
            if arg in create and i + 1 < len(rest):
                self.branches[key] = rest[i + 1]
                return
            if arg in ("--detach", "-d") or arg == "--":
                if arg != "--":
                    self.branches[key] = None
                return
            if not arg.startswith("-"):
                positional.append(arg)
            i += 1
        if len(positional) != 1:
            return
        name = positional[0]
        target, options, git_env = context
        if git([*options, "rev-parse", "--verify", "--quiet", f"refs/heads/{name}"], target, git_env) is not None:
            self.branches[key] = name
        elif git([*options, "rev-parse", "--verify", "--quiet", f"{name}^{{commit}}"], target, git_env) is not None:
            # A commit that is not a local branch: detached HEAD.
            self.branches[key] = None
        elif sub == "switch" or name == "-":
            # Unknown destination (remote-tracking guess or previous branch): stop trusting HEAD.
            self.branches[key] = None


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(data, dict):
        return 0
    command = (data.get("tool_input") or {}).get("command") or ""
    cwd = data.get("cwd") or os.getcwd()
    if not command:
        return 0
    if Checker(cwd).run(command, cwd):
        log("block-main-commit", "commit-on-main", cwd)
        print(
            "Blocked (commit-on-main): committing directly to main or master is not allowed. "
            "Create a branch first, only if the user asked for or approved one.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
