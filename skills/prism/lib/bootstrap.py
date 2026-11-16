#!/usr/bin/env python3
"""Starter apps for a new project.

usage:
  bootstrap.py status                 which platforms have no app yet, and how each one's shell is made
  bootstrap.py shell <platform>       make the empty app shell with the platform's own tool,
                                      then commit it on the repo's base branch
  bootstrap.py check <platform>       does the platform have an app now (after the user made it in Xcode / Android Studio)?

The architecture skeleton on top of the shell (coordinator, one screen, its ViewModel and repository) is a normal
Prism run with kind "bootstrap": see steps/bootstrap.md.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import project
from setup_detect import kind_of

MARKER = {"android": "android", "ios": "ios"}
IGNORED = {".git", "ARCHITECTURE.md", "CLAUDE.md", "AGENTS.md", "README.md", ".gitignore", ".DS_Store"}


def run(cmd, cwd, env=None):
    exe = shutil.which(cmd[0]) or cmd[0]
    try:
        proc = subprocess.run([exe, *cmd[1:]], cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", stdin=subprocess.DEVNULL, env=env, timeout=900)
        return proc.returncode, (proc.stdout + proc.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as error:
        return 1, str(error)


def app_repo(platform):
    repos = project.repos().get(platform, [])
    return next((r for r in repos if r.get("role", "app") == "app"), repos[0] if repos else None)


def has_app(platform, repo):
    folder = Path(repo["path"])
    if not folder.exists():
        return False
    found = kind_of(folder)
    if found == MARKER.get(platform):
        return True
    if platform == "android":
        return any(folder.glob("*/build.gradle*")) or (folder / "settings.gradle.kts").exists()
    return False


def shell_command(platform, name, org):
    command = project.pack(platform).get("shell")
    if not command:
        return None
    snake = re.sub(r"[^a-z0-9_]", "_", name.lower()).strip("_") or "app"
    return [t.replace("{name}", snake).replace("{org}", org) for t in command["cmd"]], command.get("needs")


def status():
    cfg = project.config()
    out = {}
    for platform in project.platforms():
        repo = app_repo(platform)
        if not repo:
            continue
        made = shell_command(platform, cfg.get("name", "app"), cfg.get("org", "com.example"))
        tool = made[1] if made else None
        out[platform] = {"repo": repo["path"], "has_app": has_app(platform, repo),
                         "shell": " ".join(made[0]) if made else None,
                         "tool_missing": bool(tool and not shutil.which(tool)),
                         "by_hand": None if made else project.pack(platform).get("create_note"),
                         "needs_mac": project.needs_mac(platform) and project.OS != "mac"}
    return out


def copy_in(source, target):
    copied = []
    for item in source.iterdir():
        dest = target / item.name
        if dest.exists():
            continue
        (shutil.copytree if item.is_dir() else shutil.copy2)(item, dest)
        copied.append(item.name)
    return copied


def shell(platform):
    cfg = project.config()
    repo = app_repo(platform)
    if not repo:
        raise SystemExit(f"{platform} is not in this project")
    if has_app(platform, repo):
        return {"platform": platform, "result": "already has an app"}
    made = shell_command(platform, cfg.get("name", "app"), cfg.get("org", "com.example"))
    if not made:
        return {"platform": platform, "result": "by hand", "how": project.pack(platform).get("create_note")}
    cmd, tool = made
    if tool and not shutil.which(tool):
        return {"platform": platform, "result": "blocked", "reason": f"{tool} is not installed; run doctor.py --install {tool}"}
    target = Path(repo["path"])
    branch = subprocess.run(["git", "-C", str(target), "branch", "--show-current"], capture_output=True, text=True).stdout.strip()
    if branch and branch != repo.get("base", "main"):
        return {"platform": platform, "result": "blocked", "reason": f"{target} is on '{branch}', not '{repo.get('base')}'"}
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ, CI="1")
        code, log = run(cmd, tmp, env)
        made_dir = next((p for p in Path(tmp).iterdir() if p.is_dir()), None)
        if code or not made_dir:
            return {"platform": platform, "result": "failed", "cmd": " ".join(cmd), "log": log[-1500:]}
        copied = copy_in(made_dir, target)
    run(["git", "add", "-A"], target)
    code, log = run(["git", "-c", "user.name=Prism", "-c", "user.email=prism@localhost", "commit", "-m",
                     f"App shell ({' '.join(cmd[:3])})"], target)
    return {"platform": platform, "result": "made" if code == 0 else "made, not committed", "cmd": " ".join(cmd),
            "files": copied[:30], "log": None if code == 0 else log[-500:]}


def main():
    args = sys.argv[1:]
    if not args or args[0] == "status":
        print(json.dumps(status(), indent=2, ensure_ascii=False))
    elif args[0] == "shell" and len(args) > 1:
        print(json.dumps([shell(p) for p in args[1:]], indent=2, ensure_ascii=False))
    elif args[0] == "check" and len(args) > 1:
        print(json.dumps({p: has_app(p, app_repo(p)) if app_repo(p) else None for p in args[1:]}))
    else:
        raise SystemExit("usage: bootstrap.py status | shell <platform>... | check <platform>...")


if __name__ == "__main__":
    main()
