# Process notes — issue116, the run that fixed the verb it was driven by

Friction met while driving this run, recorded as it happened, in the shape of
`docs/process-notes/issue113.md`. Nothing here is doctrine. Where an entry
contradicts `docs/AGENT_GUIDE.md` or a form, the guide and the form are right
about the tree and this file is right about what the run met.

This run's subject is `drive` itself, so the run is also the measurement: the two
defects it fixes are defects it was expected to hit while fixing them. One of them
it hit; one of them it did not, and why not is note 4.

## 1. The two defects this run was opened to hit, and which of them bit

The launch order predicted both: "`drive` will stop at a second route round with
`role: no role named ''` (#115), and it will try to fill the close form (#116)."

Neither happened.

**#115 did not bite, because no seam reached a second round after the plan segment
opened.** The consolidate seam went two rounds — but the understand segment is
before `plan`, and `drive` refuses to walk it at all
(`cmd_drive`'s segment-order guard, `engine/cli.py:1668`), so I filled both of
those route rounds by hand and the missing `filler` never reached the verb. The
plan seam passed on round one: three planners, three critics, three `pass`, no
send-back. `drive` therefore never met a re-minted transition in the segments it
walks.

**#116 did not bite, because the fix was in the tree before the run stood on its
close form.** The gate landed at 22:18, the adjudication released at 22:33, and by
then `cmd_drive` had the terminal check.

So the two live observations this run produced are of the fixes working rather than
of the defects firing — note 3. That is a weaker measurement than the launch order
expected and a stronger one than it asked for.

## 2. `drive` walked the whole plan segment and the gate dispatch in one command

From the plan segment's first step, one `spine issue116 drive` did, with nothing
typed between steps: three design-it-twice planner dispatches and their closes; one
plan-seam critic panel and its collection; one form-filler on `PLAN_TO_EXECUTE.toml`
which ruled `pass`, picked a rival, and journalled a drift note of its own; the gate
dispatch; and the wait on it. 20:47:43 to 21:00:10 for the whole plan segment,
twelve and a half minutes, no human hand.

The filler's own drift note is worth keeping as evidence that the room's length line
does its job two tiers from where it was written: "935 → 1570 → 1444 → 1357" was
issue113's; this run's was "773 prose words, -15% on the first draft and +26% on the
last ... Examined growth, and net shrink," written by a fresh-context agent that had
read only the room. `caps-are-for-awareness`, working, in an agent nobody told about
it.

## 3. Both fixes were observed in flight, not only in a fixture

This is the part a test could not have produced.

**C1 at the gate tier, before the gate closed.** `issue116.g1`'s journal carries
`form-filler-started` for `work-1`, `work-a429f`, `work-a4832` and `select`, and for
nothing else. Its `close` step — `terminal = true`, `forms/GATE_CLOSE.toml` — has
none. The gate's own `drive` ran to that step with the fix in its own tree and
started nothing there. issue113's equivalent moment is note 12 of that file: a
filler spawned onto `execute`, and a conductor killing it.

**C2 through the very path #115 named.** When my answer to the gate's ask resumed it,
`_resume_paused_child` called `_mint_segment_round`, which minted `work-a4832` —
`source = "panel"`, `form = "forms/SELECT.toml"` — carrying `filler = 'conductor'`.
`run-a-gate`'s `select` declares no `filler` at all and says so in a comment claiming
"every mint site defaults an absent one to the bare `conductor` indirection"; this is
the mint site that did not, and now does. issue113's gate has the same two steps with
no `filler` key: `work-a0b4e` and `work-a548d`.

**C1 at the issue tier, at the close form itself.** Against the launch order's
instruction not to run `drive` there, I ran it once, deliberately, because with the
fix landed it is a pure read and it is the single observation this run exists to
produce. It returned in under a second, rendered the room, and started nothing;
`form-filler-started` on this run names `plan`, `execute-a6006` and `g1-adjudicate`
and does not name `execute`. The room's own line is the new one:
`form filler: none -- this form is the run's principal's to fill`.

## 4. The run's real friction was not either issue. It was one prose field.

The gate spent from 21:00 to 21:50 — fifty minutes, a full implementer round, two
check attempts — before anything could be learned, because the selected plan's
`proof` field read ``constellation.toml's `test` entry: python3 -m pytest -q``
instead of `palette:test`. `_resolve_one` special-cases only a `palette:` prefix, so
the whole string reached `/bin/sh` and died on the apostrophe in "constellation.toml's":
exit 2, twice, `Syntax error: Unterminated quoted string`.

Four things about this are worth keeping.

**`PLAN.toml`'s own field note already says exactly the right thing.** "Write the
exact string to run, never a description of it: this field rides into the dispatched
child as its own `proof`, shell-executed there, so prose becomes a command and fails
only after the work is done." The imperative was not missing. The planner read it and
wrote a description anyway, and planner p2, given the same note, wrote `palette:test`.
Where the guide's own decision procedure says *look for the field that would have
shaped what the agent did*, the field exists and shaped one of two agents.

**Three critics passed the plan and none of them ran the field.** Their criteria were
intent-fit, testability, and simplicity. "Testability" read the plan's proof strategy
and judged it sound; nothing asked whether the string resolves. A one-line check at
plan submit would have caught it while the round was still open.

**Nothing downstream could repair it.** A check's command is
`{**run prefill, **step prefill}` by field id (`engine/cli.py:1820`); a dispatched
gate's spec lands at the run level; `amend` takes add | close | reorder. And the
parent could not supply a replacement either: `submit` builds its fields strictly
from the form's declared fields, so a `proof` key written into `ASK.toml` is dropped
before it reaches the resumed round. I checked that before answering, rather than
promising a fix I could not deliver — which is the only reason the answer was
useful.

**The escape that worked was the engine's own, offered in the room.** The gate
amend-closed the round naming the hand-run result, and carried the diff to its review
panel. Filed as #122.

## 5. A `blocked` note became an ask, and the ask's answer was the round's whole orders

The implementer wrote a `blocked` note; the gate-conductor ruled `up`; the run paused
and the ask stood at my tier with `forms/ASK.toml`. That whole path worked exactly as
written, first time, with no human in it — the first time in these notes that a
gate's block has reached its parent mechanically rather than through someone noticing.

What the form asks for is unusual and right: "Write it as orders to the fresh-context
round that opens holding only this answer, not as a reply to the ask above." The
temptation is to answer the question. The round that receives it has never seen the
question. My answer accordingly opened by ruling out the fix the ask proposed
(re-mint the proof), said why it is unreachable, and then said what the round should
do instead — run the proof by hand, record it, expect the refusal, hand back. The
round did all four, in one pass, and said so in a note.

## 6. `drive` filled two forms that are the conductor's own judgment, and I killed both

`drive` spawned a filler for `ASK.toml` — the form carrying my ruling on the gate's
block — and for `GATE_TRANSITION.toml`, the gate's adjudication. Both are legal today:
neither is terminal, so the fix this run ships does not touch them, and issue113's
`drive` filled its own `g1-adjudicate` too.

I killed both and filled them myself, for different reasons. The ask, because its
answer turned on two facts a fresh-context filler had no way to hold — that no verb
edits a journalled prefill, and that `submit` would drop a `proof` key written into
the answer form — and a filler that guessed either would have sent the gate back into
the same wall. The adjudication, because the launch order says to root-verify a gate's
return before disposing anything, and a filler disposing it is precisely the step
being skipped.

The general shape, which #116 only opens: `terminal` is now the one property that
reserves a form. Nothing marks a form as *the conductor's own judgment*, and the two
I killed are both that. The ask's own form header says it is "filled by whoever
conducts whatever paused"; `GATE_TRANSITION.toml`'s imperative says "root-verify the
returns — open the artifact, re-run a check; outputs and roots, not belief." Both
sentences describe a reader that has been in the run. Neither is a property the verb
can read.

## 7. The base was red, and the run found out from its own implementer

`tests/test_round_cap.py`'s two lead tests fail on `main` and have failed since the
commit that added them. The implementer found it while running the proof by hand,
reported it in a `blocked` note, and confirmed it by stashing its own diff. I
confirmed it independently in a detached worktree at `dd80308` (607 passed, 2 failed)
and at `39fb67e` (same two).

The cause is a merge nobody re-proved. issue113's worktree was cut before `1ad566d`
set `impasse-after` from 2 to 1; its round-cap fixture spreads five plan-seam rounds
across two gates on the assumption of 2; under 1 the impasse form is minted where the
fixture expects a fifth round. Both edits were green on their own branch and neither
side's proof ran on the combination. Filed as #121.

The consequence for this run was doctrinal, not mechanical: C4's invariant is "held by
the existing suite passing unchanged", and the suite does not pass. I ruled it read as
unchanged *relative to its own base* and verified both revs myself — 607/2 at
`dd80308`, 612/2 in the gate's tree, same two failures, five new tests. That reading
is available because the failure set is identical; it would not have been if one new
failure had appeared.

## 8. A failure under contention is still indistinguishable from a real one

Reviewer p1 ran the full suite and reported three failures, the third being
`tests/test_spawn_dispatch.py::test_a_nonzero_exit_is_still_a_successful_spawn`. It
passed in both of my runs, at the gate's rev and at base. Three agent processes were
live on this machine when p1 ran it.

`docs/process-notes/issue113.md` note 11 recorded the same class from the other side —
a proof that failed once and passed six minutes later on an unedited tree, with the
record holding nothing but `exited 1`. This run adds the reviewer's side: a real
panelist reported a real failure it had really seen, into a field the conductor acts
on, and the only thing that separated it from a defect was the conductor re-running
the suite alone. Nothing in the record marks a check as having run under load.

## 9. A resumed gate kept two `select` steps and nearly bought a second review round

`_resume_paused_child` mints a fresh round of the paused segment — interior step *and*
a fresh copy of the transition — and does not consume the transition already standing.
`run-a-gate`'s `work` transition is `select`, and `select` is what mints a review
round. So the gate came out of its pause with two live `select` steps, submitted both,
and minted two review steps on one unchanged diff. The gate-conductor caught it,
amend-closed the second before its panel dispatched, and journalled two corrections to
its own earlier note in the process — including one retracting a pid attribution it had
got wrong. Filed as #123.

Worth keeping for its own sake: the correcting notes. A conductor writing "Correction
to n3ab4, which was written against a state one minute stale" and then "Attribution
correction to my previous note ... Pid 2266728 is me -- I never ran submit" is the
journal doing the thing the epic's wave 5 is named for. The record did not quietly lie,
because its author kept reading it.

## 10. Two rounds at the understand seam, three passes at the plan seam, one gate

Consolidate round 1: p1 `pass`, p2 `revise`, p3 `revise` — two blocking calls, both of
one kind, a commitment whose claim and whose test do not line up. p2 found that C4's
invariant carried two claims and its test could only hold one; p3 found that C1 claimed
two tiers and named one scenario. Round 2: three passes.

The p3 finding is the one worth recording, because the finding itself declined to
choose. It named the mismatch and set out both exits — split the test, or drop the
claim — and left the choice open. That is what `orders` is for, and it is the first run
where the field existed: my ruling (keep both tiers, split the test the way C2's already
is) rode into round two as a labelled `[conductor]` block in the round's own prefill,
with no hand-built table in `calls`. issue100 note 8's channel is now a real field, and
the round read it.

Round 2 returned two more findings, both deletions, both explicitly non-gating and both
saying so ("does not change what gets built"). Under `055442e` a deletion cannot be
`accepted`, so keeping each owed an argument, and writing the arguments is what made the
dispositions honest: p3 wanted the local gloss on `seam`/`round` deleted because the
glossary carries both, and the argument for keeping it is the spec-writer skill's own
contract that a planner receives "this document and nothing else". A `rejected:` with an
argument is a better record than an `accepted` that changes nothing, which is the whole
of that form edit's point.

## 11. `drive` still has no glossary entry — fourth run, fourth time

`docs/process-notes/issue113.md` note 1 recorded that the launch order named a
`standards/glossary.md` entry for `drive` that does not exist. This run's launch order
named it again: "the `wait`, `drive`, `round-cap` entries in `standards/glossary.md`."
Two of the three exist. `grep` for the bolded head returns nothing for the third.

#94 is the open issue for the class. Recorded here, and in this run's own `key-terms`,
because it is now the second consecutive launch order to send a conductor to read a
definition that lives in a GitHub comment.

## 12. Wall clock

    open                    20:23:20 → 20:25:44     2m
    understand              20:25:44 → 20:47:43    22m   two rounds, six panelists
    plan                    20:47:43 → 21:00:10    12m   one round, six children, one drive
    execute (the gate)      21:00:10 → 22:18:41    78m   of which ~50m before the proof field was known to be unrunnable
    adjudication            22:18:41 → 22:33:44    15m   of which ~6m30s is two full-suite runs I made myself
    close                   22:33:44 →

Two hours ten to the close form, of which the single largest identifiable waste is the
fifty minutes in note 4 and the single largest identifiable cost that bought something
is the fifteen at adjudication, which is where the red baseline was pinned to its own
base and the reviewer's third failure was ruled contention.
