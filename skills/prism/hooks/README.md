# Prism hooks

- `hooks/block-forbidden.py` (PreToolUse, this skill). During a run it blocks:
  - `gh pr merge`, force-push, hard reset, stash, `clean -f`, branch deletes;
  - switching to any branch except `feature/<slug>`;
  - commit/push except on `feature/<slug>`.

  With no active run it does nothing.
- `hooks/check-handoff-stop.py` (Stop in each node agent's file, which becomes SubagentStop). A node agent can't finish until its handoff passes the check. After 3 tries the node is marked blocked.
- `hooks/only-run-dir.py` (PreToolUse Write|Edit, in read-only node agents): they may write only inside the run folder.
- `hooks/log-fetch.py` (PostToolUse WebFetch, in the researcher): every opened URL goes to `fetch-log.txt`, so an unopened URL can't be cited.

- `hooks/no-prompt-steering.py` (PreToolUse Agent|Task|SendMessage, global in `~/.claude/settings.json`): the coordinator can't add its own instructions to a node. Prompts must equal `graph.py prompt <id>`, and messages must equal `graph.py fix <id>`. Graph work through a non-graph agent is blocked too. It also counts fix messages: a 4th to the same node is blocked (`lib/caps.py`).
- `hooks/only-repos.py` (builder): edits only inside the platform repos and the run folder. The skill and its checks can never be edited by a node.
- `hooks/read-only-bash.py` (verifier): read-only shell commands only.
- `hooks/cold-reader-reads.py` (cold-reader, Read): only `brief.json`, `map-*.json` and its own `coldread.json`.
- `hooks/rowfixer-reads.py` (row fixer, Read): only `brief.json` and its `rowfix-*` files.
