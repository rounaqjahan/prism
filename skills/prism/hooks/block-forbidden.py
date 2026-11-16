#!/usr/bin/env python3
import json
import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import fgstate

SEPARATORS = {";", "&&", "||", "|", "&", "\n"}


def segments(command):
    lexer = shlex.shlex(command.replace("\n", " ; "), posix=True, punctuation_chars=";&|")
    lexer.whitespace_split = True
    current = []
    try:
        for token in lexer:
            if token in SEPARATORS:
                if current:
                    yield current
                current = []
            else:
                current.append(token)
    except ValueError:
        yield command.split()
        return
    if current:
        yield current


def branch_of(folder):
    result = subprocess.run(["git", "-C", folder, "rev-parse", "--abbrev-ref", "HEAD"],
                            capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def git_parts(tokens, cwd):
    folder, i = cwd, 1
    while i < len(tokens) and tokens[i].startswith("-"):
        if tokens[i] == "-C" and i + 1 < len(tokens):
            folder = str(Path(cwd, tokens[i + 1]))
            i += 2
        elif tokens[i] == "-c":
            i += 2
        else:
            i += 1
    if i >= len(tokens):
        return folder, None, []
    return folder, tokens[i], tokens[i + 1:]


def ok_branch(name, allowed):
    return name == allowed or name.startswith(allowed + "-")


def git_problem(sub, rest, folder, allowed):
    flags = {t for t in rest if t.startswith("-")}
    words = [t for t in rest if not t.startswith("-")]
    on_branch = branch_of(folder)
    if sub == "push":
        if flags & {"--force", "-f", "--force-with-lease", "--force-if-includes", "--delete", "-d", "--mirror"} or any(w.startswith("+") for w in words):
            return "force-push or remote delete rewrites history; ask the user"
        refs = words[1:]
        if any(not (ok_branch(r.removeprefix("HEAD:"), allowed) or r == "HEAD") for r in refs):
            return f"push only {allowed}"
        if not refs and on_branch and not ok_branch(on_branch, allowed):
            return f"push only from {allowed} (now on {on_branch})"
    if sub == "commit" and on_branch and not ok_branch(on_branch, allowed):
        return f"commit only on {allowed} (now on {on_branch})"
    if sub == "reset" and "--hard" in flags:
        return "hard reset throws work away"
    if sub == "stash":
        return "stash hides other people's work; leave dirty files alone"
    if sub == "clean" and any(f.startswith("-") and "f" in f for f in flags):
        return "clean -f deletes untracked files"
    if sub == "branch" and flags & {"-D", "-d", "--delete"}:
        return "deleting branches is the user's call"
    if sub in ("checkout", "switch"):
        if "--" in rest:
            return "checkout -- <file> throws away changes"
        target = [w for w in words if w != "--"]
        if not target or not ok_branch(target[0], allowed):
            return f"switch only to {allowed} (create it with checkout -b / switch -c)"
    return None


def problem(tokens, cwd, allowed):
    if tokens[:3] == ["gh", "pr", "merge"]:
        return "the graph creates PRs and never merges; merging is the user's"
    if tokens[:1] == ["git"]:
        folder, sub, rest = git_parts(tokens, cwd)
        if sub:
            return git_problem(sub, rest, folder, allowed)
    return None


def main():
    data = json.load(sys.stdin)
    slug = fgstate.active_slug()
    if data.get("tool_name") != "Bash" or not slug:
        return 0
    command = data.get("tool_input", {}).get("command", "")
    cwd = data.get("cwd") or "."
    allowed = f"feature/{fgstate.branch_slug(slug)}"
    for tokens in segments(command):
        if tokens[:1] == ["cd"] and len(tokens) > 1:
            cwd = str(Path(cwd, Path(tokens[1]).expanduser()))
            continue
        reason = problem(tokens, cwd, allowed)
        if reason:
            print(f"Prism ({slug}) blocked `{' '.join(tokens)}`: {reason}.", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
