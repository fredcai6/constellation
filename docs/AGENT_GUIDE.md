# Agent Guide

Orientation for any agent working in this repository: what this project is for, where everything
lives, and what binds you before you write. Root pointer files (`CLAUDE.md`, `AGENTS.md`)
redirect here so there is one guide, not many. `README.md` is the human's page and may lag
this one; where they disagree, this file is right.

## What this is

Constellation is a framework for subagent-driven development. An engine walks a fixed template
of steps and hands you only the step in front of you — its imperative, its fields, its checks —
so instructions arrive when they are needed instead of all at once. The process is mechanical
so your attention goes to the work rather than to remembering the process, and the record of
what was done and why falls out of doing it, so a run can be set down and picked up cold by
someone who was not there.

Work runs as a hierarchy: human, conductor, worker. What each level may decide alone is written
in the **authority block** its run opens with — your principal, what you own, your latitude, and
where gaps go. High-level decisions stay with the human. That is the design, not a limit on it.

**Report what you found, never what would fill the field.** A field with no answer takes
`waived: <reason>` or `unknown: <reason>`, one journaled step. An intentional null is a result
like any other: you still return it, and you still say why. Missing information, or a question
your scope cannot answer, goes up the chain as far as the human. The level above may rule on it
and send it back down — that is the hierarchy working, not a rebuke.

If what you are asked to do has no visible connection to the run you are in, say so and ask up.
A discontinuity is a signal, and carrying it upward is what the channel is for.

**One name for one thing, so read the name here.** `standards/glossary.md` fixes what each
technical term means in this repo, which is not always what it means elsewhere — `anchor`,
`transition`, `corpus` and `move` all carry a local sense. When a word in a form could be read
two ways, look it up before you act on your reading. If the entry does not settle it, ask up:
*what do you mean by X* is a legitimate question at every level, and a term that keeps needing
it belongs in the glossary through the `key-terms` field.

Mechanically: a run is understand → plan → build → criticize → refine. Work happens in **runs**,
opened from an **assembly** — a fixed skeleton of **segments**, each a worklist of steps ending
in a **transition**. Every step is a **form**: an imperative and fields, which carry all the
doctrine there is. Runs nest by dispatch; orders flow
down as read-only **prefill**, evidence flows up as **returns**, and nothing else crosses. State
is a fold over a per-run TOML journal, nothing else. The engine is a secretary, never a guard.

This repo builds itself with itself: Constellation is both the system under development and the
framework that development runs through. Work here is about the framework more often than about
anything else, and a change to a form is real work.

**The decision procedure for every keep/kill call: structure that shapes an agent's thinking
stays; structure that audits an agent's behavior goes.** When a change would add a check on
what an agent did, look first for the field or imperative that would have shaped what it did
instead. `docs/V2_DESIGN.md` states the thesis in full, along with the corollary that settles
calls the thesis alone cannot.

That test decides what belongs in the system. A second question decides what is worth doing
now: **does fixing this change what an agent does at a step, or what a human sees when it
decides?** If neither, the finding is true and inert — record it and leave it. Real, cheap and
correct is not sufficient, which is what `standards/issue.md` says from the other side.

Adding guidance is not free: before writing more, ask whether a consolidation pass is due —
what the repo already carries that it no longer needs.

`standards/glossary.md` is the single largest file in corpus. Its growth is the intended
mechanism rather than drift — new terms enter it through the key-terms field precisely so a
meaning is written down once instead of reconstructed per reader. Pairs that can look like
padding at a glance — `run-an-issue` and `run-a-gate` each carrying their own `IMPASSE.toml`,
and `run-an-issue/forms/CLOSE.toml` beside `run-a-gate/forms/GATE_CLOSE.toml` — read that
length because each answers the same question at two different tiers in deliberately
different words (a plan a fourth round keeps failing, versus a diff one does). `run-a-gate`
has no `OPEN.toml` at all: its `ASSEMBLY.toml` states there is nothing to fill at open, so
gate-tier open carries no form and no words.

## How work happens

Work runs through the engine itself. `spine` with no arguments lists open runs; `spine
<work-id>` says where you are and what to fill; `spine open run-an-issue --title T --issue N`
starts one. Journals and response forms live at `.agent-work/<work-id>/`, gitignored — as are
`.code-map/` and `map/`. Nothing derived is ever committed; `docs/DERIVED_IS_CODE.md` says why.

## Repository organization

| Path | Holds |
|---|---|
| `engine/` + `spine` | the secretary: rail, forms, journal, install copy. |
| `assemblies/` | run templates, one directory each |
| `skills/<name>/` | one posture each: a `SKILL.md` and the forms only that skill fills |
| `standards/` | what binds writing and issues — see below |
| `tools/` | decoupled tooling: no verb, no step, no form field, no import from `engine/`. |
| `tests/` | the fast suite: no model calls |
| `evals/` | end-to-end runs against a real light model |
| `constellation.toml` | the palette, and the logical model tiers resolved at dispatch |
| `.worktrees/` | one git worktree per open issue-tier run, made and pushed by `open`, removed by `close` once the archive holds the record. Gitignored. |

## Documentation map

| Document | Source of truth for |
|---|---|
| `docs/AGENT_GUIDE.md` | this guide — purpose, layout, documentation map |
| `docs/V2_DESIGN.md` | the founding design: thesis, rulings, and the reasoning behind them. A starting point, not a target sheet; where it and the tree differ, the tree is right and the passage goes. |
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
