---
name: slice-feature
description: Decide whether a feature is small enough for one build, and if not, cut it into ordered, vertical steps that each work on their own. Used by the Prism spec-writer when it writes spec.json; works for any app and any stack.
---

# Slice a feature into steps

A feature that is too big for one build is cut into **steps**. Each step goes through the whole graph on its own (spec, map, build, checks, PR), so every agent works on a small, focused piece. You decide this from the **spec**, once, for every platform: all platforms follow the same layered architecture, so a step that is small in the spec is small everywhere.

## 1. Count the feature

Count these from the spec you are writing and the brief's rows:

| Count | What counts as one |
|---|---|
| **entry points** | a place where the user starts the feature (a button, a menu item, a screen, a gesture) |
| **screens** | a screen, sheet, dialog or panel the feature adds or changes |
| **rules** | a rule the user can observe ("only the owner can…", "the next item opens after…") |
| **states** | a state with its own look beyond the default (loading, empty, error, success, disabled…) |
| **API calls** | a server call the feature adds or changes |
| **rows** | brief test rows, not counting the smoke row and the flag-off row |

## 2. Decide: one step or several

**One step** when every count is at or under its limit:

| entry points | screens | rules | states | API calls | rows |
|---|---|---|---|---|---|
| 1 | 3 | 4 | 5 | 2 | 6 |

If **any** count is over its limit, slice. Write the counts that decided it in each step's `size`.

## 3. How to slice

- **Vertical, never by layer.** Every step delivers behaviour the user can see and test, through every layer it needs (screen, logic, data). Never "data layer first, screens later".
- **Smallest usable path first.** Step 1 is the simplest end-to-end version of the feature: the golden path through one entry point. Later steps add the other entry points, rules, states and edge cases.
- **Each step works on its own.** After any step the app builds, runs and behaves correctly with the flag on; nothing is half-wired.
- **Each step is tested by its own rows.** Every brief row belongs to exactly one step. Put the smoke row and the flag-off row in step 1 (the coordinator copies them into every later step, because every run walks the smoke path).
- **Each step is within the limits** in section 2. If a step is still over, cut it again.
- **Keep related rules together.** Rules that share a state or a screen go in the same step.
- **Order by dependency.** A step only builds on steps before it (`depends_on`).
- **At most 7 steps.** If the feature needs more, say so in the first step's `goal`: it should be split into separate features, and the user decides.

## 4. Write it into spec.json

Always write `phases`, even for one step:

```json
"phases": [
  {"id": "P1", "name": "short name", "goal": "one sentence: what the user can do after this step",
   "covers": ["spec behaviours this step delivers, by the names used in screens/states/actions"],
   "rows": ["S1", "S6", "S7"],
   "depends_on": [],
   "size": "1 entry point · 2 screens · 3 rules · 4 states · 1 API call · 3 rows"}
]
```

- One entry means no slicing: it covers everything and lists every row.
- The checker refuses a brief row that is in no step or in two, a missing `goal`, `covers` or `rows`, and a missing `size` when there are several steps.

## 5. When the brief is one step of a sliced feature

If `brief.json` has `step`, this run builds only that step. Write the spec for that step only, and `phases` holds exactly that one step (copy it from `brief.json` → `step`). Never slice again.
