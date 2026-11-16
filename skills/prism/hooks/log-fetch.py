#!/usr/bin/env python3
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import fgstate


def main():
    data = json.load(sys.stdin)
    slug = fgstate.active_slug()
    url = data.get("tool_input", {}).get("url")
    if not slug or data.get("tool_name") != "WebFetch" or not url:
        return 0
    with open(fgstate.run_dir(slug) / "fetch-log.txt", "a") as log:
        log.write(url + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
