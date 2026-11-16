import html
import json
import os
import re


def load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def esc(x):
    return html.escape(str(x or ""))


def problem_of(rdir, node, number):
    base, platform = node.split(":")
    name = {"gate": "gate", "verify": "verdict", "run": "run", "pr": "pr", "ci": "ci"}.get(base, base)
    data = load(os.path.join(rdir, f"{name}-{platform}-retry{number}.json"))
    if data is None:
        return "details not kept (this retry happened before failure snapshots were added)"
    if data.get("blocked"):
        return data["blocked"]
    if base == "gate":
        cmds = [c["cmd"] for c in data.get("commands", []) if c.get("exit")]
        return "; ".join((data.get("file_rules") or [])[:3] + [f"failed: {c}" for c in cmds[:2]]) or "gate failed"
    if base == "verify":
        return "; ".join(f'{c.get("rule")}: {c.get("fix") or c.get("evidence")}' for c in data.get("checks", [])
                         if c.get("result") == "fail")[:400] or "verify failed"
    if base == "run":
        return "; ".join(f'scenario {s.get("n")}: {s.get("claim") or s.get("reason")}' for s in data.get("scenarios", [])
                         if s.get("result") == "fail")[:400] or "a scenario failed"
    return f"{base} {data.get('result', 'failed')}"


def self_fixes(rdir, state):
    log = state.get("log", [])
    out = []
    for i, entry in enumerate(log):
        match = re.match(r"retry (\d+)/\d+ back to", entry.get("reason", ""))
        if entry.get("event") != "fail" or not match:
            continue
        node = entry["node"]
        fixed = any(later.get("node") == node and later.get("event") == "pass" for later in log[i + 1:])
        out.append({"node": node, "time": entry.get("t", ""), "problem": problem_of(rdir, node, match.group(1)),
                    "fixed": fixed})
    return out


def pct(n, total):
    return f"{round(100 * n / total)}%" if total else "0%"


def card(label, value, cls=""):
    return f'<li><span class="pname">{label}</span><span class="counts"><b class="{cls}">{value}</b></span></li>'


def eval_section(rdir, state, pill):
    told = (load(os.path.join(rdir, "eval.json")) or {}).get("entries", [])
    auto = self_fixes(rdir, state)
    count = {k: sum(1 for e in told if e.get("category") == k) for k in ("miss", "bug", "new")}
    auto_fixed = sum(1 for a in auto if a["fixed"])
    you_fixes = count["miss"] + count["bug"]
    fixes = auto_fixed + you_fixes
    cards = '<ul class="summary">' + "".join([
        card("Fixed by the graph on its own", f"{auto_fixed} of {fixes} fixes · {pct(auto_fixed, fixes)}", "c-pass"),
        card("Fixes you had to ask for", f"{you_fixes} of {fixes} fixes · {pct(you_fixes, fixes)}", "c-fail"),
        card("Instruction misses (of your requests)", f'{count["miss"]} of {len(told)} · {pct(count["miss"], len(told))}', "c-fail"),
        card("New asks (not counted against the graph)", f'{count["new"]} of {len(told)}'),
    ]) + "</ul>"
    auto_rows = "".join(
        f'<tr><th scope="row">{i}</th><td>{esc(a["node"])}</td><td>{esc(a["time"])}</td><td>{esc(a["problem"])}</td>'
        f'<td>{pill("pass" if a["fixed"] else "fail")}</td></tr>' for i, a in enumerate(auto, 1))
    auto_table = (f'<h3>Fixed by the graph without you</h3><p class="hint">Each time a gate, verify, run, PR or CI check '
                  f'failed and the builder fixed it on a retry, with no message from you.</p><div class="scroll">'
                  f'<table class="lanes"><thead><tr><th>#</th><th>Check</th><th>When</th><th>What was wrong</th>'
                  f'<th>Fixed by the graph</th></tr></thead><tbody>{auto_rows or "<tr><td colspan=5>none</td></tr>"}'
                  f'</tbody></table></div>')
    told_rows = "".join(
        f'<tr><th scope="row">{i}</th><td>{esc(e.get("said"))}</td><td>{esc(e.get("why"))}</td>'
        f'<td>{pill(e.get("category"))}</td><td>{esc(e.get("fixed_by"))}</td></tr>' for i, e in enumerate(told, 1))
    told_table = (f'<h3>What you had to tell the graph</h3><p class="hint"><b>Miss</b>: a skill, an instruction or the '
                  f'reference already said otherwise. <b>Graph bug</b>: the graph\'s own script or process was wrong. '
                  f'<b>New ask</b>: not stated before.</p><div class="scroll"><table class="lanes"><thead><tr><th>#</th>'
                  f'<th>What you said</th><th>Why</th><th>Category</th><th>Fixed by</th></tr></thead><tbody>'
                  f'{told_rows or "<tr><td colspan=5>nothing yet</td></tr>"}</tbody></table></div>')
    return cards + auto_table + told_table
