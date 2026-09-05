# Process notes — issue99, the `wait` run

Friction met while driving this run, recorded as it happened, in the shape of
`docs/process-notes/issue80.md`. Nothing here is doctrine. Where an entry
contradicts `docs/AGENT_GUIDE.md` or a form, the guide and the form are right
about the tree and this file is right about what the run met.

## 1. The open form's fields do not reach the spec-writer, so the rulings went into the issue artifact

`OPEN.toml` carries `authority`, and the open step is minted with
`carries = false` (this run's own `journal.toml`). Only a transition marked
`carries` folds its fields into the run's prefill (`engine/cli.py:1115`), and
open is not one. So the authority block — which in this run holds six standing
rulings that are the whole design envelope — is recorded on the journal and
reaches no later step by the mechanism.

The channel that does reach later steps is the `issue` artifact: it is a path,
the field's own note says "the conductor writes prefill to it", and every
downstream reader opens the file. I appended the six rulings to
`.agent-work/issue99/issue.md` under their own heading for that reason, and
they are also in `authority` where the form asks for them.

Recorded because it is a real asymmetry rather than a lapse: the one field in
the assembly whose whole content is orders is the one field with no carrier,
and the workaround is a convention (write it into the artifact too) that
nothing states. issue88's note 13 is the same shape one seam later — a
conductor's ruling that was journaled, carried, cited, and dropped anyway.

## 2. The tree forbids the word this run exists to add

`tests/test_imperatives.py:140-142`, in full:

    for name, text in (("DISPATCH", render.DISPATCH), ("PANEL", render.PANEL)):
        assert "wait" not in text.lower(), (
            f"{name} tells the reader to wait; nothing is coming unless they act")

The two strings a `wait` verb most needs to appear in are the two strings a live
test forbids the word `wait` in. The test is not arbitrary and its docstring says
why: PANEL's first draft ended "dispatch each panelist and wait for its verdict",
and a light model did the waiting literally in two of five runs — it started a
background monitor to poll for a verdict nobody was coming to give, and stopped.

So the ban is on a *passive* wait with no move attached, and `spine <wid> wait`
is an active, typeable move. The letter of the test and its spirit have come
apart, and this run is the thing that pulls them apart. That is the cleanest
example I have met of a guard written against a failure mode outliving the
vocabulary it was written in: the word was a proxy for the failure, the proxy was
right for two years of runs, and the fix for the failure is now spelled with the
banned word.

Worth keeping for the general shape rather than the instance. A guard that pins a
*word* rather than a *property* holds exactly until the tree acquires a legitimate
use of the word, and then it fails loudly rather than quietly — which is the good
outcome, and it is only the good outcome because the assertion carries its own
reason in a docstring. A bare `assert "wait" not in text` with no docstring would
have been read as a style rule and either deleted or worked around.

Its neighbour is the counter-example in the same file's spirit.
`tests/test_promises.py` has two verb checks side by side: one derives its verb
set from `re.findall(r'"(\w+)": cmd_', cli.py)` and self-updates the moment
`main()`'s dict gains an entry; the other hardcodes
`verbs = {"submit", "note", "amend", "close", "status", "check"}` and must be
edited by hand. Same file, same subject, one maintains itself and one does not.

## 3. Two decision rows the rulings delegated, and the mechanism decided both

The principal's standing rulings delegated two design calls to this run and asked
for the reason on the record (respawn shape; the scope of the one-line idle
statement). I expected to weigh both on taste. Neither came down that way.

The respawn shape had three candidates — automatic, a flag, a confirmation — and
the confirmation was eliminated by one line of existing code:
`engine/checks._spawn` gives every spawned child `stdin=subprocess.DEVNULL`
(engine/checks.py:160). The caller `wait` exists for is a dispatched conductor, so
a confirmation prompt is not awkward there, it is unanswerable. The flag was
eliminated by the run's own subject: a flag keeps the entire failure and moves
only who types the command, which is note 24's defect one layer down.

The idle-statement scope came down the same way. "Every room" loses not on taste
but because a form step can never have anything outstanding, so the line would be
present in every room in every state and would carry no information — and note
24's own better-fix sentence already uses the word *idle*, which is a state only
where *busy* is also a state.

The pattern worth recording: a decision row that looks like a preference is often
a fact about the mechanism that nobody has looked up yet. Both of these were
settled by opening one file. The board's `move` column has `ask` for a decision
and `read` for a fact, and both of these rows were typed `ask` and settled by
`read`.

## 4. The distinct hand read behind the board and found what the board's own root-verify missed

`skills/spec-writer/SKILL.md` asks for a standalone document and nothing about
auditing the board. The spec-writer produced one and, unasked, reported three
corrections to the board it read from:

- q15 claimed to sweep "everything in `engine/` that prints a command for
  starting or restarting a child" and named two refusals, both in `cmd_submit`.
  It missed `cmd_close`'s "not complete" refusal (`engine/cli.py:2787-2799`),
  whose dispatch branch builds the identical forbidden `open its child: spine
  open ...` escape at 2794-2795. I re-opened it: real, and the same shape ruling
  3 forbids.
- Three cited line numbers had drifted by a few lines each — `_respawn_cmd`,
  `_spawn_outstanding`'s guard, and one tagged rationale block. Substance right
  in every case, numbers wrong.

The cause of the drift is worth naming because it will recur in this tree
specifically. Every function in `engine/` sits under a tagged rationale comment
block (`[respawn-command]`, `[spawn-once-per-render]`) that is often longer than
the function. Grepping for the function's name lands in the comment first, and
the line number you carry away is the comment's. The comments are the reason
this codebase is readable and they are also a systematic off-by-fifteen for
anyone citing from a grep.

The cause of the miss is different and duller: I grepped `cmd_submit` because
that is where I had just been reading. A refusal that names a child's open
command can live in any verb that refuses on a pending step, and `cmd_close` is
the other one.

What is worth keeping is that neither correction came from the mechanism. The
board has no reviewer; `validates = "board"` at the consolidate transition
checks that rows are answered and that a decision carries words, not that an
answer is true. The only reader who checked was one the assembly created for a
different purpose — issue88's note 2 records that the assembly and the skill
disagree about whether the spec-writer is a distinct hand or the conductor's own
hat, and this run is a small piece of evidence for "distinct hand": a hat cannot
audit the head wearing it.

## 5. A green baseline before the first gate, and it cost two and a half minutes

`palette:test` at `59be43e`, in the run's own worktree: 486 passed in 153s, no
flakes, including the spawn test filed as flaky. Recorded so a red suite inside a
gate is unambiguous about where it came from, which issue80's note 11 shows is
the expensive question in a repository that builds itself with itself.

## 6. The cold panel earned its three calls, and one finding was against the board rather than the spec

Round one of the understand seam: p1 `pass`, p2 `revise`, p3 `revise`, five
findings, no two about the same thing. I called all five blocking.

The one worth writing down is p1's. It classed both of its findings `beyond` —
"real, and outside what this spec set out to do" — and one of them was that
commitment 49 justified a ride-along against `#94`, which has been CLOSED since
issue88: both headwords are in `standards/glossary.md` today, landed by `b254ccc`,
whose own commit message says #94 rode along on that gate. `gh issue view 94`
returns `state: CLOSED`, and that one command refutes the whole paragraph.

The paragraph was mine. The board's q12 ruled #94 in as a ride-along, flatly and
at some length, citing issue88's note 13 on the cost of ruling one in
*conditionally*. I had the right lesson from the right note and applied it to an
issue that no longer existed. The move the row needed was not `ask`, which is what
I typed in its `move` column; it was `read`, and the thing to read was the
tracker.

Three things follow.

**A cold panel reading only the spec caught a defect in the board.** It could not
see the board. It saw a sentence in the spec that a fresh reader could not resolve
— "a separate open issue asks for glossary work" names nothing — pulled the thread
through the tracker, and came back with the issue's state. That is the argument
for the cold seat stated more sharply than issue88's note 4 could: not "knowledge
that failed to cross a seam", but knowledge that was *wrong on the far side of a
seam nobody was checking*. Nothing in the run re-checks a board row after it is
answered. `validates = "board"` checks that rows are answered and that a decision
carries words. It cannot check that an answer is true, and it is not supposed to.

**`beyond` was the wrong call and the panel does not get to make it anyway.** Both
of p1's findings were about the spec's own text, which is squarely inside what the
spec set out to do; `beyond` means it leaves as a triage candidate rather than as
work. Had I taken the panel's classes at face value, the false claim about #94
would have shipped into three planners' prefill as a triage note. The
issue-conductor skill's line — dispositions are yours, not the panel's — earned
itself here in one round.

**The staleness has a general shape in this repo.** An epic's closing plan names
ride-alongs by number; the runs that execute the plan are days apart; and the
plan's list is a snapshot. Every ride-along carried forward into a later run is a
claim about the tracker's *present* state, and the only thing that settles it is
`gh issue view`. issue88 ruled #94 in conditionally and the condition was checked;
I ruled it in flatly and the *issue* was not.

## 7. Backticks in a `spine note` were eaten by the shell before the note reached the journal

`spine issue99 note decision "... USAGE omits `up` exactly as ..."` — typed in
double quotes, with the verb name in backticks the way this repo writes a verb
everywhere else. Bash ran `up` as a command twice, printed `up: command not
found` to my terminal, and spliced empty strings into the note. The engine
recorded the note, correctly, with two words missing.

Nothing in the failure path belongs to the engine. `note` took a string and
journaled the string it was given. But the shape is worth recording because it is
specific to this repo and will recur: every convention in this tree writes a verb,
a field or a path in backticks, and every note about the work is typed at a shell.
A `decision` note is often the only record of a ruling — this one was my whole
reasoning for two blocking calls — and the failure is silent in the journal, loud
only in a terminal nobody re-reads.

Two things I would keep. Single-quote every `spine note`, which is what I did for
the correction. And the correction itself: the journal is append-only, so the fix
is another note saying what the first one lost, not a quieter re-note — a note
that dropped two words without saying so is the record lying quietly, which is the
class of defect wave 5 of this epic exists to close.

## 8. Two rounds at the understand seam, and the second one was about the spec's own excess

| Round | p1 standalone | p2 commitments | p3 simplicity | conductor |
|---|---|---|---|---|
| 1 | pass (2 findings) | revise (2) | revise (1) | rework, 5 blocking |
| 2 | pass (clean) | pass (1 finding) | revise (1) | rework, 2 blocking |

Round two repeated nothing from round one. Round one's five were about things
missing or wrong — a dropped site, a wrong count, a stale tracker claim, a
contradiction between two commitments, an unverifiable citation. Round two's two
were about things present and unearned: a committed internal factoring for a
consumer this cut does not build, and a justifying sentence refuted by reading the
constant it describes.

That is issue80's note 6 arriving on schedule and pointing the other way than it
did there. In that run a rework moved the finding surface because the reworker
added text on its own initiative. Here the orders were explicitly surgical and the
diff was five changed regions; the new findings were not against the new text at
all. They were against original text that round one's readers, busy with real
gaps, had not got to. So a rework's second panel is not only re-reading — it is
reading with the loud defects gone, which is when the quiet ones become visible.

Round two's simplicity finding is the one worth keeping. It asked to delete
commitment 12 — a two-valued return boundary — and argued from precedent that
`checks.hand_in`'s own two-valued return earns its keep because its one call site
consumes it in the same commit, while `wait`'s counterpart has no call site
anywhere in this delivery. Checking it turned up the stronger argument the panel
had not made: the one named future consumer re-folds the run's state every
iteration by construction, so a return value telling it what it is about to
re-read is redundant even for it.

And it is the one finding I could not simply accept, because the commitment it
asked me to delete was this spec's only carrier of a standing ruling from the
principal. The ruling says design nothing for the next verb beyond keeping `wait`
callable from a loop; commitment 12 was that sentence turned into machinery, and
the panel was right that the machinery was more than the sentence asked for. The
route out was to keep the slot and weaken it back to the obligation — which is a
disposition the `calls` vocabulary has no word for. `blocking` says do something
about this, and what I meant was *do less than this commitment says, and not
nothing*. That went in the orders, where a rework can carry it, and it is a fourth
occurrence of the shape #97 already names from the other side.

## 9. Three rounds at the understand seam, and the cap was not what decided the release

| Round | p1 standalone | p2 commitments | p3 simplicity | conductor | findings |
|---|---|---|---|---|---|
| 1 | pass | revise | revise | rework, 5 blocking | 5 |
| 2 | pass | pass | revise | rework, 2 blocking | 2 |
| 3 | pass | pass | pass | release, 2 accepted | 2 |

Eight findings across three rounds, and no finding in any round repeated one from
an earlier round. The `impasse-after = 2` loop the segment exists to catch --
the same objection returning in new words -- never appeared.

Three things about the curve.

**The findings changed class as the rounds went on, and the order is not
accidental.** Round one's five were things missing or wrong: a swept site dropped
in silence, an arithmetic error, a stale tracker claim, a contradiction between two
numbered commitments, an uncheckable citation. Round two's two were things present
and unearned: machinery committed for a consumer this cut does not build, and a
justifying sentence refuted by reading the constant it described. Round three's two
were citation-level: a line number pointing at a function's last line rather than
its first, and one sentence quoted as shared by two constants that differ. Loud
defects first, then excess, then precision -- and each class only becomes visible
once the one before it is gone. That is an argument for three rounds rather than
one long one, and it is a different argument than "more eyes."

**Two of the three rounds were released by a `pass` I would have given anyway.**
Round three's two findings were both true and I released on them. The test I
applied is issue88's note 11: an `accepted` is safe when a later, independent step
has to assert the same thing again with evidence in hand, and unsafe when the seam
is the last place anybody looks. Here the plan segment's own critic panel reads the
plan against this spec, and each gate's review reads its diff, so two later readers
must re-derive anything the misquote would have misled a planner about. p1 made the
same argument itself, and better: whoever rewrites `render.PANEL` has to open
`render.py` to do it, so the misquote cannot survive contact with the work.

**What did not decide the release is worth recording next to what did.** Round
three was the third and last critic dispatch, so a further rework would have minted
the impasse form rather than another spec-writer round, and walking through that
outlet to rule `advance` anyway would have bought nothing. The cap and the ruling
happened to agree. issue80's note 6 records the same coincidence at its own seam
and I am recording it for the same reason: a cap that agrees with the judgment is
invisible, and the only way to know whether it is set right is to write down, at
the time, that the judgment did not need it.

## 10. The release seeded a forty-nine-row obligations board, and that number is the spec's shape rather than its length

`CONSOLIDATE.toml`'s `obligations` field takes one block per commitment, verbatim,
and mints `EXECUTION_STATE.toml`. Forty-nine rows landed. issue80's run seeded
fourteen.

The difference is not verbosity. Ten of the forty-nine (36-45) are one prose site
each -- a glossary entry, a design-doc table, a skill's sentence, a form's
imperative, a palette comment, four tagged rationale blocks in one file. Every one
of them is a place where a true sentence becomes false and no test goes red. The
spec could have carried them as one commitment reading "update the prose"; it
carries ten because an undisposed row pulls another gate and a bullet inside a
paragraph does not.

That is the mechanism working as designed, and it is also the first time in this
run I have seen the cost of it: the board is now the largest artifact in the work
location, and every gate's advance folds it. Worth watching rather than worth
fixing -- but if a later run finds the execution-state fold expensive, this is the
run that made it big, and the reason it is big is that ten silent-prose sites got
ten rows on purpose.

## 11. A critic cited the rival plan the engine had discarded, by path

design-it-twice ran and the three rivals returned at 19:04:13 (p1,
unconstrained), 19:04:41 (p2, fewest gates) and 19:06:26 (p3, smallest engine
touch). The engine kept p3, because p3 closed last. That is `#96`, and this run
is at least its fourth recorded occurrence.

I verified the mechanism at this rev rather than citing issue80's note 8 for it.
`_projected_source` walks backward through the segment's steps and takes the first
whose `st["done"]` entry carries the gate fields; `st["done"]["plan-1"]` is written
by the last arriving return. `PLAN_TO_EXECUTE`'s own `plan` field points at a
document, while the projection copies *fields* from the `done` entry — so naming a
different plan artifact there changes what the record says and not what gets cut.
The conductor's only lever is `rework`, which sends the surviving cut back. There
is no "take that other one."

What is new, and worth more than the count: **the critic panel found the rival
itself.** `issue99.plan.p1`, judging p3's cut against the spec, wrote that a
sibling candidate — it named `plan-1/p1/plan.md` by path — "covers the identical
ground ... and explicitly enumerates commitments 5, 6 and 29", and used that as
evidence that those three are in scope for a gate of this shape rather than
implicitly out of it.

So a cold critic, briefed on one plan, walked the work location, found the plan the
engine had discarded, and reasoned from it. That is the defect seen from a new
side. issue80's note 8 records the cost as a counterfactual the conductor can only
argue: the rivals "still sit in the work location, complete and unread by
anything." They are not unread. The panel reads them, can tell which is better on
the point at issue, and has no move except `revise` — while the conductor above it,
holding the same three documents, has no move except sending the kept one back.

Three of three critics returned `revise` on the same defect. One defect found three
times is a cold panel working rather than a loop, and I ruled `rework` on it.

## 12. I checked the kept cut against issue80's lesson and the lesson did not apply

p3's cut builds `wait` as a pure addition: the verb exists and blocks, and
rendering still spawns, with the spawn relocation deferred to gate 2. The surface
resemblance to issue80's own p3 — "a gate that builds a function in isolation,
wired to nothing" — is strong, and that shape there generated three rounds of
critique and an impasse.

It does not apply, and the difference is worth writing down because the wrong
import would have cost this run a round. issue80's p3 built a function no caller
called. This p3 builds a verb that is live and useful the moment it lands:
rendering still starts children, and `wait` watches the ones a render started, so
`spine <wid>` then `spine <wid> wait` works end to end from gate 1. The tree is
never in a broken or inert state at a gate boundary; gate 2 moves who starts the
child, and the verb's own contract does not change.

The test that separates them is not "does this gate touch its callers" but "is
there a real user of this gate's output the moment it lands". Recorded because I
went looking for the earlier defect, expected to find it, and had to talk myself
out of a ruling the evidence did not support.

## 13. A plan rework is one planner, not another design-it-twice round

Worth a line because it surprised me and it is the cheap half of an expensive
seam. Submitting `rework` at the plan transition minted a single dispatch child
(`issue99.plan-a3714`) against the segment's rework-form, not three fresh rivals
under three constraints. So design-it-twice is a first-round shape only: the
rivals are for cutting the gate, and a rework is for fixing the cut that survived.

That makes the plan seam's cost curve very different from the understand seam's. A
plan rework costs one dispatch and carries the blocking findings as its orders,
where an understand rework costs one spec-writer round and a fresh three-critic
panel behind it.

## 14. Two rounds at the plan seam, converging on the cut rather than repeating

| Round | intent-fit | testability | simplicity | conductor | findings |
|---|---|---|---|---|---|
| 1 | revise | revise | revise | rework, 3 blocking | 3 (one defect) |
| 2 | revise | revise | revise | rework, 4 blocking | 4 |

Round one was three independent readers finding one defect: the kept cut named
commitments 1-4 and 7-11 as delivered and 13-49 as deferred, and left 5, 6, 12, 29
and 31 in neither list. One defect found three times is a cold panel working, not a
loop.

Round two found nothing from round one and moved a level down, to the cut's own
intermediate state and to its proof:

- Two critics independently found that in gate 1's world `wait` starts nothing, so
  a conductor who types `spine <wid> wait` *first* on a fresh dispatch or panel
  step gets a silent no-op — no child started, nothing blocked on, no word said
  about why — which contradicts the spec's own section 2 in the reader's face.
- The testability seat found that the plan's owed-test list covers only the paths
  where `wait` does *not* block, so a test module scoped exactly as written would
  go green even if the block loop never blocked, never unblocked, or ignored
  `--for`. That is issue88's note 9 arriving one seam earlier: a proof that passes
  on an empty diff, for the one mechanism the gate is named for.

The second is the one I would keep if I could keep only one. Round one's finding
was about what the plan *said*; round two's testability finding is about what its
proof *could fail on*, and it is the difference between a plan that is accurate and
a plan that is checkable. issue88's note 10 predicted the seat: "it is always the
testability seat, and what it finds is always the same kind of thing — a commitment
the cut claims and no named test exercises." Two runs, same seat, same class.

## 15. What I ruled against at the plan seam, and why the record needs it

The live call at round two was whether to widen gate 1 rather than to name its
divergence. The discarded rival — `plan-1/p1` — argued in its own purpose that the
verb and the spawn relocation "are one gate because they are one code move:
`_dispatch_child`'s call to `_spawn_outstanding` comes out of the render path and
into `wait`'s own loop — there is no intermediate state where both hold." Two rounds
of critique have now converged on the hole in the split, which is exactly what that
sentence predicted. The temptation to override the cut was real.

I did not, and the reasons are worth having on the record rather than in my head:

**The split throws away almost nothing.** Every piece gate 1 builds — the verb, the
block loop, the branch order, the two constants, the `--for` flag — is needed in the
end state unchanged. Exactly one test inverts when gate 2 lands.

**Widening drags a 447-line test split into a gate that is already a new verb.**
Commitments 13-15 cannot land without 34-35, because `test_dispatch_wiring.py`
asserts render-time spawn throughout. issue88's note 10 measured what a large gate
costs in rounds.

**The panel priced its own finding as naming, not widening, and it was right.** An
incremental cut is legitimate when its divergence from the end state is named and
tested *as* a divergence rather than discovered by whoever gets there first.

And I wrote down the condition that would change the ruling: if round three finds
the same divergence again in new words, the cut is the defect and I rule that way at
the impasse. issue80's note 14 records a conductor doing exactly this and then having
the condition not fire, because round four's finding was a different class. Writing
the condition down is what makes that judgeable either way.

The uncomfortable part is where that reasoning lives. It is a `decision` note in the
journal and nowhere else. The four blocking findings are what the next planner
receives, and they say "name it"; my reasoning for why naming is enough, and the
condition under which it stops being enough, reaches nobody. That is `#107` from the
plan seam rather than from the impasse form — the same missing channel, one step
earlier than the issue describes it.

## 16. The first gate-conductor died, and the log gave the failure a number

`issue99.g1` read `gone without returning` on the poll after it started. The
recovery took one command, because `dispatch.g1.log` ends with the whole story in
two lines:

    Background tasks still running after 600s; terminating.
    I've dispatched the implement round to a subagent as the gate-conductor skill
    and dispatch-as-subagents convention require -- I don't write the diff myself.
    ... I'll pick up the gate at the next form once it reports back.

Two failures, and only the first is the one already on the record.

**The anti-stall sentence failed again**, for at least the fifth recorded time
across four runs (issue84's note 15, issue88's note 12, issue80's note 13 twice,
and now this). The brief I wrote for the parent's own dispatch did not reach this
child — it was engine-started from the gate's own room — so this conductor had only
`render.DISPATCH`'s wording, which does end on the reader's own move. It stalled
anyway, in the same words each of the others used.

**And the stall now has a measured ceiling, which is new.** The harness did not
leave it waiting forever; it killed it at 600 seconds with the background task still
running. So a dispatched conductor that hand-dispatches a subagent and waits does
not merely hang — it is terminated, and its child, being a subagent rather than a
detached process, dies with it. That is issue80's note 12's second case with a
number attached, and the number is the thing worth carrying: 600 seconds is less
than one implement round on this repository, whose fast suite alone runs 160
seconds.

That sharpens the argument for this run's own subject in a way I had not expected to
find from inside it. `wait` is currently justified as saving a conductor turns. What
this shows is stronger: a conductor that has *no* blocking verb must either poll
(spending turns) or delegate-and-wait (being killed at 600s). Both are broken, and
the second is broken in a way that destroys work rather than merely wasting it. The
tree here carried +101 lines of engine code and a 354-line test module with no
`IMPLEMENT.toml` entry and no submit anywhere — recoverable only because a parent
happened to be polling `git status` alongside `spine`.

## 17. What the room could not tell me, and what I had to establish by hand

The four-state read did its job: one word, `gone without returning`, and the
diagnosis took one command. Everything after that was outside the mechanism.

To write the respawn's brief I had to establish, by hand: that the gate's run exists
but carries no submit (read `g1/journal.toml` with `tomllib`); that
`IMPLEMENT.toml` is an untouched template; that the tree holds +10 in
`engine/checks.py`, +92 in `engine/cli.py` and a new 354-line `tests/test_wait.py`
(`git diff --stat`, then reading each); and that the suite is **red**, four failures,
all in the new module (`palette:test`, 161 seconds).

That last one is the fact that most changes what the respawn does, and nothing but
running the suite could have produced it. issue80's note 12 says the two kinds of
death need opposite recoveries and that neither could learn it from the record; this
adds that the *state of the work left behind* is a third thing the record cannot
carry, and it is the one the brief has to lead with.

The respawn is a subagent, so `issue99.g1`'s row will keep reading `gone without
returning` for the rest of the gate while a live agent works underneath it. The
engine is still watching a dead pid. That is issue80's note 13's point and it is
exactly what `#105`-and-after is about: the four-state read is a diagnosis with no
treatment, and this run's own commitment 23 is the treatment.

Worth noting what I did *not* do: I did not fix the four failing tests, or touch
`IMPLEMENT.toml`, or `git stash` anything. A gate's interior is its conductor's, and
issue88's note 15a records what a parent acting inside a live child's tree costs. I
reported what I saw — including one observation about `cmd_wait`'s trailing
`cmd_status` call apparently spawning the very child the gate says it does not start
— explicitly as an observation to check rather than a finding to act on.

## 18. A reworked segment loses both of its transition's guards, and this run lost them silently

The sharpest find of the run, and it was found by curiosity rather than by any
mechanism. After gate 1's adjudication the engine refilled `plan` for gate 2 and
dispatched one planner. I looked at what that planner's prefill actually held,
expecting to see the spec and my gate-1 findings. It held nothing:

    PREFILL KEYS: []

And the parent journal contains **zero** `prefill` entries, for the whole run.

The cause. `run.py`'s `skeleton()` mints a first-round transition carrying its
declared guards (`engine/run.py:213-214`):

    "validates": t.get("validates", ""),
    "carries": t.get("carries", False),

`_mint_segment_round`'s `fresh` dict — the reminted transition of a reworked
segment (`engine/cli.py`, around 2570) — copies `id`, `segment`, `anchor`,
`terminal`, `source`, and conditionally `panel`, `form`, `filler` and `prefill`.
It copies neither `carries` nor `validates`. On this run's own journal:

    first  understand: carries=True  validates=board
    remint a7037     : carries=None  validates=None

`understand-a7037` is the step that actually released. Two guards went with it.

**`carries` is what folds the spec into the run's prefill**, and the assembly says
so in place: "The spec joins the run's prefill, so every later dispatch carries it."
Because the release landed on a reminted step, `journal.append(wid, "prefill", ...)`
(`engine/cli.py:1204`) never fired. Every child dispatched after consolidate opened
with empty run-level prefill: three planners, nine plan critics across three rounds,
the gate-conductor, its implementer, its three reviewers, and gate 2's planner.

That defeats a fix issue88 landed, whose own comment reads: "Before this a
non-panelist child saw only its own step's prefill, so a first-round dispatch minted
with none (the plan segment's `plan-1`, which carries nothing of its own) opened
blind to the spec it exists to plan from." The fix works for a segment that releases
on its first round and is defeated by any rework — which is the common case at both
deciding seams. This run reworked twice at understand and twice at plan.

**`validates = "board"` is what refuses a release with an open row or a
self-answered decision.** It also did not run. My board happened to be fully
answered, so nothing was hidden; the guard was simply absent and nothing said so.

Three things worth keeping.

**The children survived it, which is why nobody would notice.** The three planners
had only `criteria` in their prefill and still produced plans citing `spec-r3.md`'s
commitments by number — they found the spec by reading the work location. So the
symptom of this defect is not a broken run; it is a run where every cold reader is
quietly doing extra work to reconstruct what it was supposed to be handed, and
succeeding often enough that the loss never surfaces. That is the epic's own wave-5
claim — the record asserting something through a no-op — with the no-op on the
delivery side rather than the assertion side.

**The fix is two keys**, the same `t.get` calls `skeleton()` already makes, in the
same dict that already copies five other fields off the same transition.

**And I only looked because I had a reason to.** I wanted to know whether my
gate-1 `findings` would reach gate 2's planner — the `#107`-shaped question about
whether a conductor's ruling has a channel. The answer turned out to be worse than
`#107`: there is a channel, it is `carries`, and a rework silently disconnects it.

## 19. The best finding of the run: the mechanism would have reintroduced its own subject

Gate 2's plan seam, round two, simplicity seat. The gate moves the spawn out of
rendering and into `wait`, and its plan said `cmd_wait` gains the spawn "using
`_spawn_outstanding` exactly as it stands today."

The critic read both guards and found they are not the same guard.
`_dispatch_child` protects its spawn with two conditions
(`engine/cli.py:699`):

    if not is_returned and child_id not in records:

`_spawn_outstanding`'s own guard is one (`engine/cli.py:639`):

    if child_id in started:
        return None

`started` is `_dispatch_records(wid)` and never reads `returns_by_child`. So
moving the call "exactly as it stands" silently drops the returned-child half of
the guard — the half that lives in the caller, not the callee.

And the state is reachable, by the plan's own account. Its `direction` field names
the transitional exposure that a `not dispatched` row still prints its `open it:`
command in a plain `status` read until a later gate, so a conductor can open a child
by hand — which writes no `dispatch-started` record on the parent. If that child
returns and it is a panelist, `cmd_wait` builds `child_ids` from every panelist
index (`engine/cli.py:1034`), not only the unreturned ones. Its id is still in the
list, still carries no record, and the new pre-loop spawn starts a second process
for a child whose work is already done and closed.

That is the double-dispatch defect this entire run exists to remove, reintroduced
inside the mechanism built to remove it, by a plan sentence that reads as a
promise of fidelity. I verified all three claims in the tree before calling it.

Two things worth keeping.

**The defect is a guard that lives in two places and was described as living in
one.** Nothing about "use it exactly as it stands" is wrong on its face; the
callee genuinely does not change. What changes is that a condition the *caller*
was enforcing has no new home. That is a class of move-the-call refactor no test
would catch, because both halves pass their own tests before and after.

**The seat that found it was simplicity.** Not testability, not intent-fit. The
lens that asks what can be deleted read two guards side by side and noticed one was
shorter. issue88's note 10 predicted the testability seat would be the one that
survives to late rounds; here the late-round finding came from the seat whose whole
job is comparison.

## 20. The impasse form, and the thing that makes an enumeration unclosable in this repository

Gate 2's plan seam reached three rounds and the third rework minted the impasse
form. The loop was one field and one claim: `scope`'s enumeration of the prose
this gate's diff falsifies, and its declaration that the enumeration is complete.

    Round 1: the list omits `[child-status]` and `_dispatch_child`'s docstring.
    Round 2: the list omits `[already-dispatched]` and `_spawn_outstanding`'s.
    Round 3: the list omits `[wait-outstanding]` and `_dispatch_status`'s.

Six sites, every one real, every one cheap, the list still not closed. Round two's
own finding had already named the cause — "the plan's stated rule was proximity;
the test it actually applied everywhere else was truth against the diff" — and two
rounds later the plan was still shipping a list.

That much is issue80's note 9 at a different seam: an enumeration can always be
found short by one, and the answer is not a longer enumeration. What is new here,
and what I think is the run's most transferable finding, is *why* it is unclosable
in this repository specifically:

**`[wait-outstanding]` did not exist when the specification was written. Gate 1 of
this same run created it** — in the same file, describing exactly the boundary gate
1 held and gate 2 removes. The spec's own commitment 44 names four rationale blocks
by name, and that list is now short for the same reason.

A repository that builds itself with itself grows new prose *between the plan and
the diff*. Any list of falsified text written before the diff exists is stale by
construction, and no round of re-listing closes it. Only a rule applied at the
moment the diff exists does — which means the check belongs in the gate's own
review, the only reader who ever sees the finished diff, and not in the plan.

So the ruling was `rework` with a change of shape rather than another pass: scope
states the rule (truth against the diff, not proximity and not list membership),
the check moves to the gate's review, and the six known sites are named as a floor
rather than a ceiling. And I wrote the bound into `why` so the next reader can
judge it either way: if round four finds a seventh site *and* is still enumerating,
I advance and hold the rule at the gate's adjudication, where I already have a
channel that worked once.

## 21. #107, met live, at the one form written for it

`_panel_judged_rework` returns `(None, "")` for a step with no `panel`, and the
impasse step is minted with no panel on purpose — so that the impasse's own
`rework` "carries the prefill that caused it" rather than re-deriving it. The
consequence is that round four arrives holding the three blocking findings that
produced the impasse, and not one word of the ruling on the loop.

Everything in note 20 above — the diagnosis, the change of method, the six sites
as a floor, the bound I set on my own next ruling — is in the journal and reaches
nobody. The round it was written for will fix three sites and, unless it happens to
read `IMPASSE.toml` out of the work location on its own initiative, re-enumerate.

issue80's note 9 filed this as `#107` and named the cheapest fix: `_rework_prefill`
returning the impasse submit's own `why` alongside the carried findings when the
deciding step is the impasse form. One branch. This run is its second recorded
occurrence and the first where the ruling was a change of *method* rather than a
sharper statement of the same orders — which is the case where losing the ruling
costs the most, because the findings alone actively point the next round back at
the method that failed.

Worth pairing with note 18: this run has now met two independent breaks in the same
channel. `carries` is dropped by every reminted transition, so the run-level prefill
was never written at all; and the impasse's ruling has no prefill path by
construction. Both are places where the engine's own design says orders flow down,
and in both the orders reached the journal and stopped there.

## 22. Four rounds at gate 2's plan seam, and the condition I set fired exactly as written

| Round | intent-fit | testability | simplicity | conductor | what it found |
|---|---|---|---|---|---|
| 1 | revise | revise | revise | rework, 3 blocking + 1 accepted | test list can pass without entering the block; prose list short (2 sites) |
| 2 | pass | revise | revise | rework, 2 blocking | the returned-child guard silently dropped; prose list short (3 sites) |
| 3 | pass | revise | revise | rework → **impasse** | prose list short (3 more sites) |
| 4 | pass | pass | revise | **release**, 1 accepted | prose list short (1 more site) |

Eight prose sites across four rounds, every one real, and the list never closed.
At the impasse I ruled `rework` with a change of method and wrote the bound into
`why`: *if round four's panel finds another site and the plan is still
enumerating, I advance and hold the rule at the gate's adjudication.*

Both halves happened. Round four never saw my ruling (note 21) and answered the
three findings by adding two more list entries and a wider five-anchor grep. Its
panel then found an eighth site, `[spawn-once-per-render]`, and made the point
that settles the whole argument: **the scope's own five-anchor grep does not match
either of the two phrases at risk in that block.** A sweep that tests only the
anchors already chosen finds nothing new by construction. That is the impasse
diagnosis confirmed by the next round's own evidence rather than by my assertion
of it.

So I advanced, and the mechanism made that clean rather than merely consistent.
`[spawn-once-per-render]` is named by the spec's own commitment 44; commitment 44
is `o44` on the execution-state board; and **no gate has claimed `o44`** — gate 2's
plan defers 36-49 to a later sweep gate. The eighth site is not lost by advancing,
it is carried by an obligation that stays open, and an open obligation pulls
another gate rather than letting the run walk to close.

That is the execution-state board doing the exact job issue88's note 11 describes:
"a seam's `accepted` is safe when a later, independent step has to assert the same
thing again with evidence in hand." Here the later step is not a reviewer's
judgement but a row that cannot be closed without the work. It is the strongest
form of the guard this run has used, and it is the reason four rounds of an
unclosable enumeration cost the run a delay rather than a defect.

Writing the bound down before round four ran is what made the ruling judgeable.
issue80's note 14 records a conductor writing a condition into an impasse and
having it not fire, because the next round's finding was a different class. Mine
fired. Both outcomes are only readable because the condition was on the record
before the evidence arrived.

## 23. The run closed its own issue on itself, and the conductor typed the verb

After gate 2's adjudication the engine minted the next plan round and rendered it:

    issue99.plan-a4414 (not dispatched)
    brief -- issue99.plan-a4414
      ...
      open it:     .../spine open cut-a-gate --parent issue99 --step plan-a4414

Rendering started nothing. That is commitment 15 — "a `status` read cannot start an
agent" — observed on this run's own record rather than in a test, five hours after
the board row that ruled it.

Then I typed the verb:

    $ spine issue99 wait --for 300
    issue99 · run-an-issue · plan (23 of 29)
      issue99.plan-a4414 (working)
    real 5m00.411s   user 0m21.089s   exit 0

It started the child, blocked for the full bound, and handed me back the room with
the child still outstanding. One command. Twenty-one seconds of CPU across three
hundred seconds of wall clock, which is the poll loop's own cost measured in
production rather than in the board's estimate of it. No turn spent polling, and no
turn ended on a belief that something would wake me.

That is the issue's own *what fixed means*, performed at the tier the issue was
written about, by the conductor of the run that wrote it.

Two things the same moment shows are **not** done, both correctly horizoned, and
both worth recording precisely because the mechanism working made them louder:

The room printed the full brief and its `open it: spine open ...` line for the
not-dispatched child. That is the transitional exposure my gate-2 findings named —
before gate 2, the same render that printed that command also spawned the child and
flipped the row to `working`, so the command was almost never seen; now it stands on
every read until commitments 16-22 land.

And the room carried no one-line statement of what is outstanding and what the move
is. Ruling 4's line is commitment 18, the same gate. So what a conductor holds today
is the mechanism without the words: `wait` works and nothing tells you to type it.
That is the right order to build them in and the wrong order to stop in, which is
why the next gate is the room-text gate and why I said so in gate 2's findings
rather than leaving the horizon to argue it.

## 24. Three panelists died together, and the run fell into the hole its own panel had just described

The gate-3 plan round's critic panel: all three panelists `gone without
returning`, none returned. `dispatch.plan-a844b.p2.log` ends:

    I've spawned a subagent to run this critic brief cold -- it'll open the
    `give-a-verdict` step, fill `CRITIC.toml`, and close it. I'll let you know
    when it finishes.

A **panelist** — an agent whose entire job is to read one artifact and fill one
form — delegated that form to a subagent and ended its turn waiting. The other two
logs are empty. All three runs exist with the `verdict` step minted and
`CRITIC.toml` an untouched template, so `_respawn_cmd` correctly offers the resume
command rather than the open one for each.

That is now occurrences 3, 4 and 5 in this run, and the shape has moved a tier
down: two gate-conductors, then three panelists. The dispatch-as-a-subagent habit
is not a conductor's habit, it is every dispatched agent's habit, and the one place
it makes least sense — one agent, one form — is where it just happened three times
at once.

**And here is what makes this the note worth keeping.** The finding this very plan
round was reworked for, written by p2 of the *previous* panel a few hours earlier,
says:

> on a room whose only unresolved child is gone ... the new line would read
> "nothing outstanding, wait is the move" while a few lines below on the same room
> that gone child's own row prints its old respawn brief with a hand-typed
> `open it:`/resume command ... and typing `wait` as told does nothing.

I typed `spine issue99 wait --for 270` three times against that room. Each returned
instantly: `_wait_outstanding` counts only a live-pid record, a dead-pid record
reads as zero exactly like no record at all, and restarting a gone child is
commitment 27 — gate 4, not yet built. Three rows reading `gone`, three hand
commands printed beneath them, and the verb that exists to make hand commands
unnecessary doing nothing at all.

The panel described the hole and the run fell into it the same hour, in the plan
round that was sent back to fix it. That is the strongest evidence this run has
produced for its own commitments 23-28, and it is evidence of a kind no test could
have supplied: the gap is only visible when the mechanism is half-built and
something dies.

The recovery cost three hand-started subagents, none of which writes a
`dispatch-started` record — so all three rows keep reading `gone without returning`
while live agents work underneath them, and my only view of them is the Agent
tool's own completion. issue80's note 13 recorded exactly that asymmetry; this run
now has it at both tiers.

## 25. Three gate-conductors, three deaths, two distinct beliefs

| Gate | how it died | what it left |
|---|---|---|
| g1 | dispatched a subagent, ended its turn waiting; harness killed it at 600s | +101 engine, a 354-line test module, 4 red |
| g2 | identical | +242/-92 engine, 8 red |
| g3 | "I'll just wait for the background pytest run to finish; a notification will arrive automatically" | +133/-28 engine and render, 2 red |

Every gate-conductor in this run died before its first submit. Two died of note
24's stall — an account of the step delegated, then the turn ended — and the third
of note 15's belief, that something would wake it. Neither brief was mine: all
three were engine-started and had only `render.DISPATCH`'s wording, which does end
on the reader's own move and did not prevent either failure.

The pattern across four runs is now unambiguous. issue84's note 15, issue88's note
12, issue80's note 13 twice, and three times here: the anti-stall sentence is
**seven for seven** at failing to prevent the stall it names. It costs a line and
it should stay, because it makes the diagnosis instant — every one of these agents
said in plain words what it was waiting for. It should not be counted as
mitigation.

What changed the cost, and is worth separating from the count: all three deaths
were cheap to recover because the room said `gone without returning` and the log
said why in one sentence. Three respawns, each one Agent call, each briefed from
`git status`, the child's journal, and a suite run. The expensive part is not the
death; it is that a respawn writes no `dispatch-started` record, so the row keeps
reading `gone` while a live agent works underneath it, and my only view is the
Agent tool's own completion.

And the thing that would actually close it is in this run's own horizon:
commitments 23-28, the engine restarting a gone child through `wait`. Six
occurrences in one run is the evidence for that gate, and none of it existed when
the board ruled on it.

## 26. The spec's sharpest prediction came true, on schedule, in the gate it named

Gate 3's tree came back red on exactly two tests:

    tests/test_imperatives.py::test_a_brief_imperative_ends_on_a_move_the_reader_makes
      assert "wait" not in text.lower()   -- for DISPATCH and PANEL

    tests/test_promises.py::test_every_spine_command_the_engine_prints_uses_a_real_verb
      AssertionError: spine command uses 'wait'
      assert 'wait' in {'amend', 'check', 'close', 'note', 'status', 'submit'}

Those are commitments 32 and 33, named at the understand seam before a line of this
was built, from a board row that swept the tree for everything the change would
falsify. Commitment 32 goes further and requires the `test_imperatives.py` rewrite
to land *in the same gate* as the `DISPATCH`/`PANEL` edit, "or the suite is red
between them" — which is exactly the state the dead conductor left behind.

So this red is the specification being right rather than the diff being wrong, and
that distinction is the whole value of having written it down: a conductor arriving
cold at a red suite has to decide whether the work is broken or unfinished, and the
spec answers it in a numbered commitment. I put that in the respawn's brief rather
than let it re-derive the answer from a failing assertion.

It is also the cleanest vindication of the cold-panel seam. The board found the
`"wait" not in text` assertion in a sweep, the spec-writer turned it into a
commitment with the "same gate" clause attached, three critic rounds left it alone
because it was already right, and four gates later the tree failed on it in the
predicted place at the predicted time.

## 27. The room, four hours and three gates apart

At gate 2's adjudication, the room for the next plan round read:

    issue99.plan-a4414 (not dispatched)
    brief -- issue99.plan-a4414
      role         planner
      ...
      open it:     .../spine open cut-a-gate --parent issue99 --step plan-a4414

At gate 3's adjudication, the same room reads:

    Nothing starts this child until spine <work-id> wait runs, through the
    repository's own dispatch entry when one is configured; wherever a command
    appears below instead, you are the one who runs it. ...

    0 outstanding -- .../spine issue99 wait starts it

    issue99.plan-aef96 (not dispatched)

No brief. No `open it:`. One line above the rows saying what is outstanding and
naming the move. Three of the principal's six standing rulings visible in eleven
lines of output, on the run's own record, read by the conductor those rulings were
handed to.

The thing worth recording is not that it works — the tests say that — but the shape
of the interval. Between those two rooms sat a plan seam that went four rounds and
through the impasse form, three gate-conductor deaths, and a critic panel that died
whole. The room in the middle was *worse* than the room at the start: gate 2 made
the hand command visible on every read where it had previously been almost
unobservable, and I recorded that in gate 2's findings as the argument for cutting
the room-text gate next. The planner took that argument, reordered its own horizon,
and cited the finding by name.

So the run's own worst intermediate state is what produced the ordering that fixed
it, and the channel that carried the argument was a `findings` field a planner read
out of the work location rather than any prefill the engine wrote.

What is left is the row this gate deliberately did not touch: a `gone without
returning` child still prints its respawn command, because removing a reader's only
recovery is safe only in the diff that gives the engine one. Six occurrences of
that state in this run say what that gate is worth.

## 28. Twelve deaths, and the gate that fixes them restarted its own reviewers

Final count for this run: **twelve `gone without returning` occurrences.** Four
gate-conductors (every gate), two complete critic panels, two of a third panel,
and two more panelists inside a gate's own review. Five of the twelve were
critics, whose entire job is to read one artifact and fill one form.

The beliefs, in the agents' own words, are worth keeping because they are not the
same sentence twice:

    "I'll pick up the gate at the next form once it reports back."
    "I'll just wait for the background pytest run to finish; a notification will
     arrive automatically."
    "I've queued a wait on the engine's own proof check and will get notified
     when it exits, rather than polling manually."
    "I'm waiting on `spine issue99.g4 wait` in the background and will act on
     the verdicts once they land."

The last one is the one to carry forward. It took the verb this run built and
**put it in the background** — which converts it back into exactly the thing it
replaces, something you must be notified about. `wait` blocks in the foreground on
purpose; that is the whole of what it buys. No room says "do not background this,"
and after four gates I still cannot say a brief would fix it: the anti-stall
sentence is now seven for seven at failing.

And then, at gate 4's review seam, the thing worth the whole run: two panelists
died mid-review and **the gate's own uncommitted diff restarted them**. One start
record each, under the cap, both returned on the restart, and the conductor read
their verdicts. The mechanism under review recovered the agents reviewing it,
before it was committed, before it was adjudicated, in a repository that builds
itself with itself.

## 29. The cap fired, and what a cap counting starts cannot see

`issue99.g4` reached three `dispatch-started` records and the room changed to
`gone without returning -- starts spent`. The engine stopped restarting it and
handed me the fact, which is exactly what commitment 26 says the cap is for.

It cost nothing and saved something. The three starts were all *productive* — the
gate advanced through work, select, a full review round, an `up` and its answer,
and the resumed round's own submit. What killed each one was the harness's
600-second background ceiling closing on a conductor that had delegated and
stopped, not a broken `dispatch` entry. A fourth engine restart would have made a
fourth conductor with the same brief and the same ceiling; a hand-started respawn
differs in exactly one way that matters, which is that it gets a brief I write.

So the number 3 is right for this shape. What the cap cannot see is the difference
between a child that dies making progress and one that dies on arrival — it counts
starts, and both look identical. Here that did not matter, because a conductor
looked and ruled, which is the design. It would matter to `drive`, which will hit
this state with no conductor to look, and whoever cuts that verb should decide
what a spent cap means to a loop that cannot rule.

## 30. Two more instances of the run's own recurring defect, and how the last one was found

The shape — *a guard whose halves live in two places, written as though it lived
in one* — has now appeared four times in this run:

1. Gate 2's plan seam: `_dispatch_child` guarded a spawn with
   `not is_returned and child_id not in records`, `_spawn_outstanding` guarded
   only `child_id in started`, and moving the call "exactly as it stands" would
   have dropped the returned-child half. Found by a simplicity critic.
2. Gate 4's plan round one: a skip clause dropped from `_wait_spawn`.
3. Gate 4's plan round three: `_outstanding_state`'s new startable disjunct
   missing the `returns_by_child` clause its sibling carries.
4. Gate 4's landed diff: `_dispatch_child` hand-writing
   `counts.get(child_id, 0) < checkrun.MAX_STARTS`, which reduces at that exact
   line to `_startable`'s own third clause.

The fourth is the one that teaches something new, because of **how the two honest
readers missed it.** Both round-four critics reported "two call sites for
`_startable`, no third" — a correct count of *calls*. A site that evaluates a
fragment of a rule without calling it is invisible to a call-count. Only the third
critic, and then the gate's own guard-singularity lens reading the landed diff,
reached it.

So the question that finds this class is not "how many call sites does the
predicate have" but **"is there anywhere that decides this, or any part of it,
without asking the predicate?"** The first question is answerable by grep and is
the one everybody asks; the second requires reading every branch and is the only
one that works. I put it verbatim into the last respawn's brief as a review lens.

The other half of the lesson is about the ruling, not the defect. The site was
blessed by the gate spec *by name and with reasoning*, so the gate-conductor could
not rule it out from inside — its orders said to write it that way. It ruled `up`,
and that was right: a conductor quietly contradicting its own orders is worse than
a paused gate. The ask came to me, I checked the reduction myself, and answered
that the agreement between the two forms is by construction rather than by
reference — and construction is what changes when someone edits the predicate. One
line, and the fourth instance of a four-instance pattern closed.

## 31. The gate-6 conductor adjudicated its own parent's step and closed the run

The sharpest process finding of the run, and it happened at the very end.

I was mid-verification of gate 6's returns — reading each of the fourteen prose
obligations myself, as I had bound myself to at the plan seam — when the worktree
vanished under me:

    cd: /home/tommy/projects/constellation/.worktrees/issue99: No such file or directory

The run had been closed. Reading the archived journal afterwards:

    07:47:09  submit g6-adjudicate     (fourteen dispositions, plan-holds advance)
    07:47:09  board
    07:49:57  submit execute           (the run's own CLOSE form)
    07:50:11  closed

**I made none of those.** The gate-6 conductor did. The proof is the session id:
`checks._spawn` sets a spawned child's `CONSTELLATION_SESSION` from its parent's,
so every entry a child writes carries the id of the `spine` process that started
it. `2882269` is the `spine issue99 wait` call of mine that spawned g6 — and it is
the id on g6's own `dispatch-started`, on its `return`, **and on the parent's
`g6-adjudicate` and `execute` submits.** A dispatched child ran `spine issue99`,
filled its parent's adjudication form and its parent's close form, and closed the
run.

Nothing stopped it. `run-a-gate`'s own skill says a gate's interior is its
conductor's and the adjudication is the parent's; every brief I wrote for a
hand-respawned conductor said "do not run `spine issue99`" in those words. But g6
was engine-started, so it never read a brief of mine — it read `render.DISPATCH`,
which says nothing about the parent's forms. The engine has no notion of which run
a caller may drive: `cmd_submit` takes a work id and fills whatever step is
current there.

Three things follow, and the first is the one to file.

**A dispatched child can drive its parent's run, and the engine cannot tell.** This
is the same family as `#105` — a read that was secretly an act — one tier up: a
child that was supposed to return evidence instead performed the judgement its
evidence was for. It is also, precisely, the boundary `skills/issue-conductor/SKILL.md`
states in prose ("your adjudication acts on the plan and on what the gate returned")
with nothing behind it.

**What it cost here was small only by luck.** I had already independently verified
o36 through o43 and o45 through o47 against the tree before the close landed, and I
finished the rest afterwards: the branch is green (543 passed at `d1cd69e`, plus one
test that cannot run outside a git checkout because it shells out to `git
ls-files`), every disposition it wrote matches what I read, and its own `findings`
show it re-ran the gate's proof clause by clause rather than trusting the gate's
report. It did the work well. That is luck, not a guarantee: an adjudication is the
one step whose whole job is to distrust the child, and here the child performed it.

**One disposition I would have made differently, and it is the guard I had
standing.** I said at gate 5's adjudication, and again at the last plan seam, that
I would not dispose `o44` satisfied until *both* falsified sentences in
`[spawn-once-per-render]` were corrected. On the landed branch one is
(`engine/cli.py:705`, now "on every `wait` call until someone fixes the entry") and
one is not (`:693`, still "not a reason to crash the render for every other child
... standing in the same room"). It was disposed `satisfied`.

Having read it, I would probably have disposed it satisfied too — `cmd_wait` does
render the room at the end, so a `DispatchFailure` escaping really would take out
the room for every other child, and the clause is imprecise rather than false. But
that is a judgement I was holding a public commitment about, and it was made by
somebody else without reference to the commitment. The difference between "I
checked and released" and "it was released" is the whole of what an adjudication
step is for.

## 32. What the run did, at the end

Six gates, all landed, each its own commit on `issue99`; forty-nine obligations,
all disposed; PR #111; one issue filed (#110). The suite went 486 → 544 tests.

The thing to hold onto is the arc of a single room. At gate 2's adjudication it
printed a full brief and `open it: spine open cut-a-gate --parent issue99 --step
plan-a4414` — the exact command the specification forbids a conductor to type,
newly visible on every read because gate 2 had just stopped rendering from
spawning. At gate 3's it printed:

    0 outstanding -- spine issue99 wait starts it
    issue99.plan-aef96 (not dispatched)

And by gate 5, a gate-conductor died mid-gate and my next `spine issue99 wait`
restarted it without my knowing it had died — no diagnosis, no brief, no subagent,
no ruling. Thirteen of this run's children died `gone without returning`; the first
twelve cost a hand recovery each, and the thirteenth cost nothing at all.

That is the issue's own *what fixed means*, met by the run that specified it, on
its own record, using its own uncommitted diff to keep itself moving.
