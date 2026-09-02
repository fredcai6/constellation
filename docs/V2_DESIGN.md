# Constellation v2 Design

**Status:** the design of record, rulings by Tommy, last folded in 2026-08-29. This document
says what the system is and what it is ruled to become; where the tree differs from a ruling,
the section says so in place. History lives in git.

## Thesis

One test decides every keep/kill call in this redesign: **structure that shapes an agent's
thinking stays; structure that audits an agent's behavior goes.**

The corollary that makes the test reproducible — and the actual lesson of v1's failures:
**a check may exist only if its escape is one journaled step available to the agent being
checked.** The five-step self-waive handshake failed this; `waived: <reason>` passes it. A
command check that verifies work is audit-shaped by the raw thesis, yet it stays — because its
escape is one step. When the thesis alone cannot settle a call, the corollary settles it.

The valuable, model-portable part of Constellation is the choreography — understand → refine →
criticize, cross-review with recorded evidence, design-it-twice, fresh context at boundaries.
Every recorded win comes from that side. Every recorded machinery failure comes from the other
side: enforcement refusing legitimate work. v2 rebuilds the system so the choreography is nearly
all that remains.

## The workflow

Three tiers, one shape. A **conductor** opens a run from an assembly, judges at its seams,
dispatches fresh subagents for everything else, and returns to the tier above. Orders go down
as read-only prefill; evidence comes up as returns; nothing else crosses. The tiers are named
for what they conduct:

| Tier | Conductor | Assembly | Unit | Dispatches |
|---|---|---|---|---|
| epic | `epic-conductor` | `run-an-epic` (not yet built) | one claim too large for one run | issue runs, in waves |
| issue | `issue-conductor` | `run-an-issue` | one issue | a spec writer, a planner, critics, and gate runs — one gate at a time |
| gate | `gate-conductor` | `run-a-gate` | one bounded diff | an implementer, then the reviewers it picks |

Beside the tiers, `explore-an-idea` (conductor: `explorer`) turns a muddy idea into a spec,
and the four excursion assemblies — `find-prior-art`, `build-a-prototype`, `draw-a-picture`,
`give-a-verdict` — each answer one question as a child run and return a scoped verdict.

**Every step is do → review → route.** A fresh subagent does the work; fresh subagents
review it from cold; the conductor routes — forward, back to do, or up. The conductor's own
hands touch only two things: the conversation with a live principal, and the route. Open and
close are the engine's, not an agent's. The tables mark each beat with who acts: *engine*,
*conductor*, or *subagent* — a subagent is always a new context.

**The issue tier.**

| Beat | Who | Form | Produces | Then |
|---|---|---|---|---|
| **open** | engine | — | the worktree at `<top-level checkout>/.worktrees/<work-id>` on a pushed branch; the work area at `.agent-work/<work-id>/`; the issue and the authority block captured as prefill | understand |
| **understand** · do 1 | issue-conductor with the human; a subagent under a delegated principal | `UNDERSTAND` board | every row answered, mooted, or deferred with a reason; decisions and understandings in the principal's words; excursions dispatched from rows, returns stamped to the row | do 2 |
| understand · do 2 | subagent, the spec writer | `SPEC` | the **problem specification** — standalone, every category considered, each obligation carrying a disposition | review |
| understand · review | critic subagents, cold | `CRITIC` | completeness and ambiguity: findings classed gap / beyond; `pass | revise` | route |
| understand · route | issue-conductor | the transition form | back to do 1 when information is missing; back to do 2 when it is there and the spec needs amending; forward when the spec is sufficient; up when the issue itself is wrong | the gate cycle |
| **gate cycle** · route | engine | — | every obligation in the spec has a disposition → close; otherwise → plan | plan, or close |
| **plan** · do | subagent, the planner — on the first round, two more planners beside it, each under a constraint the conductor picked to open a different path | `PLAN` (first cut), `REWORK` (a revise) | the **next gate** from the spec and what has landed, plus a coarse horizon | review |
| plan · review | critic subagents, cold | `CRITIC` | intent-fit, testability, simplicity, and replaceability where a component is uncertain: findings classed gap / beyond; `pass | revise` | route |
| plan · route | issue-conductor | `PLAN_TO_EXECUTE`; `IMPASSE` after three | pass → the **gate spec** (purpose, scope, proof, model, direction) minted as a dispatch and its review step; revise → back to do; up → an ask for help; after three rounds a ruling | execute |
| **execute** · do | subagent, the gate-conductor, as a `run-a-gate` child | the spec as prefill | the **gate report** — the diff on the worktree, residue, and the engine's record of cycles, verdict, checks, amends | review |
| execute · review | issue-conductor | `GATE_TRANSITION` | root-verify the returns; did the spec achieve the goal; what this gate taught | route |
| execute · route | issue-conductor | same form | **advance** commits the gate on the run's branch and records, in the run's execution state, the obligations it satisfied; **remint** cuts a fresh gate; **drop** closes a pending one; **replan** recuts; **up** asks for help | the top of the gate cycle |
| **close** | engine, then issue-conductor | `CLOSE` | the report the human or epic-conductor reads — what landed, evidence, decisions, open triage, residue; the work folder moved to `.agent-work/archive/<work-id>/` in the top-level checkout, out of the worktree's way; the PR pushed | returns to the parent, or the human |

