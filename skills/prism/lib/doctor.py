#!/usr/bin/env python3
"""Check what Prism and each platform need on this machine, and install what is missing.

usage:
  doctor.py [core] [ios] [android]                           check, print JSON
  doctor.py --install <item> [<item> ...]                     install items (uses the OS package manager)
  doctor.py --project                                         check core + every platform in the active project
Exit code 1 when something required is missing.
"""
import json
import os
import platform as _platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

OS = {"Darwin": "mac", "Windows": "windows"}.get(_platform.system(), "linux")


def which(name):
    return shutil.which(name)


def out(*cmd):
    exe = which(cmd[0]) or cmd[0]
    try:
        proc = subprocess.run([exe, *cmd[1:]], capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=60)
        return proc.returncode, (proc.stdout + proc.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as error:
        return 127, str(error)


def linux_pm():
    for pm, install in (("apt-get", ["sudo", "apt-get", "install", "-y"]), ("dnf", ["sudo", "dnf", "install", "-y"]),
                        ("pacman", ["sudo", "pacman", "-S", "--noconfirm"]), ("zypper", ["sudo", "zypper", "install", "-y"])):
        if which(pm):
            return pm, install
    return None, None


def package_install(names):
    """names: {"mac": "brew formula", "windows": "winget id", "linux": {"apt-get": "pkg", ...} or "pkg", "snap": "..."}"""
    if OS == "mac":
        if not which("brew"):
            return None, "Homebrew is missing: run the installer again (it installs Homebrew), or see https://brew.sh"
        spec = names.get("mac")
        return (["brew", "install", *spec.split()] if spec else None), None
    if OS == "windows":
        spec = names.get("windows")
        if spec and which("winget"):
            return ["winget", "install", "--id", spec, "-e", "--silent", "--accept-package-agreements",
                    "--accept-source-agreements"], None
        if names.get("choco") and which("choco"):
            return ["choco", "install", "-y", names["choco"]], None
        return None, "winget is missing (install 'App Installer' from the Microsoft Store)"
    pm, install = linux_pm()
    spec = names.get("linux")
    pkg = spec.get(pm) if isinstance(spec, dict) else spec
    if pkg and install:
        return install + pkg.split(), None
    if names.get("snap") and which("snap"):
        return ["sudo", "snap", "install", *names["snap"].split()], None
    return None, "no supported package manager found"


def version_ok(cmd, pattern, minimum):
    code, text = out(*cmd)
    match = re.search(pattern, text)
    if code or not match:
        return False, None
    found = tuple(int(x) for x in match.groups())
    return found >= minimum, ".".join(map(str, found))


def check_python():
    ok = sys.version_info >= (3, 9)
    return None if ok else f"Python {sys.version.split()[0]} is too old; Prism needs 3.9+"


def check_gh_auth():
    if not which("gh"):
        return "GitHub CLI (gh) is not installed"
    code, _ = out("gh", "auth", "status")
    return None if code == 0 else "gh is not logged in: run `gh auth login`"


def android_sdk():
    for key in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        if os.environ.get(key):
            return Path(os.environ[key])
    return {"mac": Path.home() / "Library/Android/sdk",
            "windows": Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "Android/Sdk",
            "linux": Path.home() / "Android/Sdk"}[OS]


def java_ok():
    if os.environ.get("JAVA_HOME") or which("java"):
        return True
    return any(Path(p).exists() for p in ("/Applications/Android Studio.app/Contents/jbr",
                                           r"C:\Program Files\Android\Android Studio\jbr", "/opt/android-studio/jbr"))


ITEMS = {
    "python": {"check": check_python, "required": True,
               "install": {"mac": "python@3.12", "windows": "Python.Python.3.12",
                           "linux": {"apt-get": "python3", "dnf": "python3", "pacman": "python", "zypper": "python3"}}},
    "git": {"check": lambda: None if which("git") else "git is not installed", "required": True,
            "install": {"mac": "git", "windows": "Git.Git", "linux": "git"}},
    "gh": {"check": lambda: None if which("gh") else "GitHub CLI (gh) is not installed", "required": True,
           "install": {"mac": "gh", "windows": "GitHub.cli", "linux": {"apt-get": "gh", "dnf": "gh", "pacman": "github-cli", "zypper": "gh"}}},
    "gh-login": {"check": check_gh_auth, "required": True, "manual": "Run `gh auth login` and follow the prompts."},
    "node": {"check": lambda: None if which("node") and which("npx") else "Node.js (node + npx) is not installed",
             "required": True,
             "install": {"mac": "node", "windows": "OpenJS.NodeJS.LTS",
                         "linux": {"apt-get": "nodejs npm", "dnf": "nodejs npm", "pacman": "nodejs npm", "zypper": "nodejs npm"}}},
    "claude": {"check": lambda: None if which("claude") else "Claude Code (claude) is not on PATH", "required": True,
               "command": ["npm", "install", "-g", "@anthropic-ai/claude-code"]},
    "bash": {"check": lambda: None if which("bash") else "bash is not available (Git for Windows provides it)",
             "required": OS == "windows", "install": {"windows": "Git.Git"}},
    "xcode": {"check": lambda: (None if OS == "mac" and out("xcodebuild", "-version")[0] == 0 else
                                "Xcode is not installed" if OS == "mac" else "iOS builds need a Mac with Xcode"),
              "manual": "Install Xcode from the Mac App Store, open it once, then run `sudo xcodebuild -license accept`."},
    "android-studio": {"check": lambda: None if java_ok() else "Android Studio (or a JDK 17+) is not installed",
                       "install": {"mac": "--cask android-studio", "windows": "Google.AndroidStudio",
                                   "snap": "android-studio --classic"}},
    "android-sdk": {"check": lambda: None if android_sdk().exists() else f"Android SDK not found at {android_sdk()}",
                    "manual": "Open Android Studio once and finish the setup wizard (it downloads the SDK), "
                              "or set ANDROID_HOME to your SDK folder."},
    "pnpm": {"check": lambda: None if which("pnpm") else "pnpm is not installed",
             "command": ["npm", "install", "-g", "pnpm"]},
    "yarn": {"check": lambda: None if which("yarn") else "yarn is not installed",
             "command": ["npm", "install", "-g", "yarn"]},
}
GROUPS = {"core": ["python", "git", "gh", "gh-login", "node", "claude", "bash"],
          "ios": ["xcode"], "android": ["android-studio", "android-sdk"]}


def install_command(item):
    spec = ITEMS[item]
    if spec.get("command"):
        return spec["command"], None
    if spec.get("install"):
        return package_install(spec["install"])
    return None, spec.get("manual", "install it by hand")


def check(groups, package_managers=()):
    items = list(dict.fromkeys(i for g in groups for i in GROUPS.get(g, [g] if g in ITEMS else [])))
    items += [pm for pm in package_managers if pm in ITEMS and pm not in items]
    report = []
    for item in items:
        problem = ITEMS[item]["check"]()
        if problem:
            cmd, note = install_command(item)
            report.append({"item": item, "problem": problem, "required": bool(ITEMS[item].get("required")),
                           "install": " ".join(cmd) if cmd else None, "manual": None if cmd else (ITEMS[item].get("manual") or note)})
    return {"os": OS, "checked": items, "missing": report, "ok": not any(r["required"] for r in report)}


def install(items):
    results = []
    for item in items:
        if item not in ITEMS:
            results.append({"item": item, "result": "unknown item"})
            continue
        if not ITEMS[item]["check"]():
            results.append({"item": item, "result": "already there"})
            continue
        cmd, note = install_command(item)
        if not cmd:
            results.append({"item": item, "result": "manual", "how": ITEMS[item].get("manual") or note})
            continue
        print(f"installing {item}: {' '.join(cmd)}", file=sys.stderr)
        code = subprocess.call([which(cmd[0]) or cmd[0], *cmd[1:]])
        results.append({"item": item, "result": "installed" if code == 0 else f"failed (exit {code})",
                        "note": "open a new terminal if it is still not found (PATH refresh)" if code == 0 else None})
    return results


def project_groups():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import project
    groups = ["core"] + project.platforms()
    pms = set()
    for platform, repos in project.repos().items():
        for repo in repos:
            if Path(repo["path"], "package.json").exists():
                pms.add(project.package_manager(repo["path"]))
    return groups, sorted(pms - {"npm"})


def main():
    args = sys.argv[1:]
    if args and args[0] == "--install":
        print(json.dumps(install(args[1:]), indent=2))
        return
    if args == ["--project"]:
        groups, pms = project_groups()
        report = check(groups, pms)
    else:
        report = check(args or ["core"])
    print(json.dumps(report, indent=2, ensure_ascii=False))
    sys.exit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
