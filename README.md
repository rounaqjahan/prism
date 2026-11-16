# Prism

Prism takes one app feature to every platform your product has (iOS, Android, Flutter, Web, React Native) by walking a fixed graph: brief → spec → a file plan per platform → cold-read of the test rows → your approval → build → checks → independent review → one PR per platform. Every step hands over a file that a script checks, and nothing repeats more than 3 times without your say.

It works with any project: an existing one (Prism reads it), one whose repos are spread over several places (Prism asks where), or a brand-new one (Prism asks how you want it built and sets it up).

## Install

**macOS / Linux**

```bash
./install.sh
```

**Windows**: double-click `install.cmd` (or run `powershell -ExecutionPolicy Bypass -File install.ps1`).

The installer:
1. installs what is missing: Python 3.9+, Git, the GitHub CLI and Node.js (Homebrew on macOS, apt/dnf/pacman/zypper on Linux, winget on Windows, with a python.org download as a fallback for Python);
2. copies the three skills and the eight agents into `~/.claude/`, pointed at the Python it found;
3. adds the one global Prism hook to `~/.claude/settings.json` (the old file is kept as `settings.json.before-prism`);
4. installs Claude Code if it isn't on PATH, and runs `gh auth login` if GitHub isn't logged in.

Run it again any time to update; it changes nothing it doesn't own.

## Set up a project

Restart Claude Code, open it in your project (or the folder that holds your repos), and type:

```
/prism setup
```

| Your situation | What setup does |
|---|---|
| **Existing project (brownfield)** | Asks where each platform's code is (a folder or a git URL, cloned if you want). Then finds every repo, base branch, remote, rule doc and CI command, and **reads the architecture from your code and docs**: where screens, logic, data and navigation live, and the rules the gate checks. Then runs a **parity check**: which features each platform has, which you correct before it's saved. |
| **New project (greenfield)** | Asks for the platforms, the repo paths and branch, then **which architecture to follow**: Prism's default **MVVM-C** (dumb screens, ViewModels, repositories, coordinators) or your own description. Folders and checks follow that choice. No parity check: the parity table starts empty. Then it offers **starter apps** and asks which platforms get one (all or some). |

Then it checks the platform tools (Xcode, Android Studio, Flutter, pnpm…) and offers to install what's missing. `/prism doctor` runs that check again any time.

Setup writes one folder, `.prism/`, in your project:

| File | What it is |
|---|---|
| `prism.json` | Platforms, repos, base branches, gate commands, file rules, feature flags, the shared layer |
| `architecture.md` | The architecture per platform, in words; the gate's rules cite its lines |
| `folder-map.md` | Where a feature's screen, logic, data and navigation go on each platform |
| `feature-flags.md` · `feature-parity.md` · `manual-run.md` · `ci-map.md` | Flags, which platform has which feature, how to run each app yourself, what the gate runs |

Commit `.prism/` so your team shares it. Edit it by hand any time, or run `/prism setup` again.

## Use

- `/prism <what you want built>` starts a run. Plain words; Prism asks about anything left open.
- `/prism` on its own continues the run in progress.
- `/prism review` handles reviewer comments on the feature's PRs.
- `/prism bootstrap` gives a new project a starter app (entry point, coordinator, two screens with ViewModels, a repository) on the platforms you pick.
- `/prism doctor` checks and installs the tools this project's platforms need.
- Run data lives in `~/.claude/prism/runs/<feature>/`; `progress.md` there shows the whole run on one page.

## Where it stops for you

The brief read-back, who runs the app, a plan choice (only when no platform has the feature), splitting a big feature, approving each platform's files before any code is written, anything blocked, and your test results before PRs are opened. Merging is always yours.

## Platforms and machines

| | macOS | Windows | Linux |
|---|---|---|---|
| Android, Flutter (Android), Web, React Native (Android) | ✓ | ✓ | ✓ |
| iOS, Flutter iOS build, React Native iOS | ✓ | plan and code only; build, gate and simulator run need a Mac | same as Windows |

On Windows, Claude Code uses Git Bash, which the installer installs with Git.

## What's inside

| Folder | What it is |
|---|---|
| `skills/prism` | The engine: graph, scripts, hooks, steps, schemas, and `platforms/` (one pack per platform: detection, default gate, MVVM-C folders and rules, standing rules, run tools) |
| `skills/slice-feature` | Cuts a feature that is too big for one build into steps |
| `skills/gather-feature-specs` | Researches a feature no platform has yet and brings 2–3 options |
| `agents/fg-*.md` | The 8 node agents |
| `install.sh` · `install.ps1` · `install.cmd` · `install.py` | Installers |

Adding a platform (for example KMP or SwiftUI-macOS) means adding a pack in `skills/prism/platforms/`, or giving its repos an explicit `gate` in `prism.json`.
