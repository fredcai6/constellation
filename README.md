# Constellation

A choreography for agent work: structured runs of understand → plan → build → criticize →
refine, driven by a small engine that acts as a secretary, never a guard.

**The whole system:** Work happens in **runs**. A run is opened from an **assembly** — a fixed
skeleton of **segments**, each a worklist of steps ending in a **transition**. Every step is a
**form**: an imperative and fields, which carry all the doctrine there is. The **engine** (one
CLI, `spine`) says where you are, renders the current form, validates what you hand back, and
appends everything to a per-run TOML **journal** — state is a fold over the journal, nothing
else. Transitions look back (*what did we learn — does the plan hold?*) and mint what comes
next. Runs nest by dispatch: an **epic** run dispatches **issue** runs, an issue run dispatches
**gate** runs; orders flow down as read-only **prefill**, evidence flows up as **returns**, and
nothing else crosses. Every run is addressed by an explicit **work id** (`issue7c3f`,
`issue7c3f.g1`) and keeps its whole work package at `.agent-work/<work-id>/`; bare `spine`
lists all open runs with their titles. Each step names the **skill** that fills it — a posture, a few
hundred words. Any field may be answered `waived: <reason>` or `unknown: <reason>`; every
check's escape is one journaled step. That's it.

```text
constellation/
  README.md           this page
  docs/V2_DESIGN.md   founding spec — thesis, rulings, budgets, waves
  engine/             the secretary: 6 verbs, rail, install copy — ≤2,500 lines total
  assemblies/         run templates: run-an-issue, run-a-gate, explore-an-idea, and one per excursion
  skills/<name>/      one posture each: SKILL.md + the forms only that skill fills
  standards/          issue.md · skill.md · prose.md · understanding-moves.md · glossary.md
  tests/  evals/
```

The test for every addition: does it make "here is how work is done" shorter to state, or
longer? This page is the measure.
