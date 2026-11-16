# Steps: issues, PR, CI, report

Part of Prism (`~/.claude/skills/prism/SKILL.md`). Read when this step comes up.

**issues** (script `lib/open-issues.py`, after `mapcheck`): opens **one GitHub issue per platform whose map changes something**, in the repo holding most of that platform's mapped files (platforms sharing a repo each get their own issue). The issue has the change, the reference, the matrix link, the steps (when sliced), the platform's files and its test and regression rows. A retry, a resume or a later step updates the same issue, never opens a new one. Each PR then starts with `Closes #n` for its own platform. Exit 2 (gh not logged in, no access) → `done issues blocked --reason`.

## PR lane
- **Matrix link first.** After the first matrix publish, write its URL to `<run>/matrix-url.txt`; every PR description links it.
- **pr**: `lib/open-pr.py <p>`. It commits the platform's paths on `feature/<slug>` and opens **one PR per platform**, always. When a repo holds several platforms (iOS and Android in one monorepo), it cuts `feature/<slug>-<platform>` from the base, cherry-picks only that platform's commits, pushes it and opens that platform's own PR. A repo with one platform pushes `feature/<slug>` itself. A retry updates the same PR. When two platforms share a repo, the first one's split can fail with "would be overwritten" while the other platform's files are still uncommitted: run the other platform's `pr` step, then run the first one again. For a split feature, each later step adds its commit to the same PR, and the description keeps every step's results (one section per step). The description has `Closes #n`, the change, the matrix link, and per platform either the scenario results + evidence folder (Claude ran it) or a scenario checklist (you run it), plus the gate and verify results. Screenshots are never committed.
  - exit 0 → `done pr:<p> pass`; exit 2 (`blocked`: gh auth, push rejected, wrong branch) → `done pr:<p> blocked --reason`, then `reopen` once fixed.
- **ci**: `lib/check-ci.py <p>`, run in the background. It waits up to 20 min for the PR's checks.
  - `green` or `none` (native repos have no CI) → `done ci:<p> pass`;
  - `red` → `done ci:<p> fail`: back to build with `ci-<p>.json` and the failed log; the next `pr` updates the same PR;
  - `blocked` (still running, gh error) → `done ci:<p> blocked --reason`.
- After 3 retries from any of gate, verify, run or ci the lane is `blocked`.
- **report**: one short table per platform (pass / fail / unverified per scenario, or "you run it"), the PR link and CI result, the matrix link and the evidence folder.
