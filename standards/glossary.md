# Glossary

One name for one thing. This page is where a human and an agent fix the same meaning for a
word, so it holds the terms that mean something specific to this project — the ones an ordinary
reading would get wrong. A word whose everyday sense is already right stays out: an entry for it
is a second place to look up a definition that already has one. An engine verb is defined by
`spine --help` — it is what the engine does, not a meaning two parties have to agree on — so one
appears below only where the word carries a second sense here: `close` and `up` name an outcome a
form's `does` field takes as well as a command, and `wait` starts the child it then blocks on,
which is the opposite of what the word ordinarily promises.

That is why a term enters only once it has crossed to the human and the human has used one back.
It is proposed through the key-terms field on understanding and plan forms, and the
acknowledgement admits it: both sides using the word is the only evidence that the understanding
is joint. Coining a synonym for a term below is a defect.

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
  and prefilled with focused criteria; verdicts return to the transition. Each panelist's own
  form teaches its own vocabulary — most declare `pass | revise`, but this is read from the
  form, never assumed as a fixed pair. `verdict_fold` (`engine/run.py`) folds the panel's
  returns to one panel-wide outcome, one of three per-voice/panel kinds — **clean**, **refused**,
  **quiet** — never a merged verdict computed as a bare majority or a hardcoded word. A `clean`
  fold resolves the same way a submitted decision field does — against the transition's own
  declared `outcome` rows where one names a `decides` field (most panels now hold either verdict
  open for a conductor's own route form there), or (a panel-only transition with none,
  explore-an-idea's spec) by refilling directly, `impasse-after` rounds of it reaching the
  segment's own impasse form where one is declared. A panel is written once, at the mint that
  makes its step: declared on a transition, never grown after — with, optionally, a
  `rework-panel` the transition's later rounds get instead (run-a-gate's one rework reader). A transition also declares which of its rounds the panel reads —
  `panel-rounds = "every"` (the default) or `"opening"`, the run's opening round alone, which is
  run-an-issue's plan seam: a later cut stands the conductor's route form with no panel beside
  it. Review never lives in an interior.
- **clean** — one of `verdict_fold`'s three per-voice/panel outcomes (`engine/run.py`): a
  voice's return whose leading word is inside that voice's own form's declared vocabulary, or
  (panel-wide) the panel's own clean word once a refusal and total quiet are both ruled out.
  See **verdict panel**.
- **refused** — one of `verdict_fold`'s three per-voice/panel outcomes: a voice's own form
  declares a vocabulary but the return's leading word is not in it (missing, empty, or
  foreign), or the voice's own form could not be loaded at all. A refusal from any voice is
  the whole panel's own outcome, naming that voice, ahead of any clean word a co-panelist
  returned. Printed at every surface that reports a panel round as **unreadable**.
- **quiet** — one of `verdict_fold`'s three per-voice/panel outcomes: a voice's own form
  declares no `verdict` field at all. No panel in the tree is quiet today; the fold answers
  for the shape anyway, and `tests/test_verdict_fold.py` holds both the single-voice and the
  panel-wide case. A panel folds to quiet only once every voice is quiet; one
  voice whose form declares a vocabulary takes the whole panel out of quiet eligibility even
  where that voice's own return is itself clean.
- **unreadable** — the word `verdict_record` (`engine/run.py`) prints for a **refused**
  outcome, at every surface that reports a panel round — the room's own line, the close
  summary, the review yield — followed by the refusing voice's own tag, e.g. `unreadable p2`.
