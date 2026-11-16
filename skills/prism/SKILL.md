---
name: prism
description: >-
  Prism: builds one app feature on every platform a project has (iOS and
  Android) in parity, by walking a fixed graph of nodes with checked
  handoffs, retries and resume. Invoke when the user types "/prism setup" (set up or
  update a project), "/prism doctor", "/prism <what>" or "prism: <what>", "/prism" or
  "prism" alone (resume).
hooks:
  PreToolUse:
    - matcher: "Bash"
      hooks:
        - type: command
          command: "python3 ~/.claude/skills/prism/hooks/block-forbidden.py"
---

# Prism

One run takes one feature to every platform the project has. **The graph decides the order, not you.** `graph.json` lists every node and edge; `lib/graph.py` says which nodes run next; every node hands over a JSON file that is checked before the run moves on.

**Prism knows nothing about a project until `/prism setup` has run.** Everything project-specific (platforms, repos, base branches, gate commands, architecture and file rules, feature flags, the shared layer) lives in the project's `.prism/` folder: `prism.json` plus `architecture.md`, `folder-map.md`, `feature-flags.md`, `feature-parity.md`, `manual-run.md` and `ci-map.md`. `python3 ~/.claude/skills/prism/lib/project.py where` prints which project is active.

**This skill is the only source of rules for a run**: this file, `steps/`, `graph.json`, `contract/`, `platforms/`, `lib/`, `hooks/`, the `fg-*` agent files, and the project's `.prism/` folder. Never rely on or cite memory notes during a run. If a rule is missing, add it where it belongs: a script when it can be checked, the step's file in `steps/` for one step, the agent's file for one agent, the project's `.prism/` files for one project, and this file only for the walk and R1–R8.

Load `gather-feature-specs` at the start of every run. It is used only when no platform has the feature (the research node).

## Triggers
| User says | Do |
|---|---|
| `/prism setup` | follow `steps/setup.md`: find or create the project, read or choose its architecture, write `.prism/`, check and install tools. Running it again updates the project. |
| `/prism bootstrap` | follow `steps/bootstrap.md`: ask which platforms get a starter app (all or some), make the empty shells, then a run of kind `bootstrap` adds the architecture skeleton |
| `/prism doctor` | `python3 ~/.claude/skills/prism/lib/doctor.py --project` (or `core` with no project); offer to install each missing item, one question for all of them |
| `/prism <what>` or `prism: <what>` | no project yet (`project.py where` fails) → run setup first, then come back to the ask. Otherwise `graph.py init <slug> app-sync`, then walk. The brief decides: a platform has it → mirror it; none has it → research and plan first (`no_reference=true`), and the read-back says so. |
| `/prism` or `prism` alone | an active run → `graph.py resume`, then walk; no active run → ask "What should Prism build?" |

The trigger is only a hint. The brief node checks the platforms itself and sets `no_reference`.
`<slug>` is short kebab-case from the ask (`delete-order`). Only run `init` with `--platforms ios,android` if the user names platforms.

