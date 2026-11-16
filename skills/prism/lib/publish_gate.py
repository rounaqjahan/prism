import json
import os

HUMAN = ("brief", "plan", "mapcheck", "report")
LANE = ("build", "verify", "pr", "ci")
SETTLED = ("pass", "fail", "blocked", "skipped", "skip")


def milestones(rdir, nodes, platforms):
    return {
        "human": {n: nodes.get(n, {}).get("status") for n in HUMAN},
        "waiting": sorted(n for n in HUMAN if nodes.get(n, {}).get("status") == "running"),
        "blocked": sorted(n for n, s in nodes.items() if s.get("status") == "blocked"),
        "lanes": {p: [nodes.get(f"{s}:{p}", {}).get("status") if nodes.get(f"{s}:{p}", {}).get("status") in SETTLED
                      else "open" for s in LANE] for p in platforms},
        "results": sorted(p for p in platforms if os.path.exists(os.path.join(rdir, f"run-{p}.json"))),
    }


def decide(rdir, nodes, platforms):
    path = os.path.join(rdir, "published.json")
    now = milestones(rdir, nodes, platforms)
    try:
        last = json.load(open(path))
    except (OSError, ValueError):
        last = None
    if last == now:
        return "publish: no (no milestone since the last publish; the local file is up to date)"
    changed = "first publish" if last is None else ", ".join(k for k in now if now[k] != last.get(k))
    with open(path, "w") as f:
        json.dump(now, f)
    return f"publish: yes ({changed})"
