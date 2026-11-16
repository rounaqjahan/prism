#!/usr/bin/env python3
import base64
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from matrix_eval import eval_section
from tokens_page import section as tokens_section
import fgstate
from nodestate import shown
from publish_gate import decide
from matrix_rows import TICK_JS, regressions, row_head, setup_box, steps_section, ticks
import project

STEPS = ["map", "build", "gate", "verify", "run", "pr", "ci"]
NAMES = project.names()
LABEL = {"pass": "Pass", "fail": "Fail", "blocked": "Blocked", "unverified": "Unverified",
         "skipped": "Skipped", "skip": "Skipped", "running": "Running", "pending": "Pending",
         "ready": "Ready", "waiting": "Waiting on you",
         "notrun": "Not run", "na": "N/A", "you": "You run", "done": "Done",
         "miss": "Miss", "bug": "Graph bug", "new": "New ask"}


def load(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def run_dir(slug):
    if slug:
        return os.path.join(str(fgstate.runs_dir()), slug)
    sys.path.insert(0, os.path.dirname(__file__))
    from fgstate import active_slug
    return os.path.join(str(fgstate.runs_dir()), active_slug() or sys.exit("no active run: name the run, e.g. matrix.py <slug>"))


def make_thumb(path, out):
    if shutil.which("sips"):
        subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "70",
                        "-Z", "720", path, "--out", out], capture_output=True)
        return
    try:
        from PIL import Image
        image = Image.open(path)
        image.thumbnail((720, 720))
        image.convert("RGB").save(out, "JPEG", quality=70)
    except Exception:
        pass


def thumb(path, cache):
    if not path or not os.path.isfile(path):
        return ""
    out = os.path.join(cache, f"{abs(hash((path, os.path.getmtime(path))))}.jpg")
    if not os.path.isfile(out):
        make_thumb(path, out)
    if not os.path.isfile(out):
        if os.path.getsize(path) > 3_000_000:
            return ""
        kind = "png" if path.lower().endswith(".png") else "jpeg"
        with open(path, "rb") as f:
            return f"data:image/{kind};base64," + base64.b64encode(f.read()).decode()
    with open(out, "rb") as f:
        return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()


def shot_of(row):
    for e in row.get("evidence", []):
        if isinstance(e, str) and e.startswith("screenshot:"):
            return e.split(":", 1)[1].strip()
    return ""


def pill(status, extra=""):
    s = status if status in LABEL else "pending"
    return f'<span class="pill {s}">{LABEL[s]}{extra}</span>'


def esc(x):
    return html.escape(str(x or ""))


def lanes_table(state, platforms):
    nodes = state.get("nodes", {})
    head = "".join(f"<th>{NAMES.get(p, p)}</th>" for p in platforms)
    rows = []
    for step in STEPS:
        cells = []
        for p in platforms:
            n = nodes.get(f"{step}:{p}", {})
            st, tries, reason = shown(f"{step}:{p}", n), n.get("attempts", 0), n.get("reason", "")
            tries_txt = f'<span class="tries">{tries} {"try" if tries == 1 else "tries"}</span>' if tries else ""
            why = f'<details><summary>Why</summary><p>{esc(reason)}</p></details>' if reason and st in ("blocked", "fail") else ""
            cells.append(f"<td>{pill(st)}{tries_txt}{why}</td>")
        label = step.upper() if step in ("pr", "ci") else step.capitalize()
        rows.append(f'<tr><th scope="row">{label}</th>{"".join(cells)}</tr>')
    return f'<table class="lanes"><thead><tr><th>Step</th>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table>'


def user_runs(nodes, p):
    return nodes.get(f"run:{p}", {}).get("status") in ("skip", "skipped")


