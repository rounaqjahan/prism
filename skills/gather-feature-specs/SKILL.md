---
name: gather-feature-specs
description: >-
  Research and plan a new feature before building it. Looks up how similar products
  do it (with sources), checks this repo for reusable patterns, detects the repo's tech
  stack, and writes a behaviour spec plus an implementation plan in that stack. Use when
  the user says "gather feature specs", "spec this feature", "plan a new feature",
  "how do others do X", or asks for a feature that doesn't exist yet.
allowed-tools: WebSearch WebFetch Read Grep Glob
---

# gather-feature-specs

Turn "I want feature X" into two documents, before any code is written:

- **`feature-spec.md`**: what the feature does. Stack-neutral, so any platform can build from it.
- **`implementation-plan.md`**: how to build it **in the repo you are running in**, following that repo's own architecture.

Works in any repo and any stack. Never assume a stack, an organisation or a folder layout: detect them.

## Inputs
- The ask, in the user's words.
- Optional **output folder** from the caller (another skill may pass its own run folder). Default: `~/feature-specs/<slug>/`, outside the repo so nothing lands in git.
- Optional **mode** from the caller:
  - `behaviour-only`: steps 2, 3, 5, 6 with `feature-spec.md` only.
  - `plan-only`: steps 1, 4, 6 with `implementation-plan.md` only; an existing `feature-spec.md` is passed in.
  - Default: all steps.

## Step 1: Detect the stack
Follow `${CLAUDE_SKILL_DIR}/reference/stacks.md`. Read the manifest files at the repo root (and one level down for monorepos), then the repo's own rules: `ARCHITECTURE.md`, `CLAUDE.md`, `AGENTS.md`, `CONTRIBUTING.md`, `docs/`. Write down:
- language and UI framework
- architecture pattern and where a feature's pieces live (screen, logic, data, navigation)
- state management and dependency injection
- test framework and where tests live
- the repo's hard rules (file size limits, banned patterns, naming)

If two stacks are present (a monorepo), ask which one this plan is for. If nothing matches, ask the user.

## Step 2: Understand the ask
Ask only what is still unknown, one question at a time, in plain words:
1. Who uses it, and what do they do, step by step?
2. What happens on success, on failure, while loading, and when there is nothing to show?
3. Is it on for everyone, or behind a setting or plan?
4. What must keep working exactly as it does now?

Stop asking once these are answered. Never ask the user about code.

## Step 3: Research outside
Use WebSearch and WebFetch.
- How **3–5 comparable products** handle the same feature: the entry point, the confirmations, the undo, the empty states, the limits.
- The design guidance for **the detected stack** (sources in `stacks.md`).
- Edge cases, accessibility, privacy and security concerns others ran into.

**Every claim carries its source link.** Anything without a source is labelled *assumption*. If a page can't be read, say so and move on; never guess its content.

## Step 4: Research inside this repo
Use Grep, Glob and Read. Find:
- the **closest existing feature or pattern** (an existing menu, list action, settings row, sheet, form)
- reusable components, helpers, styles and tokens
- existing API calls and endpoints the feature can use
- config or feature-flag mechanisms
- where user-facing strings and translations live

**What the repo already does beats what other products do.** If the feature needs a backend endpoint that doesn't exist, list it as a **gap**; never invent an API.

## Step 5: Options
Present **2–3 options**. For each one:
- what the user sees
- pros and cons
- its sources
- the existing code it reuses

End with **one recommendation** and why, usually the option that reuses the most and surprises users least. Keep it short enough to read in one screen.

## Step 6: Confirm, then write
Wait for the user to pick or edit. Then fill the templates:
- `${CLAUDE_SKILL_DIR}/templates/feature-spec.md` → `<output>/feature-spec.md`
- `${CLAUDE_SKILL_DIR}/templates/implementation-plan.md` → `<output>/implementation-plan.md`

Reply with both paths and a five-line summary:
- the chosen option
- the backend gaps
- the open questions
- the number of test scenarios
- the main files the plan touches

## Rules
- Behaviour and UX only. Never copy another product's code, assets, text or branding.
- No organisation names, repo names or paths baked into the outputs, except the paths found in this repo.
- The implementation plan follows the repo's own conventions over general best practice.
- Plain language in the spec: a non-developer must be able to read `feature-spec.md`.
- Never edit the repo. This skill only reads and plans.
