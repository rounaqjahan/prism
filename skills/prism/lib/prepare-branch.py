#!/usr/bin/env python3
import json
import subprocess
import sys

import fgstate
import project


def git(root, *args):
    proc = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def prepare(root, base, branch):
    _, current, _ = git(root, "branch", "--show-current")
    if current == branch:
        return {"repo": root, "branch": branch, "action": "already on it"}
    if base and current != base:
        return {"repo": root, "blocked": f"on '{current}', not the base '{base}'; switch it yourself, then reopen"}
    exists = git(root, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}")[0] == 0
    code, _, err = git(root, "switch", branch) if exists else git(root, "switch", "-c", branch)
    if code:
        return {"repo": root, "blocked": f"git switch failed: {err[:200]}"}
    return {"repo": root, "branch": branch, "from": current, "action": "switched" if exists else "created"}


def mapped_paths(slug, platform):
    path = fgstate.run_dir(slug) / f"map-{platform}.json"
    if not path.exists():
        raise SystemExit(f"no {path.name}: branch only after the map passes")
    plan = json.loads(path.read_text())
    if plan.get("change") == "no_change":
        return []
    return [f["path"] for f in plan.get("files", []) if f.get("path")]


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: prepare-branch.py <platform>")
    platform = sys.argv[1]
    slug = fgstate.active_slug()
    repos = project.repos()[platform]
    paths = mapped_paths(slug, platform)
    base = fgstate.read_run(slug).get("bases", {}).get(platform)
    roots = {}
    for repo in repos:
        if any(project.under(p, repo["git_root"]) for p in paths):
            roots.setdefault(repo["git_root"], base or repo["base"])
    if not roots:
        print(json.dumps([{"platform": platform, "action": "no repo changes in the map; nothing branched"}]))
        return
    results = [prepare(root, base, f"feature/{fgstate.branch_slug(slug)}") for root, base in roots.items()]
    print(json.dumps(results, indent=2))
    sys.exit(1 if any("blocked" in r for r in results) else 0)


if __name__ == "__main__":
    main()
