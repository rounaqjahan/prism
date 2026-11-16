#!/usr/bin/env python3
import json
import sys
from pathlib import Path

import fgstate
from nodestate import shown

SHARED = ["brief", "research", "plan", "spec", "coldread", "mapcheck", "issues", "engine", "report"]
LANE = ["map", "build", "gate", "verify", "run", "pr", "ci"]


def load(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def cell(text, limit=110):
    text = " ".join(str(text or "").split()).replace("|", "/")
    return text if len(text) <= limit else text[:limit - 1] + "…"


def lane_row(run, platform):
    nodes = run["nodes"]
    current = next((s for s in LANE if nodes.get(f"{s}:{platform}", {}).get("status") != "pass"), None)
    if not current:
        return f"| {platform} | done | pass | – | – |"
    state = nodes.get(f"{current}:{platform}", {})
    return (f"| {platform} | {current} | {shown(f'{current}:{platform}', state)} | {state.get('attempts', 0)} "
            f"| {cell(state.get('reason'))} |")


def decisions(rdir, run):
    out = []
    for rule in (load(rdir / "brief.json") or {}).get("user_rules", []):
        if rule.get("said") and not str(rule["said"]).startswith("standing"):
            out.append(f"- \"{cell(rule['said'], 80)}\" → {cell(rule.get('rule'), 160)}")
    plan = load(rdir / "plan.json") or {}
    if plan.get("chosen_option"):
        out.append(f"- plan option {plan['chosen_option']}: {cell(plan.get('edits'), 200)}")
    choice = load(rdir / "run-choice.json") or {}
    if choice.get("who"):
        out.append(f"- who runs the app: {choice['who']} ({', '.join(choice.get('platforms', []))})")
    if run.get("bases"):
        out.append(f"- base branches named by the user: {run['bases']}")
    check = load(rdir / "mapcheck.json") or {}
    if check.get("approved"):
        out.append(f"- files approved: \"{cell(check.get('said'), 160)}\"")
    for instance, state in run["nodes"].items():
        if state.get("user_override"):
            out.append(f"- {instance} passed on the user's words: \"{cell(state['user_override']['said'], 100)}\"")
    return out or ["- none yet"]


def approved_files(rdir, run):
    if run["nodes"].get("mapcheck", {}).get("status") != "pass":
        return ["- not approved yet"]
    out = []
    for platform in run["platforms"]:
        plan = load(rdir / f"map-{platform}.json") or {}
        files = [f"{Path(f.get('path') or f.get('file') or '?').name} ({f.get('action') or f.get('op') or '?'})" for f in plan.get("files", [])]
        out.append(f"- {platform}: {', '.join(files) or plan.get('change', 'no map')}")
    return out


def sent_back(rdir):
    out = []
    for path in sorted(rdir.glob("user-feedback-*.json")):
        item = load(path) or {}
        out.append(f"- {item.get('node', path.stem)} ({path.name}): {cell(item.get('said'), 160)}")
    return out or ["- none"]


def pending(run):
    out = [f"- {i}: {shown(i, s)}{' – ' + cell(s['reason']) if s.get('reason') else ''}"
           for i, s in run["nodes"].items() if s["status"] in ("running", "blocked")]
    return out or ["- nothing running or blocked"]


def render(slug, run):
    rdir = fgstate.run_dir(slug)
    brief = load(rdir / "brief.json") or {}
    clean = (load(rdir / "coldread-rows-read.json") or {}).get("clean", [])
    lines = [f"# Prism progress: {slug}", "",
             "Written by graph.py after every change. Never edit it by hand. Node agents: read it on a retry; "
             "the cold-reader never reads it.", "",
             f"**Change:** {cell(brief.get('change'), 400) or '(brief not written yet)'}", "",
             "## Shared steps", "| step | status | tries | note |", "|---|---|---|---|"]
    for node in SHARED:
        state = run["nodes"].get(node)
        if state:
            lines.append(f"| {node} | {shown(node, state)} | {state.get('attempts', 0)} | {cell(state.get('reason'))} |")
    lines += ["", "## Platforms (current step = first step not passed)",
              "| platform | current step | status | tries | note |", "|---|---|---|---|---|"]
    lines += [lane_row(run, p) for p in run["platforms"]]
    lines += ["", "## Decisions in force (the user's words; never widen them; superseded ones are removed from brief.json)", *decisions(rdir, run),
              "", "## Approved files", *approved_files(rdir, run),
              "", "## Sent back (what each redo had to change)", *sent_back(rdir),
              "", "## Running or blocked", *pending(run),
              "", "## Clean test rows (unchanged since the last cold-read)",
              f"- {', '.join(clean) if clean else 'none yet'}", ""]
    return "\n".join(lines)


def write(slug, run):
    try:
        (fgstate.run_dir(slug) / "progress.md").write_text(render(slug, run))
    except Exception as error:
        print(f"warning: progress.md not written: {error}", file=sys.stderr)


if __name__ == "__main__":
    slug = sys.argv[1] if len(sys.argv) > 1 else fgstate.active_slug()
    write(slug, fgstate.read_run(slug))
    print(fgstate.run_dir(slug) / "progress.md")
