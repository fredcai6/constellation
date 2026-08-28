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
- **verdict panel** — 0..n reviewers a transition dispatches, each cold and prefilled with
  focused criteria; verdicts return to the transition. Any revise refills, findings merged.
  Review never lives in an interior.
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
  note lists (`pass | revise | escalate`). One string, so what the agent is told and what the
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
  plan artifacts, notes; child runs nest inside. Derived from the id, visible to everyone.
- **journal** — the per-run append-only TOML record in its work location; run state is a fold
  over it.
- **ledger** — the on-demand listing of open runs (bare `spine`): id, title, position, state;
  generated from journals, never stored.
- **model tier** — a logical dispatch weight (`light | standard | heavy`) named by assemblies
  and gate specs; the command palette maps it to a concrete runner.
- **conductor** — the one persistent agent of an assembly; pumps its interior mechanically,
  judges only at transitions.
- **proof** — a gate spec's command, run by the engine at submit: it passes once the
  gate's work is done and fails while it is not. Its exit status decides the step; a
  command that passes on an empty diff proves nothing.
- **gate** — a unit of execution minted by the plan; runs as a child run (run-a-gate) with the
  implementer working its interior and firing its review transition.
- **epic** — one claim too large for a single run, plus the evidence that the claim is true.
  Runs as run-an-epic under the admiral, dispatching issue runs. Never a list of issues.
- **wave** — a segment of an epic whose interior dispatches whole issue runs. The admiral cuts
  a wave from the epic's findings and adjudicates at its transition.
- **finding** — something real that was observed and recorded, and is not yet work. A reviewer's
  finding classed `beyond`, and an epic's unfiled finding, are the same thing at two scopes.
- **re-measure** — run an observation's own command against HEAD before planning against it.
  An issue is a claim about a rev; re-measuring is what makes it a claim about now.
- **prefill** — the parent's dispatch fields, stamped read-only into a child's opening. The
  order; contested by a blocked note up, never edited.
- **return** — the child's terminal fields, stamped into the parent's waiting step at close,
  including the child's amend summary.
- **authority block** — who your principal is, what you own, your latitude, where gaps go;
  derived at dispatch, never authored.
- **pivot criteria** — what changes the plan, not only what ends it.
- **command palette** — `constellation.toml`: the host repo's commands, which a gate spec's
  check field reaches by name rather than spelling out, and the model-tier table.
- **spec** — the statement of the problem a plan answers to, as its critic receives it. One name
  for a part two assemblies fill differently: run-an-issue's consolidate output,
  explore-an-idea's SPEC.toml artifact. A cold reader is told it holds a spec and a plan, never
  which document upstream produced the spec — that name is the assembly's business and nothing
  the reader can act on. Distinct from **gate spec** below, which is orders for work rather than
  a statement of a problem; the two never appear in one reading.
- **gate spec** — the purpose, scope, proof and optional model a conductor writes per gate at
  plan-to-execute; minted as that gate's dispatch and carried into the child run as read-only
  prefill. The orders a gate is run from, and the only place a runner is named.
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
  assemblies — measured in words against the 15,000 target (`docs/V2_DESIGN.md`, Measurable
  goals). Derived output is not in it. *The mappable corpus:* every tracked `.py` file the map
  is built from, which is the sense `tools/code_map` uses throughout its own docstrings.
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
- **ideas board** — the explore segment's board: a tree of ideas and threads grown and shaped
  across cycles, never drained. An open row is the point; the human's converge releases.
- **cycle** — one firing of the explore transition: consolidate the board, then the human says
  `cycle`, `converge`, or `shelve`.
- **flavor** — a cycle's mode, the human's pick: `shotgun` diverges, `compare` weighs a few
  seriously, `refine` hardens one.