def scenario_cell(p, n, s, runs, nodes, cache):
    rid = s.get("id") or n
    if p in s.get("na", []) or (s.get("platform") and s["platform"] != p):
        return f"<td>{pill('na')}</td>"
    told = next((r for r in (runs.get(p) or {}).get("scenarios", []) if r.get("id") == rid), None)
    if user_runs(nodes, p):
        return f"<td>{pill(told['result'])}</td>" if told else f"<td>{pill('you')}{ticks(rid, p)}</td>"
    run = runs.get(p)
    if not run:
        st = shown(f"run:{p}", nodes.get(f"run:{p}", {}))
        return f"<td>{pill(st if st in ('running', 'ready') else 'notrun')}</td>"
    if run.get("blocked") and not run.get("scenarios"):
        return f"<td>{pill('blocked')}</td>"
    row = told or next((r for r in run.get("scenarios", []) if not r.get("id") and r.get("n") == n), None)
    if not row:
        return f"<td>{pill('notrun')}</td>"
    res = row.get("result", "pending")
    note = row.get("claim") or row.get("reason") or ""
    img = thumb(shot_of(row), cache)
    fig = (f'<button class="shot" type="button" data-full="{img}" data-cap="{esc(NAMES.get(p, p))} · {esc(rid)}: {esc(note)}">'
           f'<img src="{img}" alt="{esc(p)} {esc(rid)} screenshot" loading="lazy"></button>') if img else ""
    return f'<td>{pill(res)}<p class="note">{esc(note)}</p>{fig}</td>'


def scenarios_table(rows, platforms, runs, nodes, cache):
    head = "".join(f"<th>{NAMES.get(p, p)}</th>" for p in platforms)
    body = "".join(f'<tr>{row_head(s, i)}{"".join(scenario_cell(p, i, s, runs, nodes, cache) for p in platforms)}</tr>'
                   for i, s in enumerate(rows, 1))
    return f'<table class="scen"><thead><tr><th>Row</th>{head}</tr></thead><tbody>{body}</tbody></table>'


def lane_state(p, nodes, rdir):
    for step in STEPS:
        st = shown(f"{step}:{p}", nodes.get(f"{step}:{p}", {}))
        if st in ("blocked", "fail", "running", "ready", "waiting"):
            return st, f"at {step}"
    if nodes.get(f"ci:{p}", {}).get("status") == "pass":
        pr = load(os.path.join(rdir, f"pr-{p}.json")) or {}
        return "done", f"PR #{pr.get('number')}" if pr.get("number") else "finished"
    done = [s for s in STEPS if nodes.get(f"{s}:{p}", {}).get("status") in ("pass", "skip", "skipped")]
    return "pending", f"after {done[-1]}" if done else "at map"


def summary(platforms, runs, nodes, brief, rdir):
    cards = []
    for p in platforms:
        ids = {s.get("id") for s in brief.get("scenarios", [])}
        res = [s.get("result") for s in (runs.get(p) or {}).get("scenarios", []) if s.get("id") in ids or "n" in s]
        counts = {k: res.count(k) for k in ("pass", "fail", "unverified")}
        total = sum(1 for s in brief.get("scenarios", []) if p not in s.get("na", []))
        lane, where = lane_state(p, nodes, rdir)
        runner = " · you run the app" if user_runs(nodes, p) else ""
        cards.append(
            f'<li><span class="pname">{NAMES.get(p, p)}</span>{pill(lane)}'
            f'<span class="at">{esc(where)}{runner}</span>'
            f'<span class="counts"><b class="c-pass">{counts["pass"]}</b> pass · '
            f'<b class="c-fail">{counts["fail"]}</b> fail · <b class="c-unv">{counts["unverified"]}</b> unverified · '
            f'of {total} applicable</span></li>')
    return f'<ul class="summary">{"".join(cards)}</ul>'


def who_runs(choice, platforms):
    claude = [p for p in platforms if choice.get("who") == "claude" and p in choice.get("platforms", [])]
    names = lambda ps: ", ".join(NAMES.get(p, p) for p in ps)
    parts = []
    if claude:
        parts.append(f"<b>Claude</b> runs {names(claude)} and saves one screenshot per scenario")
    you = [p for p in platforms if p not in claude]
    if you:
        parts.append(f"<b>You</b> run {names(you)}; their PRs list the scenarios as a checklist")
    if not choice:
        return "Who runs the app: not asked yet"
    return "Who runs the app: " + " · ".join(parts)


