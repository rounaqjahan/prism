#!/usr/bin/env python3
import argparse
import json
import shutil
import sys
from pathlib import Path

import caps
import fgstate
import graph_core as core
import scoped
from base_check import require_base
from check_handoff import check
from scenario_lint import coldread_guesses, row_texts, unchanged_clean_rows
import project


def checked_platforms(platforms):
    return list(platforms) + ([project.SHARED] if set(project.shared_users()) & set(platforms) else [])


def slug_from(args):
    slug = args.run or fgstate.active_slug()
    if not slug:
        raise SystemExit("no active run; start one with: graph.py init <slug> <trigger>")
    return slug


def cmd_init(args, graph):
    platforms = args.platforms.split(",") if args.platforms else graph["platforms"]
    unknown = set(platforms) - set(graph["platforms"])
    if unknown:
        raise SystemExit(f"unknown platforms: {', '.join(sorted(unknown))}")
    rdir = fgstate.run_dir(args.slug)
    if (rdir / "run.json").exists() and not args.force:
        raise SystemExit(f"run '{args.slug}' exists; use 'graph.py resume' or --force")
    bases = dict(b.split("=", 1) for b in (args.branch or []))
    require_base(checked_platforms(platforms), args.parent or args.slug, "init", bases)
    rdir.mkdir(parents=True, exist_ok=True)
    run = core.new_run(graph, args.slug, args.trigger, platforms)
    run["project"] = project.norm(project.config_path())
    if bases:
        run["bases"] = bases
    if args.parent:
        if not (fgstate.run_dir(args.parent) / "run.json").exists():
            raise SystemExit(f"parent run '{args.parent}' doesn't exist")
        run["parent"], run["step"] = args.parent, args.step
    fgstate.write_run(args.slug, run)
    fgstate.set_active(args.slug)
    print(json.dumps({"run": args.slug, "dir": str(rdir), "platforms": platforms}))


def cmd_next(args, graph, resume=False):
    slug = slug_from(args)
    rdir = fgstate.run_dir(slug)
    with fgstate.locked_run(slug) as run:
        if resume:
            require_base(checked_platforms(run["platforms"]), slug, "resume", run.get("bases"))
            for instance, state in run["nodes"].items():
                if state["status"] == "running":
                    state["status"] = "pending"
                    core.log(run, instance, "resumed")
        ready = core.settle(graph, run)
        items = []
        for instance in ready:
            run["nodes"][instance]["status"] = "running"
            run["nodes"][instance].pop("started", None)
            run["nodes"][instance].pop("fix_sent", None)
            run["nodes"][instance]["attempts"] += 1
            core.log(run, instance, "start")
            items.append(core.describe(graph, run, instance, rdir))
        running = [i for i, s in run["nodes"].items() if s["status"] == "running" and i not in ready]
        out = {"run": slug, "dir": str(rdir), "start": items, "still_running": running}
        if not items and not running:
            out["finished"] = core.finished(run, graph)
            if not out["finished"]:
                out["stuck"] = [i for i, s in run["nodes"].items() if s["status"] == "pending"]
    print(json.dumps(out, indent=2))


def cmd_done(args, graph):
    slug = slug_from(args)
    rdir = fgstate.run_dir(slug)
    with fgstate.locked_run(slug) as run:
        if args.node not in run["nodes"]:
            raise SystemExit(f"unknown node '{args.node}'")
        state = run["nodes"][args.node]
        if state["status"] != "running":
            raise SystemExit(f"{args.node} is {state['status']}, not running")
        item = core.describe(graph, run, args.node, rdir)
        if args.node == "coldread" and Path(item["writes"][0]).exists():
            read = json.loads(open(item["writes"][0]).read())
            clean = [r.get("id") for r in read.get("rows", []) if isinstance(r, dict) and not r.get("guesses")]
            (rdir / "coldread-rows-read.json").write_text(json.dumps({"texts": row_texts(rdir), "clean": clean}))
        outcome = args.result
        if args.result == "pass":
            if args.node == "brief":
                require_base(checked_platforms(run["platforms"]), slug, "brief pass", run.get("bases"))
            problems = [f"missing {w}" for w in core.missing_writes(item)]
            for path in item["writes"]:
                if path not in core.missing_writes(item):
                    problems += check(path, rdir)
            if args.node.startswith("map:"):
                problems += scoped.map_diff_problems(rdir, args.node.split(":")[1], state.get("allowed"))
            if problems:
                print("\n".join(problems), file=sys.stderr)
                raise SystemExit(f"{args.node} can't pass: fix the handoff first")
            said_blocked = [p for p in item["writes"] if json.loads(open(p).read()).get("blocked")]
            if said_blocked and not (args.user_override and args.node.startswith("gate:")):
                raise SystemExit(f"{said_blocked[0]} says blocked: use 'done {args.node} blocked --reason …'")
            if said_blocked:
                state["user_override"] = {"said": args.user_override, "blocked": json.loads(open(said_blocked[0]).read())["blocked"]}
            guesses = coldread_guesses(json.loads(open(item["writes"][0]).read())) if args.node == "coldread" else []
            if guesses and args.user_override:
                state["user_override"] = {"said": args.user_override, "guesses": guesses}
                core.log(run, args.node, "user_override", args.user_override)
            elif guesses:
                print("\n".join(guesses), file=sys.stderr)
                raise SystemExit("coldread can't pass: rewrite these rows (brief rows yourself, map rows with "
                                 "'redo map:<p>'), mark coldread blocked, then 'reopen coldread' for a fresh read")
            core.set_flags(graph, run, args.node, args.flag or [])
            state["status"] = "pass"
            state.pop("allowed", None)
            core.log(run, args.node, "pass")
        elif args.result == "fail":
            number = run["retries"].get(core.split(args.node)[1], 0) + 1
            kept = []
            for path in item["writes"]:
                if Path(path).exists():
                    copy = Path(path).with_name(f"{Path(path).stem}-retry{number}.json")
                    shutil.copyfile(path, copy)
                    kept.append(str(copy))
            outcome = core.fail(graph, run, args.node, kept or item["writes"])
        elif args.result == "skip":
            if ":" not in args.node:
                raise SystemExit("only a platform lane can be skipped")
            state["status"], state["reason"] = "skipped", args.reason or "no change needed"
            core.log(run, args.node, "skipped", state["reason"])
        else:
            if not args.reason:
                raise SystemExit("blocked needs --reason")
            core.block(run, args.node, args.reason)
        core.settle(graph, run)
        if core.finished(run, graph):
            fgstate.set_active(None)
    print(json.dumps({"node": args.node, "outcome": outcome, "status": run["nodes"][args.node]["status"],
                      "retries": run["retries"]}))


