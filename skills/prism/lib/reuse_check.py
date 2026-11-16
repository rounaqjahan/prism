#!/usr/bin/env python3
import re
import subprocess
from pathlib import Path

WINDOW = 6
RULE = "user rule: reusability. Reuse the existing code instead of re-writing it (user, 2026-11-11)"
KEYWORDS = {
    "let", "var", "func", "fun", "val", "if", "else", "guard", "return", "try", "await", "self", "nil",
    "null", "true", "false", "in", "for", "while", "private", "public", "internal", "static", "final",
    "class", "struct", "enum", "case", "switch", "when", "import", "override", "async", "suspend",
    "weak", "Task", "isCancelled", "sleep", "cancel", "launch", "delay", "this", "new", "const",
}
TOKEN = re.compile(r"[A-Za-z_]\w*|\d[\d_]*|\S")


def normalise(line):
    text = line.strip()
    if not text or re.fullmatch(r"[{}()\[\],;]+", text) or text.startswith(("import ", "package ", "@")):
        return None
    out = []
    tokens = TOKEN.findall(text)
    for i, tok in enumerate(tokens):
        nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
        if tok in KEYWORDS or tok[0].isupper() or nxt == ":" or not (tok[0].isalnum() or tok[0] == "_"):
            out.append(tok)
        elif tok[0].isdigit():
            out.append("N")
        else:
            out.append("x")
    return " ".join(out)


def windows(lines):
    norm = [(n, normalise(t)) for n, t in lines]
    norm = [(n, t) for n, t in norm if t]
    for i in range(len(norm) - WINDOW + 1):
        chunk = norm[i:i + WINDOW]
        if len({t for _, t in chunk}) < 4:
            continue
        yield chunk[0][0], chunk[-1][0], "\n".join(t for _, t in chunk)


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True).stdout


def existing_index(repo_root, source_dirs, suffix):
    index = {}
    for rel in git(repo_root, "ls-files", "--", *source_dirs).splitlines():
        if not rel.endswith(suffix):
            continue
        text = git(repo_root, "show", f"HEAD:{rel}")
        lines = list(enumerate(text.splitlines(), 1))
        for start, end, key in windows(lines):
            index.setdefault(key, f"{Path(repo_root, rel)}:{start}-{end}")
    return index


def still_there(src_file, kept):
    if src_file not in kept:
        source = Path(src_file)
        text = source.read_text(errors="ignore").splitlines() if source.exists() else []
        kept[src_file] = {k for _, _, k in windows(list(enumerate(text, 1)))}
    return kept[src_file]


def implements(lines, start):
    first = lines[start - 1] if 0 < start <= len(lines) else ""
    above = next((l.strip() for l in reversed(lines[:start - 1]) if l.strip()), "")
    return above in ("@override", "@Override") or re.search(r"\boverride\s+(func|fun)\b", first) is not None


def check(repo_root, source_dirs, files_with_added):
    problems, kept = [], {}
    by_suffix = {}
    for path, added in files_with_added:
        by_suffix.setdefault(Path(path).suffix, []).append((path, added))
    for suffix, items in by_suffix.items():
        index = existing_index(repo_root, source_dirs, suffix)
        for path, added in items:
            blocks = []
            current = Path(path).read_text(errors="ignore").splitlines()
            now_keys = [k for _, _, k in windows(list(enumerate(current, 1)))]
            for start, end, key in windows(added):
                source = index.get(key)
                if not source:
                    continue
                if source.rsplit(":", 1)[0] == str(path) and now_keys.count(key) < 2:
                    continue
                if key not in still_there(source.rsplit(":", 1)[0], kept):
                    continue
                src_file, src_range = source.rsplit(":", 1)
                src_start, src_end = (int(n) for n in src_range.split("-"))
                last = blocks[-1] if blocks else None
                if last and last[2] == src_file and start <= last[1] + 1:
                    last[1], last[4] = max(last[1], end), max(last[4], src_end)
                else:
                    blocks.append([start, end, src_file, src_start, src_end])
            problems += [f"{path}:{s}-{e}: repeats existing code at {f}:{ss}-{se}; reuse it [{RULE}]"
                         for s, e, f, ss, se in blocks if not implements(current, s)]
    return problems
