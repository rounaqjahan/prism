import glob
import time
from pathlib import Path

TERMINAL = {"pass", "skipped", "blocked"}


def node_map(graph):
    return {n["id"]: n for n in graph["nodes"]}


def split(instance):
    base, _, platform = instance.partition(":")
    return base, platform or None


def instances(graph, platforms):
    ids = []
    for node in graph["nodes"]:
        if node.get("for_each"):
            ids += [f"{node['id']}:{p}" for p in platforms]
        else:
            ids.append(node["id"])
    return ids


def new_run(graph, slug, trigger, platforms):
    flags = {k: v["default"] for k, v in graph["flags"].items() if "default" in v}
    return {
        "slug": slug,
        "trigger": trigger,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "platforms": platforms,
        "flags": flags,
        "retries": {p: 0 for p in platforms},
        "nodes": {i: {"status": "pending", "attempts": 0} for i in instances(graph, platforms)},
        "log": [],
    }


def log(run, instance, event, reason=""):
    run["log"].append({"t": time.strftime("%H:%M:%S"), "node": instance, "event": event, "reason": reason})


def deps(graph, run, instance):
    nodes = node_map(graph)
    base, platform = split(instance)
    out = []
    for entry in nodes[base]["after"]:
        name = entry if isinstance(entry, str) else entry["node"]
        only = None if isinstance(entry, str) else entry.get("only")
        if only and platform not in only:
            continue
        if nodes[name].get("for_each"):
            if platform:
                out.append((f"{name}:{platform}", "lane"))
            else:
                out += [(f"{name}:{p}", "join") for p in run["platforms"]]
        else:
            out.append((name, "global"))
    return out


def lane_verdict(graph, run, instance):
    base, platform = split(instance)
    if not platform:
        return None
    for node in graph["nodes"]:
        if node["id"] == base:
            return None
        earlier = run["nodes"].get(f"{node['id']}:{platform}")
        if earlier and earlier["status"] == "skipped" and node.get("skip_continues"):
            continue
        if earlier and earlier["status"] in ("blocked", "skipped"):
            return earlier["status"], f"lane {earlier['status']} at {node['id']}:{platform}"
    return None


def dep_verdict(graph, run, instance):
    lane = lane_verdict(graph, run, instance)
    if lane:
        return lane
    waiting = False
    joins = [dep for dep, mode in deps(graph, run, instance) if mode == "join"]
    if joins and any(state["status"] == "blocked" and not split(other)[1] and other != instance
                     for other, state in run["nodes"].items()):
        return "wait", ""
    for dep, mode in deps(graph, run, instance):
        status = run["nodes"][dep]["status"]
        if mode == "join":
            waiting = waiting or status not in TERMINAL
            continue
        if status == "blocked":
            return "blocked", f"upstream {dep} blocked"
        if status == "skipped" and mode == "lane" and not node_map(graph)[split(dep)[0]].get("skip_continues"):
            return "skipped", f"lane skipped at {dep}"
        if status not in ("pass", "skipped"):
            waiting = True
    return ("wait", "") if waiting else ("ready", "")


def settle(graph, run):
    nodes = node_map(graph)
    ready = []
    changed = True
    while changed:
        changed = False
        ready = []
        for instance, state in run["nodes"].items():
            if state["status"] != "pending" or split(instance)[0] not in nodes:
                continue
            skip_flag = nodes[split(instance)[0]].get("skip_if")
            if skip_flag and run["flags"].get(skip_flag):
                state["status"], state["reason"] = "skipped", f"{skip_flag}: the feature runs as steps (phases.json)"
                log(run, instance, "skipped", state["reason"])
                changed = True
                continue
            verdict, reason = dep_verdict(graph, run, instance)
            if verdict in ("blocked", "skipped"):
                state["status"], state["reason"] = verdict, reason
                log(run, instance, verdict, reason)
                changed = True
                continue
            if verdict != "ready":
                continue
            flag = nodes[split(instance)[0]].get("when")
            if flag and run["flags"].get(flag) is None:
                raise SystemExit(f"flag '{flag}' is not set; {graph['flags'][flag]['set_by']} must set it")
            if flag and not run["flags"][flag]:
                state["status"], state["reason"] = "skipped", f"{flag} is false"
                log(run, instance, "skipped", state["reason"])
                changed = True
                continue
            ready.append(instance)
    return ready


def resolve(paths, rdir, platform):
    out = []
    for raw in paths:
        optional = raw.endswith("?")
        name = raw.rstrip("?").replace("{p}", platform or "")
        if "*" in name:
            out += sorted(glob.glob(str(rdir / name)))
            continue
        path = rdir / name
        if optional and not path.exists():
            continue
        out.append(str(path))
    return out