def node_prompt(graph, slug, node):
    rdir = fgstate.run_dir(slug)
    run = fgstate.read_run(slug)
    if node.startswith("rowfix:"):
        return scoped.rowfix_prompt(rdir, run, node.split(":", 1)[1])
    if run["nodes"].get(node, {}).get("status") != "running":
        raise SystemExit(f"{node} is not running; only a node handed out by 'next' gets a prompt")
    item = core.describe(graph, run, node, rdir)
    lines = [f"FG_NODE: {node}", f"Run folder: {rdir}",
             f"Project: {project.norm(project.prism_dir())} (prism.json, folder-map.md, feature-flags.md, feature-parity.md, manual-run.md)",
             f"Reads: {', '.join(item['reads']) or 'none'}",
             f"Writes: {', '.join(item['writes']) or 'none'}",
             f"Attempt: {item['attempt']}"]
    platform = node.partition(":")[2] or (project.SHARED if node == project.SHARED else "")
    repos = project.repos()
    if platform in repos:
        docs = [d for r in repos[platform] for d in r.get("rules", [])]
        lines.append(f"Rules: {', '.join(dict.fromkeys(docs))}")
    if node.startswith("run:"):
        title = slug.replace("-", " ").title()
        lines.append(f"Screenshots: {project.screenshots_folder(title)}")
    if node.split(":")[0] in ("spec", "map", "build", "verify", "run"):
        lines.append(f"Progress: {rdir / 'progress.md'}")
        lines.append(f"Branch: feature/{fgstate.branch_slug(slug)}")
    if item.get("last_failure"):
        lines.append(f"last_failure: {', '.join(item['last_failure'])}")
    if node == "coldread" and unchanged_clean_rows(rdir):
        lines.append(f"Unchanged clean rows (copy their entries from the earlier coldread.json, don't re-read): "
                     f"{', '.join(unchanged_clean_rows(rdir))}")
    return "\n".join(lines)


def fix_message(graph, slug, node):
    if node.startswith("rowfix:"):
        return scoped.rowfix_fix_message(slug, node.split(":", 1)[1])
    rdir = fgstate.run_dir(slug)
    run = fgstate.read_run(slug)
    item = core.describe(graph, run, node, rdir)
    missing = core.missing_writes(item)
    problems = [f"missing {m}" for m in missing]
    for path in item["writes"]:
        if path not in missing:
            problems += check(path, rdir)
    if node.startswith("map:"):
        problems += scoped.map_diff_problems(rdir, node.split(":")[1], run["nodes"][node].get("allowed"))
    if not problems:
        raise SystemExit(f"{node}: handoff passes; nothing to fix")
    return "\n".join([f"FG_FIX: {node}", *problems,
                      "Fix only these lines in your handoff, then re-run check_handoff.py until it prints ok."])


def cmd_prompt(args, graph):
    print(node_prompt(graph, slug_from(args), args.node))


def cmd_fix(args, graph):
    caps.fix_guard(slug_from(args), args.node)
    print(fix_message(graph, slug_from(args), args.node))


