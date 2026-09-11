# Process notes — issue100, the `drive` run

Friction met while driving this run, recorded as it happened, in the shape of
`docs/process-notes/issue99.md`. Nothing here is doctrine. Where an entry
contradicts `docs/AGENT_GUIDE.md` or a form, the guide and the form are right
about the tree and this file is right about what the run met.

## 1. The open form's authority still does not carry, and the workaround is now deliberate

issue99's note 1 recorded that `OPEN.toml`'s `authority` field is minted with
`carries = false`, so the one field in the assembly whose whole content is orders
reaches no later step by the mechanism. Nothing has changed at `905a0eb`: this
run's own `journal.toml` shows `id = "open"` with `carries = false`, and the first
transition marked `carries = true` is `understand`, whose fold is the spec.

So the same workaround was applied deliberately rather than discovered: the four
standing rulings, the scope-discipline paragraph and the latitude line are written
into `.agent-work/issue100/issue.md` under their own heading as well as into
`authority`, because `issue` is a path and every downstream reader opens it.

The thing worth recording on the second occurrence is that the workaround is now a
convention with two instances and still nothing states it. A run whose conductor
had not read issue99's notes would have put the rulings in `authority` alone, and
the spec-writer — the very next step — would never have seen them. That is not a
lapse waiting to happen; it is the default behaviour of a conductor reading only
its own form.

## 2. The tree already states, as a rejected design, the thing this run must do

`engine/run.py:98-99`, in a rationale block on `hat()`:

    # Rejected: a worker child driving its parent's board. A child not handed an
    #   id cannot drive its dispatcher's run, by design, and the board is the
    #   parent's own segment.

`drive`'s form-step spawn is precisely a process handed its parent's own work id,
whose whole job is to fill and submit a step on that parent's run. The comment is
about a *worker child* — a run with its own id, dispatched under a parent — and a
form-step filler is not that: it opens no run of its own. But the sentence "a child
not handed an id cannot drive its dispatcher's run, by design" is doing two jobs at
once, and only the first survives this run: the *mechanism* (no id, no reach) is
still true of worker children, while the *design* half now has a deliberate
exception with a form step's filler.

This is the same seam #112 files from the other side — a dispatched gate-conductor
that filled its parent's adjudication and close forms because nothing stopped it.
`drive` needs that reach for a form step and must not want it for a gate. Recorded
at open because a spec that does not say so out loud will be read as either
contradicting a rationale block or as blessing #112.

## 3. The verb's own orders name a mechanism the engine does not have

Standing ruling 1 says a driven form step runs "under the step's own filler as
its role and that filler's tier as its runner." There is no filler tier. The
engine's one resolver is `_runner(tier)` (`engine/cli.py:190`), whose single
input comes from `_tier(step, asm)` — `step.prefill.model or seg.model` — or
from `_panel_descriptors`' `panelist.get("model") or seg.get("model", "")`.
Neither reads `filler`, `worker` or `role_of`. Every `model =` in `assemblies/`
is per-segment or per-panelist; a grep for a filler-to-tier join in `engine/`
returns nothing.

The orders were not wrong about what should happen, they were wrong about what
exists — and the difference only showed up because a board row asked where a
tier comes from rather than assuming the sentence described the tree. That is
the shape the understand board is for, and it is the second time in two runs
that a row typed as a fact settled a design question (issue99 note 3).

What makes it bite rather than being bookkeeping: the two form steps `drive`
actually spawns in a `run-an-issue` are the plan-to-execute route form and each
gate's adjudication. Both are conductor-filled, and both are exactly where
`skills/issue-conductor/SKILL.md` says judgment lives. Falling back to the
segment's own `model` costs no code and runs every judgment seam in a driven run
on `standard`, against ruling 4.

## 4. The proof the rulings ask for cannot be written with the discriminator the tree has

