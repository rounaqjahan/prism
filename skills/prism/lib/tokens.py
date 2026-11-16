#!/usr/bin/env python3
import json
import sys

import fgstate


def path(slug):
    return fgstate.run_dir(slug) / "tokens.json"


def load(slug):
    try:
        return json.loads(path(slug).read_text())
    except (OSError, ValueError):
        return {"entries": []}


def add(slug, node, tokens, note=""):
    data = load(slug)
    data["entries"].append({"node": node, "tokens": int(tokens), "note": note})
    path(slug).write_text(json.dumps(data, indent=1))


def feature_runs(slug):
    parent = fgstate.branch_slug(slug)
    runs = fgstate.runs_dir()
    return [parent] + sorted(d.name for d in runs.iterdir() if d.name.startswith(parent + "-") and (d / "run.json").exists())


def summary(slug):
    rows, total = [], 0
    for run in feature_runs(slug):
        by_step = {}
        for entry in load(run)["entries"]:
            step = entry["node"].split(":")[0]
            by_step[step] = by_step.get(step, 0) + entry["tokens"]
        rows.append((run, by_step, sum(by_step.values())))
        total += sum(by_step.values())
    return rows, total


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "add":
        add(sys.argv[2] if len(sys.argv) > 4 else fgstate.active_slug(), *sys.argv[-2:])
        return
    slug = sys.argv[1] if len(sys.argv) > 1 else fgstate.active_slug()
    rows, total = summary(slug)
    for run, by_step, subtotal in rows:
        print(f"{run}: {subtotal:,} tokens  " + " · ".join(f"{k} {v:,}" for k, v in by_step.items()))
    print(f"whole feature, node agents only: {total:,} tokens")


if __name__ == "__main__":
    main()
