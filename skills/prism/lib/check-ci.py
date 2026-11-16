#!/usr/bin/env python3
import json
import re
import subprocess
import sys
import time

import fgstate

WAIT_SECONDS = 1200
POLL_SECONDS = 30


def sh(*cmd):
    proc = subprocess.run(list(cmd), capture_output=True, text=True)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def checks_for(pr):
    code, out, err = sh("gh", "pr", "checks", str(pr["number"]), "--repo", pr["repo"],
                        "--json", "name,bucket,link")
    if "no checks reported" in (out + err):
        return []
    if code and not out:
        return None
    return json.loads(out or "[]")


def failed_log(rdir, platform, pr, check):
    match = re.search(r"/actions/runs/(\d+)", check.get("link", ""))
    if not match:
        return None
    _, out, _ = sh("gh", "run", "view", match.group(1), "--repo", pr["repo"], "--log-failed")
    path = rdir / f"ci-{platform}-{pr['number']}-failed.log"
    path.write_text(out[-20000:])
    return str(path)


def wait_for(pr):
    deadline = time.time() + WAIT_SECONDS
    while True:
        checks = checks_for(pr)
        if checks is None:
            return None
        if not any(c.get("bucket") == "pending" for c in checks) or time.time() > deadline:
            return checks
        time.sleep(POLL_SECONDS)


def main():
    platform = sys.argv[1]
    slug = fgstate.active_slug()
    rdir = fgstate.run_dir(slug)
    from nodestate import mark_started
    mark_started(f"ci:{platform}", slug)
    pr_file = json.loads((rdir / f"pr-{platform}.json").read_text())
    rows, evidence, result = [], [], "none"
    for pr in pr_file.get("prs") or [pr_file]:
        checks = wait_for(pr)
        if checks is None:
            out = {"platform": platform, "blocked": f"gh pr checks failed for {pr['repo']}#{pr['number']}"}
            (rdir / f"ci-{platform}.json").write_text(json.dumps(out, indent=2))
            print(json.dumps({"result": "blocked"}))
            sys.exit(2)
        for c in checks:
            row = {"repo": pr["repo"], "pr": pr["number"], "name": c.get("name"),
                   "bucket": c.get("bucket"), "link": c.get("link")}
            if c.get("bucket") in ("fail", "cancel"):
                log = failed_log(rdir, platform, pr, c)
                row["log"] = log
                evidence.append(f"log: {log}" if log else c.get("link"))
            rows.append(row)
        evidence.append(pr["url"])
    buckets = {r["bucket"] for r in rows}
    if buckets & {"fail", "cancel"}:
        result = "red"
    elif "pending" in buckets:
        out = {"platform": platform, "blocked": f"CI still running after {WAIT_SECONDS // 60} min"}
        (rdir / f"ci-{platform}.json").write_text(json.dumps(out, indent=2))
        print(json.dumps({"result": "blocked"}))
        sys.exit(2)
    elif rows:
        result = "green"
    out = {"platform": platform, "result": result, "checks": rows, "evidence": evidence}
    (rdir / f"ci-{platform}.json").write_text(json.dumps(out, indent=2))
    print(json.dumps({"result": result}))
    sys.exit(1 if result == "red" else 0)


if __name__ == "__main__":
    main()
