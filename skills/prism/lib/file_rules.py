#!/usr/bin/env python3
import json
import re
import subprocess

import project
from pathlib import Path



def _source(doc, phrase):
    """Where a rule comes from. A rule tied to a doc is only active while the doc still says it."""
    if not doc:
        return "rule in .prism/prism.json"
    return cite(project.doc_path(doc), phrase)


def size_rule(platform):
    rule = project.max_lines(platform)
    if rule is None:
        return None
    rule = {"limit": rule} if isinstance(rule, int) else rule
    return rule.get("limit", 300), rule.get("doc"), rule.get("phrase")


def patterns(platform):
    return [(r.get("doc"), r.get("phrase") or r["rule"], r["pattern"], r.get("scope"), r["rule"])
            for r in project.file_rules(platform)]


def cite(doc, phrase):
    try:
        for number, line in enumerate(Path(doc).read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if phrase.lower() in line.lower():
                return f"{doc}:{number}"
    except OSError:
        return None
    return None


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True).stdout


def git_root(path):
    folder = path if path.is_dir() else path.parent
    while not folder.exists():
        folder = folder.parent
    out = git(folder, "rev-parse", "--show-toplevel").strip()
    return Path(out) if out else None


def diff_of(path):
    root = git_root(path)
    if not root:
        return [], 0, 0, 0
    rel = str(path.relative_to(root))
    if not git(root, "ls-files", "--", rel).strip():
        lines = path.read_text(errors="ignore").splitlines() if path.exists() else []
        return list(enumerate(lines, 1)), 0, 0, 0
    before = git(root, "show", f"HEAD:{rel}").count("\n")
    added, removed, removed_blank, line = [], 0, 0, 0
    for row in git(root, "diff", "-U0", "HEAD", "--", rel).splitlines():
        hunk = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)", row)
        if hunk:
            line = int(hunk.group(1))
        elif row.startswith("+") and not row.startswith("+++"):
            added.append((line, row[1:]))
            line += 1
        elif row.startswith("-") and not row.startswith("---"):
            removed += 1
            removed_blank += not row[1:].strip()
    return added, removed, removed_blank, before


def check_size(platform, path, before, now, removed_blank, real_growth=0):
    rule = size_rule(platform)
    source = _source(rule[1], rule[2] or f"{rule[0]} lines") if rule else None
    if not source:
        return []
    limit = rule[0]
    if before == 0 and now > limit:
        return [f"{path}: new file has {now} lines [{source}]"]
    if before > limit and now > before:
        return [f"{path}: over {limit} lines and grew from {before} to {now} [{source}]"]
    if before <= limit < now:
        return [f"{path}: grew from {before} to {now} lines [{source}]"]
    if before >= limit and real_growth > 0:
        return [f"{path}: at/over the limit and grew by {real_growth} real line(s); removed blank lines hid it [{source}]"]
    return []


def check_file(platform, path):
    path = Path(path)
    if path.suffix not in project.source_exts() or not path.exists():
        return [], []
    added, removed, removed_blank, before = diff_of(path)
    now = path.read_text(errors="ignore").count("\n")
    real_growth = sum(1 for _, t in added if t.strip()) - (removed - removed_blank)
    problems = check_size(platform, path, before, now, removed_blank, real_growth)
    for doc, phrase, pattern, scope, name in patterns(platform):
        source = _source(doc, phrase)
        if source and not doc:
            source = f"{source}: {name}"
        if not source or (scope and scope not in project.norm(path)):
            continue
        for number, text in added:
            if re.search(pattern, text):
                problems.append(f"{path}:{number}: {text.strip()[:80]} [{source}]")
    notes = [f"{path}: {removed} existing line(s) removed or rewritten; verifier judges against the rule documents"] if removed else []
    return problems, notes


def standing_rules():
    return project.standing_rules()


def applies(rule, platform, path):
    return platform in rule.get("platforms", [platform]) and (
        not rule.get("ext") or Path(path).suffix in rule["ext"])


def user_rule_problems(platform, path, added, brief):
    out = []
    rules = [(r, "standing rule") for r in standing_rules()] + [
        (r, "user rule in brief.json") for r in brief.get("user_rules", [])]
    for rule, origin in rules:
        if not applies(rule, platform, path):
            continue
        if rule.get("name_pattern") and added and added[0][0] == 1 and len(added) == len(
                Path(path).read_text(errors="ignore").splitlines()):
            if not re.search(rule["name_pattern"], Path(path).name):
                out.append(f"{path}: file name breaks naming [{origin}: {rule['rule']}]")
        if not rule.get("pattern"):
            continue
        for number, text in added:
            if re.search(rule["pattern"], text):
                out.append(f"{path}:{number}: {text.strip()[:80]} [{origin}: {rule['rule']}]")
    return out


def check_files(platform, paths, brief=None):
    problems, notes = [], []
    for path in paths:
        p, n = check_file(platform, path)
        problems += p
        notes += n
        if Path(path).suffix in project.source_exts() and Path(path).exists():
            problems += user_rule_problems(platform, path, diff_of(Path(path))[0], brief or {})
    return problems, notes


def active_rules(platform):
    out = []
    rule = size_rule(platform)
    if rule:
        out.append(("size", _source(rule[1], rule[2] or f"{rule[0]} lines") or f"NOT FOUND in {rule[1]}: '{rule[2]}'"))
    for doc, phrase, pattern, _, name in patterns(platform):
        out.append((pattern, _source(doc, phrase) or f"NOT FOUND in {doc}: '{phrase}'"))
    return out