Ruling 3: the proof "asserts every step between was submitted by a spawned
process and none by the caller." The obvious discriminator is the `session`
stamp `journal.append` puts on every entry (`engine/journal.py:116`). It does
not work, and the reason is the same line issue99's note 31 used to *prove* a
child had written its parent's forms: `checks._spawn` gives the child
`os.environ.get("CONSTELLATION_SESSION", str(os.getpid()))` — **the parent's own
value** (`engine/checks.py:177-178`). Every process in a spawn tree stamps the
same string. Under `tests/conftest.py`'s `workdir` that string is the literal
`"test-session"` for the test process and every child alike.

So the field that identified a spawn tree is precisely the field that cannot
separate its members, and the run that needs the separation is this one. Nothing
in `engine/` reads `session` back at all.

The way out is not a new discriminator invented for the test. `drive` has to
journal something per form-step spawn anyway — it needs a pid to read liveness
against and a count to cap restarts with, the same two things `dispatch-started`
gives a child. That record is the discriminator, and a proof written against it
tests the mechanism instead of the fixture.

## 5. A seed question carried a stale premise from the last run's notes, and the row corrected it

q7 was seeded as: "`tests/test_imperatives.py` forbids the word `wait` in DISPATCH
and PANEL (`docs/process-notes/issue99.md` note 2); establish what that test and
its neighbours actually assert at HEAD."

At HEAD the ban does not exist. issue99's own gates replaced the substring check
with `_ends_on_a_move` (`tests/test_imperatives.py:139-154`), a structural test on
the **last sentence** of exactly two constants for `wait|hold|monitor|expect`
sitting outside a `spine <something> wait` span. Its docstring states the change:
"the word itself can no longer be the thing forbidden."

The note was true when it was written and false by the time this run opened,
because the run that wrote the note is the run that fixed the thing it described.
Process notes are a record of what a run met, and the guide already says the tree
is right where they disagree — but a *seed question* is not a note, it is an
instruction to a reader, and a premise embedded in one is carried into the answer
unless the row is phrased to test it. The phrasing that saved it was "establish
what that test **actually asserts at HEAD**", not "confirm the ban".

Worth keeping as the general shape: the most dangerous input to a fresh run is the
previous run's own notes, precisely because they are the most relevant thing
available. Seed a row against the claim, never on top of it.

## 6. Nine fact rows, four parallel reads, and every one of them settled without leaving the tree

Every row on this board declined its excursion, and the reason is the same in all
twelve: the questions are about this codebase at this rev. `find-prior-art` asks
the world, and nothing about `_startable`'s call sites is in the world.

The nine fact rows were settled by four parallel reads dispatched at once, each
holding two rows and each required to cite `file:line` and quote the load-bearing
text. Every claim that shaped a decision was then re-opened by hand against the
file before it reached the board — `checks._spawn`'s environment,
`_startable`'s predicate, `journal.append`'s stamps, `_ends_on_a_move`,
`test_promises.py`'s two verb checks. Two of the four reports carried the same
warning issue99's note 4 recorded, unprompted: a grep for a function name lands in
the tagged rationale block above it, and the line number you carry away is the
comment's.

The one row that would have been worth an excursion is the one that did not need
one either: q11 asks whether a fake `dispatch` entry can carry a whole run to
close. That is a `build-a-prototype` question by shape. It was answerable by
reading `_throwaway_dispatch` and confirming that no spawned fake in the suite has
ever run `spine` at all — an absence, which a prototype would have taken an hour
to rediscover.

## 7. The panel passed the spec on the one criterion it actually failed

Round one's verdicts: p2 `pass`, p3 `pass`, p1 `revise` with one gap. The
conductor sent it back anyway, on a defect no panelist raised.

The spec was written without a single name in it. `wait` was "the wait command",
the journal was "the run's own log" and "the system's per-run record", a `brief`
was "orders", the understand segment was "the initial understanding phase", a
gate was "a dispatched unit of work", the `dispatch` palette entry was "a
configured command template" and, in the proof commitment, "a stand-in spawning
mechanism". Thirteen commitments and not one file path.

The interesting part is which panelist missed it. p1's whole criterion was
"standalone: could a fresh-context reader with no tracker reach plan from this
spec alone" — and p1 not only passed the spec on that axis, it went and read
`engine/cli.py` itself to ground its own finding, citing four line numbers the
spec never mentions. The criterion was met in the reading and failed in the
document: p1 could plan from the spec because p1 did the mapping work in its own
head, and never noticed it had done it.

