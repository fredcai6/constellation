# Process notes — issue88, the dispatch run

Friction met while driving this run, recorded as it happened, in the shape of
`docs/process-notes/issue84.md`. Nothing here is doctrine. Where an entry
contradicts `docs/AGENT_GUIDE.md` or a form, the guide and the form are right
about the tree and this file is right about what the run met.

## 1. `OPEN.toml`'s `issue` field is an artifact and nothing at the step says so

The field's own note reads "The issue this run solves, per standards/issue.md —
a file in the work location; the conductor writes prefill to it." Read at
speed, "a file in the work location" is a parenthetical about where the issue
lives, not a statement that this field takes a path. I filled it with the
issue's text and the submit refused after the whole form was typed:

    issue: '<the entire issue body, escaped, echoed back inside the refusal>'
      is not a readable path -- an artifact field's value is a file's location,
      not its content

The refusal is exactly right and arrives one beat too late — the same shape as
issue84's note 1, where `note` refuses after the whole note is typed and echoes
it back inside the error. Both are the general case: a field whose value has a
*kind* announces the kind only by refusing. A template comment that said
`# artifact: a path, not the content` on the field, the way a decision field's
note lists its values, would have cost one line.

## 2. The assembly and the form disagree about whose hand writes the spec

`assemblies/run-an-issue/ASSEMBLY.toml` on the understand segment: "The
spec-writer step below is a second, later round of the same segment, **a
distinct hand**, not a second hat on this one."

`skills/spec-writer/forms/SPEC.toml`, first line: "Owned by the spec-writer
skill; filled by the spec-writer — **the conductor's own hat** for this one
round, distinct from the interrogator hat it wears to work the board."

One says distinct hand, the other says the conductor's own hat, and the engine
renders neither — the spec step is an ordinary form step with `your posture:`
pointing at `skills/spec-writer/SKILL.md`, no brief and no dispatch, so a
conductor reading only the room fills it in session. I dispatched a subagent
instead, on the reading that a distinct hand is what the segment wants and that
`skills/issue-conductor/SKILL.md`'s "default to a fresh context at each step
boundary" points the same way. Recorded because the next conductor will meet
the same two sentences and there is no third that settles them.

## 3. A rework round inherits the previous round's filled response form

`understand`'s rework mints the step-form again (there is no rework-form: "a
second round is another first cut, not a patch"). The response form path is
the same — `.agent-work/issue88/SPEC.toml` — and `cmd_status` materializes a
template only `if not dest.exists()`. So round two opens standing on round
one's *answer*, already filled in:

    spec = ".agent-work/issue88/SPEC.md"

Here that is harmless and arguably right: the spec-writer rewrites SPEC.md in
place and the path is still true. But the form is the round's return, and a
round that submits without touching it re-submits the previous round's answer
with no signal that it did. The trap is a round whose artifact is a *different*
file: the stale path submits clean, the engine records a submit, and the
record then names an artifact the round did not write.

