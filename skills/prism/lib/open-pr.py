#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import tempfile

import fgstate
import project

NAMES = project.names()
TRAILER = ""
FOOTER = ""


def sh(*cmd, cwd=None):
    proc = subprocess.run(list(cmd), cwd=cwd, capture_output=True, text=True)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def load(path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def base_of(repo):
    if repo["base"]:
        return repo["base"]
    _, out, _ = sh("gh", "repo", "view", repo["remote"], "--json", "defaultBranchRef", "-q", ".defaultBranchRef.name")
    return out or "main"


def who_runs(choice, platform):
    return choice.get("who", "user") if platform in choice.get("platforms", []) else "user"


def issue_line(issues, platform):
    issue = issues.get("issues", {}).get(platform)
    if isinstance(issue, dict):
        issue = issue.get("number") or issue.get("url")
    return f"Closes #{issue}" if isinstance(issue, int) or str(issue or "").isdigit() else (
        f"Closes {issue}" if issue else "")


def platform_section(rdir, brief, choice, platform):
    lines = [f"### {NAMES.get(platform, platform)}"]
    run = load(rdir / f"run-{platform}.json", {}) or {}
    results = {s.get("n"): s for s in run.get("scenarios", [])}
    if who_runs(choice, platform) == "claude" and results:
        lines += ["Claude ran the app and walked every scenario.", "",
                  "| # | Do | Expect | Result |", "|---|---|---|---|"]
        for i, s in enumerate(brief.get("scenarios", []), 1):
            res = results.get(i, {}).get("result", "not run")
            lines.append(f"| {i} | {s.get('do')} | {s.get('expect')} | {res} |")
        folder = choice.get("evidence_folder")
        if folder:
            lines += ["", f"Evidence: one screenshot per scenario in `{folder}` (not committed)."]
    else:
        plan = load(rdir / f"map-{platform}.json", {}) or {}
        rows = [s for s in brief.get("scenarios", []) if platform not in s.get("na", [])] + plan.get("regressions", [])
        passed = {s.get("id") for s in run.get("scenarios", []) if s.get("result") == "pass"}
        lines += ["Run by the user on the simulator: ticked rows passed, unticked rows are not reported yet." if passed
                  else "Not run by Claude. Walk these on the simulator before merging:", ""]
        lines += [checklist_line(s).replace("- [ ]", "- [x]", 1) if s.get("id") in passed else checklist_line(s) for s in rows]
    gate = load(rdir / f"gate-{platform}.json", {}) or {}
    verdict = load(rdir / f"verdict-{platform}.json", {}) or {}
    lines += ["", f"Local gate: {gate.get('result', 'n/a')} · Independent verify: {verdict.get('result', 'n/a')}"]
    return "\n".join(lines)


def checklist_line(row):
    join = lambda v: " → ".join(v) if isinstance(v, list) else str(v or "")
    head = f"**{row.get('id', '')} {row.get('name', '')}**".strip() if row.get("id") else ""
    write = f" ⚠ Needs server write: {row['server_write']}." if row.get("server_write") else ""
    return f"- [ ] {head + ': ' if head else ''}{join(row.get('do'))} — expect: {join(row.get('expect'))}.{write}"


def step_sections(rdir, run, brief, choice, platform):
    if not run.get("parent"):
        return platform_section(rdir, brief, choice, platform)
    out = []
    for step in sorted(fgstate.runs_dir().glob(f"{run['parent']}-*")):
        state = load(step / "run.json", {}) or {}
        if state.get("nodes", {}).get(f"build:{platform}", {}).get("status") != "pass":
            continue
        section = platform_section(step, load(step / "brief.json", {}), load(step / "run-choice.json", {}) or {}, platform)
        out.append(section.replace("### ", f"### Step {state.get('step')} · ", 1))
    return "\n\n".join(out)


def body_for(rdir, run, remote, repos, only=None):
    brief = load(rdir / "brief.json", {})
    choice = load(rdir / "run-choice.json", {}) or {}
    issues = load(rdir / "issues.json", {}) or {}
    lanes = [p for p in run["platforms"] if any(r["remote"] == remote for r in repos.get(p, []))
             and run["nodes"].get(f"build:{p}", {}).get("status") == "pass" and (only is None or p == only)]
    url = (rdir / "matrix-url.txt").read_text().strip() if (rdir / "matrix-url.txt").exists() else ""
    closes = [c for c in (issue_line(issues, p) for p in lanes) if c]
    title = fgstate.branch_slug(run["slug"]).replace("-", " ").title()
    if run.get("step") and not run.get("parent"):
        title += f" · step {run['step']}"
    parts = ["\n".join(closes)] if closes else []
    parts += [f"## {title}", brief.get("change", ""),
              f"**Test matrix:** {url or 'not published yet'}",
              "\n\n".join(step_sections(rdir, run, brief, choice, p) for p in lanes), FOOTER]
    parts = [part for part in parts if part]
    names = " + ".join(NAMES.get(p, p) for p in lanes)
    return f"{title} ({names})", "\n\n".join(parts)


def commit_and_push(root, paths, branch, message, push=True):
    for path in paths:
        if os.path.exists(path) or sh("git", "ls-files", "--error-unmatch", path, cwd=root)[0] == 0:
            sh("git", "add", "-A", "--", path, cwd=root)
    if sh("git", "diff", "--cached", "--quiet", cwd=root)[0]:
        code, _, err = sh("git", "commit", "-m", f"{message}\n\n{TRAILER}".strip(), cwd=root)
        if code:
            return f"commit failed: {err[:400]}"
    if not push:
        return None
    code, _, err = sh("git", "push", "-u", "origin", branch, cwd=root)
    return f"push failed: {err[:400]}" if code else None


def split_branch(root, repo, paths, work, target):
    base = f"origin/{base_of(repo)}"
    sh("git", "fetch", "-q", "origin", base_of(repo), cwd=root)
    rel = [project.norm(p)[len(project.norm(root).rstrip("/")) + 1:] for p in paths]
    _, out, _ = sh("git", "log", "--reverse", "--format=%H", f"{base}..{work}", "--", *rel, cwd=root)
    exists = sh("git", "rev-parse", "--verify", "--quiet", f"refs/heads/{target}", cwd=root)[0] == 0
    code, _, err = sh("git", "switch", "-q", target, cwd=root) if exists else sh("git", "switch", "-q", "-c", target, base, cwd=root)
    if code:
        return f"git switch {target} failed: {err[:300]}"
    _, cherry, _ = sh("git", "cherry", target, work, cwd=root)
    pending = {line[2:] for line in cherry.splitlines() if line.startswith("+")}
    for commit in [c for c in out.splitlines() if c in pending]:
        code, _, err = sh("git", "cherry-pick", commit, cwd=root)
        if code:
            sh("git", "cherry-pick", "--abort", cwd=root)
            sh("git", "switch", "-q", work, cwd=root)
            return f"cherry-pick {commit[:8]} onto {target} failed: {err[:300]}"
    code, _, err = sh("git", "push", "-q", "-u", "origin", target, cwd=root)
    sh("git", "switch", "-q", work, cwd=root)
    return f"push failed: {err[:400]}" if code else None


def open_or_update(remote, base, branch, title, body):
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write(body)
    _, out, _ = sh("gh", "pr", "list", "--repo", remote, "--head", branch, "--state", "open",
                   "--json", "number,url")
    found = json.loads(out or "[]")
    if found:
        code, _, err = sh("gh", "pr", "edit", str(found[0]["number"]), "--repo", remote,
                          "--title", title, "--body-file", f.name)
        return (found[0], None) if not code else (None, f"gh pr edit failed: {err[:400]}")
    code, out, err = sh("gh", "pr", "create", "--repo", remote, "--base", base, "--head", branch,
                        "--title", title, "--body-file", f.name)
    if code:
        return None, f"gh pr create failed: {err[:400]}"
    number = int(out.rstrip("/").rsplit("/", 1)[-1])
    return {"number": number, "url": out}, None


def main():
    platform = sys.argv[1]
    slug = fgstate.active_slug()
    rdir = fgstate.run_dir(slug)
    from nodestate import mark_started
    mark_started(f"pr:{platform}", slug)
    run = fgstate.read_run(slug)
    repos = project.repos()
    branch = f"feature/{fgstate.branch_slug(slug)}"
    plan = load(rdir / f"map-{platform}.json", {}) or {}
    build = load(rdir / f"build-{platform}.json", {}) or {}
    mapped = sorted({f["path"] for f in plan.get("files", []) if f.get("path")} | set(build.get("files_changed", [])))
    roots = {}
    for repo in repos[platform]:
        if any(project.under(p, repo["path"]) for p in mapped):
            entry = roots.setdefault(repo["git_root"], {"repo": repo, "paths": []})
            entry["paths"] += [p for p in mapped if project.under(p, repo["path"])]
    if not roots:
        out = rdir / f"pr-{platform}.json"
        out.write_text(json.dumps({"platform": platform, "blocked": "map changes no repo; nothing to PR"}, indent=2))
        print(json.dumps({"result": "blocked"}))
        sys.exit(2)
    prs, problem = [], None
    for root, entry in roots.items():
        repo = entry["repo"]
        current = sh("git", "branch", "--show-current", cwd=root)[1]
        if current != branch:
            problem = f"{root} is on '{current}', not {branch}"
            break
        shared = sum(1 for p in run["platforms"] if any(r["git_root"] == root for r in repos.get(p, []))) > 1
        pr_branch = f"{branch}-{platform}" if shared else branch
        problem = commit_and_push(root, entry["paths"], branch,
                                  f"feat({platform}): {slug.replace('-', ' ')}", push=not shared)
        if not problem and shared:
            problem = split_branch(root, repo, entry["paths"], branch, pr_branch)
        if problem:
            break
        title, body = body_for(rdir, run, repo["remote"], repos, only=platform if shared else None)
        pr, problem = open_or_update(repo["remote"], base_of(repo), pr_branch, title, body)
        if problem:
            break
        prs.append({"repo": repo["remote"], "number": pr["number"], "url": pr["url"], "branch": pr_branch})
    out = rdir / f"pr-{platform}.json"
    if problem:
        out.write_text(json.dumps({"platform": platform, "blocked": problem}, indent=2))
        print(json.dumps({"result": "blocked", "reason": problem}))
        sys.exit(2)
    first = prs[0]
    out.write_text(json.dumps({"platform": platform, "repo": first["repo"], "number": first["number"],
                               "url": first["url"], "branch": prs[0].get("branch", branch), "prs": prs}, indent=2))
    print(json.dumps({"result": "pass", "prs": prs}))


if __name__ == "__main__":
    main()
