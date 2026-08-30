# Glossary

One name for one thing. New terms enter through the key-terms field on understanding and plan
forms; coining a synonym for a term below is a defect.

- **run** — one instantiated pass through an assembly, addressed by its work id, recorded in
  its journal.
- **assembly** — a run template: a fixed skeleton of segments, each transition naming what its
  plan field may mint and which skill fills each step.
- **segment** — the engine's one structural concept: an ordered interior of items — steps or
  nested segments — ending in one transition. *Phase*, *gate*, and *wave* are segment names,
  not engine concepts.
- **interior** — a segment's mutable contents, one of two kinds: a **worklist** of steps
  (grown, pruned, and reordered by amend; exhausted means the segment ends) or a **board**.
- **board** — an expansive segment's interior as a living TOML document in the work location:
  seeded at entry, worked freely in place, validated by the engine at the transition. The
  understand board; the explore ideas board. Blocked is per-row, never per-run; a row
  resolves by prose evidence, an artifact, or a dispatched child's returns.
- **askable** — a board row workable right now: its own status is `open`, and no id in its
  `after` is `open` or `up`.
- **held** — a board row whose own status is `open` and one or more of whose `after` ids is
  `open` or `up`; those ids are what it is held by.
- **cluster** — an optional tag grouping board rows taken to the principal in one sitting. A
  cluster is ready when it has at least one open row and every open row in it is askable.
- **moot** — a board row settled by another row's answer rather than its own. The answer that
  mooted it is recorded as prose in its own `answer`; which row did the mooting is not
  recorded anywhere, and nothing needs it.
- **transition** — one word, two senses, on the same grounds as `anchor`. *A segment's exit
  gate:* fires when the interior drains, and each firing releases, refills the interior, or
  goes up. The OODA beat; cycling is re-firing. *An outcome verb:* mints the named segment's
  own transition step alone, without refilling its interior — `advance`'s move over a live
  revise, distinct from `release`, which mints nothing at all.