Not filed as an issue by this run — it is one line of behaviour in
`cmd_status` and the fix is not obvious (blanking a form on a re-mint would
throw away a conductor's in-progress work on an ordinary re-render). Recorded
because a conductor who does not notice will not be told.

## 4. Two of three cold critics found real gaps the conductor's own board had already seen

Not friction — the opposite — but worth recording next to the friction, since
issue84's note 25 asked whether this much review is worth it.

Round one's spec passed one critic and drew `revise` from two. Both revises
were real and both were load-bearing: one caught that commitment 22 retired
four *prose* statements of "the engine launches nothing" while the same claim
is also encoded as two literal-substring assertions in
`tests/test_imperatives.py`, which the correction breaks; the other caught that
the spec's own commitments 4-6 and 12 described an input state only reachable
on the render that eliminates it, and that nothing said what a failed spawn
reports.

The first of those is the interesting one: the understand board *had* the fact
(q11 names those two assertions and their line numbers) and the spec still did
not carry it as a commitment. So the panel was not finding something nobody
knew — it was finding something known that failed to cross one seam. That is a
different value from "a second pair of eyes", and it is an argument for the
cold panel specifically: a reader with the board open would have skimmed past
it, and the panel reads the spec alone by construction.

## 5. Round-by-round evidence for the spec seam's three critic rounds

Issue84's note 25 asked whether this much review is worth it and answered with
its own numbers. Here are this run's, for the understand seam's cold panel,
which reads the spec and nothing else.

| Round | p1 standalone | p2 commitments | p3 simplicity | conductor |
|---|---|---|---|---|
| 1 | revise | revise | pass | rework, 3 blocking |
| 2 | revise | revise | pass | rework, 3 blocking |
| 3 | — | — | — | — |

Nine panelist reads across two rounds, six findings, none of them a repeat of
another. The two `pass` seats both found the same *kind* of thing — a numbered
commitment that restates two others and that no gate could exercise on its own
(commitment 18 in round one, commitment 20 in round two) — from two independent
fresh contexts, which is a mild signal that the simplicity seat is the one
whose findings a spec-writer most reliably reintroduces.

The strongest single finding of the run came from round two's p1 and would have
cost a gate if it had been missed: the spec committed to a palette entry taking
three named substitutions but never said how a value reaches its slot, and the
only `[commands]` precedent in this tree — `_resolve_command`'s trailing-word
append, run through `subprocess.run(cmd, shell=True)` at `engine/checks.py:189`
— cannot carry a rendered brief, which is multi-line with colons and paths in
it by construction. The recut on the issue names `evals/harness.py`'s `drive`
(one argv element, no shell) as the reference; the spec mentioned neither
`harness.py` nor the argv-versus-shell distinction anywhere in twenty-five
commitments. A planner reading the spec alone would have followed the wrong
precedent and it would have failed on the first real dispatch, not on an edge
case.

Two observations about the value, since the cost is three model calls a round:

Both revise findings in round one were things the *board* already knew. q11
names `tests/test_imperatives.py:108-124` and its two literal assertions with
line numbers; the spec still shipped without a commitment covering them. So the
panel's yield here was not new knowledge — it was knowledge that failed to
cross one seam, caught by the only reader in the run constructed not to have
the board open. That is a different argument for the cold panel than "a second
pair of eyes", and a stronger one.

And the panel did not converge on nothing. Round two's findings were entirely
distinct from round one's, on a spec that had just been rewritten to answer
round one. The loop that `impasse-after = 2` exists to catch — the same
objection returning in new words — did not appear.

## 6. `accepted` still cannot say "noted, and specifically not consenting to the deletion"

`#97` is filed and this run met it exactly as filed, twice, at the same seam.

The `calls` vocabulary is `blocking | accepted | beyond | rejected: <reason>`,
and only `rejected` takes a reason. Round three's simplicity seat returned two
findings, both proposing deletions (commitment 24 restates the out-of-scope
prose; commitment 9's corollary paragraph is longer than the one sentence the
previous round's orders asked for). Neither changes what gets built, so neither
is blocking. `accepted` is the right word for "true, and the round stands
anyway" — and it is also, to a later reader, indistinguishable from consent to
the deletion the finding proposed.

The only way to disambiguate was a `decision` note beside the call, which is
where I put it. That works and is not the mechanism: the call is what rides
into the record and into the plan's prefill; the note is somewhere else. Worth
attaching to `#97` as a third occurrence, at a seam the issue does not yet name
— #97 was observed at issue87's understand and plan seams; this is issue88's
consolidate.

Round one hit the mirror image: the simplicity seat's finding was also a
deletion (commitment 18), and I called it **blocking** rather than accepted,
partly because blocking is the only call that says "do this" without ambiguity.
That is the vocabulary bending a disposition: a non-gating finding got a gating
call because the gating call was the only unambiguous one. That is worth
recording as evidence, since it is the defect acting on a conductor's choice
rather than on a later reader's reading.

## 7. #96's missing pick, met with three genuinely different cuts

design-it-twice ran and the three rivals returned in the order p2, p3, p1. The
round the critic panel reads is p1's, because p1 closed last. The glossary says
"the conductor picks or merges before the critic panel reads any of them"; there
is no pick, and none was offered to me. That is `#96`, filed, and this is a
third occurrence.

What makes this one worth recording rather than merely counting is that the
three cuts were not variations on a theme:

- **p2 (fewest gates)** cut all twenty-four commitments as one gate, arguing the
  spawn (write side) and the status read cannot be proved apart — you cannot
  prove a spawn without a status read, and there is nothing to read without a
  spawn record. It named the fallback split in its own plan document in case the
  panel judged one gate that size unreviewable.
- **p3 (smallest touch)** cut a pure whole-word argv-substitution function with
  a unit test and no call site — explicitly dead code until a later gate uses
  it.
- **p1 (unconstrained)** cut the spawn primitive with its journal record, proved
  in isolation, deliberately *not* wired into `_dispatch_status`/`_panel_status`
  and with no live entry added to this repo's `constellation.toml`, on the
  ground that ~24 fast-suite files render a dispatch or panel room against a
  fixture that copies the real palette verbatim.

I would have picked p1's on the merits: it is the only one that is both
reviewable and not dead code, and the only one that carried commitment 20 — the
fast suite spawns nothing — into its own scope rather than deferring it. The
engine arrived at the same answer by arrival order. That is luck. Had p1
finished first, the panel would be reading p2's single gate covering the whole
spec, and the run would be a different run.

So the counterfactual is not hypothetical here, which is the part `#96`'s own
filing could not supply: the defect's cost is the difference between those two
cuts, and this run happened to land on the right side of it for no reason
anybody chose.

## 8. The gate-conductor's tier is standard, and ruling 4 says conductors are heavy

`assemblies/run-an-issue/ASSEMBLY.toml`'s execute segment declares `model =
"standard"`, so the gate dispatch brief renders `tier standard / runner
claude-sonnet-5` for a role whose posture is `skills/gate-conductor/SKILL.md`.
Epic #55's ruling 4 of 2026-09-03 says "conductors heavy, planners,
implementers and panels standard, as the palette resolves them."

Those disagree about one role. A gate-conductor is a conductor by name, by
skill file, and by what it does — it picks a panel, rules on findings, and
routes rounds — and it runs one tier below the issue-conductor above it.

I followed the brief, because the brief is what the engine renders and my own
launch order says to take the tier from it. Recording it because the ruling is
the principal's and the assembly is the tree's, and only the principal can say
which was meant. The fix, if the ruling is meant literally, is one line: the
execute segment needs a per-role tier, or the dispatch has to read the
dispatched assembly's own conductor tier rather than the dispatching segment's
default.

Note that the same segment's `model = "standard"` is also correct for
everything else it governs, so this is not "the segment has the wrong tier" —
it is that one segment-level default serves a dispatched *conductor* and its
*implementers* alike, and ruling 4 separates exactly those two.

## 9. The plan panel's second gate caught a configuration that would have shipped inert

Recorded because it is the clearest single answer this run has to note 25's
question, and because the failure mode is one no test in the cut would have
found.

The wiring gate's first cut fixed this repo's `dispatch` entry as

    dispatch = ["claude", "-p", "{brief}", "--model", "{runner}"]

and justified the shape by pointing at `evals/harness.py`'s `drive`, which is
what epic #55's own recut names as the reference. `drive`'s actual argv is

    ["claude", "-p", prompt, "--model", tier_model(tier),
     "--allowedTools", "Bash", "Read", "Write", "Edit"]

and its docstring says why in as many words: "It gets Bash and file tools and
nothing else -- no instructions about the engine beyond what it can read from
`spine` itself. That is the point."

The cut dropped the last four words of that argv. A child spawned without
them, with `stdin` at `DEVNULL` — which `_spawn` guarantees — has no tools and
no way to be granted any, so it cannot read a board, fill a form, or run
`spine`. It would sit there alive and doing nothing, while the parent's
`status` reported it *working*, from a real pid, correctly. That is precisely
the reading this whole run exists to make impossible, reintroduced one layer
below the mechanism that fixes it.

No test in the gate would have caught it, and this is the part worth keeping:
the fast suite never spawns a real `claude` by construction — that is
commitment 20, and it is correct — so the one entry the whole run turns on is
the one thing the suite is designed never to exercise. The same panelist round
found the mirror of that: nothing in the cut read the real `constellation.toml`
and asserted its entry, and nothing asserted *zero spawns* on a `workdir`
render, so the fast-suite guard was checked only by "the suite still passes" —
which stays true whether the guard works or is missing, because the spawn is a
detached fire-and-forget `Popen` whose failure is caught and logged without
changing the room. A broken guard would have fired dozens of real `claude`
processes per `pytest -q` and nothing would have turned red.

The general shape: when a change's whole point is a side effect the test suite
must never produce, the suite cannot be the proof of it, and "the suite still
passes" is a proof that passes on an empty diff. What is needed is a positive
assertion of the negative — monkeypatch the spawn and assert non-invocation —
plus a test that reads the real configuration rather than a fixture's.

## 10. Three critic rounds on one plan, and what the yield curve looked like

The 2026-09-02 ruling caps critic dispatches at three per artifact, and this
run hit that cap twice — once on the spec, once on the wiring gate's plan. The
wiring gate's three rounds are the cleaner data, because the artifact stayed
one thing across all three:

| Round | intent-fit | testability | simplicity | gating findings |
|---|---|---|---|---|
| 1 | revise | revise (x2) | pass | 4 |
| 2 | pass | revise | pass | 2 |
| 3 | pass | revise | pass | 1 |

Round one's four included the one that mattered most in the whole run — the
`dispatch` entry missing `--allowedTools`, which would have shipped a
configuration that spawns a child with no tools. Rounds two and three each
produced exactly one gating item, and both were test-enumeration lines: a
missing multi-panelist scenario, then a missing absent-key scenario. Neither
was a design error; both were "this commitment has no test that could fail."

So the curve is real and steep, and the cap is set at about the right place.
But the shape of what survives to round three is worth naming: it is always
the testability seat, and what it finds is always the same *kind* of thing —
a commitment the cut claims and no named test exercises. Two rounds of that
suggests the gap is not in the planner's attention but in the form: nothing
asks a plan to state, per commitment it claims, which named test closes it.
`PLAN.toml` has `scope` and `proof`, and a prose "New tests" list is where the
mapping lives or does not. A plan field that paired each claimed commitment
with its test would have made all three of these rounds' findings mechanical
rather than discovered — and would have made the third round's finding
impossible to write, because the empty cell would be visible in the artifact.

Recorded rather than filed: it is a form change, and this run does not touch
`PLAN.toml`.

## 11. Releasing at the cap, and how the conductor kept the record honest

The third round's finding was true and I released anyway, which is the first
time in this run I let a verified gap through a seam. Worth writing down how
that stayed honest, since "accepted" on a true finding is exactly the move
that can rot.

The finding: after this gate lands the real palette entry, commitment 3's code
path — a repository with no `dispatch` entry, rendering a dispatch room —
would have no coverage at all, because every existing test that renders one
stands on the fixture that copies the real palette, and no new test covers the
absent-key case through the wiring.

What made release defensible was not that the finding was small. It was that
the gate's `scope` already names commitment 3 among the eight it settles, so
the gate's own test-adequacy reviewer can require the test without the
conductor writing it into the orders — and that same lens had already done
exactly this twice inside g1. And the guard that cannot be dodged: the
disposition is mine at adjudication, and I said in the journal, before the
gate ran, that I would not dispose `o3` satisfied without opening a test that
drives the absent-key path through `_dispatch_status` or `_panel_status`.

That is the shape worth keeping. A seam's `accepted` is safe when a later,
independent step has to assert the same thing again with evidence in hand. It
is unsafe when the seam is the last place anybody looks. The execution-state
board is what makes the difference here: an obligation I decline to dispose
stays open and pulls another gate, so releasing cannot quietly become
finishing.

## 12. The run reproduced its own subject: a gate-conductor stalled waiting, one tier down

Worth more than the rest of this file, because it happened inside the run that
exists to make it impossible, and because it shows exactly what the fix would
have bought.

Gate g2's conductor dispatched its implementer, the implementer stopped
without filling its form, the gate-conductor noticed and nudged it — and then
ended its own turn saying "Waiting for it to resume and report back." Nothing
was going to wake it. This is note 15 and note 24 together, one tier down,
under a dispatch brief that said in as many words: *never end a turn waiting
for something, nothing will wake you, poll in a loop instead.* Issue84's note
15 already recorded that an instruction-based fix does not hold — "the second
time under a brief written to prevent the first" — and this is the third
recorded instance of the same thing, mine.

What I could see from above, and what I could not:

`spine issue88.g2` said `work (1 of 3)` the whole time and kept saying it.
`IMPLEMENT.toml` was an untouched template. `git status` showed
`constellation.toml`, `engine/cli.py` and `tests/conftest.py` modified and
`tests/test_dispatch_wiring.py` new — so real work had happened and no form
recorded it. That is note 16's trap precisely: an unfilled form beside a real
diff is what a working child, a dead child, and a stopped child all look like.
I had no way to tell which I had.

What actually told me was not the record. It was that the subagent harness
reported the agent *completed*, and its final text said it was waiting. Both
of those are outside the engine — the harness's own liveness, and prose I had
to read. Had this gate-conductor been spawned by the engine through the
`dispatch` entry this very run is building, its pid would have been in g2's
parent journal and `spine issue88` would have said **gone without returning**
rather than showing me a step that had not moved. That is commitment 15, and
this is the occurrence it is written against.

The recovery is the other half of the lesson. I did not dispatch a replacement
— note 16 is what happens when a parent acts on the artifact alone. I checked
that the subagent had genuinely finished, then resumed *that same agent* with
its own context intact, and told it to determine whether its implementer was
still alive before touching the form itself. One agent per form, always; the
question "is the child alive" has to be answered before the question "should I
replace it", and today only the harness can answer the first.

Two smaller things this exposed:

The anti-stall sentence in a dispatch brief is now three-for-three at failing
to prevent the stall. It is worth keeping — it costs a line — but it should
not be counted as mitigation. What it did buy here was a fast diagnosis: the
agent said it was waiting, in those words, because the brief had made waiting
a named thing.

And the stall was two levels deep. The implementer stopped, then the
gate-conductor stopped waiting on it. A liveness read that a parent can
perform without opening the child as a run has to work at every tier, not just
the top one — the parent of the stalled implementer was itself a dispatched
child.

## 13. A panel caught the conductor's own ruling being dropped

The read-side plan's first cut touched `standards/glossary.md` — to write the
new `dispatch` and `liveness` entries — and said nothing about `#94`, the
filed issue that puts `impasse` and `projection` into that same file.

This run had already ruled on that. At the understand board, row q13 asked
whether epic #55's three ride-along issues fold into this run's gates, and it
was settled under the principal's own recorded rule ("each small enough to
fold into whichever gate touches its seam") as: `#94` rides along if and only
if a gate touches `standards/glossary.md`. That ruling is in the run journal
as a decision note and in `CONSOLIDATE.toml`'s `key-terms` field, which the
plan itself cited — one paragraph above the sentence it then ignored.

So the ruling was recorded, carried into the plan's own prefill, quoted by the
planner, and dropped anyway. The panelist that caught it did so by reading the
`key-terms` field to the end and then checking the glossary for the headwords,
which are not there.

Two things worth keeping from this.

A conductor's ruling is not self-enforcing just because it is journaled. This
one had every advantage — recorded at the seam that made it, carried in
prefill, cited by the agent that then dropped it — and only an independent
reader caught it. The obligations board is what makes spec commitments
self-enforcing: an undisposed row pulls another gate. A conditional ruling
made at the understand board has no such carrier; it lives as prose in a field
and depends on someone re-reading it at the moment its condition comes true.
That asymmetry is the finding, and it is a real gap in the machinery rather
than a lapse by this planner.

And it argues for the `beyond`/ride-along vocabulary being weaker than it
looks. This run recorded three ride-along candidates at q13 and ruled two of
them out; the one it ruled *in* was conditional on a fact ("a gate touches
this file") that would not be known for hours. A conditional acceptance with
no row anywhere is a promise with no owner, and the only reason it survived is
that a critic panel happened to be pointed at the plan that broke it.

## 14. Dispatched children ran twice, and the second copy found the first mid-write

Several panelist and planner slots in the plan segment reported the same
thing: they opened their run, began work, and discovered partway through that
another instance of the same task had already filled and closed it. One
planner's report is explicit about the damage — its `REWORK.toml` write was
correctly rejected as "modified since read", but its `plan.md` write landed on
top of the other instance's file, because the write path does not conflict-check
a file that did not exist at its own last read. It repaired this by pulling the
frozen fields back out of the run's own `journal.toml` submit entry and
rewriting `plan.md` to match, so the artifact and the record agree again.

That repair is only possible because the journal is append-only and the submit
entry froze the authoritative text. The *artifact* was clobbered and
recoverable; had the two instances raced on the response form instead, the
record would have kept whichever landed last, which is note 16's own scenario
arriving by a different route — not from a parent double-dispatching, but from
one dispatch being run twice.

I did not double-dispatch: each slot was spawned once. The duplication came
from below the engine, in how a completed agent can be resumed, and the engine
has no view of it at all. Which is the sharper version of the point: this run
built a liveness read for *whether* a child is running, and this failure is
about *how many* copies of it are. A pid per child answers the first and not
the second. If the engine spawns and journals one `dispatch-started` per child
and something else starts a second copy of that same child, the record shows
one pid and one child, and looks correct.

The mitigation that actually worked, and which cost one line: every panel and
planner brief in the second half of this run began with "run `spine <child-id>`
first — if that run already exists and is closed, another pass already
completed this slot; report that and stop." Every slot that hit the race
reported it and stopped instead of redoing the work. That is a brief patching a
gap again, with note 15's caveat attached — it worked here and it is not a
mechanism.

## 15. A gate's whole diff disappeared into a git stash

Mid-way through g3's implement round the working tree went clean. Three files
that had been modified minutes earlier — `docs/V2_DESIGN.md`, `engine/cli.py`,
`engine/render.py` — were back at HEAD, no untracked files, and
`IMPLEMENT.toml` still an empty template. From the engine's side nothing had
happened at all: `spine issue88.g3` said `work (1 of 3)`, which was true before
and after.

The work was in `stash@{0}` — `WIP on issue88: f42b48d` — 131 insertions
across the three files. Something inside the gate ran `git stash`. The reflog
shows only `reset: moving to HEAD` entries, which is the engine's own commit
path, so the stash came from an agent, not from `cmd_submit`.

Three things worth keeping.

The engine's record could not see it. A gate's diff is the one part of a run
that lives entirely in git and not in the journal, so the whole apparatus this
run built — pids, `dispatch-started` entries, four-state reads — would have
reported the gate as working, correctly, while its output sat in a stash. The
liveness question this issue answers is "is the child running"; it does not
and cannot answer "is the child's work still there." Only `git status` answers
that, and only if someone runs it.

I found it because I was polling `git status --short` alongside `spine` on
every cycle, out of habit rather than design. Nothing in the conductor skill
says to do that, and the gate adjudication form's own imperative — root-verify
the returns, open the artifact, re-run the check — applies at the *end* of a
gate. There is no checkpoint that looks at the tree in the middle of one.

And the division of labour held, which is the part I would repeat. A gate's
interior is the gate-conductor's, so I did not `git stash pop` into the middle
of its implement cycle. I sent it what I could see — the stash entry, the file
list, the empty form, the untouched step — and told it to recover the work
itself and to check the restored diff against its own scope, since the stash's
three files are narrower than the scope (no `standards/glossary.md`, nothing
under `tests/`), so either more work was never written or more was lost.
Acting inside a child's run to fix a child's problem would have made the next
question — what did the gate actually build — unanswerable from its own
record.

### 15a. Correction to note 15: the stash was transient, and I read a snapshot as a state

The gate-conductor checked immediately after my message and found the stash
gone, the three files back, and two more (`tests/test_brief.py`,
`tests/test_verdict_panels.py`) modified beyond what the stash had held — with
the diff still growing between two of its own consecutive checks. Its
conclusion, which is right: the implementer was alive the whole time and the
stash was a transient step inside its own round, most likely a way of running
the suite against a clean tree. Nothing was lost, and there was nothing to
recover.

I raised it as a possible loss on the strength of one `git status` and one
`git stash list`, both taken at a single instant. That is the same mistake
note 16 records at the level of forms, arriving at the level of the working
tree: I read one snapshot of an artifact and inferred a state — "the work is
gone" — from evidence equally consistent with "the child is in the middle of
something." An empty working tree during a live implement round means no more
than an unfilled form does.

What kept the mistake cheap was the division of labour rather than the
diagnosis. I did not `git stash pop`. Had I restored that stash into the tree
while the implementer was mid-round, I would have been a second writer in its
working directory, and the two of us would have raced over `engine/cli.py`
exactly as two agents race over one form. Instead I reported what I saw to the
agent that owned the interior and let it check. It looked, found the answer in
one command, and kept working.

So the useful pairing is: note 15's real content is that the engine's record
cannot see the working tree at all, which stands. This correction is that a
parent watching the working tree to compensate will read transients as
disasters, because a tree mid-round is as ambiguous as a form mid-round. The
fix for both is the same shape and this run does not build it — something a
working child touches *because* it is working, that a parent can read without
opening the child. A pid says the process exists. It does not say the process
is making progress, and neither does a diff.

## 16. The engine was dispatching alongside me for the last third of the run, and I did not know

Written after close, from the archived journal, because it explains most of
what notes 14 and 15a were groping at and is the single thing the principal
most needs from this run.

The parent journal carries **fourteen `dispatch-started` entries**. Every one
is a real child the engine spawned itself, through the `dispatch` palette
entry g2 landed. The first is `issue88.g2` at `08:26:01Z`; the last is
`issue88.g3` at `09:19:59Z`. In between: every planner round
(`plan-aaacb`, `plan-a334e`, `plan-ac391`) and every panelist of three
consecutive critic panels (`plan-a6534.p1/p2/p3`, `plan-ad34e.p1/p2/p3`,
`plan-ad081.p1/p2/p3`).

I dispatched every one of those as a subagent by hand, at the same time.

So from `08:26Z` onward there were two agents pointed at each of those forms:
mine, and the engine's. That is note 16 of `docs/process-notes/issue84.md` --
the double-dispatch that run only nearly committed -- performed for real,
fourteen times, by the run that was built to prevent it. It is also the whole
explanation of note 14 above: every "the run closed underneath me", every
"another instance of this same task already submitted", every clobbered
`plan.md`. Those were not the harness resuming a completed agent, which is
what I guessed at the time. They were the engine's child and my child racing
for one form, and in several cases the engine's won.

The mechanism did not misfire. `o19` held perfectly -- no child was spawned
twice by the engine, across all fourteen. The record is accurate and always
was. What failed is that nothing told *me* the situation had changed
underneath my own posture.

The precise cause is worth stating, because it is not "the conductor was
careless":

`_palette(tree)` reads `constellation.toml` from the run's worktree, and g2's
diff was uncommitted in that worktree while g2 was still being reviewed. The
moment g2's implementer wrote the `dispatch` entry into that file, the entry
was live for the parent run. My next `spine issue88` -- a poll, run to check
whether the gate had returned -- rendered the execute segment's dispatch room
and spawned a second `issue88.g2`. Polling stopped being a read and became an
act, silently, between one poll and the next, because a *child gate's
uncommitted work* changed the parent's own behaviour.

Three things follow.

**A run that changes the engine changes itself mid-flight.** This repo builds
itself with itself, so a gate's uncommitted diff is live for the run that
dispatched it. Nothing in the tree marks that boundary, and no room says "the
engine now starts these itself." The conductor skill still tells a conductor to
dispatch, the brief still renders `open it:`, and both were still true for the
first half of this run and quietly false for the second.

**This is the argument for `wait` and `drive` that no design document makes.**
Wave 6b and 6c are currently justified as convenience -- a verb that blocks
until children return, and a walker that runs the loop. What this run shows is
that they are a *correctness* requirement once the engine spawns: with the
engine dispatching, a conductor that also dispatches is a second writer, and
the only safe conductor is one that does not hand-dispatch at all. The room
has to say which world it is in, and `wait` is what makes not-dispatching
survivable.

**The four-state read cannot see this and should not be asked to.** It
answers "is this child's process alive", and both of the two agents at each
form were alive. A pid per child is a liveness fact, not a uniqueness fact.
The guard that would have caught it is the one `o19` already implements --
never spawn a child that has a record -- extended to a fact the engine does
not have: whether *anything else* is already working that form. Nothing in the
record can know that, because a hand-dispatched child writes no record at all.
That, and not the flakes or the stash, is the sharpest open question this run
leaves behind.
