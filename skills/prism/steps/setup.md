# Step: setup (`/prism setup`)

Part of Prism (`~/.claude/skills/prism/SKILL.md`). Sets up a project once, before its first run, and updates it when the user runs it again. Every command below is `python3 ~/.claude/skills/prism/lib/<script>`.

Setup writes only two places: the project's `.prism/` folder, and (for a new project, on the user's yes) the new repo folders. It never edits code in an existing repo.

Ask with the question tool when it is available, one decision per question. Never ask what the files already answer.

## 1. Tools first
Run `doctor.py core`. For every `missing` item, ask once, as one question for all of them: "Prism needs <items>. Install them now?" On yes, run `doctor.py --install <items>` and run `doctor.py core` again. An item with only a `manual` step (for example `gh auth login`, Xcode): show that step and wait. Don't go on while a `required` item is missing.

## 2. Which project
- `project.py where` succeeds and points inside the working folder → this is a **re-run**: read `.prism/prism.json`, run `setup_detect.py` on its repo paths, and show only what changed (new repo, new platform, new base branch, new CI commands). Ask for paths only for a platform the user adds. Update on yes. Never rewrite `feature-parity.md`, `folder-map.md` or `feature-flags.md` unless the user asks; a parity re-check runs only when they ask for it.
- Otherwise ask: "Is this an existing product (it already has code) or a new one?" Options: **Existing** · **New**.
  - **Existing** → **brownfield** (3A). Paths are asked, never guessed.
  - **New** → **greenfield** (3C). No parity check.

## 3A. Brownfield: ask for the paths, then read the code
1. **Paths.** Ask: "Where is each platform's code? Give a folder or a git URL for each platform (iOS, Android); one folder can hold several (a monorepo). Say 'here' for the folder Claude Code is open in." For a git URL, ask where to clone it (default: next to the working folder), then `git clone <url> <folder>`. A folder that doesn't exist: ask again. A platform the user names that has no code yet is greenfield (3C) inside this project.
2. **Repos.** Run `setup_detect.py <every folder the user gave>`. From its JSON: each platform and its repos (`path`, `role`, `base`, `remote`, `source`). Read back what was found per path. When a path holds a platform the user didn't name, or a named platform wasn't found there, ask. A repo with `"note": "not a git repo yet"` can't take part in a run; say so.
3. **Architecture: read it from the project, never ask for it.** For each platform:
   - read every doc in that platform's `rules` in full (CLAUDE.md, AGENTS.md, ARCHITECTURE.md…);
   - look at `architecture_hints`, list the source folders two or three levels deep, and open one existing screen and the code behind it (its ViewModel / hook / bloc / store, its repository or API call, how it is reached);
   - write the platform's entry for `answers.json → architecture.platforms`: `description` (one paragraph, how this codebase is built), `folders` (`screens`, `logic`, `data`, `navigation`: where a new feature's pieces go, as a path pattern with `<feature>`), and `rules`;
   - `rules` are only what the docs say or what every file you looked at does, each with a regex that matches the **forbidden** thing in an added line and an optional `scope` (a path part such as `/views/`). Prefer few, sure rules. Something you can't express as a regex goes in `description`, for the verifier;
   - `max_file_lines` only when a doc states a limit;
   - `architecture.source` is `"project"`. Only when a platform has no docs and too little code to tell (a fresh template), ask about that platform as in 3C step 3.