- **anchor** — one word, two senses. The rule above bars a second name for one thing; it does
  not bar one name for two, and these two never appear in the same reading. *In a run:* a
  template step flagged so that amending it away is loud in the ledger and the parent's
  adjudication view — still one journaled step to amend, never a refusal. *In the map:* an
  authored identity for a definition or a purpose — a comment line holding only a bracketed
  kebab slug, directly above what it names: `# [stable-id]` in Python, `<!-- [stable-id] -->`
  in markdown, each language's own way of hiding a line from its own reader. Minted on demand;
  the one fact about a definition the map stores instead of deriving.
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
- **incorporate** — an outcome verb at run-an-issue's spec and plan seams: the writer's one
  pass over the panel's findings (those called `writer`, where a `calls` table is present),
  the conductor's `orders` ahead of them, taken or rejected on the writer's own judgement. The
  round it mints carries no panel, and a second incorporate on the same artifact refuses: what
  comes back is released (the one-look ruling, 2026-09-25).
- **rewrite** — an outcome verb at the same two seams, for a `severe` finding — one that
  changes which problem the run is solving, or the fundamental thing its next step codes. A
  fresh artifact written from the conductor's `orders` alone, forward-looking, with no findings
  and no draft carried; its round restarts the send-back count and carries its own panel.
- **skip** — an outcome verb: amend-closes every not-done, non-terminal step of the named
  segment. Its own terminal step is excluded, so sweeping a segment's gates never closes the
  run's own close step sitting not-done alongside them.
- **remint** — an outcome verb: mints a fresh dispatch/adjudication pair off the gate rows in
  the field the `does` string names — the same mint a plan field first drove them through.
- **close** — an outcome verb: closes the not-done step the decided field's own argument
  names, plus every step sharing its `child` — a pair closes together, and the deciding step
  can never target its own pair.
- **up** — the bare CLI verb in `main()`'s dispatch table (`engine/cli.py`'s `verbs` dict,
  alongside `status`/`submit`/`note`/`amend`/`close`/`trace`/`wait`), and the value `pause`'s own
  outcome rows accept: the asker stops what it holds, the question stands one tier up in the
  run that dispatched it, and — once that run answers — the answer returns as the resumed
  unit's own orders, the same prefill shape `rework` already carries its own findings in.
- **pause** — an outcome verb, declared wherever an outcome row's `does` field reads `pause`
  or `pause <segment>` (grep the assemblies for `does = "pause`): mints an ask into the run
  that dispatched this one — a step standing on
  the still-live pair that dispatched it, reordered ahead of it, so the parent sees the ask
  without opening the child — and a paused marker here, in place of the round it decided at.
  The parent's own answer resumes that marker's segment as a fresh round, carrying the answer
  forward as prefill the same shape `rework` already carries its own findings.
- **paused marker** — the step `pause` mints in place of the round it decided at: no form, no
  panel, no dispatch, only the positive `paused` key naming the segment the parent's answer
  will resume. Recognized everywhere by that key, never by the absence of the other three,
  which `amend add --transition` already mints today with no pause behind it at all.
- **impasse** — a segment ruling reached once its transition has sent the same artifact back
  `impasse-after` times: the segment's own impasse form — not a fresh round — reaches whoever
  conducts it. Declared at run-a-gate's `work`, at 2, the loop itself being the question there.
  run-an-issue's spec and plan seams declare none: a send-back there is **incorporate** or
  **rewrite**, and neither loops (the one-look ruling, 2026-09-25). `advance`
  closes the segment on the artifact as it stands, over a live objection; `rework` is the answer
  only when it names what the round changes that a reading did not; `up` pauses the segment as
  an ask at the run that dispatched it, the same as any other pause.
- **rewrite-cap** — run-an-issue's spec and plan seams' own ceiling: how many **rewrite**s a
  seam may make before it releases, counted since the last release or since a pause's answer
  opened a round. At 1 (ruling, 2026-09-25): one major rewrite, then a second becomes an ask
  at the run's principal — the conductor's to answer only where the run's authority grants it.
