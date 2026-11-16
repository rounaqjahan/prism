#!/usr/bin/env python3
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import fgstate
import graph_core as core
from check_handoff import check

MAX_TRIES = 3
MARKER = re.compile(r"FG_NODE:\s*([a-z]+(?::[a-z]+)?)")


def find_node(graph, run, agent_type, transcript):
    if not transcript or not Path(transcript).exists():
        return None
    found = MARKER.search(Path(transcript).read_text(errors="ignore"))
    if not found or run["nodes"].get(found.group(1), {}).get("status") != "running":
        return None
    instance = found.group(1)
    agent = core.describe(graph, run, instance, fgstate.run_dir(run["slug"])).get("agent")
    return instance if agent and agent_type.endswith(agent) else None


def record(slug, data, instance, outcome):
    entry = {"t": time.strftime("%H:%M:%S"), "agent_type": data.get("agent_type"), "node": instance,
             "transcript": bool(data.get("agent_transcript_path")), "outcome": outcome}
    with open(fgstate.run_dir(slug) / "hook-log.jsonl", "a") as log:
        log.write(json.dumps(entry) + "\n")


def main():
    data = json.load(sys.stdin)
    slug = fgstate.active_slug()
    if not slug:
        return 0
    graph = fgstate.load_graph()
    with fgstate.locked_run(slug) as run:
        instance = find_node(graph, run, data.get("agent_type", ""), data.get("agent_transcript_path"))
        if not instance:
            record(slug, data, None, "not a graph node")
            return 0
        item = core.describe(graph, run, instance, fgstate.run_dir(slug))
        missing = core.missing_writes(item)
        problems = [f"missing {m}" for m in missing]
        for path in item["writes"]:
            if path not in missing:
                problems += check(path)
        if not problems:
            record(slug, data, instance, "handoff ok")
            return 0
        state = run["nodes"][instance]
        state["stop_tries"] = state.get("stop_tries", 0) + 1
        if state["stop_tries"] > MAX_TRIES:
            core.block(run, instance, f"handoff still invalid after {MAX_TRIES} tries: {problems[0]}")
            record(slug, data, instance, "blocked")
            return 0
        record(slug, data, instance, f"stopped: {problems[0]}")
    print(f"Prism: {instance} can't finish yet (try {state['stop_tries']}/{MAX_TRIES}). Fix:\n- "
          + "\n- ".join(problems), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
