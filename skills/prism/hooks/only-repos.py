#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import fgstate
import project


def allowed_roots(slug):
    repos = project.repos()
    roots = [os.path.realpath(r["path"]) for rs in repos.values() for r in rs]
    return roots + [os.path.realpath(fgstate.run_dir(slug))]


def main():
    data = json.load(sys.stdin)
    slug = fgstate.active_slug()
    target = data.get("tool_input", {}).get("file_path") or data.get("tool_input", {}).get("notebook_path")
    if not slug or not target:
        return 0
    resolved = os.path.realpath(os.path.expanduser(target))
    if any(resolved == root or resolved.startswith(root + os.sep) for root in allowed_roots(slug)):
        return 0
    print(f"Prism: a builder may edit only the platform repos and the run folder, not {resolved}. "
          "The skill, its checks and its contract are never edited by a node.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
