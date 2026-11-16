# Step: bootstrap (`/prism bootstrap`)

Part of Prism (`~/.claude/skills/prism/SKILL.md`). Gives a new project a starter app on the platforms the user picks, so feature runs have something to build on. Offered at the end of greenfield setup; the user can also type `/prism bootstrap` any time. Commands are `python3 ~/.claude/skills/prism/lib/<script>`.

## 1. Which platforms
Run `bootstrap.py status`. Platforms with `has_app: true` are left out. If none are left, say so and stop.

Ask once, multi-select: "Create the starter app on which platforms?" List every platform without an app, all selected by default, so the user can keep all or untick some. Platforms they untick stay empty until they run `/prism bootstrap` again. Mention on the same question any platform with `needs_mac: true`: its shell can be made but not built on this machine.

## 2. The empty shell, per chosen platform
- `shell` is set: `tool_missing` → offer `doctor.py --install <tool>` first. Then `bootstrap.py shell <platforms…>`. It makes the app with the platform's own tool in a temp folder, copies it into the repo and commits it on the base branch. `failed` → show the log's last lines and ask: retry, make it by hand, or drop that platform.
- `by_hand` is set (iOS, Android): show that text and wait for the user to say done. Then `bootstrap.py check <platform>`; `false` → say what's missing and wait again. Commit what they made on the base branch (`git add -A` + `git commit -m "App shell"`), after showing them `git status`.

## 3. The starter app: a normal run, kind `bootstrap`
`graph.py init bootstrap app-sync --platforms <the chosen platforms that now have a shell>`, then walk as usual, with these differences:

**brief** (no interview; read it back and wait for yes):
- `change`: "Starter app: the app entry point, one coordinator for navigation, a Home screen and a Details screen, each with its ViewModel, and one repository with in-memory sample data, following architecture.md."
- `kind`: `"bootstrap"`, `reference_platform`: `null`, `setup`: one line per platform saying how the app is started (from `manual-run.md`).
- `scenarios` (row shape from `steps/brief.md`):
  - S1 `new`: launch the app → the Home screen shows the title "Home" and a list of three sample items.
  - S2 `new`: on Home, tap the first item → the Details screen opens and shows that item's name.
  - S3 `new`: on Details, tap Back → the Home screen shows again with the same three items.
  - S4 `edge`: the repository returns no items → Home shows "No items yet" and no list.
- `user_rules`: R6 as usual. No feature-flag rule (`bootstrap` isn't `feature`).
- `done brief pass --flag no_reference=false`.

The spec, maps, build, gate, verify, run, PR and CI steps then run as for any feature. The maps put every file where `folder-map.md` says, and the PRs are opened from `feature/bootstrap`. When they are merged, feature runs can start.
