# Working in constellation

v2 of an agent-choreography system. **The thesis, and the decision procedure for
everything here: structure that shapes an agent's thinking stays; structure that
audits an agent's behavior goes.** When a change would add a check on what an
agent did, look first for the field or imperative that would have shaped what it
did instead.

Read `README.md` for the model in one page. `docs/V2_DESIGN.md` is the design of
record; treat its prose as history and its rulings as live — six of its claims are
known untrue and tracked in #24.

## Run things through the palette

`constellation.toml`'s `[commands]` is the only place a runner is named:

    palette:test       python3 -m pytest -q          # 193 fast tests, ~11s, no model calls
    palette:validate   test + pytest -m agent -q     # adds 7 real light-model runs, minutes
    palette:lint       python3 -m pyflakes engine
    palette:lines      the machinery cap's instrument
    palette:map        the derived code map, built at closeout, never committed

**`pytest.ini` lives outside this repo**, at `~/projects/pytest.ini`. Bare `pytest`
therefore runs all seven agent evals and spends real money. Use `python3 -m pytest`.
Tracked as #25.

## Two caps, neither enforced by any test

- **Engine ≤ 2,500 lines** — `engine/` + `spine`, measured by `palette:lines`. At 2,077.
- **Corpus ≤ 15,000 words** — authored artifacts an agent must read before it can
  work. At 13,854 counting this file, and ~60% of it reaches no agent at any step — which is #29.

`tools/code_map/` (3,356 lines) is outside both by ruling: no verb, no step, no form
field, no import from `engine/`.

## How work happens

Work runs through the engine itself. `spine` with no arguments lists open runs;
`spine <work-id>` says where you are and what to fill. `spine open run-an-issue
--title T --issue N` starts one. Journals and response forms live at
`.agent-work/<work-id>/`, gitignored — as are `.code-map/` and `map/`. Nothing
derived is ever committed.

## Before you write

- `standards/prose.md` — how this repo writes. Rule 2 is the one that bites: one
  name for one thing, backed by `standards/glossary.md`. **Grep the glossary for the
  term you are introducing, not only the one you are replacing.** That check has
  failed three rounds running, and each failure shipped a homonym.
- `standards/issue.md` — what an issue and an epic are, and the re-measure rule: an
  observation is a claim about a rev, so run its command against HEAD before planning
  against it. A defect that is real, cheap, and harmless is the easiest work to
  justify and the least worth doing.

## Traps that have cost real time

- **`tools/code_map/checks.py:36-41`** is a headed docstring saying `check` exits 1
  on this repo and must not be silenced. It exits 0, 7/7. It describes a different
  repo. Two reviewers have flagged it; one nearly gated on it. See #28 — several
  docstrings in that package still describe their predecessor.
- **A gate spec's `done` is shell-executed** (`engine/cli.py:383`). Prose in that
  field becomes a command and fails inside the dispatched child, after the work is
  done. Write a runnable one-liner. Tracked as #27.

## The backlog

Three epics: **#29** the corpus is not load-bearing · **#30** the engine advances
where it should refuse · **#31** implement, review, and adjudicate are three jobs
sharing one form. Each carries its claim, its evidence, and its unfiled findings.
Everything else is a child of one of them, or deliberately outside (#3, #19).
