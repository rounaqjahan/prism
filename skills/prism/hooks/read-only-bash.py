#!/usr/bin/env python3
import json
import shlex
import sys

GIT_READ = {"diff", "log", "show", "status", "grep", "ls-files", "blame", "rev-parse"}
READ_COMMANDS = {"cat", "head", "tail", "wc", "ls", "grep", "find", "sed", "awk", "sort", "uniq", "diff", "file", "stat", "pwd", "echo"}


def is_python(name):
    base = name.replace("\\", "/").rsplit("/", 1)[-1].lower()
    return base in ("python3", "python", "py", "python3.exe", "python.exe", "py.exe") or base.startswith("python3.")


def problem(tokens):
    if not tokens:
        return None
    name = tokens[0]
    if name == "git":
        rest = [t for t in tokens[1:] if not t.startswith("-")]
        if "-C" in tokens:
            rest = rest[1:]
        return None if rest and rest[0] in GIT_READ else f"git {rest[0] if rest else ''} is not read-only"
    script = [t for t in tokens[1:] if t not in ("-X", "utf8")]
    if is_python(name) and script and script[0].replace("\\", "/").endswith("prism/lib/check_handoff.py"):
        return None
    if name == "sed" and any(t.startswith("-i") for t in tokens):
        return "sed -i edits files"
    if name == "find" and any(t in ("-delete", "-exec", "-execdir") for t in tokens):
        return "find may only list"
    return None if name in READ_COMMANDS else f"'{name}' is not on the verifier's read-only list"


def main():
    data = json.load(sys.stdin)
    if data.get("tool_name") != "Bash":
        return 0
    command = data.get("tool_input", {}).get("command", "")
    if ">" in command.replace("2>&1", "").replace(">/dev/null", "").replace(">NUL", ""):
        print("Prism: the verifier is read-only; no output redirection to files.", file=sys.stderr)
        return 2
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|")
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        print("Prism: the verifier's command could not be parsed; keep it simple.", file=sys.stderr)
        return 2
    segment = []
    for token in tokens + [";"]:
        if token in (";", "&&", "||", "|", "&"):
            reason = problem(segment)
            if reason:
                print(f"Prism: the verifier is read-only: {reason}.", file=sys.stderr)
                return 2
            segment = []
        else:
            segment.append(token)
    return 0


if __name__ == "__main__":
    sys.exit(main())
