#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import fgstate
from graph import fix_message, node_prompt

NODE = re.compile(r"FG_(?:NODE|FIX):\s*([a-z]+(?::[a-z]+)?)")


def deny(text):
    print(f"Prism: {text}", file=sys.stderr)
    return 2


def expected(kind, node, slug):
    graph = fgstate.load_graph()
    try:
        return node_prompt(graph, slug, node) if kind == "prompt" else fix_message(graph, slug, node)
    except SystemExit as error:
        return f"<none: {error}>"


def check_agent(data, slug):
    tool = data.get("tool_input", {})
    prompt = tool.get("prompt", "").strip()
    is_graph_agent = str(tool.get("subagent_type", "")).startswith("fg-")
    mentions_run = "FG_NODE" in prompt or str(fgstate.runs_dir()) in prompt
    if not (is_graph_agent or mentions_run):
        return 0
    found = NODE.search(prompt)
    if not found:
        return deny("a graph agent's prompt must be exactly `graph.py prompt <node>`.")
    want = expected("prompt", found.group(1), slug)
    if prompt != want.strip():
        return deny(f"prompt for {found.group(1)} must be exactly the output of "
                    f"`graph.py prompt {found.group(1)}`, with no added instructions. Expected:\n{want}")
    from nodestate import mark_started
    mark_started(found.group(1), slug)
    return 0


def check_message(data, slug):
    message = str(data.get("tool_input", {}).get("message", "")).strip()
    if not ("FG_" in message or str(fgstate.runs_dir()) in message):
        return 0
    found = NODE.search(message)
    if not found or not message.startswith("FG_FIX:"):
        return deny("a message to a graph agent must be exactly `graph.py fix <node>`.")
    want = expected("fix", found.group(1), slug)
    if message != want.strip():
        return deny(f"fix message for {found.group(1)} must be exactly the output of `graph.py fix {found.group(1)}`.")
    import caps
    if not caps.count_fix(slug, found.group(1)):
        return deny(f"{found.group(1)} has had {caps.MAX} fix messages: send no more; mark it blocked and tell the user.")
    return 0


def main():
    data = json.load(sys.stdin)
    slug = fgstate.active_slug()
    if not slug:
        return 0
    if data.get("tool_name") in ("Agent", "Task"):
        return check_agent(data, slug)
    if data.get("tool_name") == "SendMessage":
        return check_message(data, slug)
    return 0


if __name__ == "__main__":
    sys.exit(main())
