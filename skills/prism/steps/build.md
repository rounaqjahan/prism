# Steps: branch, baseline, build, gate, verify

Part of Prism (`~/.claude/skills/prism/SKILL.md`). Read when this step comes up.

## Build lanes
- **Before a lane's first build attempt, branch first.** Run `python3 ~/.claude/skills/prism/lib/prepare-branch.py <p>`, which puts only the repos that `map-<p>.json` changes on `feature/<slug>` (created from the repo's base branch). A repo with no mapped files (for example the host app when only the SDK changes) is never branched, and a skipped lane is never branched. Never build on a repo's base branch. If a repo is on some other branch, the script refuses: mark the build blocked with its reason.
- **Then** record the baseline: `python3 ~/.claude/skills/prism/lib/local-gate.py <p> --baseline`. It saves what is already dirty or already failing, so the gate only blames the run for what the run broke. Never retake it on a retry.
- **build**: spawn `fg-builder` with `FG_NODE: build:<p>`. On a retry, include `last_failure`, and on retries 2–3 tell it to diagnose first.
- **gate**: `python3 ~/.claude/skills/prism/lib/local-gate.py <p>`. It writes `gate-<p>.json`.
  - `pass` → `done gate:<p> pass`;
  - `fail` → `done gate:<p> fail` (back to build);
  - `blocked` (Xcode open, unreadable repo) → `done gate:<p> blocked --reason`, then `reopen` once fixed.
  - `blocked` because the app already failed to build before the change: show the user the failing command and its error, and ask "fix the base first, or go on with that build unverified?". Only on their explicit go-on: `reopen gate:<p>`, `next`, then `done gate:<p> pass --user-override "<their words>"`. It is logged in `run.json` and shown under decisions in `progress.md`. The same applies to a finding the coordinator believes is a false alarm: show the user the finding and why, and pass only on their explicit words; then fix the check that raised it. Never use it for a failure the change caused, and never without the user's words.
- **verify**: spawn `fg-verifier` with `FG_NODE: verify:<p>`.
  - `pass` → done pass;
  - `fail` → done fail (back to build with the verdict);
  - `unverified` → done blocked with the unverified checks.