- **round-cap** — a segment property beside `impasse-after`, in a different kind: a ceiling on
  the **round**s a **seam** sends back in a row, counted since the seam last released one
  (`engine/review_yield.py`'s `seam_round_steps_since_release`) — a release starts the count
  over, and so does a round a pause's answer opened (#177); a fresh artifact or an impasse
  ruling does not — where `impasse-after` counts one
  artifact's own rework rounds and resets on a new one. A round with no panel (run-an-issue's
  plan seam after the opening cut) counts once its conductor disposes of it. Declared on
  `run-a-gate`'s `review`; run-an-issue's spec and plan seams use **rewrite-cap** instead. Where a send-back
  would land the count at the cap, it mints an ask to the run's principal instead — naming the
  seam, the count, and the findings of every round counted — and `impasse-after`'s own outlet,
  where a segment declares one, is not consulted on that send-back: the cap outranks it where
  both would otherwise fire on the same round. At the issue tier the ask is the principal's to
  fill, never a form filler's.
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
  set it — never a fourth word beside them. `principal` is the one `filler` value that is not
  a role: the run's principal, outside the engine, holding the pen on the run's own close form
  and on an ask standing in the run's own journal — `drive` starts nothing there.
- **posture** — who an agent is at a step and how it carries it: a skill's stance, written at
  `skills/<role>/SKILL.md`. A brief names it as a path with the instruction to read it before
  starting; a role with no SKILL.md gets no posture line at all.
