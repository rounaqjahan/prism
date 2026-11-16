#!/usr/bin/env python3
"""Scan folders and draft a Prism project: which platforms, which repos, base branches,
rule docs, gate commands, CI commands and shared code. Read-only: it never writes.

usage: setup_detect.py <folder> [<folder> ...]
Prints JSON: {"platforms": {...}, "shared_candidates": [...], "empty": [...], "missing": [...], "notes": [...]}
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import project

SKIP = {".git", "node_modules", "build", "Build", "Pods", ".dart_tool", "DerivedData", ".gradle", ".build",
        "dist", ".next", ".expo", "vendor", "Carthage", ".idea", ".vscode", "coverage", "out", "target"}
MAX_DEPTH = 4
RULE_DOCS = ["CLAUDE.md", "AGENTS.md", "ARCHITECTURE.md", "docs/ARCHITECTURE.md", "docs/architecture.md",
             "CONTRIBUTING.md"]
WEB_DEPS = {"next", "vite", "react-dom", "vue", "svelte", "@angular/core", "nuxt", "@remix-run/react", "astro"}
RN_DEPS = {"react-native", "expo"}
CODE_EXTS = {".swift", ".kt", ".java", ".dart", ".ts", ".tsx", ".js", ".jsx", ".vue", ".svelte"}


def git(root, *args):
    try:
        proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=30)
        return proc.stdout.strip() if proc.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def git_info(folder):
    root = git(folder, "rev-parse", "--show-toplevel")
    if not root:
        return {"git_root": project.norm(folder), "remote": None, "base": "main", "git": False}
    url = git(root, "remote", "get-url", "origin")
    match = re.search(r"[:/]([^/:]+/[^/]+?)(\.git)?$", url)
    head = git(root, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    base = head.split("/", 1)[1] if "/" in head else ""
    if not base:
        branches = git(root, "branch", "--format=%(refname:short)").split()
        base = next((b for b in ("main", "master", "develop", "trunk") if b in branches), None) \
            or git(root, "branch", "--show-current") or "main"
    return {"git_root": project.norm(Path(root).resolve()), "remote": match.group(1) if match else None,
            "base": base, "git": True}


def package_json(folder):
    try:
        data = json.loads((folder / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {}), **data.get("peerDependencies", {})}
    return {"deps": deps, "scripts": data.get("scripts", {}), "name": data.get("name"),
            "workspaces": data.get("workspaces") or (folder / "pnpm-workspace.yaml").exists()}


def kind_of(folder):
    names = set(os.listdir(folder))
    if "pubspec.yaml" in names:
        return "flutter"
    pkg = package_json(folder) if "package.json" in names else None
    if pkg:
        if RN_DEPS & set(pkg["deps"]):
            return "rn"
        if WEB_DEPS & set(pkg["deps"]):
            return "web"
        if pkg["workspaces"]:
            return "workspace"
        return "js-package"
    if names & {"settings.gradle", "settings.gradle.kts"}:
        return "android"
    if any(n.endswith((".xcodeproj", ".xcworkspace")) for n in names) or "Package.swift" in names:
        return "ios"
    return None


def has_code(folder):
    count = 0
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in SKIP]
        count += sum(1 for f in files if Path(f).suffix in CODE_EXTS)
        if count >= 3:
            return True
    return False


def code_dirs(folder, exts):
    out = []
    for child in sorted(Path(folder).iterdir()):
        if not child.is_dir() or child.name in SKIP or child.name.startswith(".") or "test" in child.name.lower():
            continue
        if any(Path(f).suffix in exts for _, _, files in os.walk(child) for f in files):
            out.append(child.name)
    return out or ["."]


def android_modules(folder):
    apps, libs = [], []
    for build in list(folder.glob("*/build.gradle")) + list(folder.glob("*/build.gradle.kts")) + \
            list(folder.glob("*/*/build.gradle")) + list(folder.glob("*/*/build.gradle.kts")):
        text = build.read_text(encoding="utf-8", errors="ignore")
        module = build.parent
        if not (module / "src" / "main").exists():
            continue
        rel = project.norm(module.relative_to(folder))
        if "com.android.application" in text or "android.application" in text:
            apps.append(rel)
        elif "com.android.library" in text or "android.library" in text:
            libs.append(rel)
    return apps, libs


def repo_entry(platform, folder, role, source):
    info = git_info(folder)
    rules = [d for d in RULE_DOCS if (folder / d).exists()]
    root = Path(info["git_root"])
    rules += [project.norm(root / d) for d in RULE_DOCS if root != folder and (root / d).exists()]
    entry = {"role": role, "path": project.norm(folder.resolve()), "git_root": info["git_root"],
             "remote": info["remote"], "base": info["base"], "source": source, "rules": rules,
             "gate": project.materialize_gate(platform, role, folder)}
    if not info["git"]:
        entry["note"] = "not a git repo yet"
    if platform == "ios" and not entry["gate"]:
        entry["note"] = "no Xcode scheme found; fill in the gate by hand"
    return entry


PRO_ONLY = {"web": "Web", "flutter": "Flutter", "rn": "React Native"}


def classify(folder, kind):
    if kind in PRO_ONLY:
        return None, []
    if kind == "android":
        apps, libs = android_modules(folder)
        role = "app" if apps or not libs else "sdk"
        source = [f"{m}/src/main" for m in apps + libs] or ["app/src/main"]
        return "android", [repo_entry("android", folder, role, source)]
    if kind == "ios":
        names = os.listdir(folder)
        role = "app" if any(n.endswith((".xcodeproj", ".xcworkspace")) for n in names) else "sdk"
        source = ["Sources"] if role == "sdk" and (folder / "Sources").is_dir() else code_dirs(folder, {".swift"})
        return "ios", [repo_entry("ios", folder, role, source)]
    return None, []


def walk(start):
    found, workspaces = [], []
    stack = [(Path(start).resolve(), 0)]
    while stack:
        folder, depth = stack.pop()
        try:
            kind = kind_of(folder)
        except OSError:
            continue
        if kind in ("flutter", "web", "rn", "android", "ios"):
            found.append((folder, kind))
            continue
        if kind == "workspace":
            workspaces.append(folder)
        if depth >= MAX_DEPTH:
            continue
        try:
            children = sorted(c for c in folder.iterdir() if c.is_dir() and c.name not in SKIP and not c.name.startswith("."))
        except OSError:
            continue
        stack += [(c, depth + 1) for c in reversed(children)]
    return found, workspaces


def local_links(folder, kind):
    links = []
    if kind in ("web", "rn", "js-package"):
        pkg = package_json(folder) or {"deps": {}}
        links += [v.split(":", 1)[1] for v in pkg["deps"].values()
                  if isinstance(v, str) and v.startswith(("file:", "link:", "portal:"))]
        links += [name for name, v in pkg["deps"].items() if isinstance(v, str) and v.startswith("workspace:")]
    if kind == "ios" and (folder / "Package.swift").exists():
        links += re.findall(r'\.package\(\s*(?:name:\s*"[^"]*",\s*)?path:\s*"([^"]+)"',
                            (folder / "Package.swift").read_text(encoding="utf-8", errors="ignore"))
    return links


def ci_commands(git_root):
    root, out = Path(git_root), []
    for wf in sorted((root / ".github" / "workflows").glob("*.y*ml")):
        text = wf.read_text(encoding="utf-8", errors="ignore")
        for match in re.finditer(r"^\s*-?\s*run:[ \t]*(?![|>])(\S.*)$", text, re.M):
            out.append({"file": project.norm(wf.relative_to(root)), "run": match.group(1).strip().strip("'\"")})
        for block in re.finditer(r"^(\s*)-?\s*run:\s*\|\s*\n((?:\1\s+.+\n?)+)", text, re.M):
            for line in block.group(2).splitlines():
                if line.strip():
                    out.append({"file": project.norm(wf.relative_to(root)), "run": line.strip()})
    gitlab = root / ".gitlab-ci.yml"
    if gitlab.exists():
        for match in re.finditer(r"^\s+-\s+(.+)$", gitlab.read_text(encoding="utf-8", errors="ignore"), re.M):
            out.append({"file": ".gitlab-ci.yml", "run": match.group(1).strip()})
    return out[:40]


ARCH_SIGNS = {
    "folders": {"ViewModels": "MVVM", "view_models": "MVVM", "viewmodels": "MVVM", "viewmodel": "MVVM",
                "Coordinators": "Coordinator", "coordinators": "Coordinator", "Presenters": "MVP/VIPER",
                "Interactors": "VIPER/Clean", "usecases": "Clean architecture", "UseCases": "Clean architecture",
                "domain": "Clean architecture", "Reducers": "TCA/Redux", "reducers": "Redux", "bloc": "BLoC",
                "blocs": "BLoC", "cubit": "BLoC", "providers": "Provider/Riverpod", "store": "Redux/store",
                "slices": "Redux Toolkit", "repositories": "Repository pattern", "Repositories": "Repository pattern",
                "features": "Feature folders", "Features": "Feature folders"},
    "deps": {"flutter_bloc": "BLoC", "flutter_riverpod": "Riverpod", "riverpod": "Riverpod", "provider": "Provider",
             "get_it": "get_it DI", "go_router": "go_router", "getx": "GetX", "get": "GetX", "mobx": "MobX",
             "@reduxjs/toolkit": "Redux Toolkit", "redux": "Redux", "zustand": "Zustand", "mobx-react": "MobX",
             "@tanstack/react-query": "React Query", "react-query": "React Query", "jotai": "Jotai",
             "@react-navigation/native": "React Navigation", "expo-router": "expo-router",
             "react-router": "React Router", "react-router-dom": "React Router"},
    "text": {"ComposableArchitecture": "TCA", "dagger.hilt": "Hilt", "@HiltViewModel": "Hilt", "org.koin": "Koin",
             "androidx.compose": "Jetpack Compose", "Swinject": "Swinject", "RxSwift": "RxSwift", "Combine": "Combine"},
}


def architecture_hints(folder, kind):
    signs = set()
    for root, dirs, files in os.walk(folder):
        depth = len(Path(root).relative_to(folder).parts)
        dirs[:] = [d for d in dirs if d not in SKIP and not d.startswith(".")] if depth < 6 else []
        signs |= {ARCH_SIGNS["folders"][d] for d in dirs if d in ARCH_SIGNS["folders"]}
    if kind in ("android", "ios"):
        files = list(folder.glob("**/build.gradle*"))[:20] + list(folder.glob("Package.swift")) + \
            list(folder.glob("*.xcodeproj/project.pbxproj"))[:2] + list(folder.glob("Podfile"))
        text = " ".join(f.read_text(encoding="utf-8", errors="ignore")[:200000] for f in files)
        signs |= {v for k, v in ARCH_SIGNS["text"].items() if k in text}
    return sorted(signs)


FLAG_HINTS = re.compile(r"(feature[_-]?flag|FeatureFlag|RemoteConfig|LaunchDarkly|Unleash|Statsig|GrowthBook|isEnabled\()")


def flag_hints(folder):
    hits = []
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in SKIP and not d.startswith(".")]
        for f in files:
            if Path(f).suffix in CODE_EXTS and re.search(r"(?i)feature.?flag|^feature\.\w+$|remote.?config", f):
                hits.append(project.norm(Path(root, f)))
        if len(hits) >= 5:
            break
    return hits


def detect(folders):
    result = {"platforms": {}, "shared_candidates": [], "empty": [], "missing": [], "ci": {}, "flag_hints": [],
              "notes": [], "os": project.OS}
    paths_by_kind = []
    for start in folders:
        start = Path(os.path.expanduser(start))
        if not start.exists():
            result["missing"].append(project.norm(start))
            continue
        found, workspaces = walk(start)
        if not found and not has_code(start):
            result["empty"].append(project.norm(start.resolve()))
            continue
        for folder, kind in found:
            platform, entries = classify(folder, kind)
            if not platform:
                if kind in PRO_ONLY:
                    result["notes"].append(f"{project.norm(folder)} is a {PRO_ONLY[kind]} app: skipped. "
                                           "Web, Flutter and React Native are in Prism Pro.")
                continue
            spec = result["platforms"].setdefault(platform, {"repos": [], "architecture_hints": []})
            spec["architecture_hints"] = sorted(set(spec["architecture_hints"]) | set(architecture_hints(folder, kind)))
            known = {(e["path"], e["role"]) for e in spec["repos"]}
            spec["repos"] += [e for e in entries if (e["path"], e["role"]) not in known]
            paths_by_kind.append((folder, kind))
            result["flag_hints"] += flag_hints(folder)
        for ws in workspaces:
            result["notes"].append(f"{project.norm(ws)} is a JS workspace; its packages may be a shared layer")
    by_path = {project.norm(f.resolve()): k for f, k in paths_by_kind}
    for folder, kind in paths_by_kind:
        for link in local_links(folder, kind):
            target = (folder / link).resolve() if not link.startswith(("@", "~")) and "/" in link or link.startswith(".") else None
            result["shared_candidates"].append({"used_by_folder": project.norm(folder.resolve()), "kind": kind,
                                                "link": link, "path": project.norm(target) if target else None,
                                                "is_platform_repo": bool(target and project.norm(target) in by_path)})
    roots = {e["git_root"] for spec in result["platforms"].values() for e in spec["repos"]}
    result["ci"] = {r: ci_commands(r) for r in sorted(roots)}
    result["flag_hints"] = sorted(set(result["flag_hints"]))[:15]
    if len({e["git_root"] for spec in result["platforms"].values() for e in spec["repos"]}) == 1 and len(result["platforms"]) > 1:
        result["notes"].append("all platforms live in one git repo (monorepo)")
    if project.OS != "mac" and "ios" in result["platforms"]:
        result["notes"].append("iOS found, but this machine is not a Mac: iOS lanes can be planned and coded here, "
                               "but their build, gate and run need a Mac")
    return result


def main():
    folders = sys.argv[1:] or [os.getcwd()]
    print(json.dumps(detect(folders), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
