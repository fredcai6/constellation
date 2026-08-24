# Constellation v2 Design

**Status:** cold critique complete 2026-08-23; founding conversation rulings folded in
2026-08-23. Rulings by Tommy. This revision supersedes the copy in v1
(`constellation-skills/docs/V2_DESIGN.md`); where they differ, this one governs.

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

## Why now — measurements

- The v1 engine is 4,515 lines with 85 refusal sites. With its MCP wrapper (2,749), lifecycle
  (1,243), generator (1,089), and validator (758), the machinery totals ~10,000 lines.
- The skill corpus is ~57,000 words. A commander that obeys its own `context` steps reads
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
  decision in flight floats up while other askable rows proceed. An amend names the segment it
  inserts into; closed segments are history, not addresses.
- **Transitions look back, decide, and instantiate.** Every transition form has two parts: the
  look-back (*what did this segment teach us — does the plan still hold?*) and the look-forward,
  a `plan` field whose submitted content is minted as the next segment's interior. The v1
  concepts "refine step," "OODA beat," and "replan" are all this one step. The cheap path — two
  sentences, no action — must stay cheap in mechanics (one short field, one command), but the
  form's prose stays neutral: field notes say what a field is, never what the answer usually is.
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

### Verbs (6, down from 18)

| Verb | Does |
|---|---|
| `open` | instantiate a run from an assembly template; mints the work id, takes the title; copies the skeleton into the journal; sets up the work location |
| `status` | where you are: the step's prefill and imperative rendered as prose, the path of the materialized response form, and the other legal moves spelled out as typeable commands |
| `submit` | read the filled response form; the engine validates fields, runs its command checks and appends their output, journals, advances. A refusal names the missing or failing field and nothing else |
| `amend` | edit a segment's worklist — add, close, reorder; one required `reason` string, journaled |
| `note` | append an observation, triage candidate, or decision to the record |
| `close` | terminal; stamps return fields into the parent's waiting step if the run is parented; archives |

Two run states the verbs must express:

- **Blocked / awaiting a decision** — a `note` with kind `blocked` naming the gap and where it
  went; the run stays open and `status` surfaces the block first — a parent's `status` surfaces
  its children's blocks first. Unblocking is a `note` with kind `resumed`.
- **Rework** — a reviewer's `revise` verdict mints a fresh implement step prefilled with the
  findings; the loop is visible in the worklist. Steps are never resubmitted; `submit` advances
  monotonically.

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
corollary (the escape is: proceed). v1's rail already delivers doctrine as error text at the
moment it applies — the one v1 component built the way v2 says everything should be built; v2
keeps that and drops the hard refusals.

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

One budget for **total machinery** — engine, CLI, rail, assembly loading, Windows support,
install copy: **≤ 1,500 lines.** The bar is aspirational and deliberately tough — everything
earns its keep — and it is one number: a green engine achieved by relocating lines into another
component counts as a miss. Forms and templates are corpus words, not machinery lines.
Greenfield rewrite; the old machinery stays untouched until cutover.

## Layer 2 — forms carry the doctrine

Each step's form holds its own imperative, fields, and field notes.
`global-everyone.md`, `global-orchestrator.md`, `checklist-engine.md`, and `commander-core.md`
dissolve into the forms that need their content. Rare-case knowledge moves into the error text
that fires when the case occurs. Shared prose budget: one page.

The mandated `context` step dies. A conductor's required pre-reading becomes the issue and the
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

Skills keep their v1 names and their distinct postures. What they share is the engine, the
forms, and the standards — not a merged identity.

