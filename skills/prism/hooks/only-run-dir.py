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
    if not slug:
        return 0
    target = data.get("tool_input", {}).get("file_path") or data.get("tool_input", {}).get("notebook_path")
    if not target:
        return 0
    allowed = os.path.realpath(fgstate.run_dir(slug))
    resolved = os.path.realpath(os.path.expanduser(target))
    if resolved == allowed or resolved.startswith(allowed + os.sep):
        return 0
    print(f"Prism: this node is read-only. It may write only inside {allowed}, not {resolved}.",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
