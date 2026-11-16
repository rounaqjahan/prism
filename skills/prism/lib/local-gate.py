#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import fgstate
from file_rules import check_files, diff_of
from reuse_check import check as reuse_check
import project

FAILURE = re.compile(r"(error:|FAILED|\[E\]|\s•\s|✘|✗|Error:)")


def repos(platform):
    return project.repos()[platform]


def xcode_open():
    return project.OS == "mac" and subprocess.run(["pgrep", "-x", "Xcode"], capture_output=True).returncode == 0


def blocked_reason(platform, repo):
    try:
        os.listdir(repo["path"])
    except OSError:
        return f"can't read {repo['path']} (the OS blocked access, or the path in .prism/prism.json is wrong)"
    commands = project.gate_commands(platform, repo)
    if project.OS != "mac" and (project.needs_mac(platform) or any(c["needs_mac"] for c in commands)):
        return f"{project.name(platform)} builds need a Mac with Xcode; run this lane's gate on a Mac"
    if any(c["argv"] and c["argv"][0].endswith("xcodebuild") for c in commands) and xcode_open():
        return "Xcode is open; never xcodebuild while Xcode is open. Close Xcode, then reopen this node"
    return None


def failure_keys(output):
    keys = set()
    for line in output.splitlines():
        if FAILURE.search(line):
            keys.add(re.sub(r"\d+", "#", line.strip())[:200])
    return keys


def dirty_files(repo):
    root = repo["git_root"]
    rel = os.path.relpath(repo["path"], root)
    out = subprocess.run(["git", "-C", root, "status", "--porcelain", "-uall", "--", rel],
                         capture_output=True, text=True).stdout
    return sorted(str(Path(root, line[3:].split(" -> ")[-1])) for line in out.splitlines())


def gate_env(platform):
    env = dict(os.environ, CI="1")
    java = project.java_home() if platform == "android" else None
    if java and "JAVA_HOME" not in os.environ:
        env["JAVA_HOME"] = java
    return env


