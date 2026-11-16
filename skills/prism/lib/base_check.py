#!/usr/bin/env python3
import json
import os
import subprocess
import sys

import fgstate
import project


def git(root, *args):
    proc = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True)
    return proc.returncode, proc.stdout.strip()


def repos_for(platforms, bases=None):
    table = project.repos()
    roots = {}
    for platform in platforms:
        for repo in table.get(platform, []):
            base = (bases or {}).get(platform, repo["base"])
            entry = roots.setdefault(repo["git_root"], {"base": base, "paths": [], "platforms": set(), "bases": set()})
            entry["bases"].add(base)
            rel = os.path.relpath(repo["path"], repo["git_root"])
            entry["paths"] += [os.path.normpath(os.path.join(rel, s)) for s in repo["source"]]
            entry["platforms"].add(platform)
    return roots


def check_repo(root, base, paths, feature_branch):
    try:
        os.listdir(root)
    except OSError:
        return [], [f"{root}: can't be read (the OS blocked access, or the path is wrong in .prism/prism.json); its platform is planned blind"]
    problems, warnings = [], []
    _, branch = git(root, "branch", "--show-current")
    if branch not in (base, feature_branch):
        ahead = git(root, "rev-list", "--count", f"{base}..HEAD")[1] or "?"
        problems.append(f"{root}: on '{branch}' ({ahead} commits not in '{base}'); switch it to '{base}' "
                        f"(git -C {root} switch {base})")
    elif branch == feature_branch and git(root, "merge-base", "--is-ancestor", base, "HEAD")[0]:
        problems.append(f"{root}: '{feature_branch}' was not cut from the current '{base}'")
    _, dirty = git(root, "status", "--porcelain", "--", *paths)
    if dirty:
        problems.append(f"{root}: {len(dirty.splitlines())} uncommitted change(s) in source folders "
                        f"({', '.join(paths)}); commit or move them first")
    _, other = git(root, "status", "--porcelain")
    if other and not dirty:
        warnings.append(f"{root}: uncommitted changes outside the source folders (not read by the plan)")
    code, behind = git(root, "rev-list", "--count", f"{base}..origin/{base}")
    if code == 0 and behind not in ("", "0"):
        warnings.append(f"{root}: '{base}' is {behind} commit(s) behind origin/{base} (as of the last fetch); "
                        f"pull it if the plan should see them")
    return problems, warnings


def base_report(platforms, slug, bases=None):
    feature_branch = f"feature/{fgstate.branch_slug(slug)}"
    problems, warnings = [], []
    for root, info in repos_for(platforms, bases).items():
        tag = "/".join(sorted(info["platforms"]))
        if len(info["bases"]) > 1:
            problems.append(f"[{tag}] {root}: platforms in one repo name different branches "
                            f"({', '.join(sorted(info['bases']))}); one repo has one base")
            continue
        p, w = check_repo(root, info["base"], info["paths"], feature_branch)
        problems += [f"[{tag}] {line}" for line in p]
        warnings += [f"[{tag}] {line}" for line in w]
    return problems, warnings


def require_base(platforms, slug, when, bases=None):
    problems, warnings = base_report(platforms, slug, bases)
    for line in warnings:
        print(f"warning: {line}", file=sys.stderr)
    if problems:
        raise SystemExit(f"{when} refused: every repo must be clean on its base branch before anything is "
                         "read or planned.\n" + "\n".join(problems))


def main():
    platforms = sys.argv[1].split(",") if len(sys.argv) > 1 else project.platforms() + ([project.SHARED] if project.shared() else [])
    slug = sys.argv[2] if len(sys.argv) > 2 else "none"
    bases = dict(a[len("--branch="):].split("=", 1) for a in sys.argv[3:] if a.startswith("--branch="))
    problems, warnings = base_report(platforms, slug, bases)
    print(json.dumps({"ok": not problems, "problems": problems, "warnings": warnings}, indent=2))
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