def prs_table(rdir, platforms):
    rows = []
    for p in platforms:
        pr = load(os.path.join(rdir, f"pr-{p}.json")) or {}
        ci = load(os.path.join(rdir, f"ci-{p}.json")) or {}
        issue = ((load(os.path.join(rdir, "issues.json")) or {}).get("issues") or {}).get(p) or {}
        links = " ".join(f'<a href="{esc(x.get("url"))}">{esc(x.get("repo"))}#{esc(x.get("number"))}</a>'
                         for x in pr.get("prs") or ([pr] if pr.get("url") else []))
        ci_txt = {"green": "CI green", "red": "CI red, back to build", "none": "no CI on this repo"}.get(
            ci.get("result"), esc(ci.get("blocked")) or "waiting")
        issue_txt = f'<a href="{esc(issue.get("url"))}">#{esc(issue.get("number"))}</a>' if issue.get("url") else "none"
        rows.append(f'<tr><th scope="row">{NAMES.get(p, p)}</th><td>{issue_txt}</td><td>{links or esc(pr.get("blocked")) or "not opened yet"}</td>'
                    f"<td>{ci_txt}</td></tr>")
    return f'<table class="lanes"><thead><tr><th>Platform</th><th>Issue</th><th>Pull request</th><th>CI</th></tr></thead><tbody>{"".join(rows)}</tbody></table>'


def main():
    rdir = run_dir(sys.argv[1] if len(sys.argv) > 1 else None)
    state = load(os.path.join(rdir, "run.json"), {})
    brief = load(os.path.join(rdir, "brief.json"), {})
    nodes = state.get("nodes", {})
    every = state.get("platforms") or brief.get("platforms", [])
    out_of_run = [p for p in every if nodes.get(f"build:{p}", {}).get("status") in ("skip", "skipped")]
    platforms = [p for p in every if p not in out_of_run]
    runs = {p: load(os.path.join(rdir, f"run-{p}.json")) for p in platforms}
    reasons = sorted({nodes[f"build:{p}"].get("reason", "") for p in out_of_run} - {""})
    excluded = (f'<p class="foot">Not in this run: {esc(", ".join(NAMES.get(p, p) for p in out_of_run))}'
                f'{" (" + esc("; ".join(reasons)) + ")" if reasons else ""}</p>') if out_of_run else ""
    all_user = bool(platforms) and all(user_runs(nodes, p) for p in platforms)
    scen_hint = ("You walk these yourself: tap Pass, Fail or Skip on each row as you go (your marks stay in this browser), then tell Claude the results. Each PR lists the same rows as a checklist. N/A means the row does not apply to that platform."
                 if all_user else "One screenshot per scenario per platform. Tap a screenshot to enlarge it.")
    regress = regressions(rdir, platforms)
    cache = os.path.join(tempfile.gettempdir(), "fg-matrix-thumbs")
    os.makedirs(cache, exist_ok=True)
    slug = state.get("slug", os.path.basename(rdir))
    title = slug.replace("-", " ").title()
    choice = load(os.path.join(rdir, "run-choice.json"), {}) or {}
    folder = choice.get("evidence_folder", "")
    if not folder and choice.get("who") == "user":
        folder = "none: you run the app, so Claude takes no screenshots"
    with open(os.path.join(os.path.dirname(__file__), "matrix.css")) as f:
        css = f.read()
    page = TEMPLATE.format(
        title=esc(title), css=css, change=esc(brief.get("change")),
        ref=esc(NAMES.get(brief.get("reference_platform"), brief.get("reference_platform") or "none")),
        updated=time.strftime("%Y-%m-%d %H:%M"), trigger=esc(state.get("trigger")),
        summary=summary(platforms, runs, nodes, brief, rdir), scen_hint=esc(scen_hint), excluded=excluded,
        scen=scenarios_table(brief.get("scenarios", []), platforms, runs, nodes, cache),
        regress=scenarios_table(regress, platforms, runs, nodes, cache) if regress else
        '<p class="hint">No regression rows yet: each platform\'s map lists what else uses the code it changes.</p>',
        setup=setup_box(brief), run=esc(slug), tickjs=TICK_JS, steps=steps_section(rdir, state),
        lanes=lanes_table(state, platforms), who=who_runs(choice, platforms),
        prs=prs_table(rdir, platforms), evals=eval_section(rdir, state, pill), tokens=tokens_section(slug),
        folder=esc(folder) or "not created yet")
    problems = page_problems(page, len(brief.get("scenarios", [])) + len(regress))
    out = os.path.join(rdir, "matrix.html")
    with open(out, "w") as f:
        f.write(page)
    if problems:
        sys.exit("matrix.html is broken, do not publish it: " + "; ".join(problems))
    print(out)
    print(decide(rdir, nodes, platforms))