**The gate tier.** The spec is the opening prefill, so there is nothing to fill at open.

| Beat | Who | Form | Produces | Then |
|---|---|---|---|---|
| **open** | engine | — | the gate's work area under its parent's; the spec as prefill | do |
| **do** | subagent, the implementer | `IMPLEMENT` | the change; deviations, including any forward-leaning fix; the proof command's output, run by the engine | select |
| **select** | gate-conductor | its own form | which reviewers read this diff — spec-fit and test adequacy by default, more where the diff calls for it — and why an omitted one was omitted, or `waived:` | review |
| **review** | reviewer subagents, cold | `REVIEW` | what was exercised and what was not; findings classed gap / beyond; `pass | revise` | route |
| **route** | gate-conductor | its own form; `IMPASSE` after three | each finding **blocking / accepted / beyond / rejected**; rework → do with the blocking findings as prefill; pass → close; up → an ask for help, the spec being wrong the usual reason | do, or close |
| **close** | gate-conductor | `GATE_CLOSE` | the residue; the engine appends the rest — together, the gate report. Nothing is committed here: git is the issue tier's | the parent's execute · review |

Where the tree differs today: understand is one segment, not two -- do 1 (the board) and
do 2 (the spec-writer's own round, in place rather than a dispatched subagent) share it, a
cold critic panel and the route sitting on its one transition; there is no `up` outcome
distinct from the interrogator's own impasse path. `run-a-gate` runs all six beats above, and
its `route` form now calls every review finding and every declared deviation
blocking/accepted/beyond/rejected, a `rework` carrying the blocking ones alone into the next
implement round. Its one-word `resolution` keeps `revise` beside the three words this table
names, because the review panel's own merged verdict resolves against that same outcome table
and an undeclared value refuses; `up` is a legal word at `route` now as well as at an impasse,
and at this tier both now pause the gate rather than releasing it -- an ask standing at the run
that dispatched it until that run answers, declared wherever an outcome row's `does` reads
`pause`. Wave 3b brings the tree to the shape above.

## Why now — measurements

*v1 measurements, taken before it was deleted — archival record, not a live count.*

- The v1 engine is 4,515 lines with 85 refusal sites. With its MCP wrapper (2,749), lifecycle
  (1,243), generator (1,089), and validator (758), the machinery totals ~10,000 lines.
- The skill corpus is ~57,000 words. A issue-conductor that obeys its own `context` steps reads
  20–30k tokens of doctrine before it reads the issue.
- The recorded machinery failures are the enforcement layer fighting itself: the archive-move
  lease deadlock, the five-step self-waive handshake, the Stop hook contradicting the HARD-band
  advisory. No recorded failure shows an agent harmed by these guards' absence.
- The AGENT_GUIDE's cardinal rule — "every addition should make 'here is how work is done'
  shorter to state, not longer" — fails against the current corpus.

## Layer 1 — the engine is a secretary

The engine keeps the plan straight. It says where you are, hands you the current step's form,
checks what you hand back, and keeps the record. It never proves who you are, never governs how
you work, and never needs its own documentation: every `status` output teaches the agent
everything it must know at that step.

### The run model: segments

The engine knows one recursive structural concept, the **segment**: an ordered interior of
items — each a step or a nested segment — ending in one **transition** step. Everything else is
vocabulary the assemblies put on top: a *phase* is a top-level segment, a *gate* is a segment
minted into an execute phase, an epic's *wave* is a segment whose interior dispatches whole
child runs.

- **The skeleton is fixed; interiors come in two kinds.** A run's segment sequence comes from
  its assembly and does not move. Sequenced work (gates, produce→criticize loops) is a
  **worklist of steps**: the working agent amends it as answers land — add a step, close one
  pre-emptively with a reason, reorder; the segment ends when the worklist is exhausted, so
  loop sizes are discovered, never preset. Expansive work (understand's questions, explore's
  ideas) is a **board**: a living TOML document in the work location, seeded by the engine at
  segment entry, worked freely in place — add, resolve, moot with reasons, cluster — and
  validated by the engine at the transition. Steps answer "what's next"; a board serves the
  chooser who needs sight of the many. On a board, blocked is per-row, never per-run: a
  decision in flight floats up while other askable rows proceed. A row resolves in any output
  style — prose evidence, an artifact in the work location (a data view, a repro), or a
  dispatched child's returns: a child dispatched from a row (a prototype excursion) stamps its
  returns back to that row, the same mechanics as a gate one level earlier. An amend names the segment it
  inserts into; closed segments are history, not addresses.
- **Transitions look back, decide, and instantiate.** A transition is its segment's exit gate:
  it fires when the interior drains, and each firing does one of three things — **releases**
  (advance, filling the look-forward: a `plan` field minted as what comes next), **refills**
  the interior (rework: a fresh step with the findings as prefill), or **goes up** (a ruling's
  `up`, reached from an impasse or a route form -- never a verdict panel's own third word).
  Cycling is the transition re-firing; the engine has no loop concept, and the firing count
  rides the returns. The v1 concepts "refine step," "OODA beat," "replan," and every
  review/criticize step are all this one mechanism. The cheap path — two sentences, no
  action — must stay cheap in mechanics (one short field, one command), but the form's prose
  stays neutral: field notes say what a field is, never what the answer usually is.
- **Transitions dispatch verdict panels; review never lives in an interior.** A transition may
  dispatch 0..n reviewers — each a child prefilled with focused criteria, cold by
  construction — whose verdicts land as returns to the transition. Any `revise` refills, with
  findings merged; panel composition is the conductor's call at fire time, defaulting to one
  and scaling with criticality. Interiors contain only production. A generator transition has
  two voices: the panel's verdict, then the conductor's decide-and-mint on pass.
- **A finding is advice, and scope belongs to the plan.** Independent review is the main way
  scope growth enters a bounded change: a reviewer is rewarded for finding something, and the
  cheapest something is "you should also add." So every finding is classed — **gap** (the spec
  or plan is not filled; only a gap gates) or **beyond** (real, and outside this scope; a
  triage candidate, never rework here) — and the tier that owns the plan disposes of each one:
  accept with the edit named, contest with a reason, or file it. Reviewers judge whether the
  work was filled; they never enlarge what it is. On this project a finding that deletes
  outweighs a finding that adds, because machinery is a cost.
- **Anchors.** A template step may be marked `anchor` (open, transitions, close). Amending an
  anchor away works like any amend — one journaled step with a reason — but the ledger and the
  parent's adjudication view flag it loudly. The freeze is enforced by the tier above reading
  the flag, not by refusal.

### Steps enter a run three ways, one mechanism

Step entries are appended to the journal by: `open` (the assembly template's skeleton), `submit`
of a `plan` field (minted interiors), and `amend` (worklist repairs). A run stops depending on
its template at `open` — the template's steps are copied into the journal, so templates evolve
without stranding live runs.

### Addressing: work ids and work locations

Every run has a **work id**, minted at `open`. When the run tracks a tracker issue, the id is
its number (`issue17`) — the tracker is already a collision-free allocator, and the id
associates for free; the preferred cadence is issue-led, so this is the normal case. The
stable fallback is `<kind><hash>` (`issue7c3f`, four random hex chars, collision-checked
against the local ledger) — random beats a counter because two worktrees allocating in
parallel cannot see each other's next number. Children by suffix (`issue17.g1`). Ids are
short and meaningless on purpose; the "what" is the run's title, held by the ledger at
whatever length it needs. Every call names its work id explicitly; there is
no default and the id is never inferred from cwd or environment — a dispatched crew not
handed an id cannot accidentally drive its dispatcher's run.

A run's work location is `.agent-work/<work-id>/` — the whole work package bundled together:
journal, materialized response forms, plan artifacts, notes. Child runs nest inside the
parent's (`.agent-work/issue7c3f/g1/`). The engine derives the path from the id, so nobody
invents paths, but nothing is hidden: agents read and write their own work location directly.
Branch and worktree names derive from the id too.

A bare `spine` with no id prints the ledger — every open run's id, title, assembly, position,
and state — generated on demand from the journals, never stored.

### Verbs (7, down from 18)

| Verb | Does |
|---|---|
| `open` | instantiate a run from an assembly template; mints the work id, takes the title; copies the skeleton into the journal; sets up the work location |
| `status` | where you are: the step's prefill and imperative rendered as prose, the path of the materialized response form, and the other legal moves spelled out as typeable commands |
| `submit` | read the filled response form; the engine validates fields, runs its command checks and appends their output, journals, advances. A refusal names the missing or failing field and nothing else |
| `amend` | edit a segment's worklist — add, close, reorder; one required `reason` string, journaled |
| `note` | append an observation, triage candidate, or decision to the record |
| `close` | terminal; stamps return fields into the parent's waiting step if the run is parented; archives |
| `trace` | this run and everything it dispatched, as one timeline; for debugging the seam, and deliberately not offered among `status`'s legal moves |

Two run states the verbs must express:

- **Blocked / awaiting a decision** — a `note` with kind `blocked` naming the gap and where it
  went; the run stays open and `status` surfaces the block first — a parent's `status` surfaces
  its children's blocks first. Unblocking is a `note` with kind `resumed`.
- **Rework** — a `revise` verdict refills the interior: a fresh step prefilled with the
  findings, the cycle visible in the worklist and counted in the returns. Steps are never
  resubmitted; `submit` advances monotonically.

### The door is a CLI, shaped like a text adventure

No MCP server. v1's agents struggled with its CLI for two reasons — recalling syntax without an
affordance, and shell-quoting multi-line content — and both are fixed in the CLI itself:

- **`status` is a room description.** It says where you are, renders the step's prefill and
  imperative as prose, names the response form, and spells out the other legal moves as
  literal, typeable commands. The agent never guesses a verb and never recalls syntax;
  nothing about the engine is resident in context between steps.
- **One way of replying: fill the file.** When a step becomes current, the engine
  materializes its response template into the work location — the current step only, holding
  only the fields the agent fills (`check` fields never appear; the engine runs them at
  submit and appends the output). The agent fills it with its file tools; `submit` reads it
  back. No heredocs, no inline flags, no shell-quoting problem; the filled file stays in the
  work location as a record artifact.
- The engine core is a library; if agents still struggle, a thin MCP door over the same core is
  a later, measured addition — not a founding component.

### Field kinds

| Kind | Satisfied by |
|---|---|
| `check` | the engine executes a command and records the output |
| `evidence` | the agent pastes proof: output, diff, verdict |
| `artifact` | a file exists at the named path |
| `decision` | the principal's recorded answer |
| `plan` | submitted content is minted as structure — a segment's steps, a gate's spec and dispatch, or board rows |

Any field may instead carry `waived: <reason>` ("does not apply") or `unknown: <reason>`
("could not determine") — each one journaled step, rendered by `status` without ceremony.
Honest nulls are a legal move everywhere; ask-up is always listed among the legal moves.
Attest, attach, satisfy-by-reference, and waive stop existing as agent-facing concepts.

### Cross-run flow: prefill down, returns up, nothing else

When a parent step dispatches a child run, the fields the parent filled become the child's
opening prefill — read-only. The prefill is the order: a child that thinks it is wrong does not
edit it; it sends a `note` kind `blocked` up. The authority block is derived, never authored:
principal = the parent run's conductor; gaps go to the parent's journal.

When a child closes, its terminal step's return fields are stamped into the parent's waiting
step — including a mechanical summary of the child's amends (segment, reason, anchor touched or
not), so adjudication reads from the parent's own form, never from the child's journal.

No other context crosses in either direction. Trust-but-verify operates on outputs and roots,
not journals: an `artifact` return is a path the parent can open; a `check` return carries the
command and its recorded output, so verification is re-running it, not believing it. Fabricated
evidence is opposed with openness and re-runnable checks, caught at the artifact, and redone —
never prevented with enforcement.

### The record

One append-only TOML journal per run, in its work location (`[[entry]]` blocks appended; a
~40-line writer — there is no stdlib TOML writer — and stdlib `tomllib` reads). Every write is session-stamped. Stamps are
observations: two sessions interleaving is a fact the record shows, not a state the engine
prevents. There is no mutable spine file: current state is a fold over the journal, which is
what makes concurrent sessions safe and cross-session resume free. TOML is the one authored
format everywhere — forms, assemblies, journal, command palette; agents never read or write it
raw for engine state ("the secretary fills out the forms"): `status` renders, `submit` parses.

### The rail: advisory and fail-open

A minimal Stop/SessionStart hook survives: it warns when a turn ends with a named run still
open, and re-injects resume context after compaction. It never hard-refuses, so it passes the
corollary (the escape is: proceed), and it delivers doctrine as error text at the moment it
applies.

### Windows

The proven file-safety code ports as code, not prose: atomic-write retry and POSIX-shell
discovery for check commands (~300 lines in v1). Everything else Windows-shaped moves into the
error text that fires when the case occurs.

### Deleted with no replacement

Leases, heartbeats, staleness, reclaim, identity violations, the context gauge with its trips
and override ledger, journal hashing, occupancy reports, validated amend deltas, the rail's hard
refusals, the MCP server, and every CLI-vs-door distinction. Bind/release descent is deleted
*with* a replacement: explicit work-id addressing, above.

### Size

**Anything the engine can derive, it derives.** A rule stated in a form for an agent to apply
against data the engine already holds is mechanical work the secretary exists to remove, rather
than left to the agent (`docs/DERIVED_IS_CODE.md`). A tool with no seam into a run — nothing in
`engine/` imports it, nothing on a run's path calls it, invoked by hand from the palette —
belongs in `tools/`, not `engine/`; `tools/code_map`, run by `palette:map` at closeout, is the
standing case.
Greenfield rewrite; the old machinery stays untouched until cutover.

## Layer 2 — forms carry the doctrine

Each step's form holds its own imperative, fields, and field notes; there is no shared
doctrine file for a form to lean on. Rare-case knowledge lives in the error text that fires
when the case occurs. Shared prose budget: one page.

There is no mandated context step. A conductor's required pre-reading is the issue and the
derived authority block.

**Form ownership.** A form lives with the skill when the skill fills it the same way in any
assembly (IMPLEMENT, REVIEW); it lives with the assembly when the assembly changes what it asks
(transitions). A skill bundle may reference only itself, `standards/`, and the engine — never an
assembly; assemblies point at skills, skills never point back. That direction is what keeps
install a copy.

**One tier of guidance, two repo-specific artifacts.** v2 drops the global/repo-specific split:
there is no project overlay. Exactly two artifacts are repo-specific by nature and exempt: the
**glossary** (vocabulary, below) and one small **command palette** (`constellation.toml`: the
host repo's test/lint/build commands, which `check` fields reference instead of hardcoding).
Both are named here so neither grows back into an overlay.

## Layer 3 — choreography

Each skill is one posture. What they share is the engine, the forms, and the standards — not
a merged identity.

| Skill | Posture |
|---|---|
| `explorer` | expansive: muddy problem, generate and walk paths, work inward |
| `interrogator` | convergent: specific idea or issue, find the holes, reach clarity for refinement |
| `interrogator-delegated` | same board, the epic-conductor as principal: settle by the launch order, batch the rest up as one cluster, propose terms never write them |
| `epic-conductor` | epic tier: conducts run-an-epic; cuts waves, dispatches issue runs, adjudicates at wave transitions |
| `issue-conductor` | one issue, live human principal; conducts run-an-issue |
| `issue-conductor-delegated` | one issue, frozen launch order; genuine gaps go up, never improvised |
| `implementer` | bounded diff from a prefilled gate spec; conducts nothing |
| `gate-conductor` | one gate: dispatches the implementer, picks the review panel, synthesizes its findings, returns the gate report; conducts run-a-gate |
| `reviewer` | cold panelist, dispatched by a gate's review transition; reads a gate spec and an implement step's outputs, judges whether the work fills the spec |
| `critic` | cold panelist, dispatched by a plan-shaped transition; reads a spec and a plan, judges whether the plan meets the spec's intent |
| `excursion` | one named question as a child run — prior art, prototype, picture, or rival — returning a scoped verdict and what regenerates it |
| `triage` | route candidates into issues per the standard; runs at close |
| `how-to-talk` | prose standard, unchanged |

**Conductors judge at transitions, pump in between.** A conductor's interior role is
mechanical — `status`, dispatch, relay — and its judgment engages only at its transitions. This
is what keeps a issue-conductor's context small enough to survive k gates: the implement–review loop
conducts at the gate tier, not the issue-conductor's, and the gate-conductor conducts it.

**Three jobs at a gate, kept apart by their forms.** The review panel at the gate's transition
answers *did the work fill the spec* — `pass` releases to close, `revise` refills the interior
with the findings; a panel that thinks the spec itself is wrong writes that as a revise finding,
not a third verdict word. The gate-conductor answers *what does
this review mean* — it picks the panel, and disposes of each finding before any refill:
blocking, accepted, beyond, or rejected with a reason, because a panel finding is advice and
never a work order. The issue-conductor at its gate-adjudication step answers *did the spec achieve
the goal* — it acts on the plan (advance / remint the gate / drop a now-pointless gate /
replan), never on the diff. The reviewer's form cites the gate spec and nothing else; the gate
conductor's synthesis cites the findings and the spec; the adjudication form cites the plan and
the returns and has no field for re-examining the work.

Not built, and off the critical path: `cartographer`, `scout`, `docent`, `charter`,
`curator`, `write-a-skill`. Each is ported or dropped later on its own merits. The **episode
store** parks with them; its idea — the repo-level OODA loop — survives as plain journal notes
until Tommy returns to it.

### Assemblies

An assembly is a run template: a fixed skeleton of segments, each transition naming what its
`plan` field may mint and which skill fills each step. New workflows are new assembly files,
not new prose or engine code. **Each assembly names its conductor.** Three tiers, one shape —
each conductor dispatches the tier below and judges at its transitions:

- **explore-an-idea** (conductor: explorer): understand → refine → criticize, cycled with the
  human, confirmation gate at the end.
- **run-an-epic** (conductor: epic-conductor): open cuts the brief into wave 1 → waves of dispatched
  run-an-issue children → wave transitions (advance / repair / replan / stop, child amends
  adjudicated from the returns) → close.
- **run-an-issue** (conductor: issue-conductor); the assembly on disk still cuts every gate
  at plan-to-execute, which the rolling-horizon issue changes:

```text
<open>            seeds the understand board from the issue
[understand]      board: rows typed fact | decision | understanding, each
                  naming its move — read, trace, reproduce, evidence loop,
                  ask, mirror — or the excursion that would settle it.
                  Decisions go to the principal one at a time, ~3 options
                  with pros/cons and a recommendation
<consolidate>     the problem specification: stands alone, plannable from by
                  a reader with no tracker; the engine is the verdict here,
                  validating the board
[plan]*           the next gate, fully specified, and a coarse horizon of
                  what likely follows; design-it-twice lives here
<plan→execute>    critic panel reads the spec and the next gate; revise
                  refills plan, pass mints one gate dispatch and its
                  adjudication step
[ dispatch run-a-gate → <gate adjudication> ]
                  the adjudication is the replan beat: advance re-enters
                  plan with the gate's findings as evidence; remint, drop
                  and replan as before; close once every obligation in the
                  spec has a disposition
<close>           returns stamped up if parented
```

- **run-a-gate** (conductor: gate-conductor, which the assembly on disk now names):
  `<open (prefilled spec)> → [implement]* →
  <review: panel picked by the gate-conductor; synthesis; pass | revise> →
  <close (gate report)>`. A gate is n cycles of implement-then-review; the implementer's
  submit is what fires the review transition. The judgment between the two — which lenses
  read this diff, which findings gate, what returns — is the gate-conductor's and never the
  implementer's: producing, judging, and deciding what a judgment means are three jobs
  (`#31`), and a producer holding the third is a loop with no stop. **The review
  transition is an anchor**: a gate reaching close without it has graded its own work, so
  amending it away stays one journaled step and is loud in the ledger and the parent's
  adjudication view.

### Model tiers

Multi-model is a first-class constraint; the layering keeps provider names out of everything
portable:

- Forms and assemblies name only **logical tiers**: `light | standard | heavy`.
- The **command palette** maps tiers to concrete runners — `[models]` in `constellation.toml`
  (`standard = "claude-sonnet"`, or a codex invocation, or whatever the shop runs).
- The **assembly** sets each step's default tier; a **gate spec may override** via its optional
  `model` item, and the resolved tier rides the prefill.

The tier must be *used*, not merely recorded, and the mechanics make using it the path of
least resistance: at a dispatch step, `status` renders the resolved runner invocation as the
literal, typeable dispatch command — the conductor copies it, never composes it. The child's
`open` records the tier it was dispatched under; the ledger and the child's returns both
surface it, so a mismatch is visible at the transition that adjudicates the child. The engine
still launches nothing — it resolves, renders, and records.

### The authority block

Every run opens with: who your principal is, what you own, what latitude you have, and where
gaps go. Derived at dispatch from the parent run — never authored, never enforced by machinery,
so it cannot go stale. This is a keep-with-conviction: the delegated-issue-conductor experience
showed authority capture doing real work.

### Fresh context at boundaries

The conductor decides fresh-or-continue at each step boundary; the default is fresh past a
threshold. The handoff artifact is the step's form — prefill down, returns up. Handoffs losing
understanding means the form is missing fields; fix the form, not the boundary.

## The issue workflow — rulings

What the workflow tables above rest on, where the reason is not obvious from the shape.

**1. Planning is rolling-horizon.** The plan step fully specifies the *next* gate and sketches
the horizon behind it — the likely later gates, coarsely, and the conditions that would change
them. Plan-to-execute mints one gate. The gate's adjudication is the replan beat: `advance`
records what the gate satisfied and re-enters the cycle, and the planner cuts the next gate
from what was just learned; `remint`, `drop` and `replan` keep their meanings. The spec is not
the execution diary: what a gate satisfied is recorded in the run's **execution state** — a
mechanical file in the work location the engine folds, never a hand edit to the spec. The
cycle's own first move is the engine's: every obligation in the spec carries a disposition
there — satisfied, deferred, invalidated, handed off, or rejected with a reason — and the run
closes; otherwise it plans. The run never closes because the gate list ran out. Ambiguity a
gate exposes rises as a question and is answered inside the replan; a flaw large enough to
send the run back to understanding means restarting the issue run, decided one level up.
There is no route from a gate back to the board.

Why: plans did not converge and gates did. `#7`'s plan went eight rounds to 4,930 words while
all four of its gates passed first time; `#50` shipped two gate specs short of its plan, both
transcription losses between `plan.md` and the spec; and the critic panel has never seen a gate
spec, because it reads `PLAN.toml` and the specs are authored at the transition after it
releases (`#27`). One change answers all three: when the plan step's artifact *is* the next
gate spec, the critic reads what gets dispatched, there is nothing to transcribe, and a plan
cannot outgrow the work it plans because it is one gate long. The horizon stays because pure
one-step planning misses seams, ordering and the chance to isolate an uncertain component —
but it is provisional by construction and no critic attacks it at gate grain.

**2. The gate-conductor is a role, and the implementer is not it.** A gate has three jobs:
the implementer produces the diff; the reviewer judges whether it fills the spec; the
gate-conductor decides what the review means. The gate-conductor conducts `run-a-gate`: it
dispatches the implementer, picks the review panel for this diff, synthesizes the findings —
each one **blocking**, **accepted** (real, and lands in the gate's latitude or a note),
**beyond** (triage), or **rejected** with a reason — decides whether a round of rework is
owed, and returns the gate report. It does not redefine the spec; that goes up. Decision
authority, encoded rather than inferred:

| Who | Decides |
|---|---|
| implementer | local implementation detail inside the spec; routine refactors inside the gate; forward-leaning fixes under ruling 4 |
| gate-conductor | sequencing inside the gate; which lenses read the diff; whether a finding gates; whether the evidence is sufficient; what becomes triage |
| issue-conductor | whether the gate achieved the issue's intent; what the next gate is; whether the plan holds; whether the issue is done; what goes up |
| human / epic-conductor | architecture that crosses a stated boundary; scope changes; changes to intent; tradeoffs that turn on priorities outside the run |

**3. The gate-spec contract, which both issues plan against.** A gate spec is `purpose`,
`scope`, `proof`, optional `model`, and optional `direction` — what this gate is expected to
teach the next plan round, when the planner knows. Two rules on the fields, from `#50`'s close:
`scope` carries every commitment, including the prose ones the reviewer judges against the
spec; `proof` holds commands only, one per commitment a command can prove. A commitment
written into `proof` as a sentence is a defect the critic names before dispatch, not a shell
error the implementer meets after the work is done.

**4. Forward-leaning changes are permitted, bounded, and always declared.** An implementer
may make a change the spec did not name when all three hold: it is in a file this gate already
touches; it needs no proof of its own — if trusting it takes a new test, it is work, and work
gets a gate; and it is separable — reverting it alone would leave the gate's diff complete.
Anything failing one condition is a note, never a detour. Every such change is one line in
`deviations`, naming the file. The gate-conductor disposes of it at synthesis like any finding.
No size number: the second condition does the work a line count pretends to, and a number
invites trimming to it. Do not tighten this to *a note for everything*: with two readers
between the change and the commit, that rule manufactures the cheapest and least worthwhile
class of issue in the backlog.

**5. Sufficiency has two lanes, and the mechanical lane is fields, not refusals.** Every
phase asks first what can be established mechanically — required fields carry a disposition,
mappings are complete, references resolve, checks ran — and only then asks a fresh-context
panel whether the artifact is good enough for the next phase. The mechanical lane lives as
form fields whose escape is `waived: <reason>`, and as engine validation only where the
corollary already allows it (the understand board's open-row refusal is the model). A
cross-mapping check — every goal has a criterion, every criterion a goal — is a field the
conductor fills, never a refusal the engine raises. The problem specification's standard is
that each category was considered, not that each is full.

**6. Every step is do → review → route, and the conductor only routes.** A fresh subagent
does; fresh subagents review from cold; the conductor decides what the review means and
where the work goes next. The conductor writes nothing it would then have to judge — not the
spec, not the plan. Its context stays the size of its decisions, which is what lets one agent
hold an issue across k gates. The one exception is the conversation with a live principal,
which cannot be delegated away from the top of the run. A verdict is about the artifact and
nothing else: a critic or reviewer returns findings and `pass | revise`. Every route word —
back, forward, up — belongs to the conductor's route form, and a reviewer who thinks the spec
itself is wrong says so as a finding and lets the conductor send it up.

**7. Understand ends in a reviewed spec.** Understanding is one step: work the board with
the principal, have a writer produce the problem specification from it, have critics read
the spec cold for completeness and ambiguity, and route — back to the board when information
is missing, back to the writer when it is there and the spec needs amending, forward when a
planner could work from it without guessing what the human meant. Sufficient, not perfect.

**8. Git is the issue tier's, and the engine's.** Open makes the worktree at
`<top-level checkout>/.worktrees/<work-id>` on a pushed branch, the work area at
`.agent-work/<work-id>/`, and captures the issue and the authority block as prefill; nothing is
filled by hand. Each accepted gate is one commit on that branch, made at execute·route on
`advance` — a gate is small enough to be the unit of commit, and nothing below the issue tier
touches git. Close builds the report the human or epic-conductor reads — what landed, the
evidence, the decisions, open triage, residue — moves the run's work folder to
`.agent-work/archive/<work-id>/` in the top-level checkout so a swept worktree does not take
the record with it, and pushes the PR. The archive stays gitignored: it lands under
`.agent-work/`, the same entry every run's own work location already sits under, so there is no
second gitignore call for a repo to make.

**9. `up` is an ask for help, not an exit.** At any route, `up` pauses the run with the ask —
what was attempted, what failed, the findings, the question the tier cannot answer — and the
tier above answers. Often that is a sentence of missing context, and the run resumes with it
as prefill; sometimes it is a decision to end the run. Either is the level above's call. The
ask never skips a level: a gate asks its issue-conductor, an issue run asks its
epic-conductor or the human.

**10. Design-it-twice is two more planners, not a field.** On the first plan round the
conductor dispatches the planner and, beside it, two more, each under a constraint the
conductor thinks might open a different path; it reads three plans and picks or merges before
the critics read one. Later rounds run one planner — re-arguing a settled alternative is
accretion. This is separate from the replaceability lens, which is a critic's question about
an uncertain component: if we distrust this choice, how hard is it to replace?

**11. The reviewer lenses that exist.** Spec-fit — does the work fill the spec — and test
adequacy — are these the right tests, or could the work be substantially wrong while they
pass. Both read every gate by default. A wider taxonomy is parked until rolling horizon has
run; the select step is the seam it lands through. Lessons between runs (`#16`) is unchanged
by any of this.

## Standards

Short cited pages, not skills. Forms cite them from the field that produces the artifact.

- `standards/issue.md` — an issue is the problem, observations with baselines, and what fixed
  means. Breadcrumbs are optional and discardable. Implementation steps in an issue are a defect.
- `standards/skill.md` — what a good skill looks like: reads only its form, one move.
- `standards/prose.md` — how-to-talk.

The understanding moves live at the fields that use them: the
understand board's `excursion` column carries the three that dispatch a child run — ask the
world, spike it, picture it — and its `move` column the three worked in place: reproduce it,
trace one case, and **run the evidence loop** (v1 `diagnose`), which makes the break happen on
demand and then runs hypothesis → test until the cause is shown, never guessed. The mandate is
per row, not per form: *name the excursion that would settle this row now, or decline with a
reason.* The plan form carries none — `PLAN.toml`'s `design-it-twice` argues a rival against a
commitment already made, which is a different move from settling an open question before one.
Consolidate's `settle` reports what the column produced, so the answers reach the planner and
the cold panel.

### Vocabulary: the glossary and how terms flow

`standards/glossary.md`: a repo needs one name for one thing, and that is repo-specific by
nature. Nobody is told to read the dictionary; terms flow through the forms instead, cheapest
layer first.

1. **Key-terms field** on understanding and plan forms: the author names the artifact's
   load-bearing terms; each cites its glossary entry or is proposed as a new one. New vocabulary
   enters the glossary through this field — coining a synonym instead is a defect.
2. **Vocabulary lens** on verdict forms: one check — terms consistent with the glossary and
   the prose standard; name violations.
3. **Language reviewer**, a focused panelist dispatched only for prose-heavy artifacts (design
   specs, shaped briefs, standards): its criteria are `how-to-talk` plus the glossary — one
   panelist among the cold critics.

## Terminology: pivot criteria

**Pivot criteria** replaces "kill condition." The question is what changes the plan, not what
ends it. "There is nothing here" is the largest member of a family that includes rescoping a
gate, reordering a wave, and downgrading an assumption to an open question.

## Measurable goals

| Measure | v1 | v2 target |
|---|---|---|
| Engine verbs | 18 | 7 |
| Conductor pre-reading | 20–30k tokens of doctrine | the issue + the authority block |
| Shared doctrine prose | ~11,000 words (`_shared/`) | one page + standards |

v1 is deleted, so its column is the archival record as measured then, not a figure a later
audit can retake.

## Waves

1. **Critique.** Done 2026-08-23; findings folded into this revision, founding rulings likewise.
2. **Engine.** Segment schema, six verbs with work-id addressing, field kinds, worklist amends,
   plan minting, prefill/returns, TOML journal + writer, the Zork-shaped CLI, advisory rail,
   Windows port, tests. Accepted when the appendix example round-trips.
3. **run-an-issue + run-a-gate.** Forms and slimmed skills: issue-conductor, issue-conductor-delegated,
   interrogator, implementer, reviewer, excursion, triage — plus their v2
   evals. **Ends with a real run-an-issue on a toy issue in this repo, run from the branch** —
   the toy issue builds a genuine v2 component, so the validation run also builds v2. The pivot
   criteria below arm here, not at cutover.
3b. **The issue workflow** (`#55`). Three issue runs, not one: open and close as the engine's
   (worktree, branch, archive, PR) first, because both later runs work inside it; then
   rolling-horizon planning with the reviewed spec; then the gate-conductor, run *under* the
   new planner as its validation — the wave-3 pattern, where the issue builds a genuine
   component. One issue would be a plan cut across two assemblies and two new skills,
   authored all at once under the planner it retires.
4. **explorer + epic-conductor.** The explore and epic assemblies, wave-tier transitions, their evals.
5. **Cutover.** Install, full eval pass, archive v1.
   Hard cutover: v2 is validated with real runs, then replaces v1 wholesale.

## Pivot criteria for this effort

- Explorer and interrogator share the understanding form only if one form serves both postures
  in drafting. If the forms fight, split them — a cheap pivot.
- A validation run needing doctrine beyond its forms means the missing knowledge moves into a
  form or an error message — never into a new shared doc.
- Fresh-at-boundary handoffs losing understanding means the form is missing fields. Fix the
  form, not the boundary. Repeated loss on small issues means the fresh default is set too low.
- A cutover validation run failing where v1 succeeded is diagnosed before v1 is deleted.
- The repo needing a document beyond the one-page README to explain its own layout means the
  layout is too clever. Simplify it.

## Open questions

- **Rework cap:** answered by `impasse-after`. The count is surfaced in the returns, and
  after three rounds the engine stops offering a fourth and the conductor rules — advance over
  the objection, one more round it can name the change for, or up. A guardrail, not a target.
- **Reviewer lenses beyond two:** which ship next, and how much of selection is mechanical
  (changed file types, the spec's risks) versus the gate-conductor's call. After rolling
  horizon runs.
- **Who works the board when the principal is delegated:** the issue-conductor itself, as
  with a live human, or an interrogator subagent so the conductor's context stays clean.
  Decide when the delegated issue-conductor exists; try both.
- **Forward-leaning, re-measured:** ruling 4 rests on the absence of a recorded harm. The
  first gate where a declared forward-leaning change is rejected at synthesis is the
  re-measurement.
- **Fresh-by-default threshold:** what step count or gate count flips the default from continue
  to fresh? Pick after the wave-3 validation run.

## Appendix — worked example

Normative for shape, not for names: the engine's schema is accepted when this round-trips.
Under rolling horizon an `advance` here re-enters the plan step rather than walking to the next
minted gate.

```toml
# assemblies/run-an-issue/forms/GATE_TRANSITION.toml — a transition form, complete
imperative = """
The gate has returned. Decide whether its spec achieved the goal, and whether
the plan still holds."""

[[field]]
id = "learned"
kind = "evidence"
note = "What this gate taught us."

[[field]]
id = "plan-holds"
kind = "decision"
note = "advance | remint | drop <gate-id> | replan — on anything but advance, the amend is the evidence."
```

```text
$ spine issue7c3f status

issue7c3f · run-an-issue · execute · gate transition g1 (5 of 7)
  issue7c3f: parser drops the last record when the file ends without a newline

  Gate g1 closed: verdict pass, 2 implement/review cycles, returns below.
  Decide whether its spec achieved the goal, and whether the plan still holds.

  returns from issue7c3f.g1
    verdict    pass (2 cycles)
    diff       src/parser.c +41 -7
    check      pytest -q tests/parser — 41 passed  (re-run: spine issue7c3f.g1 check done)

  your response form: .agent-work/issue7c3f/G1_TRANSITION.toml
  fill it, then:     spine issue7c3f submit
  also legal:        spine issue7c3f note ...   spine issue7c3f amend ...
```

```toml
# .agent-work/issue7c3f/G1_TRANSITION.toml, filled
learned = """
Review passed in two cycles; the parser change was smaller than planned.
Gate g2's scope note still assumed the larger change — trimmed via amend a3."""

plan-holds = "advance"
```