def cmd_reopen(args, graph):
    slug = slug_from(args)
    with fgstate.locked_run(slug) as run:
        state = run["nodes"].get(args.node)
        if not state or state["status"] != "blocked":
            raise SystemExit(f"{args.node} is not blocked")
        caps.reopen_guard(args.node, state, args.said)
        if args.said:
            core.log(run, args.node, "user_said", args.said)
        reopened = core.reopen(run, args.node)
        fgstate.set_active(slug)
    print(json.dumps({"reopened": reopened}))


def cmd_redo(args, graph):
    slug = slug_from(args)
    rdir = fgstate.run_dir(slug)
    with fgstate.locked_run(slug) as run:
        if run["nodes"].get(args.node, {}).get("status") not in ("pass", "running", "pending"):
            raise SystemExit(f"{args.node} can't be redone from {run['nodes'].get(args.node, {}).get('status')}")
        count = sum(1 for p in rdir.glob(f"user-feedback-{args.node.replace(':', '-')}-*.json")) + 1
        path = rdir / f"user-feedback-{args.node.replace(':', '-')}-{count}.json"
        caps.redo_guard(args.node, count, args.more)
        items = [i.strip() for i in (args.items or "").split(",") if i.strip()]
        if args.node.startswith("map:"):
            if not items:
                raise SystemExit("redo map:<p> needs --items: the row ids or file names the retry may change, "
                                 "or 'all' when the user changed the whole plan")
            scoped.snapshot_map(rdir, args.node.split(":")[1])
            run["nodes"][args.node]["allowed"] = items
        path.write_text(json.dumps({"from": "user", "node": args.node, "said": args.said, "items": items, "more": args.more}, indent=2))
        reopened = core.redo(graph, run, args.node, str(path))
        fgstate.set_active(slug)
        cold = run["nodes"].get("coldread", {})
        if "coldread" in reopened and cold.get("attempts", 0) >= 3:
            cold["status"], cold["reason"] = "blocked", ("3 cold-read rounds used: ask the user to skip or run one "
                                                         "more round (reopen coldread --said …)")
    print(json.dumps({"redo": args.node, "feedback": str(path), "back_to_pending": reopened}))


def cmd_status(args, graph):
    slug = slug_from(args)
    run = fgstate.read_run(slug)
    print(f"run {slug} · {run['trigger']} · flags {run['flags']} · retries {run['retries']}")
    for instance, state in run["nodes"].items():
        reason = f"  {state['reason']}" if state.get("reason") else ""
        print(f"  {instance:<16} {state['status']:<8} tries {state['attempts']}{reason}")


def main():
    parser = argparse.ArgumentParser(prog="graph.py")
    parser.add_argument("--run")
    sub = parser.add_subparsers(dest="cmd", required=True)
    init = sub.add_parser("init")
    init.add_argument("slug")
    init.add_argument("trigger", choices=["app-sync", "create-feature"])
    init.add_argument("--platforms")
    init.add_argument("--force", action="store_true")
    init.add_argument("--branch", action="append", help="platform=branch, only when the user names a branch for a platform")
    init.add_argument("--parent", help="the sliced feature's run; this run builds one of its steps")
    init.add_argument("--step", help="the step id from the parent's spec phases, e.g. P2")
    for name in ("next", "resume", "status"):
        sub.add_parser(name)
    reopen = sub.add_parser("reopen")
    reopen.add_argument("node")
    reopen.add_argument("--said", help="the user's words; required after 3 rounds or when retries ran out")
    sub.add_parser("prompt").add_argument("node")
    sub.add_parser("fix").add_argument("node")
    redo = sub.add_parser("redo")
    redo.add_argument("node")
    redo.add_argument("--said", required=True)
    redo.add_argument("--more", help="the user's words allowing a 4th or later redo")
    redo.add_argument("--items", help="map redo: comma list of row ids / file names the retry may change, or 'all'")
    rowfix = sub.add_parser("rowfix")
    rowfix.add_argument("platform")
    rowfix.add_argument("--rows", required=True)
    rowfix.add_argument("--said", required=True)
    rowfix.add_argument("--more", help="the user's words allowing a 4th or later round")
    sub.add_parser("rowfix-done").add_argument("platform")
    done = sub.add_parser("done")
    done.add_argument("node")
    done.add_argument("result", choices=["pass", "fail", "blocked", "skip"])
    done.add_argument("--reason")
    done.add_argument("--flag", action="append")
    done.add_argument("--user-override", help="the user's own words accepting coldread guesses, or a gate blocked by a failure that was there before the change")
    args = parser.parse_args()
    graph = fgstate.load_graph()
    commands = {"init": cmd_init, "next": cmd_next, "resume": lambda a, g: cmd_next(a, g, resume=True),
                "done": cmd_done, "reopen": cmd_reopen, "prompt": cmd_prompt, "fix": cmd_fix, "redo": cmd_redo,
                "rowfix": scoped.cmd_rowfix, "rowfix-done": scoped.cmd_rowfix_done}
    commands.get(args.cmd, cmd_status)(args, graph)

if __name__ == "__main__":
    main()