- **verdict panel** — 0..n panelists a transition dispatches, each reading from fresh context
  and prefilled with focused criteria; verdicts return to the transition. The panel's vocabulary
  is `pass | revise`, never a third word: a panel that judges the artifact itself wrong to build
  writes that as a revise finding, the same as any other. Any revise refills, findings merged.
  The merged verdict resolves the same way a submitted decision field does — against the
  transition's own declared `outcome` rows where one names a `decides` field, or (a panel-only
  transition with none) by refilling directly, three rounds of it reaching the segment's own
  impasse form where one is declared. A panel is written once, at the mint that makes its
  step: declared on a transition, or named at an earlier one (run-a-gate's `select`), never
  grown after. Review never lives in an interior.
- **anchor** — one word, two senses. The rule above bars a second name for one thing; it does
  not bar one name for two, and these two never appear in the same reading. *In a run:* a
  template step flagged so that amending it away is loud in the ledger and the parent's
  adjudication view — still one journaled step to amend, never a refusal. *In the map:* an
  authored identity for a definition — a comment line holding only a bracketed kebab slug,
  `# [stable-id]`, directly above what it names. Minted on demand; the one fact about a
  definition the map stores instead of deriving.
- **form** — one step's imperative, fields, and field notes; the unit that carries doctrine.
- **field kind** — how a field is satisfied: `check`, `evidence`, `artifact`, `decision`,
  `plan`. A field takes `waived: <reason>` or `unknown: <reason>` in place of an answer —
  except a `decision` whose note declares a vocabulary, where the values are the whole of
  what it accepts.
- **vocabulary** — the values a `decision` field accepts, read from the alternatives its own
  note lists (`pass | revise`). One string, so what the agent is told and what the
  engine enforces cannot drift. A value outside it refuses; the kind, not the punctuation, is
  what makes the note binding. A field its own segment `decides` is exempt — `outcome` rows
  enforce it instead, values and acts declared together.
- **outcome** — a `[[outcome]]` row, declared on a segment or (a gate-adjudication step's) its
  transition: pairs one legal value of the field its `decides` names with the verb(s) it
  `does`. The engine refuses a value no row declares and performs exactly the verbs a matched
  row names — no assembly's vocabulary lives in the engine.
- **decides** — a segment or transition key naming the field whose leading word selects among
  the segment's own `outcome` rows. The field's own note teaches the same values the rows
  declare; a mismatch between them is a defect the field-note check holds to.
- **release** — an `outcome` row's default `does`, needing no verb word at all: mints nothing,
  the run walks on to whatever already follows.
- **refill** — an outcome verb: a fresh round of the named segment, carrying the deciding
  submit's own fields forward as prefill — a board segment's fresh transition step, or a
  worklist segment's fresh round.
- **rework** — an outcome verb: a fresh round of the named segment through its `rework-form`
  (or its `step-form` where none is declared), carrying forward the deciding step's own
  prefill — what caused the impasse — rather than the ruling fields just submitted. Where
  `refill` forwards what was just decided, `rework` forwards what was already there.
- **skip** — an outcome verb: amend-closes every not-done, non-terminal step of the named
  segment. Its own terminal step is excluded, so sweeping a segment's gates never closes the
  run's own close step sitting not-done alongside them.
- **remint** — an outcome verb: mints a fresh dispatch/adjudication pair off the gate rows in
  the field the `does` string names — the same mint a plan field first drove them through.
- **close** — an outcome verb: closes the not-done step the decided field's own argument
  names, plus every step sharing its `child` — a pair closes together, and the deciding step
  can never target its own pair.
- **plan field** — a field whose submitted content is minted as steps: the next segment's
  interior, a gate's spec.
- **work id** — a run's address: the tracker issue's number when one exists (`issue17`),
  `<kind><hash>` otherwise (`issue7c3f`); children by suffix (`issue17.g1`). The title holds
  the "what." Required on every call, never inferred.
- **work location** — a run's work package, `.agent-work/<work-id>/`: journal, response forms,
  plan artifacts, notes; child runs nest inside. A dotted work id nests one directory per
  segment rather than sitting in one directory named for the whole id: `issue17.g1` lives at
  `.agent-work/issue17/g1/`. Derived from the id, resolved against whichever tree actually
  holds it — this checkout's own `.agent-work/`, or a sibling worktree's, never assumed. A
  stored artifact path is work-location-inclusive: recorded whole (`.agent-work/<work-id>/plan.md`),
  not relative to some other root.
- **worktree** — the git worktree an issue-tier run opens into: `open` makes it at
  `<top-level checkout>/.worktrees/<work-id>` on a pushed branch of the same name, before
  anything is journaled. Only the issue-tier root gets one; a gate dispatched under it nests its
  own work location inside that same worktree rather than opening a second one.
- **top-level checkout** — the git checkout a worktree is a sibling of: where `.worktrees/` and
  the archive live, and where `close` pushes the branch and opens the PR. One name throughout —
  never `<project>`.
- **archive** — where `close` moves a closed issue-tier run's work location, `.agent-work/archive/`
  in the top-level checkout, once the PR is pushed and before the worktree is removed, so
  sweeping the worktree does not take the record with it — nested the same way work location
  itself nests: `issue17.g1` archives to `.agent-work/archive/issue17/g1/`. Still
  under `.agent-work/`, so still gitignored — not a separate call a repo makes.
- **journal** — the per-run append-only TOML record in its work location; run state is a fold
  over it.
- **ledger** — the on-demand listing of open runs (bare `spine`): id, title, position, state;
  generated from journals, never stored.
- **model tier** — a logical dispatch weight (`light | standard | heavy`) named by assemblies
  and gate specs; the command palette maps it to a concrete runner.
- **conductor** — the one persistent agent of an assembly; pumps its interior mechanically,
  judges only at transitions.
- **role** — who fills a step: a step's own `filler` field, the bare `conductor` unwrapped to
  the assembly's own conductor; a board segment's `board-worker` (or its `-delegated` variant,
  once the run has a parent); or a panel entry's `worker`. One name for whichever of the three
  set it — never a fourth word beside them.
- **posture** — who an agent is at a step and how it carries it: a skill's stance, written at
  `skills/<role>/SKILL.md`. A brief names it as a path with the instruction to read it before
  starting; a role with no SKILL.md gets no posture line at all.
- **proof** — a gate spec's command, run by the engine at submit: it passes once the
  gate's work is done and fails while it is not. Its exit status decides the step; a
  command that passes on an empty diff proves nothing.
- **gate** — a unit of execution minted by the plan; runs as a child run (run-a-gate) with the
  implementer working its interior and the gate-conductor naming, at `select`, the panel that
  reviews it.
- **epic** — one claim too large for a single run, plus the evidence that the claim is true.
  Runs as run-an-epic under the epic-conductor, dispatching issue runs. Never a list of issues.
- **wave** — a segment of an epic whose interior dispatches whole issue runs. The epic-conductor cuts
  a wave from the epic's findings and adjudicates at its transition.
- **finding** — something real that was observed and recorded, and is not yet work. A reviewer's
  finding classed `beyond`, and an epic's unfiled finding, are the same thing at two scopes.
- **call** — one route-step ruling on a single review finding or declared deviation, read once
  against this gate's own diff: `blocking | accepted | beyond | rejected`. Distinct from the
  issue tier's **disposition** (`GATE_TRANSITION.toml`'s `dispositions` field): a call judges
  one finding or deviation once; a disposition judges one spec commitment across the run's
  whole life.
- **re-measure** — run an observation's own command against HEAD before planning against it.
  An issue is a claim about a rev; re-measuring is what makes it a claim about now.
- **prefill** — the parent's dispatch fields, stamped read-only into a child's opening. The
  order; contested by a blocked note up, never edited.
- **return** — the child's terminal fields, stamped into the parent's waiting step at close,
  including the child's amend summary.
- **brief** — one dispatch's whole orders, rendered identically for a gate and a panelist by
  `render.brief` so the two never drift: role, posture, tier, runner, the open command, how to
  finish. An excursion's board row is its brief instead — either way, fresh context's whole
  handoff.
- **fresh context** — what a reader holds at a boundary: the artifact in front of it and the
  codebase, and nothing from the work that produced the artifact. The default at every step
  boundary, and what a panelist reads from by design, so the form is the whole handoff.
- **authority block** — who your principal is, what you own, your latitude, where gaps go;
  derived at dispatch, never authored.
- **pivot criteria** — what changes the plan, not only what ends it.
- **command palette** — `constellation.toml`: the host repo's commands, which a gate spec's
  check field reaches by name rather than spelling out, and the model-tier table.
- **spec** — the statement of the problem a plan answers to, as its critic receives it. One name
  for a part two assemblies fill differently: run-an-issue's own SPEC.toml artifact, written by
  the spec-writer and carried forward by consolidate; explore-an-idea's SPEC.toml artifact. Both
  are standalone — written so a reader with no tracker reach can plan from the document alone,
  never a delta against an issue only the reader could resolve by holding it too. A fresh-context
  reader is told it holds a spec and a plan, never which document upstream produced the spec —
  that name is the assembly's business and nothing the reader can act on. Distinct from
  **gate spec** below, which is orders for work rather than a statement of a problem; the two
  never appear in one reading.
- **spec writer** — the hat the persistent conductor wears to draft the spec, understand's own
  step-form round (`skills/spec-writer/`), distinct from the interrogator hat it wears to work
  the board. Judged by a cold critic panel on the segment's transition, the same shape
  plan-to-execute uses to judge a plan; a revise refills the round, findings as prefill, and
  there is no rework-form — a second round is another first cut, not a patch.
- **gate spec** — the purpose, scope, proof and optional model, optional direction a planner
  writes per round of the plan segment — one gate spec per round, the round's own artifact.
  Plan-to-execute projects it, unauthored a second time, into that gate's dispatch as read-only
  prefill. The orders a gate is run from, and the only place a runner is named.
- **horizon** — the gates likely to follow the one a plan round just cut, coarsely, and the
  conditions that would change them. Sits beside the gate spec on the same round; the critics
  read it, provisional by construction and never attacked at gate grain, and it never crosses
  into the implementer's own prefill — the gate ahead is this one alone.
- **map** — the derived page tree under `map/`: one page per entity, a module index per module,
  one top index. Built by `tools/code_map` — the generator, and that is its only name — through
  `palette:map`; gitignored, regenerated at closeout, never committed. The artifact, not the act
  of making it.
- **entity** — a mapped definition: one function or class, named by its enclosing scope's symbol
  plus its own name. The unit the map gives a page to.
- **hole** — a mapped entity or module with no docstring, so the map has nothing to say about
  what it is for. Counted per module and repo-wide in the map's report.
- **corpus** — one word, two senses, on the same grounds as `anchor`. *The v2 corpus:* the
  authored artifacts an agent must read before it can work — skills, forms, standards,
  assemblies — measured in words against the target `docs/AGENT_GUIDE.md` sets.
  Derived output is not in it. *The mappable corpus:* every tracked `.py` file the map
  is built from, which is the sense `tools/code_map` uses throughout its own docstrings.
- **delivery** — the engine actually rendering a word or line into `status`'s output, not
  merely a form or skill claiming it will. `render.py`'s whole job; a corpus sentence
  describing a delivery the engine does not make is a promise nothing keeps.
- **understanding** — a board row type beside `fact` and `decision`: the reading you are
  proceeding on, resolved only by the principal confirming or correcting it. Sent up as a
  mirror — one sentence, no options. Common understanding is the state where you and the
  principal would describe the problem in the same words.
- **frame** — what a board row is about: `capability`, `use-case`, `event`, `constraint`,
  `assumption`. Orthogonal to its type, which is what it resolves to.
- **move** — how a board row gets settled: `read`, `trace`, `reproduce` or `evidence-loop`
  worked in place, or an excursion dispatched as a child run; `ask` for a decision, `mirror`
  for an understanding. The row's `move` column names the in-place one; `excursion` owns the
  dispatched one.
- **excursion** — a move dispatched as a child run to answer one named question, opened from a
  board row, which is its brief; its return lands under the row. Returns a scoped verdict and
  the command that regenerates it. Four kinds, each its own form: prior art, prototype,
  picture, rival.
- **rival** — a design produced against an incumbent under one named constraint, to test
  whether the incumbent holds. Design-it-twice, without the count.
- **design-it-twice** — ruling 10: a plan segment's first round dispatches the planner and two
  more, each under a constraint chosen to open a different path; the conductor picks or merges
  before the critic panel reads any of them. Read once, on round one, from a `panel` declared
  on the segment itself rather than its transition; a rework round re-argues nothing, so it
  never reads it. `criteria` is the shared field a verdict panel and this one both carry — a
  criterion when the sibling judges, a constraint when it authors.
- **ideas board** — the explore segment's board: a tree of ideas and threads grown and shaped
  across cycles, never drained. An open row is the point; the human's converge releases.
- **cycle** — one firing of the explore transition: consolidate the board, then the human says
  `cycle`, `converge`, or `shelve`.
- **flavor** — a cycle's mode, the human's pick: `shotgun` diverges, `compare` weighs a few
  seriously, `refine` hardens one.
- **execution state** — run-an-issue's second board, seeded once (consolidate's `obligations`
  field) from the spec's own numbered commitments and worked in place afterward: a gate's own
  adjudication disposes the rows it settles. `execute`'s `advance` reads it at every gate's
  commit — an open row refills the plan segment for another round, every row disposed mints
  nothing and the run walks on. Unvalidated, like the ideas board: the engine reads dispositions
  and refuses nothing.
- **obligation** — one row on the execution-state board: a spec commitment, and the disposition
  it settles to — `satisfied | deferred | invalidated | handed-off | rejected`, each with a
  reason folded into the status the way `deferred: <reason>` already reads elsewhere. `open`
  until disposed; no word here is checked against anything.
