#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path

import fgstate
from scenario_lint import coldread_problems, issues_problems, lint_rows, phases_problems
import project

URL = re.compile(r"https?://[^\s\"'<>)]+")
FILE_LINE = re.compile(r"^(/[^:]+):(\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*)$")
PREFIXED = re.compile(r"^(log|screenshot):\s*(/\S+)$")
TYPES = {"str": str, "list": list, "dict": dict, "bool": bool, "int": int}


def schema_for(path):
    name = Path(path).stem.split("-")[0]
    schema = fgstate.SKILL_DIR / "schemas" / f"{name}.json"
    if not schema.exists():
        return None
    data = json.loads(schema.read_text(encoding="utf-8"))
    if name == "brief":
        data.setdefault("enums", {})["kind"] = project.kinds()
    return data


def type_ok(value, spec):
    for option in spec.split("|"):
        if option == "null" and value is None:
            return True
        if option == "list+" and isinstance(value, list) and value:
            return True
        kind = TYPES.get(option)
        if not kind or not isinstance(value, kind) or (kind is int and isinstance(value, bool)):
            continue
        return option != "str" or bool(value.strip())
    return False


def evidence_problem(ref):
    if not isinstance(ref, str) or not ref.strip():
        return "empty evidence"
    ref = ref.strip()
    if URL.fullmatch(ref) or (ref.startswith("cmd:") and ref[4:].strip()):
        return None
    prefixed = PREFIXED.match(ref)
    if prefixed:
        return None if Path(prefixed.group(2)).exists() else f"evidence file not found: {ref}"
    match = FILE_LINE.match(ref)
    if not match:
        return f"evidence '{ref}' is not /abs/file:line, a URL, 'cmd: …', or 'log:|screenshot: /abs/path'"
    file = Path(match.group(1))
    if not file.is_file():
        return f"evidence file not found: {file}"
    numbers = [int(n) for n in re.findall(r"\d+", match.group(2))]
    lines = sum(1 for _ in file.open(errors="ignore"))
    if min(numbers) < 1 or max(numbers) > lines:
        return f"evidence line {max(numbers)} is past the end of {file} ({lines} lines)"
    return None


def evidence_list(value):
    refs = value if isinstance(value, list) else [value]
    if not refs:
        return ["no evidence"]
    return [p for p in (evidence_problem(r) for r in refs) if p]


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from strings(child)


def check_evidence(data, rdir):
    out = []
    for item in walk(data):
        if "claim" in item:
            out += [f"claim '{item['claim']}': {p}" for p in evidence_list(item.get("evidence"))]
    return out


def check_apis(data, rdir):
    out = []
    for api in data.get("apis", []):
        name = api.get("name", "?")
        if api.get("status") not in ("exists", "gap"):
            out.append(f"api '{name}': status must be 'exists' or 'gap', never guessed")
        elif api["status"] == "exists":
            out += [f"api '{name}': {p}" for p in evidence_list(api.get("evidence"))]
    return out


def normalise(url):
    return url.split("#")[0].rstrip("/.,;")


def check_urls(data, rdir):
    log = rdir / "fetch-log.txt"
    fetched = {normalise(u) for u in log.read_text().split()} if log.exists() else set()
    cited = {normalise(u) for s in strings(data) for u in URL.findall(s)}
    return [f"url never fetched in this run: {u}" for u in sorted(cited - fetched)]


def check_scenarios(data, rdir):
    return lint_rows(data.get("scenarios"), "scenario")


def check_regressions(data, rdir):
    rows = data.get("regressions")
    if data.get("change") == "change" and not rows and not any(
            "none exists" in str(c.get("claim", "")).lower() and "regression" in str(c.get("claim", "")).lower()
            for c in data.get("claims", [])):
        return ["'regressions' is empty: list what else uses the changed code, or add a claim "
                "'no regression risk: none exists' backed by the 'cmd: …' search"]
    out = lint_rows(rows, "regression", scope="regress")
    for row in rows or []:
        if isinstance(row, dict) and row.get("covers"):
            problem = evidence_problem(str(row["covers"]).split(" ")[0])
            if problem:
                out.append(f"{row.get('id')}: covers must start with the caller's /abs/file:line ({problem})")
    return out