| Skill | Posture |
|---|---|
| `explorer` | expansive: muddy problem, generate and walk paths, work inward |
| `interrogator` | convergent: specific idea or issue, find the holes, reach clarity for refinement |
| `admiral` | epic tier: conducts run-an-epic; cuts waves, dispatches issue runs, adjudicates at wave transitions |
| `commander` | one issue, live human principal; conducts run-an-issue |
| `commander-delegated` | one issue, frozen launch order; genuine gaps go up, never improvised |
| `gate-executor` | one gate; conducts run-a-gate: dispatch implementer and reviewer, pump the loop, return |
| `implementer` | bounded diff from a prefilled gate spec |
| `reviewer` | cold context; *did the work fill the spec?* — verdict against the gate spec and only the gate spec |
| `prototyper` | one named question, throwaway code, disposed |
| `triage` | route candidates into issues per the standard; runs at close |
| `how-to-talk` | prose standard, unchanged |

**Conductors judge at transitions, pump in between.** A conductor's interior role is
mechanical — `status`, dispatch, relay — and its judgment engages only at its transitions. This
is what keeps a commander's context small enough to survive k gates, and it is why the gate
executor exists: the implement–review loop conducts at the gate tier, not the commander's.

**Two review questions, kept apart by their forms.** The reviewer answers *did the work fill
the spec* — verdict `pass` (advance to close), `revise` (findings prefill a fresh implement
step; the loop cycles mechanically), or `escalate` (the gate itself is wrong; goes up early).
The commander at the gate transition answers *did the spec achieve the goal* — it acts on the
plan (advance / remint the gate / drop a now-pointless gate / replan), never on the diff. The
reviewer's form cites the gate spec and nothing else; the transition form cites the plan and
the returns and has no field for re-examining the work.

Absorbed, with their essence relocated: `replan` → the transition step (every transition *is*
the OODA beat); `to-initial-issues` → the epic assembly's opening transition (cut the confirmed
brief into the first wave, issues per `standards/issue.md`); `diagnose` → the evidence-loop
understanding move.

Parked, v1-frozen, off the critical path: `cartographer`, `scout`, `docent`, `charter`,
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
- **run-an-epic** (conductor: admiral): open cuts the brief into wave 1 → waves of dispatched
  run-an-issue children → wave transitions (advance / repair / replan / stop, child amends
  adjudicated from the returns) → close.
- **run-an-issue** (conductor: commander):

```text
<open>            seeds the question board from the issue
[understand]      board: questions typed fact | decision, clustered; decisions
                  go to the principal one at a time, ~3 options with pros/cons
                  and a recommendation — effort scales with criticality
<consolidate>     learnings + key terms — the prefill for fresh-context
                  planning; the engine validates the board here
[plan → critic]*  produce/criticize loop; design-it-twice lives here
<plan→execute>    the plan field mints k gate dispatches from the plan's gate specs
k*[ dispatch run-a-gate → <gate transition> ]
<close>           returns stamped up if parented
```

- **run-a-gate** (conductor: gate-executor):
  `<open (prefilled spec)> → [implement → review]* → <close (verdict, loop count, artifacts)>`

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
so it cannot go stale. This is a keep-with-conviction: the delegated-commander experience
showed authority capture doing real work.

### Fresh context at boundaries

The conductor decides fresh-or-continue at each step boundary; the default is fresh past a
threshold. The handoff artifact is the step's form — prefill down, returns up. Handoffs losing
understanding means the form is missing fields; fix the form, not the boundary.

## Standards

Short cited pages, not skills. Forms cite them from the field that produces the artifact.

- `standards/issue.md` — an issue is the problem, observations with baselines, and what fixed
  means. Breadcrumbs are optional and discardable. Implementation steps in an issue are a defect.
- `standards/skill.md` — what a good skill looks like: word budget, reads only its form, one move.
- `standards/prose.md` — how-to-talk.
- `standards/understanding-moves.md` — spike it (dispatch the prototyper), picture it (build a
  data view that makes the problem visible), reproduce it, trace one case, and **run the
  evidence loop** (v1 `diagnose`): reproduce the break, then hypothesis → test until the cause
  is shown, never guessed. Both understanding forms carry a mandatory field: *name the spike or
  data view that would settle something now, or decline with a reason.*

### Vocabulary: the glossary and how terms flow

`standards/glossary.md`: a repo needs one name for one thing, and that is repo-specific by
nature. Nobody is told to read the dictionary; terms flow through the forms instead, cheapest
layer first.

