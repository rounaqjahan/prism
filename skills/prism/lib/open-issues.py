#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import fgstate
import project

NAMES = project.names()
FOOTER = "🤖 Generated with [Claude Code](https://claude.com/claude-code)"


def sh(*cmd):
    proc = subprocess.run(list(cmd), capture_output=True, text=True)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def load(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def joined(value):
    return " → ".join(value) if isinstance(value, list) else str(value or "")


def row_line(row):
    head = f"**{row.get('id', '')} {row.get('name', '')}**: " if row.get("id") else ""
    write = f" ⚠ Needs server write: {row['server_write']}." if row.get("server_write") else ""
    return f"- [ ] {head}{joined(row.get('do'))} — expect: {joined(row.get('expect'))}.{write}"


def issue_repo(platform, plan, repos):
    paths = [f.get("path", "") for f in plan.get("files", []) if isinstance(f, dict)]
    scored = [(sum(project.under(p, r["path"]) for p in paths), r) for r in repos.get(platform, [])]
    scored = [s for s in scored if s[0]]
    return max(scored, key=lambda s: s[0])[1] if scored else None


def body(title, platform, brief, plan, repo, parent_spec, step, matrix):
    rows = [s for s in brief.get("scenarios", []) if platform not in s.get("na", [])] + plan.get("regressions", [])
    files = sorted({os.path.relpath(f["path"], repo["git_root"]) for f in plan.get("files", [])
                    if isinstance(f, dict) and project.under(f.get("path", ""), repo["git_root"])})
    parts = [f"## {title} ({NAMES.get(platform, platform)})", brief.get("change", ""),
             f"**Reference platform:** {NAMES.get(brief.get('reference_platform'), brief.get('reference_platform') or 'none')}",
             f"**Test matrix:** {matrix or 'not published yet'}"]
    phases = (parent_spec or {}).get("phases", [])
    if len(phases) > 1:
        parts.append("### Steps\n" + "\n".join(
            f"- {'**' if p.get('id') == step else ''}{p.get('id')} {p.get('name')}: {p.get('goal')}"
            f"{' (this step)**' if p.get('id') == step else ''}" for p in phases))
    if files:
        parts.append("### Where (from the map)\n" + "\n".join(f"- `{f}`" for f in files))
    if rows:
        parts.append("### Test rows\n" + "\n".join(row_line(r) for r in rows))
    parts.append(FOOTER)
    return "\n\n".join(parts)


def find_open(remote, title):
    _, out, _ = sh("gh", "issue", "list", "--repo", remote, "--state", "open", "--search", f"{title} in:title",
                   "--json", "number,title,url")
    return next((i for i in json.loads(out or "[]") if i.get("title") == title), None)


def upsert(remote, title, text, known):
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write(text)
    found = known if known and known.get("repo") == remote else find_open(remote, title)
    if found:
        code, _, err = sh("gh", "issue", "edit", str(found["number"]), "--repo", remote, "--body-file", f.name)
        return ({"number": found["number"], "url": found["url"]}, None) if not code else (None, f"gh issue edit: {err[:300]}")
    code, out, err = sh("gh", "issue", "create", "--repo", remote, "--title", title, "--body-file", f.name)
    if code:
        return None, f"gh issue create: {err[:300]}"
    return {"number": int(out.rstrip("/").rsplit("/", 1)[-1]), "url": out}, None


def main():
    slug = fgstate.active_slug()
    rdir = Path(os.environ.get("FG_RUN_DIR") or fgstate.run_dir(slug))
    from nodestate import mark_started
    mark_started("issues", slug)
    run = fgstate.read_run(slug)
    feature = fgstate.branch_slug(slug)
    shared = fgstate.run_dir(feature)
    brief = load(rdir / "brief.json", {})
    repos = project.repos()
    url_file = shared / "matrix-url.txt" if (shared / "matrix-url.txt").exists() else rdir / "matrix-url.txt"
    matrix = url_file.read_text().strip() if url_file.exists() else ""
    known = (load(shared / "issues.json", {}) or {}).get("issues", {})
    title = feature.replace("-", " ").title()
    issues, problems = {}, []
    for platform in run["platforms"]:
        plan = load(rdir / f"map-{platform}.json", {}) or {}
        if plan.get("change") != "change":
            continue
        repo = issue_repo(platform, plan, repos)
        if not repo:
            continue
        name = f"{title} ({NAMES.get(platform, platform)})"
        text = body(title, platform, brief, plan, repo, load(shared / "spec.json", {}), run.get("step"), matrix)
        issue, problem = upsert(repo["remote"], name, text, known.get(platform))
        if problem:
            problems.append(f"{platform}: {problem}")
            continue
        issues[platform] = dict(issue, repo=repo["remote"])
    out = {"issues": issues}
    if problems:
        out["blocked"] = "; ".join(problems)
    (rdir / "issues.json").write_text(json.dumps(out, indent=2))
    if shared != rdir and issues:
        merged = dict(known, **issues)
        (shared / "issues.json").write_text(json.dumps({"issues": merged}, indent=2))
    print(json.dumps({"result": "blocked" if problems else "pass", "issues": issues}))
    sys.exit(2 if problems else 0)


if __name__ == "__main__":
    main()