def page_problems(page, rows):
    out = []
    slots = set(re.findall(r"(?<!\{)\{([a-z_]+)\}(?!\})", TEMPLATE))
    if any("{" + s + "}" in page for s in slots):
        out.append("a template slot was left unfilled")
    rendered = page.count('<th scope="row"><span class="n">')
    if rendered < rows:
        out.append(f"expected {rows} test rows, rendered {rendered}")
    script = page.rsplit("<script>", 1)[-1].split("</script>")[0]
    if shutil.which("node"):
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
            f.write(script)
        if subprocess.run(["node", "--check", f.name], capture_output=True).returncode:
            out.append("the page script has a syntax error")
    return out


TEMPLATE = """<title>{title} Matrix</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>{css}</style>
<body data-run="{run}">
<main>
<header>
<p class="eyebrow">Prism · {trigger} · updated {updated}</p>
<h1>{title}</h1>
<p class="change">{change}</p>
<p class="meta">Reference platform: <b>{ref}</b></p>
<p class="meta">{who}</p>
</header>
{steps}
{summary}
{setup}
<section><h2>Scenarios</h2><p class="hint">{scen_hint}</p>
<p class="mine"><span id="mine"></span> <button type="button" id="reset">Clear my marks</button></p>
<div class="scroll">{scen}</div></section>
<section><h2>What this change could break</h2><p class="hint">Regression rows from each platform's map: other code that runs through what this change touched. Each row only applies to its own platform.</p>
<div class="scroll">{regress}</div></section>
<section><h2>Pipeline</h2><p class="hint">Each platform goes through map, build, gate, verify, run, PR and CI. A failed run, PR or red CI sends the platform back to build. Open “Why” for the reason a step is blocked or failed.</p>
<div class="scroll">{lanes}</div></section>
<section><h2>Pull requests</h2><p class="hint">One PR per platform, even when two platforms share a repo. The description has the change, this matrix link, and either the scenario results or a checklist for you to walk.</p>
<div class="scroll">{prs}</div></section>
<section><h2>Eval: who fixed what</h2><p class="hint">Every fix in this run: the ones the graph made on its own after a failed check, and the ones you had to ask for. The target is 100% fixed by the graph and 0 misses.</p>
{evals}</section>
{tokens}
<p class="foot">Evidence folder: <code>{folder}</code></p>
{excluded}
</main>
<dialog id="viewer"><form method="dialog"><button class="close" aria-label="Close">Close</button></form><img id="viewer-img" alt=""><p id="viewer-cap"></p></dialog>
<script>
const v = document.getElementById("viewer");
document.querySelectorAll(".shot").forEach(b => b.addEventListener("click", () => {{
  document.getElementById("viewer-img").src = b.dataset.full;
  document.getElementById("viewer-cap").textContent = b.dataset.cap;
  v.showModal();
}}));
v.addEventListener("click", e => {{ if (e.target === v) v.close(); }});
{tickjs}
</script>
"""

if __name__ == "__main__":
    main()