That is the failure mode of a criterion phrased as a capability question. "Could a
reader plan from this" is answered by a reader who *can*, and a competent reader
can always close a naming gap by grepping. The question that would have caught it
is the one `CONSOLIDATE.toml` asks the conductor two fields later: *name this
work's load-bearing terms, each citing its glossary entry.* Try that against a
document where every load-bearing term is a coinage and it fails on the first
line. The form asking me for `key-terms` is what made the defect visible, and it
is downstream of the panel by design.

Recorded because the fix is not a sharper panel brief -- `skills/issue-conductor/SKILL.md`
forbids sharpening between rounds, and rightly. The fix is that the conductor's
own seam has a field the panel does not, and reading it early is what a seam is
for.

## 8. The conductor's ruling had to ride in a field reserved for the panel's findings

`CONSOLIDATE.toml`'s `calls` is documented as "one block per finding the panel
returned -- every one of them gets a call, and this form is the only place any of
them is ruled on." My own objection is not a finding the panel returned, and the
rework round is minted from `_blocking_calls` (`engine/cli.py:1760`), which
carries the `finding` text of every `blocking`-called block verbatim and nothing
else.

So there was no legal place to put it. A `spine note decision` does not reach the
round -- that is issue99's note 1 and the open `#107` in one sentence. Ruling the
round back without carrying the reason mints a round that cannot see its why,
which is the defect `#107` names at the impasse form and which turns out to exist
one seam earlier too, wherever the conductor's reason is not one of the panel's
own words.

I added a fifth block labelled in its own first line as the conductor's ruling
rather than a panel finding, called it `blocking`, and journaled the deviation.
It works, and it works because `_blocking_calls` reads a string rather than
checking provenance -- the same absence of an ownership check that q10 records
everywhere else in this engine.

Worth keeping as a shape: a form field whose *note* names one source and whose
*mechanism* accepts any is a place where a real need will quietly route itself,
and the record will look like the panel said something it did not. The label in
the first line is doing all the work of keeping the record honest, and a label is
a convention, which is what note 1 says about the last one of these.

## 9. The second panel found what the first one could not, because the first one's fix made it visible

Round two: three panelists, three `revise`, four findings, all four called
blocking. The round-one panel had returned two `pass`es on the same document.

The document had changed in exactly one way that mattered: it now used the
repository's own names. Round one's spec said "the run's own conductor" and "a
dispatched unit of work" and "a form step"; round two's said `filler = "conductor"`,
`gate`, and `PLAN_TO_EXECUTE.toml`. p1 then walked from the phrase `filler =
"conductor"` to `assemblies/run-an-issue/ASSEMBLY.toml:198`, to
`engine/cli.py:2347` where `_mint_gates` hardcodes the same string onto every
gate's adjudication step, to `run-a-gate`'s own two transitions one tier down —
and asked the question the whole spec turns on: **what does `drive` do when the
form it reads is a judgment call whose filler is the conductor itself?**

That question was equally true of round one's spec. It was unaskable there,
because "a form step" names nothing you can grep. Naming is not presentation: a
name is an index into the tree, and a document written without names is one no
reader can check against anything. The round-one panel passed the spec twice
because it had nothing to check it against; the round-two panel failed it three
times because it did.

The general shape, and it is the argument for the naming rule that is not about
style: **a coinage is unfalsifiable.** No grep contradicts "the run's own log."
`journal.toml` can be opened, and what it does or does not contain is a fact
about the tree. Prose rule 2 buys review, not tidiness.

## 10. The answer to the panel's best finding was already written, three days earlier, in the authority block

p1's finding asks whether `drive` spawning a fresh conductor to rule on
`plan-holds` is intended, and observes that the spec implies it "through one
adjective (`reserved`) that cuts the other way as easily as this one." It is a
fair reading of the spec and the right question.