def run_commands(platform, repo, rdir, tag):
    env = gate_env(platform)
    results = []
    for i, command in enumerate(project.gate_commands(platform, repo)):
        try:
            proc = subprocess.run(command["argv"], cwd=repo["path"], capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", env=env)
            code, output = proc.returncode, proc.stdout + proc.stderr
        except OSError as error:
            code, output = 127, f"could not start {command['argv'][0]}: {error}"
        log = rdir / f"gate-{platform}-{repo['role']}-{i}-{tag}.log"
        log.write_text(output, encoding="utf-8")
        results.append({"cmd": command["cmd"], "cwd": repo["path"], "exit": code, "build": command["build"],
                        "failures": sorted(failure_keys(output)) if code else [], "log": str(log)})
    return results


def baseline(platform, rdir):
    data = {}
    for repo in repos(platform):
        reason = blocked_reason(platform, repo)
        data[repo["role"]] = {"blocked": reason} if reason else {
            "dirty": dirty_files(repo), "commands": run_commands(platform, repo, rdir, "baseline")}
    (rdir / f"baseline-{platform}.json").write_text(json.dumps(data, indent=2))
    return data


def allowed_paths(rdir, platform):
    build = json.loads((rdir / f"build-{platform}.json").read_text())
    feature = fgstate.branch_slug(rdir.name)
    runs = [fgstate.run_dir(feature)] + sorted(fgstate.runs_dir().glob(f"{feature}-*"))
    paths = set()
    for run in runs:
        plan = json.loads((run / f"map-{platform}.json").read_text()) if (run / f"map-{platform}.json").exists() else {}
        paths |= {f.get("path") for f in plan.get("files", []) if isinstance(f, dict)}
    paths |= {str(d.get("evidence", "")).split(":")[0] for d in build.get("deviations", []) if isinstance(d, dict)}
    return {p for p in paths if p}


def gate(platform, rdir):
    base = json.loads((rdir / f"baseline-{platform}.json").read_text())
    build = json.loads((rdir / f"build-{platform}.json").read_text())
    out = {"platform": platform, "result": "pass", "commands": [], "log": "", "file_rules": [], "notes": []}
    changed = set(build.get("files_changed", []))
    platform_touched = bool(changed) or any(
        set(dirty_files(r)) - set(base.get(r["role"], {}).get("dirty", []))
        for r in repos(platform) if not blocked_reason(platform, r))
    for repo in repos(platform):
        reason = blocked_reason(platform, repo)
        if reason:
            out["result"], out["blocked"] = "blocked", reason
            break
        branch = subprocess.run(["git", "-C", repo["git_root"], "branch", "--show-current"],
                                capture_output=True, text=True).stdout.strip()
        repo_changed = any(project.under(f, repo["path"]) for f in changed)
        if repo_changed and branch != f"feature/{fgstate.branch_slug()}":
            out["result"] = "fail"
            out["file_rules"].append(f"{repo['git_root']} is on '{branch}', not feature/{fgstate.branch_slug()}")
        before = base.get(repo["role"], {})
        new_dirty = set(dirty_files(repo)) - set(before.get("dirty", []))
        touched = {f for f in changed if project.under(f, repo["path"])} | new_dirty
        if not platform_touched:
            continue
        old = {c["cmd"]: set(c["failures"]) for c in before.get("commands", [])}
        for result in run_commands(platform, repo, rdir, "gate"):
            result["new_failures"] = sorted(set(result["failures"]) - old.get(result["cmd"], set()))
            is_build = result["build"]
            if result["exit"] and is_build:
                was_broken = any(c["cmd"] == result["cmd"] and c["exit"] for c in before.get("commands", []))
                if was_broken:
                    out["result"], out["blocked"] = "blocked", f"the app did not build before this change either: {result['log']}"
                else:
                    out["result"] = "fail"
            elif result["exit"] and (result["new_failures"] or result["cmd"] not in old):
                out["result"] = "fail"
            out["commands"].append(result)
        brief = json.loads((rdir / "brief.json").read_text()) if (rdir / "brief.json").exists() else {}
        problems, notes = check_files(platform, sorted(touched), brief)
        problems += [f"{f}: changed but not in map-{platform}.json or a recorded deviation [graph rule R6: only the asked feature]"
                     for f in sorted(touched - allowed_paths(rdir, platform))]
        rel = os.path.relpath(repo["path"], repo["git_root"])
        sources = [os.path.normpath(os.path.join(rel, d)) for d in repo["source"]]
        added = [(f, diff_of(Path(f))[0]) for f in sorted(touched) if Path(f).suffix in project.source_exts() and Path(f).exists()]
        problems += reuse_check(repo["git_root"], sources, added)
        out["file_rules"] += problems
        out["notes"] += notes
    if out["file_rules"] and out["result"] == "pass":
        out["result"] = "fail"
    if not out["commands"] and out["result"] == "pass":
        out["commands"].append({"cmd": "none", "exit": 0, "note": "no files changed on this platform"})
    out["log"] = "; ".join(c.get("log", "") for c in out["commands"] if c.get("log"))
    (rdir / f"gate-{platform}.json").write_text(json.dumps(out, indent=2))
    return out


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: local-gate.py <platform> [--baseline]")
    platform = sys.argv[1]
    slug = fgstate.active_slug()
    rdir = Path(os.environ.get("FG_RUN_DIR") or fgstate.run_dir(slug))
    if "--baseline" in sys.argv:
        print(json.dumps(baseline(platform, rdir), indent=2)[:3000])
        return
    from nodestate import mark_started
    mark_started(f"gate:{platform}", slug)
    result = gate(platform, rdir)
    print(json.dumps({k: result[k] for k in ("result", "file_rules", "notes")} | {"blocked": result.get("blocked")}, indent=2))


if __name__ == "__main__":
    main()
