import json
import shutil
from pathlib import Path

import caps
import fgstate
from scenario_lint import lint_rows


def load(path):
    return json.loads(Path(path).read_text())


def keyed(plan):
    files = {f.get("path") or f.get("file"): f for f in plan.get("files", []) if isinstance(f, dict)}
    rows = {r.get("id"): r for r in plan.get("regressions", []) if isinstance(r, dict)}
    return files, rows


def allowed_hit(key, allowed):
    return any(key == item or str(key).endswith("/" + item) or Path(str(key)).name == item for item in allowed)


def snapshot_map(rdir, platform):
    source = Path(rdir) / f"map-{platform}.json"
    if source.exists():
        shutil.copyfile(source, Path(rdir) / f"approved-map-{platform}.json")


def map_diff_problems(rdir, platform, allowed):
    if not allowed or allowed == ["all"]:
        return []
    before_path = Path(rdir) / f"approved-map-{platform}.json"
    after_path = Path(rdir) / f"map-{platform}.json"
    if not before_path.exists() or not after_path.exists():
        return []
    before_files, before_rows = keyed(load(before_path))
    after_files, after_rows = keyed(load(after_path))
    out = []
    for kind, before, after in (("file", before_files, after_files), ("row", before_rows, after_rows)):
        for key in sorted(set(before) | set(after), key=str):
            if before.get(key) == after.get(key) or allowed_hit(key, allowed):
                continue
            change = "added" if key not in before else "removed" if key not in after else "changed"
            out.append(f"{kind} {key} was {change}, but this retry may only change: {', '.join(allowed)}. "
                       f"Put it back exactly as in {before_path.name}.")
    return out


def rowfix_state(run, platform):
    state = run.get("rowfix", {}).get(platform)
    if not state:
        raise SystemExit(f"no row fix started for {platform}; use 'graph.py rowfix {platform} --rows … --said …'")
    return state


def cmd_rowfix(args, graph):
    slug = args.run or fgstate.active_slug()
    rdir = fgstate.run_dir(slug)
    ids = [i.strip() for i in args.rows.split(",") if i.strip()]
    with fgstate.locked_run(slug) as run:
        if run["nodes"].get(f"map:{args.platform}", {}).get("status") != "pass":
            raise SystemExit(f"map:{args.platform} must have passed before its rows are fixed")
        _, rows = keyed(load(rdir / f"map-{args.platform}.json"))
        unknown = [i for i in ids if i not in rows]
        if unknown or not ids:
            raise SystemExit(f"rows not in map-{args.platform}.json: {', '.join(unknown) or '(none given)'}")
        n = len(list(rdir.glob(f"rowfix-{args.platform}-*-request.json"))) + 1
        caps.rowfix_guard(args.platform, n, args.more)
        request = rdir / f"rowfix-{args.platform}-{n}-request.json"
        out = rdir / f"rowfix-{args.platform}-{n}.json"
        request.write_text(json.dumps({"platform": args.platform, "said": args.said, "rows": [rows[i] for i in ids],
                                       "writes": str(out)}, indent=2))
        run.setdefault("rowfix", {})[args.platform] = {"n": n, "rows": ids, "status": "running",
                                                       "request": str(request), "out": str(out)}
    print(rowfix_prompt(rdir, run, args.platform))


def rowfix_prompt(rdir, run, platform):
    state = rowfix_state(run, platform)
    if state["status"] != "running":
        raise SystemExit(f"rowfix:{platform} is {state['status']}, not running")
    return "\n".join([f"FG_NODE: rowfix:{platform}", f"Run folder: {rdir}",
                      f"Reads: {rdir / 'brief.json'}, {state['request']}",
                      f"Writes: {state['out']}", f"Rows: {', '.join(state['rows'])}"])


def rowfix_problems(rdir, state):
    out_path = Path(state["out"])
    if not out_path.exists():
        return [f"missing {out_path.name}"]
    try:
        rows = load(out_path).get("rows", [])
    except ValueError as error:
        return [f"{out_path.name} is not valid JSON: {error}"]
    got = [r.get("id") for r in rows if isinstance(r, dict)]
    problems = []
    if sorted(got) != sorted(state["rows"]):
        problems.append(f"return exactly the rows {', '.join(state['rows'])}; got {', '.join(map(str, got)) or 'none'}")
    return problems + lint_rows(rows, "row", "regress")


def cmd_rowfix_done(args, graph):
    slug = args.run or fgstate.active_slug()
    rdir = fgstate.run_dir(slug)
    with fgstate.locked_run(slug) as run:
        state = rowfix_state(run, args.platform)
        problems = rowfix_problems(rdir, state)
        if problems:
            raise SystemExit("row fix refused; send `graph.py fix rowfix:%s` to the same agent:\n%s"
                             % (args.platform, "\n".join(problems)))
        map_path = rdir / f"map-{args.platform}.json"
        shutil.copyfile(map_path, rdir / f"before-rowfix{state['n']}-map-{args.platform}.json")
        plan = load(map_path)
        fixed = {r["id"]: r for r in load(state["out"])["rows"]}
        plan["regressions"] = [fixed.get(r.get("id"), r) for r in plan.get("regressions", [])]
        map_path.write_text(json.dumps(plan, indent=2) + "\n")
        state["status"] = "done"
    print(json.dumps({"rowfix": args.platform, "replaced": state["rows"]}))


def rowfix_fix_message(slug, platform):
    rdir = fgstate.run_dir(slug)
    problems = rowfix_problems(rdir, rowfix_state(fgstate.read_run(slug), platform))
    if not problems:
        raise SystemExit(f"rowfix:{platform} output passes; nothing to fix")
    return "\n".join([f"FG_FIX: rowfix:{platform}", *problems,
                      "Fix only these lines in your output file, then stop."])