1. **Key-terms field** on understanding and plan forms: the author names the artifact's
   load-bearing terms; each cites its glossary entry or is proposed as a new one. New vocabulary
   enters the glossary through this field — coining a synonym instead is a defect.
2. **Vocabulary lens** on criticize forms: one check — terms consistent with the glossary and
   the prose standard; name violations.
3. **Language reviewer**, dispatched only for prose-heavy artifacts (design specs, shaped
   briefs, standards): the criticize move with a prose/vocabulary posture — `how-to-talk` plus
   the glossary as its review criteria. In the explorer's critic panel it is one lens among the
   cold critics.

## Terminology: pivot criteria

**Pivot criteria** replaces "kill condition." The question is what changes the plan, not what
ends it. "There is nothing here" is the largest member of a family that includes rescoping a
gate, reordering a wave, and downgrading an assumption to an open question.

## Measurable goals

| Measure | v1 | v2 target |
|---|---|---|
| Corpus words | ~57,000 | ≤ 15,000 |
| Machinery lines (engine + CLI + rail + loader + Windows + install) | ~10,000 | ≤ 1,500 |
| Engine verbs | 18 | 6 |
| Conductor pre-reading | 20–30k tokens of doctrine | the issue + the authority block |
| Shared doctrine prose | ~11,000 words (`_shared/`) | one page + standards |

Draft per-skill word budgets, forms included — revised at wave boundaries, enforced at cutover
with `wc`: explorer 2,500 · admiral 1,500 · commander 1,500 · commander-delegated 500 ·
gate-executor 300 · interrogator 800 · reviewer 1,000 · implementer 800 · prototyper 600 ·
triage 600 · how-to-talk 500 · standards 1,500 · assemblies 2,000. Sum ≈ 14,100 against the
15,000 cap.

## Waves

1. **Critique.** Done 2026-08-23; findings folded into this revision, founding rulings likewise.
2. **Engine.** Segment schema, six verbs with work-id addressing, field kinds, worklist amends,
   plan minting, prefill/returns, TOML journal + writer, the Zork-shaped CLI, advisory rail,
   Windows port, tests. Accepted when the appendix example round-trips.
3. **run-an-issue + run-a-gate.** Forms and slimmed skills: commander, commander-delegated,
   gate-executor, interrogator, implementer, reviewer, prototyper, triage — plus their v2
   evals. **Ends with a real run-an-issue on a toy issue in this repo, run from the branch** —
   the toy issue builds a genuine v2 component, so the validation run also builds v2. The pivot
   criteria below arm here, not at cutover.
4. **explorer + admiral.** The explore and epic assemblies, wave-tier transitions, their evals.
5. **Cutover.** Install, full eval pass, the word/line ledger against the budgets, archive v1.
   Hard cutover: v2 is validated with real runs, then replaces v1 wholesale.

## Pivot criteria for this effort

- Explorer and interrogator share the understanding form only if one form serves both postures
  in drafting. If the forms fight, split them — a cheap pivot.
- Total machinery passing ~2,000 lines means something crept back in. Stop and name it.
- A validation run needing doctrine beyond its forms means the missing knowledge moves into a
  form or an error message — never into a new shared doc.
- Fresh-at-boundary handoffs losing understanding means the form is missing fields. Fix the
  form, not the boundary. Repeated loss on small issues means the fresh default is set too low.
- A cutover validation run failing where v1 succeeded is diagnosed before v1 is deleted.
- The repo needing a document beyond the one-page README to explain its own layout means the
  layout is too clever. Simplify it.

## Open questions

- **Rework cap:** none. The gate's loop count and verdict trail ride the return, so the tier
  above cannot miss a churning loop — the count is surfaced, never capped.
- **Fresh-by-default threshold:** what step count or gate count flips the default from continue
  to fresh? Pick after the wave-3 validation run.

## Appendix — worked example

Normative for shape, not for names. Wave 2's schema is accepted when this round-trips.

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