def check_files(data, rdir):
    out = []
    for i, f in enumerate(data.get("files", [])):
        if not (isinstance(f, dict) and f.get("path") and f.get("action") in ("add", "change") and f.get("layer")):
            out.append(f"file entry {i + 1} needs 'path', 'action' (add|change) and 'layer'")
            continue
        path = Path(f["path"])
        if not path.is_absolute():
            out.append(f"{f['path']}: paths must be absolute")
        elif f["action"] == "change" and not path.is_file():
            out.append(f"{path}: marked 'change' but the file doesn't exist")
        elif f["action"] == "add" and path.exists():
            out.append(f"{path}: marked 'add' but it already exists")
        elif f["action"] == "add":
            problem = new_file_problem(path)
            if problem:
                out.append(f"{path}: {problem}")
    return out


def repo_roots():
    repos = project.repos()
    return [Path(r["path"]) for rs in repos.values() for r in rs]


def new_file_problem(path, max_new_folders=3):
    existing, new_folders = path.parent, 0
    while not existing.is_dir():
        existing, new_folders = existing.parent, new_folders + 1
    if new_folders > max_new_folders:
        return f"marked 'add' but {new_folders} new folders would be created; check folder-map.md"
    if not any(existing == root or root in existing.parents for root in repo_roots()):
        return "marked 'add' outside every repo in .prism/prism.json"
    return None


def check_verdict(data, rdir):
    out = []
    for i, c in enumerate(data.get("checks", [])):
        label = c.get("rule") or f"check {i + 1}"
        if not c.get("rule"):
            out.append(f"check {i + 1}: needs the rule ID it grades")
        if c.get("result") not in ("pass", "fail", "unverified"):
            out.append(f"{label}: result must be pass, fail or unverified")
        if c.get("result") != "unverified":
            out += [f"{label}: {p}" for p in evidence_list(c.get("evidence"))]
    results = {c.get("result") for c in data.get("checks", [])}
    if data.get("result") == "pass" and results & {"fail", "unverified"}:
        out.append("overall result is pass but a check is fail or unverified")
    return out


def check_reuses(data, rdir):
    adds = [f for f in data.get("files", []) if isinstance(f, dict) and f.get("action") == "add"]
    if not adds:
        return []
    reuses = data.get("reuses")
    none_found = [c for c in data.get("claims", []) if "none exists" in str(c.get("claim", "")).lower()
                  and str(c.get("evidence", "")).startswith("cmd:")]
    if not reuses and not none_found:
        return ["map adds files but lists no 'reuses' (existing call sites found by searching the repo), "
                "and no claim 'none exists' backed by the 'cmd: …' search used"]
    out = []
    new_paths = {f.get("path") for f in adds}
    for i, r in enumerate(reuses or []):
        what = r.get("what") if isinstance(r, dict) else None
        call = r.get("existing_call") if isinstance(r, dict) else None
        if not what or not call:
            out.append(f"reuses[{i}] needs 'what' and 'existing_call'")
            continue
        problem = evidence_problem(call)
        if problem:
            out.append(f"reuses '{what}': {problem}")
        elif call.split(":")[0] in new_paths:
            out.append(f"reuses '{what}': existing_call points at a file this map adds")
    return out


CHECKS = {
    "reuses": check_reuses,
    "evidence": check_evidence,
    "apis": check_apis,
    "urls_fetched": check_urls,
    "scenarios": check_scenarios,
    "regressions": check_regressions,
    "coldread": coldread_problems,
    "phases": phases_problems,
    "issues": issues_problems,
    "files": check_files,
    "verdict": check_verdict,
}


def check(path, rdir=None):
    path = Path(path)
    rdir = Path(rdir) if rdir else path.parent
    schema = schema_for(path)
    if schema is None:
        return [f"{path.name}: no schema for this handoff"]
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        return [f"{path.name}: not valid JSON ({error})"]
    if not isinstance(data, dict):
        return [f"{path.name}: top level must be an object"]
    if isinstance(data.get("blocked"), str) and data["blocked"].strip():
        return []
    out = []
    for field, spec in schema.get("fields", {}).items():
        if field not in data:
            out.append(f"missing field '{field}'")
        elif not type_ok(data[field], spec):
            out.append(f"field '{field}' must be {spec}")
    for field, allowed in schema.get("enums", {}).items():
        if field in data and data[field] not in allowed:
            out.append(f"field '{field}' must be one of {allowed}")
    for name in schema.get("checks", []):
        out += CHECKS[name](data, rdir)
    return [f"{path.name}: {p}" for p in out]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: check_handoff.py <handoff.json> [run-dir]")
    problems = check(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    print("\n".join(problems) or "ok")
    sys.exit(1 if problems else 0)
