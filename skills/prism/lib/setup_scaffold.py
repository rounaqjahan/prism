#!/usr/bin/env python3
"""Write a project's .prism/ folder from the setup answers, and set it as the active project.

usage: setup_scaffold.py <answers.json> [--dry-run]

answers.json (written by the coordinator after the setup interview, confirmed by the user):
{
  "workspace": "/abs/folder that will hold .prism/",
  "name": "my-product",
  "new_project": false,
  "architecture": {
    "source": "project" | "mvvm-c" | "custom",
    "summary": "one paragraph in plain words",
    "platforms": {"<p>": {"description": "...", "folders": {"screens": "...", "logic": "...", "data": "...", "navigation": "..."},
                          "rules": [{"rule": "...", "pattern": "regex", "scope": "/views/"}], "max_file_lines": 300}}
  },
  "platforms": {"<p>": {"repos": [{"role": "app", "path": "...", "base": "main", "source": ["src"], "rules": [], "gate": [...]}]}},
  "shared": {"name": "...", "used_by": ["ios", "android"], "repos": [...]} | null,
  "feature_flags": {"platforms": ["ios"], "how": "plain words: where flags are added and read"} | null,
  "kinds": ["feature"],
  "run": {"ios_simulator": "iPhone 16"},
  "create_repos": true,
  "org": "com.example",
  "parity": [{"name": "Login", "platforms": {"ios": "✓", "android": "email only"}}]
}
"parity" is only for an existing project (the user-approved table from the parity check); a new project gets an empty table.
For architecture.source "mvvm-c", platform entries may be left out: the platform packs fill them in.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import project

LAYERS = [("screens", "Screen", "what you see and tap"), ("logic", "Logic", "what happens on a tap"),
          ("data", "Data", "talking to the server and storage"), ("navigation", "Navigation", "how you reach the screen")]


def fail(message):
    raise SystemExit(f"setup_scaffold: {message}")


def architecture_for(answers, platform):
    arch = answers.get("architecture") or {"source": "mvvm-c"}
    given = (arch.get("platforms") or {}).get(platform)
    if given:
        return given
    if arch.get("source", "mvvm-c") == "mvvm-c":
        return project.pack(platform).get("mvvm_c")
    fail(f"architecture '{arch.get('source')}' has no entry for {platform}: add folders and rules for it")


def validate(answers):
    if not answers.get("platforms"):
        fail("no platforms")
    for platform, spec in answers["platforms"].items():
        if platform not in project.known_packs() and not all(r.get("gate") is not None for r in spec.get("repos", [])):
            fail(f"'{platform}' is not a built-in platform ({', '.join(project.known_packs())}); give each repo a gate")
        if not spec.get("repos"):
            fail(f"{platform} has no repos")
        arch = architecture_for(answers, platform) or {}
        for rule in arch.get("rules", []):
            try:
                re.compile(rule["pattern"])
            except (re.error, KeyError) as error:
                fail(f"{platform} rule '{rule.get('rule')}' has a bad pattern: {error}")


def run(cmd, cwd):
    exe = shutil.which(cmd[0]) or cmd[0]
    proc = subprocess.run([exe, *cmd[1:]], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def architecture_doc(answers):
    arch = answers.get("architecture") or {"source": "mvvm-c"}
    title = {"mvvm-c": "MVVM-C (Prism's default)", "project": "Read from this project",
             "custom": "Described by the team"}.get(arch.get("source", "mvvm-c"), arch.get("source"))
    lines = [f"# Architecture: {title}", ""]
    if arch.get("summary"):
        lines += [arch["summary"], ""]
    lines += ["Prism's gate checks every line below that has a pattern in `prism.json` (`file_rules`), "
              "and the verifier grades the rest. Each repo's own docs win where they are more specific.", ""]
    for platform in answers["platforms"]:
        spec = architecture_for(answers, platform) or {}
        lines += [f"## {project.name_of(platform)}", "", spec.get("description", ""), ""]
        folders = spec.get("folders", {})
        if folders:
            lines += ["| Piece | Where it lives |", "|---|---|"]
            lines += [f"| {label} ({what}) | `{folders[key]}` |" for key, label, what in LAYERS if key in folders]
            lines.append("")
        limit = spec.get("max_file_lines")
        if limit:
            lines.append(f"- Every file is {limit} lines or less.")
        lines += [f"- {r['rule']}" for r in spec.get("rules", [])]
        lines.append("")
    return "\n".join(lines)


def folder_map(answers, repos):
    lines = ["# Folder map: where a feature's pieces live", "",
             "Every feature has four pieces: **Screen**, **Logic**, **Data**, **Navigation**. "
             "The mapper reads each repo's own docs first; where they are more specific than this file, they win. "
             "Paths are relative to each repo's `path` in `prism.json`.", "",
             "| Platform · repo | Screens | Logic | Data | Navigation |", "|---|---|---|---|---|"]
    for platform, entries in repos.items():
        spec = architecture_for(answers, platform) if platform in answers["platforms"] else {}
        folders = (spec or {}).get("folders", {})
        for repo in entries:
            cells = [f"`{folders[k]}`" if k in folders else "?" for k, _, _ in LAYERS]
            lines.append(f"| {project.name_of(platform)} {repo.get('role', 'app')} (`{Path(repo['path']).name}`) | "
                         + " | ".join(cells) + " |")
    lines += ["", "`?` = not known yet. The first run's mapper fills it in from the code, and the user approves it."]
    return "\n".join(lines) + "\n"


def flags_doc(answers):
    flags = answers.get("feature_flags")
    if not flags:
        return "# Feature flags\n\nThis project does not gate new features behind flags.\n"
    return ("# Feature flags\n\n"
            f"Every `kind: feature` run puts the feature behind a flag on {', '.join(project.name_of(p) for p in flags['platforms'])}, "
            "enabled by default. Other platforms get no flag.\n\n"
            f"{flags.get('how', 'Where flags are added and read: not described yet. The first run asks the user and writes it here.')}\n\n"
            "- One flag per feature, named after it.\n"
            "- The logic layer exposes `is<Feature>Enabled`; the screen hides the entry point when it is false.\n"
            "- With the flag off, the screen looks and behaves exactly as before the feature.\n")


def parity_doc(answers):
    platforms = list(answers["platforms"])
    head = ("# Feature parity\n\nUpdated, never replaced. A run changes only its own feature's row, from merged code. "
            "✓ = has it · ✗ = doesn't · `?` = not checked yet.\n\n"
            "| Feature | " + " | ".join(project.name_of(p) for p in platforms) + " |\n"
            "|---|" + "---|" * len(platforms) + "\n")
    if answers.get("new_project"):
        return head
    rows = []
    for feature in answers.get("parity") or []:
        cells = [str(feature.get("platforms", {}).get(p, "?")).replace("|", "/") for p in platforms]
        rows.append(f"| {feature['name']} | " + " | ".join(cells) + " |")
    return head + "\n".join(rows) + ("\n" if rows else "")


def manual_run_doc(answers):
    out = ["# Running the app yourself", "",
           "When you run a platform yourself, Prism lists the scenarios as a checklist in that platform's PR. "
           "For each platform:", ""]
    hints = {"ios": "Open the project in Xcode, pick a simulator, press Run (⌘R).",
             "android": "Open the project in Android Studio, start an emulator, press Run."}
    for platform in answers["platforms"]:
        out.append(f"- **{project.name_of(platform)}:** {hints.get(platform, 'Use the project README.')}")
    out += ["", "Then walk every scenario, take one screenshot per scenario, and report pass or fail per row."]
    if answers.get("feature_flags"):
        out.append("For the flag-off scenario, set this feature's flag to off where `feature-flags.md` says, run again, "
                   "and check the screen is exactly as before.")
    return "\n".join(out) + "\n"


def ci_doc(repos):
    lines = ["# CI map: the local gate", "",
             "The local gate runs these commands before anything is pushed, so nothing known-red is pushed. "
             "Edit `gate` in `prism.json` to change them; make them match what CI runs.", "",
             "| Platform · repo | Commands |", "|---|---|"]
    for platform, entries in repos.items():
        for repo in entries:
            gate = repo.get("gate") or project.materialize_gate(platform, repo.get("role", "app"), repo["path"])
            cmds = " · ".join("`" + (" ".join(g["cmd"]) if isinstance(g["cmd"], list) else g["cmd"]) + "`" for g in gate)
            lines.append(f"| {project.name_of(platform)} {repo.get('role', 'app')} | {cmds or 'none'} |")
    return "\n".join(lines) + "\n"


def create_repo(repo, platform, answers, report):
    folder = Path(repo["path"]).expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    if not (folder / ".git").exists():
        base = repo.get("base", "main")
        code, _ = run(["git", "init", "-b", base], folder)
        if code:
            run(["git", "init"], folder)
            run(["git", "checkout", "-b", base], folder)
    spec = architecture_for(answers, platform) or {}
    arch = folder / "ARCHITECTURE.md"
    if not arch.exists():
        arch.write_text(f"# {project.name_of(platform)} architecture\n\n{spec.get('description', '')}\n\n"
                        + "\n".join(f"- {r['rule']}" for r in spec.get("rules", [])) + "\n", encoding="utf-8")
    repo.setdefault("rules", [])
    if "ARCHITECTURE.md" not in repo["rules"]:
        repo["rules"].append("ARCHITECTURE.md")
    if run(["git", "status", "--porcelain"], folder)[1]:
        run(["git", "add", "-A"], folder)
        code, out = run(["git", "-c", "user.name=Prism", "-c", "user.email=prism@localhost", "commit", "-m",
                         "Prism starter contract"], folder)
        report.append(f"{platform}: committed the starter files on '{repo.get('base', 'main')}'"
                      if code == 0 else f"{platform}: commit failed: {out[-200:]}")


def build_config(answers, workspace):
    def rel(path):
        p = Path(path).expanduser().resolve()
        try:
            return project.norm(p.relative_to(workspace))
        except ValueError:
            return project.norm(p)

    def clean(repo):
        out = {k: v for k, v in repo.items() if k not in ("note",) and v not in (None, [])}
        out["path"] = rel(repo["path"])
        out["git_root"] = rel(repo.get("git_root") or repo["path"])
        out.setdefault("source", ["."])
        return out

    cfg = {"prism": 1, "name": answers.get("name") or workspace.name, "org": answers.get("org", "com.example"),
           "architecture": {k: v for k, v in (answers.get("architecture") or {"source": "mvvm-c"}).items() if k != "platforms"},
           "platforms": {p: {"repos": [clean(r) for r in spec["repos"]]} for p, spec in answers["platforms"].items()},
           "kinds": answers.get("kinds") or ["feature"],
           "feature_flags": ({"platforms": answers["feature_flags"]["platforms"], "doc": "feature-flags.md"}
                             if answers.get("feature_flags") else None),
           "run": answers.get("run") or {}, "file_rules": [], "max_file_lines": {}, "standing_rules": [],
           "guardrails": answers.get("guardrails", [])}
    shared = answers.get("shared")
    if shared and shared.get("repos"):
        cfg["shared"] = {"name": shared.get("name", "Shared layer"), "used_by": shared.get("used_by", []),
                         "needs_publish_for": shared.get("needs_publish_for", []),
                         "repos": [clean(r) for r in shared["repos"]]}
    for platform in answers["platforms"]:
        spec = architecture_for(answers, platform) or {}
        if spec.get("max_file_lines"):
            cfg["max_file_lines"][platform] = {"limit": spec["max_file_lines"], "doc": "architecture.md",
                                               "phrase": f"Every file is {spec['max_file_lines']} lines or less"}
        for rule in spec.get("rules", []):
            cfg["file_rules"].append({"platform": platform, "rule": rule["rule"], "pattern": rule["pattern"],
                                      "doc": "architecture.md", "phrase": rule["rule"],
                                      **({"scope": rule["scope"]} if rule.get("scope") else {})})
    return cfg


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: setup_scaffold.py <answers.json> [--dry-run]")
    answers = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    dry = "--dry-run" in sys.argv
    workspace = Path(answers.get("workspace") or Path.cwd()).expanduser().resolve()
    validate(answers)
    report = []
    if answers.get("create_repos") and not dry:
        for platform, spec in answers["platforms"].items():
            for repo in spec["repos"]:
                path = Path(repo["path"]).expanduser()
                repo["path"] = project.norm((workspace / path) if not path.is_absolute() else path)
                if not path.exists() or not any(Path(repo["path"]).iterdir()):
                    create_repo(repo, platform, answers, report)
    cfg = build_config(answers, workspace)
    repos = {p: [dict(r, path=project.norm((workspace / r["path"]).resolve()) if not Path(r["path"]).is_absolute() else r["path"])
                 for r in spec["repos"]] for p, spec in cfg["platforms"].items()}
    files = {"prism.json": json.dumps(cfg, indent=2, ensure_ascii=False) + "\n",
             "architecture.md": architecture_doc(answers), "folder-map.md": folder_map(answers, repos),
             "feature-flags.md": flags_doc(answers), "feature-parity.md": parity_doc(answers),
             "manual-run.md": manual_run_doc(answers), "ci-map.md": ci_doc(repos)}
    target = workspace / ".prism"
    if dry:
        print(json.dumps({"would_write": {str(target / k): len(v) for k, v in files.items()}, "config": cfg,
                          "report": report}, indent=2, ensure_ascii=False))
        return
    target.mkdir(parents=True, exist_ok=True)
    kept = []
    for name, text in files.items():
        path = target / name
        keep = ("folder-map.md", "feature-flags.md") + (() if name == "feature-parity.md" and answers.get("parity") else ("feature-parity.md",))
        if path.exists() and name in keep and "--overwrite" not in sys.argv:
            kept.append(name)
            continue
        path.write_text(text, encoding="utf-8")
    project.use(target)
    print(json.dumps({"project": project.norm(target / "prism.json"), "kept_existing": kept, "report": report},
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
