# Prism

Prism takes one app feature to both of your platforms, **iOS and Android**, in parity. It walks a fixed graph: brief → spec → a file plan per platform → cold-read of the test rows → your approval → build → checks → independent review → one PR per platform. Every step hands over a file that a script checks, and nothing repeats more than 3 times without your say.

It works with any project: an existing one (Prism reads it), one whose repos are spread over several places (Prism asks where), or a brand-new one (Prism asks how you want it built and sets it up).

Prism is free. **[Prism Pro](https://www.agensi.io/skills/prism-pro)** adds Web, Flutter and React Native, Windows and Linux, and PR review handling.

## Prism or Prism Pro?

| | Prism (free) | Prism Pro |
|---|---|---|
| **Platforms** | iOS, Android | iOS, Android, **Web** (any framework; new apps: React + TypeScript on Vite), **Flutter, React Native** |
| **Install on** | macOS | macOS, **Windows, Linux** |
| Setup for existing and new projects, parity check, MVVM-C default | ✓ | ✓ |
| Brief → spec → file plan → build → checks → review → one PR per platform | ✓ | ✓ |
| Starter apps (`/prism bootstrap`) | iOS and Android (you make the empty app in Xcode / Android Studio) | also Web, Flutter and React Native, **made for you** with each platform's own tool |
| Claude runs the app and screenshots each scenario | iOS simulator, Android emulator | also Flutter and React Native apps |
| `/prism doctor` tool checks and installs | Xcode, Android Studio | also Flutter, Node package managers (pnpm, yarn), and Windows/Linux package managers |
| **`/prism review`**: turn reviewer comments into fixes | ✗ | ✓ |
| Projects that mix native and cross-platform apps (for example native iOS + Flutter + Web) | native iOS and Android only; other apps are skipped at setup | ✓ all in one run |

## Install

On macOS:

```bash
git clone https://github.com/rounaqjahan/prism.git
cd prism
./install.sh
```

The installer:
1. installs what is missing: Python 3.9+, Git, the GitHub CLI and Node.js (with Homebrew);
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

Then it checks the platform tools (Xcode, Android Studio…) and offers to install what's missing. `/prism doctor` runs that check again any time.

If your project also has a Web, Flutter or React Native app, setup lists it as skipped. Those platforms are in [Prism Pro](#prism-pro).

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
- `/prism bootstrap` gives a new project a starter app (entry point, coordinator, two screens with ViewModels, a repository) on the platforms you pick.
- `/prism doctor` checks and installs the tools this project's platforms need.
- Run data lives in `~/.claude/prism/runs/<feature>/`; `progress.md` there shows the whole run on one page.

## Where it stops for you

The brief read-back, who runs the app, a plan choice (only when no platform has the feature), splitting a big feature, approving each platform's files before any code is written, anything blocked, and your test results before PRs are opened. Merging is always yours.

## Requirements

- A Mac (iOS builds and the iOS simulator need Xcode).
- Claude Code, Python 3.9+, Git, the GitHub CLI logged in, Node.js. The installer adds whatever is missing.
- Xcode for iOS, Android Studio (with an emulator) for Android.

## What's inside

| Folder | What it is |
|---|---|
| `skills/prism` | The engine: graph, scripts, hooks, steps, schemas, and `platforms/` (one pack per platform: detection, default gate, MVVM-C folders and rules, standing rules, run tools) |
| `skills/slice-feature` | Cuts a feature that is too big for one build into steps |
| `skills/gather-feature-specs` | Researches a feature no platform has yet and brings 2–3 options |
| `agents/fg-*.md` | The 8 node agents |
| `install.sh` · `install.py` | Installer |

## Prism Pro

Everything in Prism, plus:

### More platforms
- **Web**: any framework your project already uses (React, Next.js, Vue, Svelte, Angular, Nuxt, Remix, Astro…), with its own gate (your project's install, lint, test and build scripts, with npm, pnpm, yarn or bun). **New projects start with React + TypeScript on Vite**, made with `create-vite@latest` (`react-ts` template); as of November 2026 that is React 19.3, Vite 8.3 and TypeScript 7.0. Because it uses the latest template, a new app always gets the current versions.
- **Flutter**: app and package repos, its own gate (analyze, test, iOS and Android builds), starter app made with `flutter create`, and Claude can run it on the iOS simulator or an Android emulator through the Dart & Flutter MCP.
- **React Native / Expo**: its own gate (install, lint, test), starter app made with `create-expo-app`, and Claude can run it on a simulator or emulator.
- **Mixed projects**: native iOS, native Android, Web, Flutter and React Native in one project, one run, one PR per platform. Monorepos that hold several platforms get one PR per platform cut from the same repo.

### Windows and Linux
- **Windows installer** (`install.cmd` / `install.ps1`): installs Python, Git for Windows (which gives Claude Code the Git Bash it uses), the GitHub CLI and Node.js with winget.
- **Linux installer**: apt, dnf, pacman and zypper.
- Android, Web, Flutter and React Native work fully on Windows and Linux. iOS lanes are planned and coded there; their build and simulator run need a Mac.

### `/prism review`: reviewer comments, handled
After the PRs are open, `/prism review`:
1. collects every open review comment from **all** of the feature's PRs (unresolved threads, review summaries, PR comments);
2. asks you, per comment, whether it's **code only**, a **behaviour change** or **no change**, and which platforms it applies to (a comment on the iOS PR may apply to Android too);
3. sends only those platforms back through build, checks and independent review. Behaviour changes get a new brief and test rows first;
4. adds a commit to each affected PR, with a checklist of which comments it answered;
5. drafts a reply for each comment ("Addressed in `<commit>`") and posts them only on your yes. Resolving threads stays with the reviewer.

### Get Prism Pro
<!-- TODO: replace with the link where people buy Prism Pro -->
**[Get Prism Pro →](#)**

Prism Pro installs the same way and replaces Prism in `~/.claude/`; your `.prism/` project folders keep working.
# prism
