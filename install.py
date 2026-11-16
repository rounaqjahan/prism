#!/usr/bin/env python3
"""Install Prism into ~/.claude on macOS.

Normally run by install.sh, which first installs
Python, Git, the GitHub CLI and Node.js when they are missing. Safe to run again: it updates in place.

  python3 install.py            install, then check and install what Prism needs
  python3 install.py --no-deps  install the files only
"""
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLAUDE = Path.home() / ".claude"
SKILLS = ["prism", "slice-feature", "gather-feature-specs"]
WINDOWS = platform.system() == "Windows"
HOOK_SCRIPT = "skills/prism/hooks/no-prompt-steering.py"


def posix(path):
    return str(path).replace("\\", "/")


def quote(text):
    return f'"{text}"' if " " in text else text


def python_command():
    """How hooks and steps call Python on this machine. -X utf8 keeps JSON and logs UTF-8 on Windows too."""
    return f"{quote(posix(sys.executable))} -X utf8"


def rewrite(text, py, home):
    text = re.sub(r"\bpython3 (?=~/\.claude/|\$HOME/\.claude/)", py + " ", text)
    if WINDOWS:
        text = text.replace("~/.claude/", f"{posix(home)}/.claude/")
    return text


def copy_tree(py):
    (CLAUDE / "skills").mkdir(parents=True, exist_ok=True)
    (CLAUDE / "agents").mkdir(parents=True, exist_ok=True)
    (CLAUDE / "prism").mkdir(parents=True, exist_ok=True)
    for skill in SKILLS:
        target = CLAUDE / "skills" / skill
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(HERE / "skills" / skill, target, ignore=shutil.ignore_patterns(".DS_Store", "__pycache__"))
    for agent in sorted((HERE / "agents").glob("fg-*.md")):
        shutil.copyfile(agent, CLAUDE / "agents" / agent.name)
    changed = 0
    for path in list((CLAUDE / "skills" / "prism").rglob("*")) + list((CLAUDE / "agents").glob("fg-*.md")) + \
            [p for s in SKILLS[1:] for p in (CLAUDE / "skills" / s).rglob("*.md")]:
        if path.is_file() and path.suffix in (".md", ".py", ".json"):
            text = path.read_text(encoding="utf-8")
            new = rewrite(text, py, Path.home())
            if new != text:
                path.write_text(new, encoding="utf-8")
                changed += 1
    if not WINDOWS:
        for script in list((CLAUDE / "skills/prism/hooks").glob("*.py")) + list((CLAUDE / "skills/prism/lib").glob("*.py")):
            script.chmod(script.stat().st_mode | 0o111)
    return changed


def register_hook(py):
    path = CLAUDE / "settings.json"
    settings = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    script = f"{posix(Path.home())}/.claude/{HOOK_SCRIPT}" if WINDOWS else f"~/.claude/{HOOK_SCRIPT}"
    command = f"{py} {quote(script)}"
    pre = settings.setdefault("hooks", {}).setdefault("PreToolUse", [])
    for entry in pre:
        for hook in entry.get("hooks", []):
            if HOOK_SCRIPT in hook.get("command", ""):
                if hook["command"] == command:
                    return "settings.json already has the Prism hook"
                hook["command"] = command
                path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
                return "updated the Prism hook in settings.json"
    if path.exists():
        shutil.copyfile(path, path.with_name("settings.json.before-prism"))
    pre.append({"matcher": "Agent|Task|SendMessage", "hooks": [{"type": "command", "command": command}]})
    path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    return "added the Prism hook to settings.json (old copy: settings.json.before-prism)"


def dependencies():
    doctor = [sys.executable, "-X", "utf8", str(CLAUDE / "skills/prism/lib/doctor.py")]
    report = json.loads(subprocess.run(doctor + ["core"], capture_output=True, text=True, encoding="utf-8").stdout)
    auto = [m["item"] for m in report["missing"] if m["install"] and m["item"] != "gh-login"]
    if auto:
        print(f"\nInstalling what Prism needs: {', '.join(auto)}")
        subprocess.call(doctor + ["--install", *auto])
        report = json.loads(subprocess.run(doctor + ["core"], capture_output=True, text=True, encoding="utf-8").stdout)
    if any(m["item"] == "gh-login" for m in report["missing"]) and shutil.which("gh") and sys.stdin.isatty():
        print("\nGitHub CLI needs a login so Prism can open PRs.")
        subprocess.call([shutil.which("gh"), "auth", "login"])
        report = json.loads(subprocess.run(doctor + ["core"], capture_output=True, text=True, encoding="utf-8").stdout)
    return report


def main():
    if sys.version_info < (3, 9):
        raise SystemExit("Prism needs Python 3.9 or newer. Run install.sh, which installs it.")
    py = python_command()
    changed = copy_tree(py)
    print(f"Copied Prism into {CLAUDE} ({changed} files pointed at {sys.executable}).")
    print(register_hook(py))
    if "--no-deps" not in sys.argv:
        report = dependencies()
        left = report["missing"]
        if left:
            print("\nStill missing:")
            for item in left:
                how = item["install"] or item["manual"]
                print(f"  - {item['problem']}" + (f"  ->  {how}" if how else ""))
            print("Open a new terminal and run the installer again if something was just installed but is not found.")
        else:
            print("\nEverything Prism needs is installed.")
    print("\nNext: restart Claude Code, open it in your project (or the folder that holds your repos), and type:")
    print("  /prism setup")


if __name__ == "__main__":
    main()
