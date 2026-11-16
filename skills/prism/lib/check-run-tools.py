#!/usr/bin/env python3
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import project

LOGIN = project.prism_home() / "run-login.md"
MCP = {"ios-mcp": ("ios-simulator-mcp", "ios-simulator"), "mobile-mcp": ("mobile-mcp", "mobile")}
EXE = ".exe" if project.OS == "windows" else ""


def sh(*cmd, cwd=None):
    exe = shutil.which(cmd[0]) or cmd[0]
    try:
        proc = subprocess.run([exe, *cmd[1:]], capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=120, cwd=cwd)
        return proc.returncode, proc.stdout + proc.stderr
    except (OSError, subprocess.TimeoutExpired) as error:
        return 1, str(error)


def mcp_servers(folder):
    _, out = sh("claude", "mcp", "list", cwd=folder)
    servers = {}
    for line in out.splitlines():
        match = re.match(r"^([\w.\- ]+?): (.+) - (✔ Connected|✓ Connected|✗.*|!.*)$", line.strip())
        if match:
            servers[match.group(1)] = {"command": match.group(2), "connected": "Connected" in match.group(3)
                                       and not match.group(3).startswith(("✗", "!"))}
    return servers


def mcp_problem(item, servers, folder):
    needle, name = MCP[item]
    found = [(n, s) for n, s in servers.items() if needle in s["command"] or n == name]
    if not found:
        return f"not available in {folder} (not installed, or installed for another folder only)"
    server, info = found[0]
    if not info["connected"]:
        return f"'{server}' is installed but not connected"
    _, detail = sh("claude", "mcp", "get", server, cwd=folder)
    if "Local config" in detail or "Project config" in detail:
        return f"'{server}' only works in one folder (local scope); install it for all projects"
    return None


def adb():
    local = project.android_sdk() / "platform-tools" / f"adb{EXE}"
    return str(local) if local.exists() else shutil.which("adb")


def check(item, servers, folder):
    if item in MCP:
        return mcp_problem(item, servers, folder)
    simulator = project.run_settings()["ios_simulator"]
    if item == "ios-simulator":
        if project.OS != "mac":
            return "iOS simulators need a Mac"
        _, out = sh("xcrun", "simctl", "list", "devices", "available")
        return None if simulator in out else f"no '{simulator}' simulator"
    if item == "xcode-open":
        return "Xcode is open" if project.OS == "mac" and sh("pgrep", "-x", "Xcode")[0] == 0 else None
    if item == "adb":
        return None if adb() else "adb not found"
    if item == "android-emulator":
        emulator = project.android_sdk() / "emulator" / f"emulator{EXE}"
        if not emulator.exists():
            return "Android emulator not installed"
        _, out = sh(str(emulator), "-list-avds")
        return None if out.strip() else "no Android virtual device"
    return None


def main():
    args = sys.argv[1:]
    folder = args[args.index("--project") + 1] if "--project" in args else os.getcwd()
    platforms = [p for i, arg in enumerate(args) if arg != "--project" and (i == 0 or args[i - 1] != "--project")
                 for p in arg.split(",") if p]
    servers = mcp_servers(folder)
    report, missing = {}, 0
    for platform in platforms:
        items = project.pack(platform).get("run_needs")
        if not items:
            report[platform] = {"ok": False, "problems": [{"item": "none", "what": "no simulator run for this platform",
                                                           "fix": "contract/run-tools.md"}]}
            continue
        problems = [{"item": i, "what": p, "fix": f"contract/run-tools.md#{i}"}
                    for i in dict.fromkeys(items + ["login"])
                    for p in [check(i, servers, folder) if i != "login" else (None if LOGIN.exists() else "no dev login file")] if p]
        report[platform] = {"ok": not problems, "problems": problems}
        missing += len(problems)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    sys.exit(1 if missing else 0)


if __name__ == "__main__":
    main()
