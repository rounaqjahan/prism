# Step: brief

Part of Prism (`~/.claude/skills/prism/SKILL.md`). Read when this step comes up.

**brief**
1. Take the ask in any form. If too vague to build or check, interview one question at a time:
   - what should behave differently;
   - where (screen, widget);
   - the exact rules, including missing / unknown;
   - one example;
   - what proves it works, and what must keep working.
2. Find the reference yourself, never from the trigger word:
   - run `python3 ~/.claude/skills/prism/lib/detect-source.py <keywords…>`. It searches each repo's **base branch** (its `base` in `prism.json`), never the working copy, so a checked-out feature branch can't fake a hit or hide one. Only when the user says the feature lives on a certain branch for a certain platform, add `--branch=<platform>=<branch>` for that platform, and start the run with `graph.py init … --branch <platform>=<branch>` so the base check, the maps and `prepare-branch.py` all use that same branch;
   - read the project's `feature-parity.md` (in the folder `python3 ~/.claude/skills/prism/lib/project.py where` prints);
   - a platform whose code has it is the reference. Two that disagree, or several dirty → ask which one.
   - if you can't tell from the reference's code exactly which control the user sees (a visible ⋯ button, long-press, swipe), ask the user for a screenshot of the reference. Never guess the control.
3. **Related features (R6).** List every other feature the reference's behaviour relies on (search, filters, pagination…) and, per platform, whether that platform has it (with file:line). For each one, ask the user, one question at a time: "Web's delete uses search results. Android has no search. Leave search alone on Android (scenario n/a), or add it?" No explicit yes = leave it alone: add `{"rule": "Do not touch <feature> on <platforms>", "pattern": "<regex of that feature's names, e.g. (?i)search|filter>", "platforms": [<platforms>], "said": "<user's answer>"}` to `user_rules` (the `pattern` is required: the gate fails any added line that matches it) and `na: [<platforms>]` to every scenario that needs it.
   **Screen layout first.** Before drafting any row, add one `setup` entry per platform describing the screen the feature lives on, read from that platform's code (never assumed from another platform): what sits at the top, the order of sections, headings and dividers, how to open and close it, and every control a row will tap, by its visible label or icon. Rows then use these names, so no row needs "on iOS…, on Android…" branches it invents itself.
   Then draft ≤10 **Do → Expect** scenarios: golden path, one per rule, missing/default, unknown (never crash), dark mode or RTL only if the app has that mode, the smoke path. A scenario may only exercise the asked feature, plus related features the user allowed. If the user gave scenarios, compare (✓ both · user-only kept as written · loop-only offered · conflicts asked).

   **Row shape (every test row: brief scenarios and map regressions).** The reader may be a person or an agent with zero context who can't ask what you meant:
   ```json
   {"id": "S1", "scope": "new|edge|regress", "name": "what the row proves, in plain words",
    "do": ["one action per item: the screen, the control by its visible label, the exact input"],
    "expect": ["one visible check per item: the exact text, count or screen", "what must not appear"],
    "covers": "the code path or behaviour it exercises",
    "note": "optional: when a correct result could look like a bug, say so and name the case it's confused with",
    "requires": "optional key=value pairs, e.g. flag=off role=admin",
    "server_write": "only if a step changes server data: the resource and endpoint"}
   ```
   - Never invent a name for a procedure ("start as A", "the usual login"). Write the steps out in every row.
   - Every wait ends on something visible ("until the list shows"), never "until loaded / ready / idle".
   - Before an Expect counts something new ("one new row"), a Do step notes the count first.
   - Define every named value (accounts, orgs, flags) once in `setup`.
   - **Server writes:** prefer a pass condition you can check without saving. A row that must change server data names it in `server_write`. Never write "change, then restore" or "reset to defaults".
   - `lib/scenario_lint.py` (run by the checker) blocks vague phrases, inline step numbering, missing ids, names or `covers`. The `coldread` node then has a fresh agent restate every row.
4. Read back: the change, the reference (or "no platform has this, so I'll research first"), the platforms, unreadable repos, the related features left alone or allowed per platform, and the scenarios. Wait for **yes**.
5. Write `brief.json`: `change`, `kind` (one of `kinds` in `prism.json`), `platforms`, `reference_platform`, `scenarios` (row shape above), and `setup`: the "before you start" list (accounts, org, flag state, server, anything a row relies on). Always add `{"rule": "Do not touch any other feature unless the user explicitly asked; related features only where this brief allows them.", "said": "standing rule R6"}` to `user_rules`. If `prism.json` has `feature_flags` and this is `kind: feature`, also add: `{"rule": "Gate the feature behind a feature flag on <the feature_flags platforms>, enabled by default, as the project's feature-flags.md says. No flag on other platforms.", "said": "standing rule"}`, plus an edge scenario that turns the flag off and checks the screen is exactly as before (`requires: "flag=off"`). Then `done brief pass --flag no_reference=<true|false>`.
