#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import fgstate


def main():
    data = json.load(sys.stdin)
    slug = fgstate.active_slug()
    target = data.get("tool_input", {}).get("file_path")
    if not slug or not target:
        return 0
    rdir = os.path.realpath(fgstate.run_dir(slug))
    resolved = os.path.realpath(os.path.expanduser(target))
    name = os.path.basename(resolved)
    if os.path.dirname(resolved) == rdir and (name == "brief.json" or name.startswith("rowfix-")):
        return 0
    print(f"Prism: the row fixer reads only brief.json and its rowfix-* files; not {resolved}. "
          "It rewrites the named rows from the setup, nothing else.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
