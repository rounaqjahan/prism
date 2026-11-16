import fgstate

MAX = 3


def fix_state(run, node):
    if node.startswith("rowfix:"):
        return run.get("rowfix", {}).get(node.split(":", 1)[1])
    return run["nodes"].get(node)


def fix_guard(slug, node):
    state = fix_state(fgstate.read_run(slug), node) or {}
    if state.get("fix_sent", 0) >= MAX:
        raise SystemExit(f"{node} has had {MAX} fix messages: send no more. Mark it blocked with the reason "
                         f"\"handoff still invalid after {MAX} fixes\" and tell the user")


def count_fix(slug, node):
    with fgstate.locked_run(slug) as run:
        state = fix_state(run, node)
        if state is None:
            return True
        if state.get("fix_sent", 0) >= MAX:
            return False
        state["fix_sent"] = state.get("fix_sent", 0) + 1
    return True


def reopen_guard(node, state, said):
    used = state.get("attempts", 0) if node == "coldread" else state.get("reopens", 0)
    out_of_retries = str(state.get("reason", "")).startswith("failed after")
    if (used >= MAX or out_of_retries) and not said:
        why = "used all its retries" if out_of_retries else f"had {MAX} rounds"
        extra = " or skip it (done coldread pass --user-override \"<their words>\")" if node == "coldread" else ""
        raise SystemExit(f"{node} has {why}: ask the user, then reopen it with their words "
                         f"(reopen {node} --said \"<their words>\"){extra}")
    state["reopens"] = state.get("reopens", 0) + 1


def redo_guard(node, count, more):
    if count > MAX and not more:
        raise SystemExit(f"{node} has been sent back {MAX} times: ask the user whether to send it back again, "
                         f"then pass their words with --more \"<their words>\"")


def rowfix_guard(platform, n, more):
    if n > MAX and not more:
        raise SystemExit(f"the row fixer has run {MAX} times for {platform}: ask the user whether to run it again, "
                         f"then pass their words with --more \"<their words>\"")