4. **Gate.** Each repo's `gate` comes from the platform pack. Compare it with that repo's `ci` commands in the detect JSON: when CI runs something different (another test task, a lint, a script), use CI's commands so the gate runs exactly what CI runs. Mark the commands that build the app with `"build": true`.
5. **Shared layer.** Only if `shared_candidates` lists local code used by two or more platforms (a JS workspace package, a path dependency): ask "`<path>` is used by <platforms>. Treat it as the shared layer that Prism changes first?" On yes, add it as `shared` with `used_by`.
6. **Feature flags.** If `flag_hints` lists files, open them and write `feature_flags.how`: where a flag is added, where its default is set, and one existing place that reads a flag (file:line). Then ask "Gate every new feature behind a flag on <those platforms>?" If there are no hints, ask "Does this project gate new features behind feature flags?" (default no).
7. **Simulator.** iOS only: `xcrun simctl list devices available` → pick the newest iPhone as `run.ios_simulator`.
8. **Parity check** (only when there is more than one platform):
   - write the answers so far to `~/.claude/prism/setup-answers.json` and run `setup_parity.py ~/.claude/prism/setup-answers.json`. It lists each platform's screens and routes by name;
   - group those names into user-facing features (`cart_view` + `CartScreen` + `/cart` → "Cart"). Leave out building blocks that aren't features (dialogs, rows, base classes);
   - for each feature and platform: ✓ (the screen exists and is reachable), ✗ (no code for it), or a short note when it differs ("email only", "max 6 tabs"). A "found" in the JSON is a hint, not proof: open the file and the place that navigates to it. A cell you can't confirm stays `?`;
   - show the table and ask the user to correct it. Their answer is final. Save it as `parity` in the answers: `[{"name": "Cart", "platforms": {"ios": "✓", "android": "✗"}}]`.

## 3B. Where `.prism/` goes
The workspace (where `.prism/` goes) is the working folder. When the repos are spread out, keep it there anyway; paths outside it are stored as absolute paths.

## 3C. Greenfield: ask, with defaults
No parity check: nothing exists yet, so `feature-parity.md` starts as an empty table and each run adds its own row. Set `new_project: true`.

1. Product name; platforms (multi-select); one repo per platform or one monorepo; the path for each repo (default `<working folder>/<name>-<platform>`); base branch (default `main`); GitHub remote per repo (optional now, needed before the first PR).
2. Kinds of change: `["feature"]`. Don't ask.
3. **Architecture: ask.** "Which architecture should every platform follow? Prism's default is **MVVM-C**: dumb screens, ViewModels for logic, repositories for data, coordinators for navigation." Options: **MVVM-C (Recommended)** · **Describe our own**.
   - MVVM-C → `architecture.source: "mvvm-c"`; leave `architecture.platforms` out, the platform packs fill in folders and rules. Show the folders per platform in the read-back.
   - Their own → the user describes it in their words. Draft `architecture.platforms` from that description: `description`, `folders`, `rules` (regex + scope, only what follows from what they said), `max_file_lines` only if they said one. Read it back and fix it with them until they say yes. `architecture.source: "custom"`, `architecture.summary`: their description.
4. Feature flags: "Gate new features behind a feature flag?" (default no). On yes, which platforms; `how` is left for the first run.
5. Set `create_repos: true`. The repos start empty; the apps come from bootstrap (step 5.3).

## 4. Read back, then write
Read back in plain words: the platforms and repos (path, base, remote), the architecture per platform (source; folders; rules), the gate per repo, the shared layer, feature flags, the parity table (brownfield), and anything that can't run on this machine (iOS needs a Mac). Wait for **yes**.

Then write `~/.claude/prism/setup-answers.json` in the shape at the top of `lib/setup_scaffold.py`, and run:
1. `setup_scaffold.py ~/.claude/prism/setup-answers.json --dry-run`. If it refuses (a bad regex, a missing gate), fix the answers and run it again.
2. `setup_scaffold.py ~/.claude/prism/setup-answers.json`. It writes `.prism/` (with the parity table for brownfield, an empty one for greenfield), creates and commits new repos when asked, and makes this the active project.

## 5. Platform tools and the first check
1. `doctor.py --project`. For missing platform tools (Android Studio, Xcode…), ask once for all: "Install <items> now?" On yes, `doctor.py --install <items>`. Manual items: show the step. A tool the user doesn't want only means that lane's gate or run is reported blocked later.
2. `base_check.py` with every platform. Show problems and warnings as they are; they must be fixed before a run, not now.
3. **Greenfield, or any platform without an app:** ask "Create starter apps now?" On yes, follow `steps/bootstrap.md` (it asks which platforms). On no, say `/prism bootstrap` does it later.
4. Tell the user: setup is done; `.prism/` can be committed so the team shares it; next is `/prism <what to build>`.
