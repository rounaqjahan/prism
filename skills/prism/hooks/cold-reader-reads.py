#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import fgstate

ALLOWED = ("brief.json", "coldread.json")


def main():
    data = json.load(sys.stdin)
    slug = fgstate.active_slug()
    target = data.get("tool_input", {}).get("file_path")
    if not slug or not target:
        return 0
    rdir = os.path.realpath(fgstate.run_dir(slug))
    resolved = os.path.realpath(os.path.expanduser(target))
    name = os.path.basename(resolved)
    if os.path.dirname(resolved) == rdir and (name in ALLOWED or (name.startswith("map-") and name.endswith(".json"))):
        return 0
    print(f"Prism: the cold-reader reads only brief.json, map-*.json and its own coldread.json; not {resolved}. "
          "Context would let it fill gaps a real tester can't.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
