#!/usr/bin/env python3
import json
import os
import subprocess
import sys

import fgstate
import project

SKIP = ("/build/", "/dist/", "/node_modules/", "/.dart_tool/", "/Pods/", "/DerivedData/")


def git(root, *args):
    result = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def readable(path):
    try:
        os.listdir(path)
        return True
    except OSError:
        return False


def scan(repo, pattern, ref):
    root = repo["git_root"]
    if not readable(repo["path"]):
        return {"readable": False, "reason": f"can't read {repo['path']} (macOS blocked access)"}
    rel = os.path.relpath(repo["path"], root)
    paths = [os.path.normpath(os.path.join(rel, s)) for s in repo["source"]]
    _, branch, _ = git(root, "branch", "--show-current")
    _, dirty, _ = git(root, "status", "--porcelain", "--", *paths)
    out = {"readable": True, "searched": ref, "checked_out": branch, "dirty": len(dirty.splitlines()) if dirty else 0}
    if branch != ref:
        out["note"] = f"working copy is on '{branch}'; hits come from '{ref}', not from the working copy"
    if git(root, "rev-parse", "--verify", "--quiet", ref)[0]:
        out["error"] = f"branch '{ref}' doesn't exist in {root}"
        return out
    if pattern:
        _, hits, _ = git(root, "grep", "-l", "-i", "-E", pattern, ref, "--", *paths)
        hits = [h.split(":", 1)[1] if h.startswith(ref + ":") else h for h in hits.splitlines()]
        files = [os.path.join(root, h) for h in hits if not any(s in "/" + h for s in SKIP)]
        out["hits"] = len(files)
        out["files"] = files[:8]
    return out


def named_branches(argv):
    words, branches = [], {}
    for arg in argv:
        if arg.startswith("--branch="):
            platform, _, branch = arg[len("--branch="):].partition("=")
            branches[platform] = branch
        else:
            words.append(arg)
    return words, branches


def main():
    words, branches = named_branches(sys.argv[1:])
    pattern = "|".join(words)
    repos = project.repos()
    report = {p: {r["role"]: scan(r, pattern, branches.get(p, r["base"])) for r in rs} for p, rs in repos.items()}
    print(json.dumps({"pattern": pattern, "platforms": report}, indent=2))


if __name__ == "__main__":
    main()