It was answered before the run opened. Standing ruling 1 names exactly two things
`drive` never touches — "The understand segment and the close form are the
principal's and are never driven" — and a route form is neither. Standing ruling 2
says a form step's filler is a fresh agent every time. Standing ruling 4 assigns
conductors the heavy tier, which on any reading where conductors are not spawned
governs nothing at all.

So the design was settled and the *spec* had lost it. The rulings live in
`OPEN.toml`'s `authority` and in the issue artifact; the spec-writer read both, and
still produced a document from which the choice could not be recovered. Nothing
checks a spec against the authority block — the two are not connected by any
mechanism, and the spec is what every later reader gets.

That is the same gap as note 1 one layer along. Note 1 is that the rulings do not
*carry* to the next step. This is that even where they do carry, nothing notices
when the artifact drops one. The panel is what noticed, four hours later, by
inference from an adjective.

Worth keeping: an authority block is orders, and orders that are not restated in
the artifact they govern survive only as long as the memory of whoever read them.
Three of this run's four blocking calls in round two were the panel finding
something; the fourth was the conductor putting a ruling back that had been made
before the spec existed.

## 11. Three planners, three cuts, and the engine kept the one that closed last

`design-it-twice` returned three rival plans for the same spec:

- p2, *fewest gates*: one gate, the whole verb — `engine/cli.py`, the palette map,
  `engine/journal.py`, `engine/render.py`, and a new test file, all at once.
- p1, *unconstrained*: three gates — the verb and its loop; then the tier map and
  `render.brief`; then the form-step spawn.
- p3, *smallest engine touch*: three-plus gates, gate 1 addition-only —
  `cmd_drive`, `_drive_bound`, one constant, and nothing in `engine/cli.py`
  edited.

The engine kept p3, and it kept it for one reason: p3 closed at 09:03:21 and the
other two at 08:58:39 and 08:59:04. That is `#96`, filed and open — the pick is
"whichever rival closed last", which is to say the slowest writer wins. Here the
slowest writer also wrote the best cut for this run's constraints, and that is
luck, not selection.

What is worth recording is what the arbitrary pick *cost nothing* here and would
have cost elsewhere. p2's single-gate cut lands four files in one diff against a
spec whose own scope-discipline paragraph exists because the last run over-built.
Had p2 closed last, the run would have taken it, and the only thing standing
between the run and that cut would have been the critic panel — which reads the
kept plan and never learns the other two existed.

One thing the three cuts agreed on, unprompted: all three named
`palette:test tests/test_drive.py` as the proof, and all three put the verb in
`main()`'s dict beside `wait` at `:3364-3366`. Where the spec named things, the
planners agreed; where it left a choice, they diverged. That is the naming rule
(note 9) paying out one segment later.

## 12. The correction the conductor recorded in `key-terms` reached the planner, by name

Round three's release carried a correction the spec itself did not: that
`conductor` is not a role but an indirection `role_of` resolves per assembly, so
the heavy-tier reservation is on the indirection whatever it resolves to, never on
the one name `issue-conductor` the spec happens to give.

There was no other channel. `calls` only rides a `rework`, and the round was
released; a `spine note` reaches no later step. `key-terms` sits on
`CONSOLIDATE.toml`, and that transition is `carries = true`, so it folds into the
run's prefill beside the spec.