## Step 0: repos on their base branch
Nothing is read, researched or planned until every repo the run can touch is **clean on its base branch** (`.prism/prism.json` → each repo's `base`). A branch the user named for a platform at `init` (`--branch <platform>=<branch>`, saved as `bases` in `run.json`) replaces that platform's base everywhere. `lib/base_check.py` checks it and `graph.py` runs it at `init`, `resume` and `done brief pass`; each refuses while any repo:
- is on another branch (only `feature/<slug>` cut from the current base is allowed, for a resumed run);
- has uncommitted changes in its source folders.

On refusal, show the user the lines it printed and wait. Never switch, stash or commit their repos to get past it. Warnings (behind `origin/<base>`, changes outside source folders, unreadable repo) are shown to the user but don't stop the run. Check by hand any time: `python3 ~/.claude/skills/prism/lib/base_check.py ios,android,flutter <slug>`.

## The walk
All commands: `python3 ~/.claude/skills/prism/lib/graph.py <cmd>`.

1. `next` prints JSON: `start` (nodes to run now), `still_running`, and at the end `finished` or `stuck`.
2. Start **every** node in `start` at once, by kind:
   - **human**: do what `pause` says, in plain language, and wait for the user. Write the node's `writes` file from the answer.
   - **agent**: spawn the subagent named in `agent` with the prompt **exactly** as printed by `graph.py prompt <id>`, nothing added, removed or reworded. The rules come from the agent file and `architecture-rules.md`, never from the coordinator. A hook (`no-prompt-steering.py`, registered in `~/.claude/settings.json`) blocks any other prompt.
   - **script**: run `script` from `~/.claude/skills/prism/` with the run folder as `FG_RUN_DIR`.
3. When a node ends: `done <id> pass|fail|blocked|skip [--reason "…"] [--flag k=v]`.
   - `pass` is refused if a `writes` file is missing or fails `check_handoff.py`. Send `graph.py fix <id>` output, verbatim, back to the **same agent** (SendMessage), up to 3 times, then `blocked`. The hook blocks any other message to a graph agent. Never fix the handoff yourself, and never edit the check. The finish hook only gets one chance per agent, so `done` is the hard gate.
   - `fail` is only for nodes with a retry edge (gate, verify, run, pr, ci). The script sends the lane back to `build` with `last_failure`. After 3 retries the lane is `blocked`.
   - `blocked` always needs a reason the user can act on.
   - `skip` is for a platform lane that needs no change (from its map).
   - The brief must pass with `--flag no_reference=true|false`. A map passes with `--flag engine_changed=true` when a platform that uses the project's shared layer (`shared` in `prism.json`) needs a change there.
4. **Progress page and eval.** After every `done`, `reopen` or `resume`, run `lib/matrix.py`. It always rewrites the local `<run>/matrix.html`, then prints `publish: yes (…)` or `publish: no`. Publish with the Artifact tool (same path, same link) **only on `publish: yes`**: a milestone (first page, a step that needs the user, an approval, something blocked, a lane's build/verify/PR/CI settling, results reported). Never publish on `publish: no`. Log every user-asked change to `<run>/eval.json`, and turn every `miss` and `bug` into a rule in the skill before the run ends. Details: `steps/state.md`.
5. Back to 1 until `finished: true`. If `stuck`, run `status` and tell the user which node is waiting on what.

Never skip, reorder, merge or invent a node. Never run a node `next` did not hand out. If a node's agent or script doesn't exist yet, mark it `blocked` with the reason "not built yet (phase N)".

## Steps: read the file when the step comes up
| Step | File |
|---|---|
| setup (`/prism setup`: project, architecture, tools) | `steps/setup.md` |
| bootstrap (`/prism bootstrap`: starter apps on the platforms the user picks) | `steps/bootstrap.md` |
| brief (interview, reference search, related features, test rows, read-back) | `steps/brief.md` |
| plan, spec, splitting into steps | `steps/plan-spec.md` |
| cold-read, row fixer, file approval, scoped retries | `steps/coldread-mapcheck.md` |
| branch, baseline, build, gate, verify | `steps/build.md` |
| who runs the app, run tools, server writes, run | `steps/run.md` |
| issues, PR, CI, report | `steps/pr.md` |
| progress page, eval, `progress.md`, handoffs | `steps/state.md` |

Ask "who runs the app" right after the brief's yes (`steps/run.md`), before any build.

**A handoff that says `{"blocked": "…"}`**: the node couldn't do its job, for example an unreadable repo or a missing screen. Run `done <id> blocked --reason "<that text>"`. Never pass it, never retry it silently.

## Rules
- **R1 Independent verify.** The verifier never wrote the code. Fail → retry the builder, at most 3 times, then blocked. The bar is never lowered.
- **R2 Screenshot evidence.** One screenshot per scenario per platform, saved to the `Screenshots:` folder (`run.screenshots` in `prism.json`). No video. Never committed.
- **R3 Architecture.** Each platform's own rule docs and the project's `architecture.md` + SOLID, clean, simple, reuse, dumb views. Plus every line in `prism.json` → `guardrails`.
- **R4 Never silently skip a platform.** A missing MCP means ask; on no, report unverified.
- **R5 Don't break other screens.** Smoke path on every platform, every run.
- **R6 Only the asked feature.** Never touch any other feature unless the user explicitly asks. When the reference's behaviour relies on another feature (for example, delete picks the next row from search results), ask the user at the brief before anything is built. Without an explicit yes, that feature is left alone on every platform.
- **R7 Deterministic rules.** Anything a regex or a file list can check is checked by the gate script, never left to an agent. `lib/local-gate.py` fails the lane when:
  - a changed file is not in `map-<p>.json` or a recorded build deviation;
  - an added line breaks a `file_rules` entry in `prism.json` (written at setup from the project's architecture; each one cites its doc line, and a rule whose doc no longer says it is switched off), or a file grows past `max_file_lines`;
  - an added line or a new file name breaks a standing rule (debug prints, TODO/FIXME, naming per platform: the `standing_rules` of each pack in `platforms/`, plus `standing_rules` in `prism.json`), which applies to every run;
  - an added line matches a `pattern` in `brief.json → user_rules`.

  Clean code, no unnecessary code and architecture beyond these patterns are graded by the verifier.
- **R8 Ask on any gap.** If the user's words leave anything open (a side effect, an edge case, "so it should also…"), stop and ask them one plain question. Never fill a gap with your own guess, never pass a guess to an agent as if the user said it, and never add behaviour to a redo, fix or brief that the user didn't state. A redo or fix message carries the user's words only.

Node agents live in `~/.claude/agents/fg-*.md`: `fg-spec-writer`, `fg-mapper`, `fg-researcher`, `fg-builder`, `fg-verifier`, `fg-runner`, `fg-cold-reader`, `fg-row-fixer`.
Hooks and what each blocks: `hooks/README.md`.

## Guardrails
Never merge a PR. Never edit the backend. Never publish packages. Don't `xcodebuild` while Xcode is open. Never edit `.prism/` during a run (only `/prism setup` writes it).
