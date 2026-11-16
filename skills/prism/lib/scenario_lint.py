import json
import re
from pathlib import Path

SCOPES = {"new", "regress", "edge"}
INLINE_NUMBERING = re.compile(r"(?:^|\s)\d+[.)]\s+\S.*\s\d+[.)]\s")
REQUIRES = re.compile(r"[\w.-]+=\S+(\s+[\w.-]+=\S+)*")
VAGUE = [
    (r"\bworks? (correctly|properly|fine|as expected)\b", "say exactly what you see"),
    (r"\bshould (work|be fine|be ok)\b", "say exactly what you see"),
    (r"\bwait (until|for) (it|the app|the screen|everything)?\s*(is |to be )?(idle|ready|settled|stable|loaded|done)\b",
     "end every wait on something visible"),
    (r"\bas usual\b|\bthe usual\b|\bnormal flow\b", "write the steps out"),
    (r"\b(do|perform) an? (return|reset|seed|round trip|login flow|refresh)\b", "write the full action, not a name for it"),
    (r"\b(then )?restore (the )?(original|previous|old)\b", "never change, then restore"),
    (r"\breset to defaults?\b", "never reset to defaults"),
    (r"\betc\.?|\band so on\b", "list every item"),
]


def row_problems(row, label, scope=None):
    if not isinstance(row, dict):
        return [f"{label}: must be an object"]
    rid = row.get("id") or label
    out = [] if row.get("id") else [f"{label}: needs a short stable 'id' (e.g. S1, R-ios-1)"]
    if not str(row.get("name", "")).strip():
        out.append(f"{rid}: needs a short 'name' that says what the row proves")
    if row.get("scope") not in SCOPES or (scope and row.get("scope") != scope):
        out.append(f"{rid}: 'scope' must be {scope or 'new, regress or edge'}")
    for key, unit in (("do", "action"), ("expect", "check")):
        items = row.get(key)
        if not isinstance(items, list) or not items or not all(isinstance(x, str) and x.strip() for x in items):
            out.append(f"{rid}: '{key}' must be a non-empty list, one {unit} per item")
            continue
        for text in items:
            if INLINE_NUMBERING.search(text):
                out.append(f'{rid}: "{text[:50]}" numbers steps inline; give each step its own item')
            for pattern, why in VAGUE:
                if re.search(pattern, text, re.I):
                    out.append(f'{rid}: "{text[:50]}" is vague: {why}')
    if not str(row.get("covers", "")).strip():
        out.append(f"{rid}: needs 'covers': the code path or behaviour this row exercises")
    if row.get("requires") and not REQUIRES.fullmatch(str(row["requires"]).strip()):
        out.append(f"{rid}: 'requires' must be key=value pairs, e.g. 'flag=off role=admin'")
    if "server_write" in row and not str(row.get("server_write") or "").strip():
        out.append(f"{rid}: 'server_write' must name the resource and endpoint it changes")
    return out


def lint_rows(rows, label, scope=None):
    out, seen = [], set()
    for i, row in enumerate(rows or [], 1):
        out += row_problems(row, f"{label} {i}", scope)
        rid = row.get("id") if isinstance(row, dict) else None
        if rid in seen:
            out.append(f"{rid}: id is used twice")
        seen.add(rid)
    return out


def all_row_ids(rdir):
    brief = json.loads((Path(rdir) / "brief.json").read_text()) if (Path(rdir) / "brief.json").exists() else {}
    ids = [s.get("id") for s in brief.get("scenarios", []) if isinstance(s, dict)]
    for path in sorted(Path(rdir).glob("map-*.json")):
        try:
            ids += [r.get("id") for r in json.loads(path.read_text()).get("regressions", []) if isinstance(r, dict)]
        except ValueError:
            continue
    return [i for i in ids if i]


def row_texts(rdir):
    brief = json.loads((Path(rdir) / "brief.json").read_text()) if (Path(rdir) / "brief.json").exists() else {}
    setup = json.dumps(brief.get("setup", []), sort_keys=True)
    rows = [s for s in brief.get("scenarios", []) if isinstance(s, dict)]
    for path in sorted(Path(rdir).glob("map-*.json")):
        try:
            rows += [r for r in json.loads(path.read_text()).get("regressions", []) if isinstance(r, dict)]
        except ValueError:
            continue
    return {r["id"]: json.dumps(r, sort_keys=True) + setup for r in rows if r.get("id")}


def unchanged_clean_rows(rdir):
    snap_path = Path(rdir) / "coldread-rows-read.json"
    if not snap_path.exists():
        return []
    snap = json.loads(snap_path.read_text())
    clean = set(snap.get("clean", []))
    return [rid for rid, text in row_texts(rdir).items() if rid in clean and snap.get("texts", {}).get(rid) == text]


def coldread_problems(data, rdir):
    rows = {r.get("id"): r for r in data.get("rows", []) if isinstance(r, dict)}
    out = [f"row {rid} was not read back" for rid in all_row_ids(rdir) if rid not in rows]
    for rid, row in rows.items():
        if not row.get("restated_do") or not row.get("restated_expect"):
            out.append(f"{rid}: restate both the steps and the pass condition")
        if not isinstance(row.get("guesses"), list):
            out.append(f"{rid}: 'guesses' must be a list ([] when nothing was guessed)")
    return out


def coldread_guesses(data):
    return [f"{r.get('id')}: {'; '.join(map(str, r['guesses']))}" for r in data.get("rows", [])
            if isinstance(r, dict) and r.get("guesses")]


def phases_problems(data, rdir):
    phases = data.get("phases") or []
    brief_path = Path(rdir) / "brief.json"
    brief = json.loads(brief_path.read_text()) if brief_path.exists() else {}
    out, seen, rows = [], set(), []
    for i, phase in enumerate(phases, 1):
        if not isinstance(phase, dict):
            out.append(f"phase {i}: must be an object")
            continue
        pid = phase.get("id") or f"phase {i}"
        for key in ("id", "name", "goal"):
            if not str(phase.get(key, "")).strip():
                out.append(f"{pid}: needs '{key}'")
        if not isinstance(phase.get("rows"), list) or not phase["rows"]:
            out.append(f"{pid}: 'rows' must list the brief row ids this step is tested by")
        if not isinstance(phase.get("covers"), list) or not phase["covers"]:
            out.append(f"{pid}: 'covers' must list the spec behaviours this step delivers")
        if len(phases) > 1 and not str(phase.get("size", "")).strip():
            out.append(f"{pid}: 'size' must give the counts that decided the split (see slice-feature)")
        if pid in seen:
            out.append(f"{pid}: id is used twice")
        seen.add(pid)
        rows += [r for r in phase.get("rows") or [] if isinstance(r, str)]
    if brief.get("step") and len(phases) != 1:
        out.append("this run builds one step of a sliced feature: 'phases' must hold only that step")
    brief_ids = [s.get("id") for s in brief.get("scenarios", []) if isinstance(s, dict) and s.get("id")]
    out += [f"brief row {r} is in no step" for r in brief_ids if r not in rows]
    out += [f"row {r} is in more than one step" for r in sorted({r for r in rows if rows.count(r) > 1})]
    out += [f"row {r} is not a brief row" for r in sorted(set(rows) - set(brief_ids)) if brief_ids]
    return out


def issues_problems(data, rdir):
    out = []
    for platform, issue in (data.get("issues") or {}).items():
        if not isinstance(issue, dict) or not isinstance(issue.get("number"), int) or not str(issue.get("url", "")).startswith("https://"):
            out.append(f"{platform}: needs 'number' (int) and 'url'")
    return out