It worked, and p3's own plan text is the receipt — its gate 2 names "the bare
`conductor` indirection resolves to heavy tier regardless of which assembly's own
conductor it names (`CONSOLIDATE.toml`'s round-3 key-terms correction)", citing the
field by name. A planner three steps downstream read a conductor's correction to a
spec out of a bookkeeping field and planned a gate against it.

Worth keeping because the field is not advertised as an orders channel. Its note
says "this work's load-bearing terms; each cites its glossary entry or proposes a
new one" — bookkeeping, on its face. What made it carry is `carries = true` on the
transition, which is a property of the *step*, not of the field. Three fields ride
that fold and only one of them, `spec`, reads like orders. The other two are where
a conductor's late correction can go when the round is already released, and
nothing says so.

## 13. Four plan rounds, and the defect was that the plan had become the implementation

The plan seam ran four rounds and four critic panels — one past the principal's
stated cap of three — and every round ended `revise` from all three panelists.
Reading them in order is the whole lesson:

1. The gate hands the panel and gate-dispatch shapes to `cmd_wait` and cannot
   then tell a resolved step from one whose child is spent.
2. The fix for that is broken: `_outstanding_state`'s `(count, name_wait)` cannot
   express the rule, because `count > 0` forces `name_wait` true by construction
   and a dead-capped child never reaches `count` at all.
3. The corrected rule is right, and now three new things are visible: no segment
   guard, a stale-read hazard on `records`/`counts`, and a proof floor that
   skips the one panel shape that matters.
4. The segment guard I ordered in round 3 raises on eight of the nine assemblies
   in the tree, because only `run-an-issue` has a segment named `plan`.

Round 4's worst finding is a crash **in the fix I ordered at the impasse.** That
is the signal, and it took me two rounds too long to read it: I was not
adjudicating a plan, I was pair-programming with a planner through a critic panel.
Each round I supplied a more precise mechanism, the panel found the next flaw in
my mechanism, and the plan document grew — 665, 1029, 1491, 1538 prose words — for
a gate that adds one function and its entry in a dict.

`skills/planner/SKILL.md` says it outright: "do not reach into a gate's own
latitude: implementation detail below gate grain belongs to the gate that will do
the work." `skills/critic/SKILL.md` says the other half: "a plan longer than the
work it plans is itself a finding." Both were true from round 2 onward and neither
panel said so, because each panelist was answering its own criterion honestly
against the document in front of it. The finding that would have stopped this is
one no criterion asked for: *is this a plan at all, or a draft of the diff?*

The release was ruled on that diagnosis rather than on the cap. Three findings
stand accepted, each recorded with what the gate must do about it, because the
route form's `calls` do not reach a projected gate — `_mint_projected_gate` builds
from the plan round's own return, "never from anything typed on the transition's
own form" — so an accepted finding at this seam is a note to the gate's
adjudication and nothing more.

## 14. Two seams, two channels, and only one of them was designed to carry

The conductor's ruling had to reach a later step three times in this run, and each
time the channel was different and none of them is named as an orders channel:

- At consolidate, sending the spec back: `calls`, whose blocking blocks
  `_blocking_calls` carries verbatim. Documented as "one block per finding the
  panel returned" — so a ruling of my own rode a field reserved for the panel's
  findings, labelled in its first line to keep the record honest (note 8).
- At consolidate, releasing the round: `key-terms`, which carries only because the
  transition is `carries = true`. It worked — a planner three steps later cited
  the correction by name (note 12).
- At the plan seam, releasing: **nothing.** `_mint_projected_gate` is explicit
  that a projected gate is built from the interior return alone. Three accepted
  findings stop at the journal.

So the run has a channel for "send it back with orders", a channel for "release it
with a correction" at one seam, and no channel at all for "release it with a
correction" at the other. The asymmetry is not obviously wrong — the argument for
it is that a gate should execute the plan that passed critique, not the plan plus
a conductor's marginalia — but it means an accepted finding at the plan seam is
recorded and unreachable, and the only tool for acting on one is `remint` after
the gate has already run.

## 15. The run driving itself, and the verb stopping on its own spent child

Once gate 1 landed, `spine issue100 drive --for N` replaced every hand-typed
`wait` at this run's own dispatch and panel seams. It walks a planner dispatch,
then the critic panel behind it, then stops at the route form — because a form
step with nothing dispatched is precisely the shape gate 1's horizon does not yet
spawn for. That set of stops is exactly the set of steps that are the conductor's:
the route forms and the gate adjudications. The mechanical part became one command
and the judgment part stayed where it was.

Then gate 3's conductor died three times — 12:07:24, 12:23:35, 12:39:12, roughly
sixteen minutes each — and `drive` stopped on commitment 9's third condition and
handed me the ruling, naming the spent child. The verb this run is building
detected the cap the previous run built, on the gate that builds the spawn, and
refused to spin. Nothing about that needed a conductor to diagnose it.

**What killed all three is in the gate's own log, in its own words:**

    Full test suite passes (572 passed) on the current tree, confirming the
    existing uncommitted diff hasn't broken anything. Still waiting on the
    implementer subagent to add the missing tests/test_form_filler_brief.py
    and submit.
    I'll hold here and wait for the background poll to notify me once both
    review subprocesses finish, then check the gate's status and move it to
    close.

That is `docs/process-notes/issue99.md` note 28, verbatim, one run later: an agent
that delegated and stopped, waiting for a notification nobody was going to send.
issue99 counted twelve of these and concluded the anti-stall sentence was "seven
for seven at failing." It is now three for three again — on the gate whose entire
subject is spawning a filler so that no agent has to wait like this.

The work was finished. The full suite is green at 589, +25 on gate 2's 564, exactly
the two new test files; the gate's own last log line reports 572 mid-round. What
died was the bookkeeping around a complete diff — the gate never opened its own
run, so it never got its own review panel.

## 16. A spent gate leaves a diff with no adversarial reader, and the record should say so

`drop it` is the escape the room offers for a spent child, and `amend close g3`
is what I ran. It closes the dispatch step on what stands. The diff survives —
it is uncommitted work in the tree, not something the step owned.

What does not survive is the gate's own review. Gate 2's reviewer found the one
test all three of its plan critics had missed (that nothing proved the `conductor`
branch runs *before* the `[roles]` lookup, only that it needs no entry there), and
gate 1's implementation resolved all three findings I released its plan with. On
this run's record the gate's own panel has been the strongest reader in the loop,
and gate 3 is the one gate that never got one.

So the adjudication for a spent gate is not the same act as an adjudication for a
returned one, and the form does not distinguish them. I compensated by commissioning
an adversarial read of the diff myself and recording that it was not a constellation
review panel — a conductor's substitute, weaker than the mechanism, and named as
such in the disposition rather than left to look like an ordinary pass.

## 17. The gate wrote the run's own ruling into the code, as doctrine

`_startable`'s rationale block, after gate 3, opens by citing this run's own
impasse form:

    Rationale: `IMPASSE.toml`'s own ruling on this gate's third round names
      the shape every prior round's gap shared -- "a guard whose halves live
      in two places, written as though it lived in one" -- and binds the
      fourth round: a fourth instance of a clause missing from one copy of a
      distributed guard means the cut, not the plan, is the defect.

It then states the whole rule once, enumerates its exact three call sites, and
tells an editor who grows the rule that it owes a re-read to all three.

That phrase is `docs/process-notes/issue99.md` note 30's — the four-instance
pattern issue99 found and could only describe. A conductor's ruling at an impasse
form, in a run one later, became a comment in the engine binding the next editor.
The channel was `_panel_judged_rework`'s prefill: the impasse ruling's `why` field
rode into the round as its orders, the planner carried it into the gate spec, and
the implementer wrote it into the tree.

Worth recording because `#107` — a conductor's ruling at an impasse reaching no one
— is open and filed against exactly this path. On this run it reached someone, and
what it produced is the only artifact in this repository where a process note's
finding has become a guard's own stated reason.

## 18. Three gates, three different readers finding what the others could not

By the end of gate 3 the run has a clear ranking of who catches what, and it is not
the one I would have predicted:

- **The plan panel** caught structural gaps well and mechanism poorly. Its four
  rounds on gate 1 found one real defect and then three defects in my own
  corrections (note 13). On gate 3 it found three genuine gaps in three rounds and
  passed clean on the fourth.
- **The gate's own review panel** was the strongest reader in the loop, twice. On
  gate 2 it found that no test proved the `conductor` branch runs *before* the
  `[roles]` lookup — all three plan critics had looked at the same question and
  none reached it, because the property only becomes visible with a diff in hand.
- **The conductor** caught what a criterion cannot ask for: that a spec had no names
  in it (note 7), and that a plan had become an implementation (note 13). Both are
  questions about the *kind* of artifact, and no panelist's criterion is phrased to
  ask them.

The general shape: a criterion finds what it names; a diff finds what a document
cannot state; and the seam finds what no criterion is phrased for. Gate 3 lost the
middle one to a spent conductor, which is why its adjudication says so out loud.
