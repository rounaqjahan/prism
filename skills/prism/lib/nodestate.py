import json
import time

import fgstate


def kinds():
    return {n["id"]: n["kind"] for n in json.loads((fgstate.SKILL_DIR / "graph.json").read_text())["nodes"]}


def mark_started(node, slug=None):
    slug = slug or fgstate.active_slug()
    if not slug:
        return
    with fgstate.locked_run(slug) as run:
        state = run["nodes"].get(node)
        if state and state["status"] == "running" and not state.get("started"):
            state["started"] = time.strftime("%H:%M:%S")


def shown(node, state, table=None):
    status = state.get("status", "pending")
    if status != "running":
        return status
    if (table or kinds()).get(node.split(":")[0]) == "human":
        return "waiting"
    return "running" if state.get("started") else "ready"
