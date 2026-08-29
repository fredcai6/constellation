# Agent Guide

Orientation for any agent working in this repository: what this project is for, where everything
lives, and what binds you before you write. Root pointer files (`CLAUDE.md`, `AGENTS.md`)
redirect here so there is one guide, not many. `README.md` is the human's page and may lag
this one; where they disagree, this file is right about the repo and `docs/V2_DESIGN.md` is
right about the design.

## What this is

Constellation is a choreography for agent work: structured runs of understand → plan → build →
criticize → refine, driven by a small engine that acts as a secretary, never a guard. Work
happens in **runs**, opened from an **assembly** — a fixed skeleton of **segments**, each a
worklist of steps ending in a **transition**. Every step is a **form**: an imperative and
fields, which carry all the doctrine there is. Runs nest by dispatch; orders flow down as
read-only **prefill**, evidence flows up as **returns**, and nothing else crosses. State is a
fold over a per-run TOML journal, nothing else.

**The decision procedure for every keep/kill call: structure that shapes an agent's thinking
stays; structure that audits an agent's behavior goes.** When a change would add a check on
what an agent did, look first for the field or imperative that would have shaped what it did
instead. `docs/V2_DESIGN.md` states the thesis in full, along with the corollary that settles
calls the thesis alone cannot.

Two budgets bound every addition: engine code at **≤ 2,500 lines**, measured by
`palette:lines`, which counts lines of code and prints comments and docstrings beside that
number rather than in it (currently 1,660); and corpus — the authored artifacts an agent must
read before it can work (`skills/`, `standards/`, `assemblies/`, this file) — at **≤ 20,000
words** (currently ~14,860). No test enforces either. Both are alert thresholds, not walls:
crossing one is not a refusal, it is a prompt to stop and ask what the repo does not need
anymore, and whether a consolidation pass is due. Never trim an artifact just to bring a
number down — that spends real guidance to shrink an integer, which is not a win. A green
engine achieved by relocating lines into another component still counts as a miss: the cap
tracks what the engine costs, not what `palette:lines` sees. `tools/` is outside both caps by
ruling.

## How work happens

Work runs through the engine itself. `spine` with no arguments lists open runs; `spine
<work-id>` says where you are and what to fill; `spine open run-an-issue --title T --issue N`
starts one. Journals and response forms live at `.agent-work/<work-id>/`, gitignored — as are
`.code-map/` and `map/`. Nothing derived is ever committed; `docs/DERIVED_IS_CODE.md` says why.

## Repository organization

| Path | Holds |
|---|---|
| `engine/` + `spine` | the secretary: rail, forms, journal, install copy. Bound by the machinery cap. |
| `assemblies/` | run templates, one directory each |
| `skills/<name>/` | one posture each: a `SKILL.md` and the forms only that skill fills |
| `standards/` | what binds writing and issues — see below |
| `tools/` | decoupled tooling. Outside both caps by ruling: no verb, no step, no form field, no import from `engine/`. |
| `tests/` | the fast suite: no model calls |
| `evals/` | end-to-end runs against a real light model |
| `constellation.toml` | the palette, and the logical model tiers resolved at dispatch |

## Documentation map

| Document | Source of truth for |
|---|---|
| `docs/AGENT_GUIDE.md` | this guide — purpose, layout, documentation map |
| `docs/V2_DESIGN.md` | the design of record: thesis, rulings, budgets, waves. Read its prose as history and its rulings as live. |
| `docs/ENGINE_NOTES.md` | mechanics the spec does not state — not doctrine |
| `docs/DERIVED_IS_CODE.md` | why nothing generated is committed |
| `standards/prose.md` | how this repo writes |
| `standards/glossary.md` | one name for one thing |
| `standards/issue.md` | what an issue and an epic are |
| `standards/skill.md` | what a skill is and what it must carry |

## Run things through the palette

`constellation.toml`'s `[commands]` is the only place a runner is named. Reach the suite or the
map through the palette; each entry carries its own note on what it costs and why it is
written the way it is. `pytest.ini` keeps the agent evals out of the default run, so reaching
them is a choice: `palette:validate`, or `pytest evals`. They drive a real model.

## Before you write

- `standards/prose.md` — Rule 2 is the one that bites: one name for one thing, backed by
  `standards/glossary.md`. **Grep the glossary for the term you are introducing, not only the
  one you are replacing.** That check is what fails, and each failure ships a homonym.
- Writing a form field the engine acts on? Make it `kind = "decision"` and list the values in
  its note (`advance | rework | up. …`). The engine reads that line and refuses anything else,
  so the sentence the agent is given and the rule it is held to are one string. On any other
  kind the same punctuation is ordinary prose.
- `standards/issue.md` — an observation is a claim about a rev, so run its command against HEAD
  before planning against it. A defect that is real, cheap, and harmless is the easiest work to
  justify and the least worth doing.
