#!/usr/bin/env python3
"""Brownfield parity check, step 1: list the screens each platform has, so features can be lined up.
Read-only. The coordinator groups the names into features, confirms each cell in the code, and the
user approves the table before setup writes feature-parity.md.

usage: setup_parity.py <answers.json>
Prints JSON: {"platforms": {"<p>": {"screens": {"cart": ["/abs/file", ...]}, "routes": [...]}}, "features": [...]}
"""
import json
import os
import re
import sys
from pathlib import Path

import project
from setup_detect import SKIP

SCREEN_FILE = re.compile(r"(?i)^(.+?)[_-]?(view|screen|page|activity|fragment|viewcontroller|vc|route)"
                         r"(controller)?\.(swift|kt|java|dart|tsx|jsx|vue|svelte|ts|js)$")
SCREEN_DIRS = {"views", "screens", "pages", "features", "presentation", "ui", "scenes", "modules", "app"}
ROUTE = re.compile(r"""(?:path|route|name)\s*[:=]\s*['"](/[\w\-/:]*|[\w\-]+)['"]|composable\(\s*['"]([\w\-/{}]+)['"]""")
NOISE = {"base", "main", "root", "app", "content", "custom", "common", "shared", "loading", "empty", "error",
         "index", "layout", "item", "row", "cell", "header", "footer", "button", "component", "container"}


def words(name):
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    return "_".join(w for w in re.split(r"[_\-\s.]+", name.lower()) if w)


def feature_key(name):
    key = words(name)
    for suffix in ("_list", "_detail", "_details", "_section", "_sheet", "_dialog", "_tab"):
        key = key[: -len(suffix)] if key.endswith(suffix) and len(key) > len(suffix) else key
    return key


def scan_repo(repo):
    screens, routes = {}, set()
    root = Path(repo["path"])
    for source in repo.get("source", ["."]):
        base = root / source
        for folder, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in SKIP and not d.startswith(".") and "test" not in d.lower()]
            in_ui = bool(SCREEN_DIRS & {p.lower() for p in Path(folder).relative_to(root).parts})
            for f in files:
                match = SCREEN_FILE.match(f)
                parts = [p.lower() for p in Path(folder).relative_to(root).parts]
                feature_dir = next((Path(folder).relative_to(root).parts[i + 1] for i, p in enumerate(parts[:-1])
                                    if p in ("features", "modules", "screens", "pages")), None)
                if match:
                    name = match.group(1)
                elif feature_dir and Path(f).suffix in (".tsx", ".jsx", ".vue", ".svelte", ".dart", ".swift", ".kt"):
                    name = feature_dir
                elif in_ui and f.lower().startswith(("page.", "index.")) and Path(folder).name not in SCREEN_DIRS:
                    name = Path(folder).name
                else:
                    continue
                key = feature_key(name)
                if not key or key in NOISE:
                    continue
                screens.setdefault(key, []).append(project.norm(Path(folder, f)))
                if Path(f).suffix in (".tsx", ".ts", ".kt", ".dart", ".swift", ".js", ".jsx"):
                    try:
                        text = Path(folder, f).read_text(encoding="utf-8", errors="ignore")[:100000]
                    except OSError:
                        continue
                    routes |= {m.group(1) or m.group(2) for m in ROUTE.finditer(text)}
    return screens, routes


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: setup_parity.py <answers.json>")
    answers = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    out = {"platforms": {}, "features": []}
    for platform, spec in answers["platforms"].items():
        screens, routes = {}, set()
        for repo in spec["repos"]:
            s, r = scan_repo(repo)
            for key, files in s.items():
                screens.setdefault(key, []).extend(files)
            routes |= r
        out["platforms"][platform] = {"screens": {k: v[:5] for k, v in sorted(screens.items())},
                                      "routes": sorted(r for r in routes if r)[:80]}
    keys = sorted({k for p in out["platforms"].values() for k in p["screens"]})
    out["features"] = [{"name": k, "platforms": {p: ("found" if k in d["screens"] else "not found")
                                                 for p, d in out["platforms"].items()}} for k in keys]
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
