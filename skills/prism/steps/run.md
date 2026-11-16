# Step: run the app

Part of Prism (`~/.claude/skills/prism/SKILL.md`). Read when this step comes up.

## Run lane
- **Ask first, right after the brief's yes** (before any build, so missing tools are found early). Ask once per run, with the recommendation and why:
  > "Should I run the app on the simulator/emulator and walk the scenarios, or will you run it yourself? **I recommend you run it yourself**, because:
  > - it's much slower: each platform needs a full build, a simulator boot and many slow UI steps;
  > - it uses a lot of tokens and time;
  > - UI automation is fragile: taps miss, screens load late, and a flaky step looks like a failure;
  > - some scenarios can't be set up on a simulator (airplane mode, server errors, org settings), so they come back unverified;
  > - I judge screenshots, which is weaker than you using the real app;
  > - Xcode must stay closed for the whole iOS run.
  >
  > Claude running it is worth it when you want screenshot evidence in the PR without doing it yourself."

  Save the answer to `<run>/run-choice.json` as `{"who": "claude"|"user", "platforms": [...]}` (the user may pick per platform). On resume, read that file and don't ask again.
  - `user` (no) for a platform → do not spawn `fg-runner`. Run `done run:<p> skip --reason "user runs the simulator"`. The lane goes straight to `pr`, and its PR lists the scenarios as a `- [ ]` checklist. Then ask: **"Do you want step-by-step instructions to run it yourself from the IDE?"** On yes, give the platform's section of ``manual-run.md` in the project folder (`project.py where` prints it)`, filled in with this run's repo paths, branches (`pr-<p>.json`, or `feature/<slug>` before the PR), flag file and scenarios. When the user reports results, write them into `run-<p>.json` and re-render the matrix.
  - `claude` (yes) →
    1. **Check the tools first**, before any build: `python3 ~/.claude/skills/prism/lib/check-run-tools.py <platforms> --project <the session's working folder>`.
    2. For each missing item, **ask first**: "<item> is missing: <what>. Want me to add it?" Use the item's section of `contract/run-tools.md`. For an MCP, on yes, run its `claude mcp add … -s user` command yourself (removing a one-folder copy first), then tell the user the only step left for them: restart Claude Code and type `/prism`. For anything that needs the user (simulator, emulator, Xcode, Flutter, login), show that section's exact steps and wait.
    3. Run the check again. If the user says no to a missing item, that platform is `done run:<p> blocked --reason "<item> missing; user chose not to add it"` and reported unverified (R4).
    4. **Server writes** (once `coldread` has passed, so the regression rows exist too): list every row with `server_write` (row, resource, endpoint) and ask once: "These rows change data on the server. Approve them?" Save the approved ids as `approved_writes` in `run-choice.json`. Unapproved rows are skipped, never run in a weaker form.
    5. Create the evidence folder named on the `Screenshots:` line of the run prompt (`run.screenshots` in `prism.json`, default `~/Desktop/<Feature> screenshots/`), save it as `evidence_folder` in `run-choice.json`, then continue as below.
- **run**: spawn `fg-runner` with `FG_NODE: run:<p>`. It runs the app, walks the scenarios and saves one screenshot per scenario to the evidence folder.
  - every scenario `pass` (or `unverified` with a reason) → `done run:<p> pass`;
  - any scenario `fail` → `done run:<p> fail` (back to build with `run-<p>.json`);
  - a handoff that says `blocked` (Xcode open, missing MCP, no device) → `done run:<p> blocked --reason`, then `reopen` once fixed.
