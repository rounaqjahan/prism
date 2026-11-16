import html
import json
import os
import project

NAMES = project.names()
SCOPE = {"new": "New", "edge": "Edge", "regress": "Regression"}


def esc(x):
    return html.escape(str(x or ""))


def items(value, tag):
    if isinstance(value, list):
        return f"<{tag}>" + "".join(f"<li>{esc(v)}</li>" for v in value) + f"</{tag}>"
    return f"<p>{esc(value)}</p>"


def row_head(row, n):
    rid = row.get("id") or str(n)
    scope = row.get("scope")
    tag = f'<span class="scope {esc(scope)}">{SCOPE.get(scope, "")}</span>' if scope in SCOPE else ""
    write = (f'<p class="write">⚠ Needs server write: {esc(row["server_write"])}</p>'
             if row.get("server_write") else "")
    need = f'<p class="req">Only counts with: <code>{esc(row["requires"])}</code></p>' if row.get("requires") else ""
    note = f'<p class="rnote"><i>Note:</i> {esc(row["note"])}</p>' if row.get("note") else ""
    covers = f'<p class="covers">covers · {esc(row["covers"])}</p>' if row.get("covers") else ""
    return (f'<th scope="row"><span class="n">{esc(rid)}</span><div class="rbody">{tag}'
            f'<b class="rname">{esc(row.get("name", ""))}</b>{write}{need}'
            f'<div class="do"><b>Do:</b>{items(row.get("do"), "ol")}</div>'
            f'<div class="expect"><b>Expect:</b>{items(row.get("expect"), "ul")}</div>{note}{covers}</div></th>')


def ticks(rid, platform):
    key = esc(f"{rid}|{platform}")
    return ('<div class="tick" data-k="' + key + '">'
            + "".join(f'<button type="button" data-v="{v}">{label}</button>'
                      for v, label in (("pass", "Pass"), ("fail", "Fail"), ("skip", "Skip"))) + "</div>")


def regressions(rdir, platforms):
    rows = []
    for p in platforms:
        try:
            with open(os.path.join(rdir, f"map-{p}.json")) as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        rows += [dict(r, platform=p) for r in data.get("regressions", []) if isinstance(r, dict)]
    return rows


def setup_box(brief):
    setup = brief.get("setup") or []
    if not setup:
        return ""
    return ('<section class="setup"><h2>Before you start</h2><ul>'
            + "".join(f"<li>{esc(s)}</li>" for s in setup) + "</ul></section>")


TICK_JS = """
const KEY = "fg-matrix-" + document.body.dataset.run;
let marks = {};
try { marks = JSON.parse(localStorage.getItem(KEY) || "{}") || {}; } catch (e) { marks = {}; }
function paint() {
  const all = document.querySelectorAll(".tick");
  let c = {pass: 0, fail: 0, skip: 0};
  all.forEach(t => {
    const v = marks[t.dataset.k];
    t.querySelectorAll("button").forEach(b => b.classList.toggle("on", b.dataset.v === v));
    if (v) c[v]++;
  });
  const out = document.getElementById("mine");
  if (out) out.textContent = all.length ? `Your results: ${c.pass} pass · ${c.fail} fail · ${c.skip} skip · ${all.length - c.pass - c.fail - c.skip} to do, of ${all.length}` : "";
}
function save() { try { localStorage.setItem(KEY, JSON.stringify(marks)); } catch (e) {} }
document.querySelectorAll(".tick button").forEach(b => b.addEventListener("click", () => {
  const k = b.parentElement.dataset.k;
  marks[k] = marks[k] === b.dataset.v ? undefined : b.dataset.v;
  save(); paint();
}));
const reset = document.getElementById("reset");
if (reset) reset.addEventListener("click", () => { marks = {}; save(); paint(); });
paint();
"""


def read(path):
    try:
        with open(path) as f:
            return json.load(f) if path.endswith(".json") else f.read().strip()
    except (OSError, ValueError):
        return None


def steps_section(rdir, state):
    runs = os.path.dirname(rdir)
    parent = state.get("parent")
    if parent:
        url = read(os.path.join(runs, parent, "matrix-url.txt"))
        link = f'<a href="{esc(url)}">the feature\'s matrix</a>' if url else "the feature's matrix"
        return f'<p class="meta">Step <b>{esc(state.get("step"))}</b> of {esc(parent)}. All steps: {link}.</p>'
    phases = (read(os.path.join(rdir, "phases.json")) or {}).get("phases", [])
    spec = {p.get("id"): p for p in (read(os.path.join(rdir, "spec.json")) or {}).get("phases", [])}
    if not phases:
        return ""
    rows = ""
    for p in phases:
        url = read(os.path.join(runs, p.get("slug", ""), "matrix-url.txt"))
        link = f'<a href="{esc(url)}">matrix</a>' if url else "not started"
        info = spec.get(p.get("id"), {})
        rows += (f'<tr><th scope="row">{esc(p.get("id"))}</th><td>{esc(p.get("name"))}</td><td>{esc(info.get("goal"))}</td>'
                 f'<td>{esc(info.get("size"))}</td><td>{esc(p.get("status"))}</td><td>{link}</td></tr>')
    return ('<section><h2>Steps</h2><p class="hint">This feature was sliced into steps at the spec. Each step is its own '
            'graph run on the same branch; they run in order.</p><div class="scroll"><table class="lanes"><thead><tr>'
            '<th>Step</th><th>Name</th><th>Goal</th><th>Size</th><th>Status</th><th>Run</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div></section>')
