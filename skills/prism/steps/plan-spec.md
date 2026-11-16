# Steps: plan and spec

Part of Prism (`~/.claude/skills/prism/SKILL.md`). Read when this step comes up.

**plan** (only when no platform has it): show the options from `research.json` as a short table, with the recommendation and the gaps. The user picks or edits. Write `plan.json` `{"chosen_option": "…", "edits": "…"}`, then `done plan pass`.

**spec → steps** (the `slice-feature` skill, used by `fg-spec-writer`). Before `done spec pass`, read `spec.json` → `phases`:
- **One step** → `done spec pass --flag sliced=false`. The run goes on as usual.
- **Several steps** → show the user a short table (id, name, goal, rows, size) and say which counts were over the `slice-feature` limits. Wait for **yes**.
  - On yes: `done spec pass --flag sliced=true` (map onward is skipped in this run) and write `<run>/phases.json`: `{"phases": [{"id": "P1", "name": "…", "slug": "<slug>-p1", "status": "pending"}, …]}`.
  - On edits: add the user's words to `brief.json` → `slicing`, run `done spec blocked --reason "user re-slicing"`, then `reopen spec` so a new spec-writer slices again.
- **The step loop.** For each step in order:
  1. `graph.py init <slug>-<id> <trigger> --parent <slug> --step <id> --platforms <same as the parent>`.
  2. Write its `brief.json` from the parent's: the same `change`, `kind`, `platforms`, `reference_platform`, `setup` and `user_rules`; `step` = that phase from the parent spec; `scenarios` = the step's rows plus copies of the smoke and flag-off rows. Add the ids of those copied rows to `step.rows` too, or the spec check refuses them as rows in no step. Add `parent_spec` = the path of the parent's `spec.json`, and copy the parent's `plan.json`, `research.json`, `fetch-log.txt`, `run-choice.json` and `matrix-url.txt` into the step's folder, so the step's spec keeps every decision the user already made. Pass the step's brief with `--flag no_reference=false` (research and plan are never repeated for a step). With no active run (the parent just finished), render the parent's page with `lib/matrix.py <parent slug>`.
  3. Read it back in one line ("Step P2 of 3: <goal>. Rows: … OK?") and walk the graph to `finished`.
  4. Set the step's `status` to `done` in the parent's `phases.json`, re-render the parent's matrix, start the next step.
  - Every step uses the feature's branch `feature/<parent slug>`, so each step adds its commits to the same branch and updates each platform's same PR and issue.
  - On `/prism` (resume): if the active run finished and has a parent, continue with the parent's next pending step.
