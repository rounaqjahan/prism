# Run state: progress page, eval, progress.md, handoffs

Part of Prism (`~/.claude/skills/prism/SKILL.md`). Read when this step comes up.

**Matrix.** After every `done`, `reopen` or `resume`, run `python3 ~/.claude/skills/prism/lib/matrix.py`. It rewrites `<run>/matrix.html` every time and prints `publish: yes (…)` only at a milestone (`lib/publish_gate.py`); publish with the Artifact tool only then. Always publish the same path, so the link never changes. Give the user the link the first time. **Eval:** whenever the user asks for a change after the graph produced work, append `{"said": "<their words>", "why": "<cause>", "category": "miss|bug|new", "fixed_by": "<rule, script or redo>"}` to `<run>/eval.json` (`miss` = a skill, an instruction or the reference already said otherwise; `bug` = the graph's own script or process was wrong; `new` = not stated before), then re-render. The matrix eval (`lib/matrix_eval.py`) shows **who fixed what**: fixes the graph made on its own (every `fail` → retry → later `pass`, read from `run.json`, with the failing handoff kept as `<handoff>-retry<n>.json` by `graph.py done … fail`) against fixes the user had to ask for (`miss` + `bug` in `eval.json`), as percentages, plus the miss percentage. The target is 100% fixed by the graph and 0 misses. **Every `miss` and `bug` must become a rule before the run ends**: add it to the shared skill (a script check in `lib/` or `contract/standing-rules.json` when a regex or file list can catch it; otherwise a line in the step's file in `steps/`, the `fg-*` agent that made the mistake, or SKILL.md only for the walk and R1–R8) and name that file in `fixed_by`. Never put it only in memory or only in the run folder: the run folder belongs to one run, and the skill is what every later run loads. The page shows each platform's scenarios as pass, fail or unverified, with screenshot thumbnails, plus the map→run pipeline status with blocked reasons. The report node links it.

## progress.md
`<run>/progress.md` is the run's one-page memory, rewritten by `lib/progress.py` every time `run.json` is written (so it can't go stale). It holds the shared steps, each platform's current step, **the user's decisions in their own words**, the approved files, what every redo was sent back for, what is running or blocked, and the clean test rows.
- The `spec`, `map`, `build`, `verify` and `run` prompts name it (`Progress:`). On a retry a mapper or builder changes **only what `last_failure` names** and keeps everything else as approved, instead of re-planning from scratch.
- Decisions are binding for every agent and never widened (a redo message carries the user's words, nothing added).
- **The cold-reader never reads it.** `hooks/cold-reader-reads.py` lets that node open only `brief.json`, `map-*.json` and its own `coldread.json`.
- To start a new session on a run, read `progress.md` first.

## Handoffs
They live in `~/.claude/prism/runs/<slug>/`, shaped by `schemas/<name>.json` and checked by `lib/check_handoff.py`:
- every `claim` carries `evidence`: `/abs/file:line`, a URL, `cmd: …`, or `log:|screenshot: /abs/path`. File and line must exist;
- every API is `exists` (with evidence) or `gap`. Never invented;
- every URL cited was fetched in this run (`fetch-log.txt`);
- every verdict check names its rule and carries evidence.

## Caps: nothing repeats more than 3 times on its own
`lib/caps.py` counts every path that can repeat. After 3, the script refuses and the next round needs the user's own words. Never invent those words: stop, ask the user one plain question, and pass what they said.
| Path | After 3 | To go on |
|---|---|---|
| build retries per platform (gate, verify, run, pr, ci share one count) | lane `blocked` | `reopen <node> --said "<their words>"` gives one more try |
| cold-read rounds | `reopen coldread` refused | `--said`, or `done coldread pass --user-override` |
| fix messages to one agent (`graph.py fix`, counted when sent) | `fix` and the hook refuse a 4th | mark the node `blocked`, tell the user |
| `reopen` of the same blocked node | refused | `reopen <node> --said "<their words>"` |
| `redo` of the same node | refused | `redo … --more "<their words>"` |
| row fixer rounds per platform | refused | `rowfix … --more "<their words>"` |

## Tokens
Every time a node agent finishes, record the `subagent_tokens` from its finish notice: `python3 lib/tokens.py add <node> <tokens>` (it writes `<run>/tokens.json`; add `model` when the agent ran on another model than Fable 5.2, e.g. `"model": "opus-5-5"`; a resumed agent's later notice is added as another entry). `python3 lib/tokens.py [slug]` prints the total per step and for the whole feature (the parent run plus every step run). The progress page shows the totals (`lib/tokens_page.py`), and the report gives that total, and separately says that the coordinator's own tokens are not in it unless the session's usage was read.
