import html

import tokens

def section(slug):
    rows, total, runs = [], 0, 0
    for run in tokens.feature_runs(slug):
        entries = tokens.load(run)["entries"]
        count = sum(e["tokens"] for e in entries)
        total += count
        runs += sum(1 for e in entries if e["tokens"] and e.get("note") != "fix message")
        steps = {}
        for e in entries:
            steps[e["node"].split(":")[0]] = steps.get(e["node"].split(":")[0], 0) + e["tokens"]
        detail = " · ".join(f"{k} {v:,}" for k, v in steps.items() if v)
        rows.append(f"<tr><td>{html.escape(run)}</td><td>{count:,}</td><td>{html.escape(detail)}</td></tr>")
    rows.append(f"<tr><td><b>Whole feature</b></td><td><b>{total:,}</b></td><td>{runs} agent runs · average "
                f"{total // max(runs, 1):,} tokens per run</td></tr>")
    return ("<section><h2>Tokens</h2><p class=\"hint\">Tokens used by the graph's agents, from each agent's "
            "finish notice. The coordinator's own tokens are not included.</p>"
            "<div class=\"scroll\"><table><thead><tr><th>Run</th><th>Tokens</th><th>By step</th>"
            "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div></section>")