- **proof** — a gate spec's command, run by the engine at submit: it passes once the
  gate's work is done and fails while it is not. Its exit status decides the step; a
  command that passes on an empty diff proves nothing. Run once before that, too: the
  planner's own submit runs it, detached at the cut, against the run's tree as it stands
  and journals the result as a `check`, which the conductor's route room reads as one of
  three readings — resolved and failing before the work (healthy), passing on an empty
  diff (proves nothing), or not resolving at all (prose, an unknown palette name) — a
  report, never a refusal (#122). One outlives the handback and the room says so plainly,
  naming `wait`, rather than guessing a fourth reading (#163).
- **handback** — how long `submit` holds its caller before returning control, 90 seconds, the
  engine's own number and nothing a gate spec declares. A dispatched agent's harness moves a
  foreground command still running at about 120 seconds into the background and the turn ends
  there unwoken, so the engine returns first. Past the handback a gate's own check keeps
  running detached and the step stays open with its proof **in flight**; the process running
  it appends the outcome, so a passing proof still lands its own submit and a failing one
  still records none. A planner's own trial of a `proof` field past the handback keeps
  running the same way, but the step it belongs to already submitted and is not held open
  for it — its reading is collected later, at the route form (#163).
- **proof budget** — how long a proof may run before it is broken rather than slow. Declared
  per gate spec as `budget`, whole seconds, 600 where the spec declares none; a proof that
  outruns it is refused. Distinct from the handback, which bounds the caller's wait rather
  than the proof — the planner's own trial of the proof at the cut is bounded by the budget
  alone, detached past the handback rather than killed at it, and reports a proof that
  outran the budget itself rather than one merely still running.
- **gate** — a unit of execution minted by the plan; runs as a child run (run-a-gate) with the
  implementer working its interior and the gate-conductor ruling, at the route form, on the
  panel that reviews it.
- **epic** — one claim too large for a single run, plus the evidence that the claim is true.
  Runs as run-an-epic under the epic-conductor, dispatching issue runs. Never a list of issues.
- **wave** — a segment of an epic whose interior dispatches whole issue runs. The epic-conductor cuts
  a wave from the epic's findings and adjudicates at its transition.
- **finding** — something real that was observed and recorded, and is not yet work. Two
  destinations, never a third (docs/PURPOSE.md): done now, or dropped with its reason recorded
  where a later run can find it. A reviewer's finding a route form calls `rejected: <reason>`,
  and an epic's unfiled finding, are the same shape at two scopes.
- **call** — one route-step ruling on a single finding raised against the artifact it names —
  a panel's finding at either tier, or (a gate's own) a declared deviation too. The words are
  the route form's own: `blocking | accepted | rejected: <reason>` at a gate's review, and
  `writer | severe | rejected: <reason>` at run-an-issue's spec and plan seams, where the call
  says where the finding goes — to the writer's one pass, to a **rewrite**, or dropped. Every
  panel-bearing transition's own route form carries the field. Distinct from the issue tier's **disposition**
  (`GATE_TRANSITION.toml`'s `dispositions` field): a call judges one finding or deviation once;
  a disposition judges one obligation across the run's whole life.
- **review yield** — a closed run's own record of its review seams, derived and printed at
  close (`engine/review_yield.py`): rounds per seam, findings per round, and each finding's
  call where a route form ruled on one. Written beside `CLOSE.toml` as `YIELD.md`, and reachable
  on a live run through `spine <work-id> trace --yield`. Nothing a conductor tabulates by hand.
- **seam** — a panel-bearing transition (`engine/review_yield.py`'s `_seam_segments`): a segment
  whose transition declares a panel (`run-an-issue`'s consolidate and plan-to-execute,
  `run-a-gate`'s review, explore-an-idea's spec). Named for a human by `seam_label` — the
  transition's own id where it declares one (review), else the disposing form's own name, else
  the segment's own id.
- **round** — one disposal of one artifact at a seam: a panel dispatch where the round carries a
  panel, the conductor's route form alone where it does not (run-an-issue's plan seam after the
  opening cut) — the count `run.rework_rounds` uses plus the first — `engine/review_yield.py`'s
  `seam_round_steps`, blind to which mint produced the step (`skeleton()`'s own, a later
  `rework`), so it counts a seam's rounds since the run opened rather
  than per artifact; the **round-cap** reads the same list cut at the seam's last release.
- **re-measure** — run an observation's own command against HEAD before planning against it.
  An issue is a claim about a rev; re-measuring is what makes it a claim about now.
- **dispatch** — a step (a gate dispatch, or one panel entry) naming a child run for the engine
  to start itself, through the repository's own `dispatch` command-palette entry — handing that
  harness the same brief its own room renders. Names the step, not the child run it opens nor
  the CLI verb that opens it. The `not dispatched -> working` transition happens only through
  `wait` now (gate 2) — rendering the step starts nothing.
- **liveness** — whether a dispatched child's own process is still there: `checks.alive` read
  against the pid its own `dispatch-started` record carries (a pid this reader may not signal
  reads as alive, the same rule a check's own in-flight proof already reads by). Read per child,
  never per step, and folded with whether that child has itself returned into the one of four
  words a room reports for it: not dispatched, working, gone without returning, returned.
- **wait** — the CLI verb (`spine <work-id> wait`) that blocks while the current step's child is
  outstanding, re-folding the journal every poll cycle until none is left or a bound
  (`checkrun.WAIT_BOUND`, overridable with `--for <seconds>`) expires, then renders exactly what
  `status` renders. The **sole** starter of a child never dispatched at all, and the capped
  **restarter** of one gone without returning, up to `checkrun.MAX_STARTS` attempts — no render
  starts or restarts a child any more (gates 2 and 4).
- **outstanding** — a dispatch or panel step's child not yet returned, split into the two shapes
  `wait` treats differently: the **startable** case — never dispatched, or dead and short of
  `checkrun.MAX_STARTS` (`_startable`, `engine/cli.py:672`) — where `wait` will start or restart
  it; and the **spent** case — dead and already at that cap, the "gone without returning --
  starts spent" row (`engine/cli.py:831`) — where nothing is left for `wait` to do, and the
  ruling escape is to drop the step instead.
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
  the board. Judged by a cold critic panel on the segment's transition, the same panel
  plan-to-execute's own transition carries. Both of the panel's own words release now (ruling 3's
  2026-09-03 follow-up): `CONSOLIDATE.toml` is the conductor's own route form here too, the same
  shape plan-to-execute's `PLAN_TO_EXECUTE.toml` already has. A spec states the problem — what
  is being solved, why, where it stops, how anyone would tell it is done — and gets one look:
  the conductor's **incorporate** hands the writer the panel's findings to take or reject, and a
  **rewrite** starts a fresh spec from the conductor's orders. There is no rework-form: the
  step-form (this same round's own `SPEC.toml`) refills for both.
- **gate spec** — the purpose, scope, proof and optional model, optional direction a planner
  writes per round of the plan segment — one gate spec per round, the round's own artifact.
  Plan-to-execute projects it, unauthored a second time, into that gate's dispatch as read-only
  prefill. The orders a gate is run from, and the only place a runner is named.
- **projection** — a transition whose own segment declares `projects` carrying a just-released
  round's gate fields (`purpose`, `scope`, `proof`, `budget`, `model`, `direction`) forward into
  a fresh gate at submit, rather than asking a conductor to retype what the panel already judged.
  Walks the segment backward for the most recent round that ever carried a gate field, so an
  impasse `advance` — whose own ruling form carries none — still finds the round it actually
  approved.
- **horizon** — the gates likely to follow the one a plan round just cut, coarsely, and the
  conditions that would change them. Sits beside the gate spec on the same round; whoever
  judges the cut reads it, provisional by construction and never attacked at gate grain, and it
  never crosses into the implementer's own prefill — the gate ahead is this one alone.
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
  assemblies. Derived output is not in it. *The mappable corpus:* every tracked `.py` file
  the map is built from, which is the sense `tools/code_map` uses throughout its own
  docstrings.
- **purpose** — why a definition exists, written beside it and anchored. Purposes form a
  hierarchy: each one names the purpose it serves, and those links are the rows of
  `map/parents.jsonl`, the one authored file in an otherwise derived map. A purpose with no
  row is an **orphan** — absence means unmapped, never mapped-to-nothing. A **root purpose**
  is where the hierarchy terminates: one of those anchored in the documents
  `constellation.toml`'s `[roots]` names, and never a node to climb past. A purpose sits on
  the definition that carries it out, so the next reader can check it against that code and
  contradict it; one no definition executes is not written down at all. `standards/purpose.md`
  is the whole of it.
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
  whether the incumbent holds. Named at a board row — one row, one rival — as an excursion the
  board asks for, never a shape a segment runs of its own accord.
- **ideas board** — the explore segment's board: a tree of ideas and threads grown and shaped
  across cycles, never drained. An open row is the point; the human's converge releases.
- **cycle** — one firing of the explore transition: consolidate the board, then the human says
  `cycle`, `converge`, or `shelve`.
- **flavor** — a cycle's mode, the human's pick: `shotgun` diverges, `compare` weighs a few
  seriously, `refine` hardens one.
- **execution state** — run-an-issue's second board, seeded once (consolidate's `obligations`
  field) from the spec's own keyed obligations and worked in place afterward: the gate claims
  the rows it settles at its close, and its adjudication accepts or contests each claim onto the
  row. `execute`'s `advance` and `drop` outcomes both read it, and `spine close` reads it once
  more — whichever of those a run's own route to its terminal step actually takes — a row still
  `open`, or claimed `owed:`, refills the plan segment for another round; every other word mints
  nothing and the run walks on. At close, each `satisfied` row's gate proof runs again against
  the finished tree, and a row it no longer holds up is written back `owed:`.
- **obligation** — one row on the execution-state board: something the spec requires, keyed,
  and the disposition it settles to — `satisfied | deferred | invalidated | handed-off |
  rejected`, each with a reason folded into the status the way `deferred: <reason>` already
  reads elsewhere. `owed: <reason>` is the one word that is a claim without a disposition: a
  gate says the obligation was not its own to satisfy, the reason says why, and it never names
  who takes it next — the gate closing it out rarely knows, and the plan round after it may not
  decide either. An `owed` row counts exactly as `open` does: the run cannot reach its terminal
  step while one stands. The gate cut against it claims the word at close, with the root that
  shows it (`GATE_CLOSE.toml`'s `claims`); the issue-conductor accepts or contests the claim
  (`GATE_TRANSITION.toml`'s `dispositions`). `open` until disposed, or claimed `owed`;
  `satisfied` is the one word re-checked, by its gate's proof at close.