def describe(graph, run, instance, rdir):
    node = node_map(graph)[split(instance)[0]]
    platform = split(instance)[1]
    state = run["nodes"][instance]
    item = {
        "id": instance,
        "kind": node["kind"],
        "attempt": state["attempts"],
        "reads": resolve(node.get("reads", []), rdir, platform),
        "writes": resolve(node.get("writes", []), rdir, platform),
    }
    for key in ("agent", "script", "skill", "pause"):
        if key in node:
            item[key] = node[key].replace("{p}", platform or "")
    if state.get("last_failure"):
        item["last_failure"] = state["last_failure"]
    if platform:
        item["retries_used"] = run["retries"][platform]
    return item


def lane_descendants(graph, start):
    lane = [n for n in graph["nodes"] if n.get("for_each")]
    found = {start}
    changed = True
    while changed:
        changed = False
        for node in lane:
            names = {a if isinstance(a, str) else a["node"] for a in node["after"]}
            if node["id"] not in found and names & found:
                found.add(node["id"])
                changed = True
    return found


def fail(graph, run, instance, handoffs):
    base, platform = split(instance)
    target = node_map(graph)[base].get("on_fail")
    if not target or not platform:
        raise SystemExit(f"{instance} has no retry edge; use 'blocked' with a reason")
    run["retries"][platform] += 1
    used = run["retries"][platform]
    if used > graph["max_retries"]:
        block(run, instance, f"failed after {graph['max_retries']} retries")
        return "blocked"
    for name in lane_descendants(graph, target):
        state = run["nodes"][f"{name}:{platform}"]
        state["status"] = "pending"
        state.pop("reason", None)
        state.pop("stop_tries", None)
    run["nodes"][f"{target}:{platform}"]["last_failure"] = handoffs
    log(run, instance, "fail", f"retry {used}/{graph['max_retries']} back to {target}:{platform}")
    return "retry"


def redo(graph, run, instance, feedback_path):
    base, platform = split(instance)
    if not platform:
        raise SystemExit("redo works on a platform lane node, e.g. build:ios")
    for name in lane_descendants(graph, base):
        state = run["nodes"][f"{name}:{platform}"]
        state["status"] = "pending"
        for key in ("reason", "stop_tries"):
            state.pop(key, None)
    run["nodes"][instance]["last_failure"] = [feedback_path]
    reopened = []
    for name in shared_descendants(graph, base):
        state = run["nodes"].get(name)
        if state and state["status"] != "pending":
            state["status"] = "pending"
            for key in ("reason", "stop_tries"):
                state.pop(key, None)
            reopened.append(name)
    log(run, instance, "redo", f"user feedback: {feedback_path}; back to pending: {', '.join(reopened) or 'none'}")
    return reopened


def shared_descendants(graph, base):
    nodes = graph["nodes"]
    found, out = {base}, []
    changed = True
    while changed:
        changed = False
        for node in nodes:
            after = {e if isinstance(e, str) else e["node"] for e in node.get("after", [])}
            if node["id"] not in found and after & found:
                found.add(node["id"])
                changed = True
                if not node.get("for_each"):
                    out.append(node["id"])
    return out


def reopen(run, instance):
    reopened = [instance]
    run["nodes"][instance]["status"] = "pending"
    run["nodes"][instance].pop("reason", None)
    run["nodes"][instance].pop("stop_tries", None)
    changed = True
    while changed:
        changed = False
        for other, state in run["nodes"].items():
            if other in reopened:
                continue
            reason = state.get("reason", "")
            if any((f"at {src}" in reason or f"upstream {src} blocked" in reason)
                   and (not split(src)[1] or split(other)[1] == split(src)[1])
                   for src in reopened):
                state["status"] = "pending"
                state.pop("reason", None)
                state.pop("stop_tries", None)
                reopened.append(other)
                changed = True
    log(run, instance, "reopened", f"{len(reopened)} nodes back to pending")
    return reopened


def block(run, instance, reason):
    run["nodes"][instance]["status"] = "blocked"
    run["nodes"][instance]["reason"] = reason
    log(run, instance, "blocked", reason)


def set_flags(graph, run, instance, pairs):
    base = split(instance)[0]
    for pair in pairs:
        key, _, raw = pair.partition("=")
        spec = graph["flags"].get(key)
        if not spec or spec["set_by"] != base:
            raise SystemExit(f"{instance} can't set flag '{key}'")
        value = raw.lower() == "true"
        if split(instance)[1]:
            value = value or bool(run["flags"].get(key))
        run["flags"][key] = value
    for key, spec in graph["flags"].items():
        if spec["set_by"] == base and spec.get("required") and run["flags"].get(key) is None:
            raise SystemExit(f"{instance} must set flag '{key}' (--flag {key}=true|false)")


def finished(run, graph=None):
    known = node_map(graph) if graph else None
    return all(s["status"] in TERMINAL for i, s in run["nodes"].items()
               if known is None or split(i)[0] in known)


def missing_writes(item):
    return [w for w in item["writes"] if not Path(w).exists()]
