# Process notes — issue113, the five-round cap run

Friction met while driving this run, recorded as it happened, in the shape of
`docs/process-notes/issue100.md`. Nothing here is doctrine. Where an entry
contradicts `docs/AGENT_GUIDE.md` or a form, the guide and the form are right
about the tree and this file is right about what the run met.

This is the first run where `drive` is the conductor's own tool from the plan
segment on, so what `drive` did and did not do is recorded deliberately rather
than as it happened to come up.

## 1. `drive` landed a run ago and has no glossary entry

`standards/glossary.md` at `ff72a72` carries `dispatch`, `liveness`, `wait`,
`outstanding`, `prefill`, `return` and `brief` in one run of entries around
`:200-231`. `drive` is not among them; `grep -n drive standards/glossary.md`
returns nothing. The conductor's own launch order names "the `wait`,
`outstanding` and `drive` entries in `standards/glossary.md`" as required
reading and one of the three does not exist.

`#94` is the open issue for exactly this class ("`impasse` and `projection`
enter the glossary"), filed by issue87's close as a ride-along. `drive` is now
a third instance, and it is a CLI verb the epic's own closing plan ruling 2
defines in a paragraph — so the definition exists, in a GitHub comment, and not
in the file that is supposed to be the one place a name is fixed.

Not this run's work (scope discipline; one gate). Recorded because the launch
order for the *next* run will name it again.

## 2. The open form's authority still does not carry — third run, third workaround

`journal.toml`'s `open` step at this run's mint: `carries = false`. Unchanged at
`ff72a72`, which is two runs after issue99 note 1 first recorded it and one after
issue100 note 1 recorded that the workaround had become a convention.

Applied again, deliberately: the five standing rulings, the scope-discipline
paragraph and the latitude line are written into `.agent-work/issue113/issue.md`
under an "Authority for this run" heading as well as into `authority`, with a
closing sentence in `issue.md` saying why the duplication is there. Three
instances, still nothing in the tree states the convention.

## 3. A second round hands you the first round's filled form, values and all

`cmd_status` materializes a response form only when the file is absent —
`engine/cli.py:1387-1389`, `if not dest.exists(): forms.materialize(...)` — and
`_response_path` derives that path from the form, not from the step. So the
understand seam's round-2 CONSOLIDATE step rendered a room pointing at
`.agent-work/issue113/CONSOLIDATE.toml` that still held round 1's answers:
`resolution = "rework"` and round 1's four `calls` blocks, verbatim.

Nothing in the room says so. The room reads exactly as it does on a first round —
"fill it, then: spine issue113 submit" — and a conductor who filled only the fields
it thought of would have submitted the *previous* round's ruling and the previous
round's per-finding calls on a panel that had returned three passes. That is not a
hypothetical: my first attempt at round 2 was a targeted edit of `resolution` and
`calls`, and it silently carried round 1's `resolution = "rework"` because the
string I was replacing (`resolution = ""`) no longer existed in the file. The
symptom that saved it was a TOML duplicate-key error from my own writer, not
anything the engine said.

The fix I used: delete the response file and re-render, which materializes it clean.

Whether the carry-forward is deliberate is not recorded anywhere — no rationale
block near `engine/cli.py:1387` mentions a second round, and `forms.materialize`'s
own docstring is about writing a template. The two readings are opposite: "your last
answers are still here, edit them" and "this is a fresh round's blank form". A
conductor arriving fresh at a step boundary — which is the default this repo
designs for — will read it as the second.

Filed as a triage candidate at close rather than fixed here: it is one seam away
from this run's subject, and this run has one gate.

## 4. Two rounds at the understand seam, and the conductor's own call was the third finding

Round 1: p1 `pass`, p2 `revise` with two gaps, p3 `pass`. Round 2: three `pass`.

Round 1's two real findings were of one kind — a commitment whose check is not
named — and both were downstream of the form edit Tommy landed this morning
(`055442e`): p2's criterion is now "is every commitment an observable end state or
an invariant with its test", and it read that criterion literally against C4 and C5,
which restated their prose instead of naming a falsifier. The form edit worked: the
finding exists because the criterion was rewritten five hours earlier.

The third blocking call was mine, upgrading p1's own `beyond` on an unreachable
citation (`.agent-work/archive/issue99/YIELD.md`, in a gitignored work location) to
`blocking`. p1 judged it non-gating and was right that no commitment stood on it;
but the seam's first criterion is standalone-ness and the document's leading
evidence was unreachable. The round was going back anyway, so the call cost nothing
— which is the only reason it was worth making, and the reason is worth stating,
because the same call on a round that was about to release would have bought a whole
extra panel dispatch for one sentence.

Round 2's `calls` carried one `rejected:` on a deletion proposal (p3 wanted the epic
#55 paragraph gone). That is the other half of `055442e` working as intended: under
the new wording `accepted` was not available to me, so keeping the paragraph owed an
argument, and writing the argument is what surfaced that the paragraph does two
things and only one of them is load-bearing. An `accepted` call would have recorded
neither.

## 5. `drive` walks the mechanical half and stops on a re-minted route form, because `_mint_segment_round` drops `filler`

This is the note the run was opened to write. `spine issue113 drive` from the plan
segment did, in one command and with no conductor typing between steps:

- dispatched the three design-it-twice planners (`plan-1.p1/p2/p3`) and closed them,
- picked a rival and minted the plan seam's round-one critic panel,
- dispatched all three critics and collected their verdicts,
- **spawned a form-filler for `PLAN_TO_EXECUTE.toml` itself** (`form-filler.plan.log`)
  which read the round, ruled `rework`, and wrote six blocking calls,
- minted and dispatched the rework round (`plan-a1380`), closed it,
- dispatched round two's critic panel and collected its verdicts,

and then stopped, on this:

    role: no role named '' in constellation.toml's [roles] table
      entries: implementer, planner

That is not a spent child and not an ask. It is `drive` failing to spawn a filler for
round two's route form, and the cause is one missing key. `skeleton()` stamps the
statically declared transition's `filler` onto the step it mints, so round one's
`plan` step carries `filler = "conductor"`. `_mint_segment_round`'s transition branch
(`engine/cli.py:3247-3271`) copies `anchor`, `terminal`, `panel` and `form` onto the
fresh round, and copies `filler` **only** in the `if not has_interior` branch --
which `plan` is not. So `plan-a101c`, round two's route form, carries no `filler` at
all, `role_of("")` finds nothing, and the spawn refuses.

Before `drive` existed nothing read `filler` on a route step, so the omission was
invisible. `drive` is the first reader, and what it reads is that **every second and
later round of a route form at either `run-an-issue` seam cannot be driven**. Round
one of a seam is mechanized; round two is handed back. The message names an empty
role rather than the missing field, so the cause is not in what the reader is told.

Two things worth keeping about the shape:

1. It fails safe. The verb stopped and rendered the room, and the room it rendered is
   a conductor's own judgment seam -- the exact step `skills/issue-conductor/SKILL.md`
   says is mine. A conductor who did not look would lose nothing but the automation.
2. It is the same seam as `docs/process-notes/issue100.md` note 3, read from the
   other side. Note 3 found that no `filler`-to-tier join existed in the engine and
   the orders had named a mechanism the tree did not have. The join now exists; what
   is missing is the field it joins on, on every round after the first.

Filed as a triage candidate at close. Not fixed here: this run has one gate and its
subject is the cap.

## 6. Two rounds at the plan seam, and the second one found that the ruling's own number cannot fire

Round one: three critics, three `revise`, six blocking calls from the drive-spawned
filler -- three distinct defects, each found by two panelists independently. The
sharpest was that the plan read `round-cap` off `_perform`'s `tseg`, which for a
gate's review send-back (`does = "rework work"`) is the `work` segment, not `review`
where the property is declared. The filler's adjudication was root-verified against
`_perform` before it was accepted; it was correct.

Round two fixed all three and produced a better finding than either. p1 and p2, from
different criteria, independently established that under the corrected ordering the
cap at a gate's review seam **can never fire at this repository's own numbers**:
`work` declares no `rework-form`, so `rework_rounds` never resets within a gate;
`impasse-after = 2` therefore goes true at review's third send-back and stays true;
and a cap checked only where the outlet does not fire is consulted at review rounds
one and two alone. Five is unreachable.

The interesting part is where the defect actually lived. It was not in the plan. It
was in **C6**, a commitment the spec panel passed twice and the conductor released --
"the per-artifact `impasse-after` outlet fires on exactly the rounds it fires on
today". Read strictly, that forbids the only ordering under which #113's own "a hard
stop, not a warning" is true. Round one's panel enforced C6 against the plan and was
right to; round two's panel then found what enforcing it costs. Two panels, two
rounds, to surface a contradiction inside the spec that no spec critic's criterion
was phrased to ask for -- the same shape `docs/process-notes/issue100.md` note 18
records, one artifact along: a criterion finds what it names, and the seam finds what
no criterion is phrased for.

I amended C6 at the seam and journaled it as a decision note, carrying the amendment
into the round through a labelled conductor's block in `calls` -- issue100 note 8's
channel, now on its second run and still the only way a conductor's own ruling
reaches the round it governs.

## 7. Four rounds at the plan seam, and the artifact shrank on three of them

935 → 1570 → 1444 → 1357 prose words. `docs/process-notes/issue100.md` note 13's
signature for a plan that has become a draft of its diff is 665 → 1029 → 1491 → 1538,
monotonically up, with each round answering the conductor's own more-precise
mechanism. This run went the other way from round two on, and the difference is not
discipline — it is *who was supplying the mechanism*. Rounds one and two's findings
were the panel's, on the plan's own cut; the conductor supplied one ruling (which of
two commitments yields) and no mechanism at all. Round three's finding was the first
one at implementation grain, and the answer to it was a deletion.

The room's own length line does the work the notes could not: it prints the count and
the delta against both the first round and the last, and then says "growth is not a
defect; unexamined growth is. Say which this was." Being asked that at every round is
what made the ruling at round three — *this section should not exist* — reachable.
`caps-are-for-awareness`, working.

## 8. The impasse form arrived on schedule and the ruling it wanted was not the one it suggests

`rework_rounds(plan)` hit 2 at round three's send-back, so the fourth round came as
`forms/IMPASSE.toml` rather than a fourth planner dispatch. Its imperative: "three
reviews finding the same kind of thing means the artifact is not the one under
repair."

They were not the same kind of thing, and saying so out loud was the ruling. Round one
found a wrong-segment defect; round two found that fixing it made the cap unreachable
at the repository's own constants; round three found one paragraph that had drifted
below plan grain. Two design defects and one over-reach is not a loop, and the form
asks for the loop. What it also asks for is the thing that made the ruling safe:
`rework` "is the answer only when you can name what that round changes that the last
three did not." The nameable change was *deletion*, and the round delivered it —
three passes, shorter document, mechanism untouched.

Worth keeping: the impasse form's own framing is a hypothesis, not a verdict, and the
`why` field is where a conductor is supposed to contradict it with the record. A
conductor that read the imperative as the answer would have ruled `advance` over a
live finding, and the gate would have inherited a paragraph that sends its implementer
into an import cycle.

## 9. Five rounds is this run's own subject, and the run priced a finding against it

At the plan seam's fourth round p3 returned a `[delete]` finding: one Risks bullet
duplicating a scope bullet, explicitly non-gating, explicitly changing nothing an
implementer builds. Under `055442e`'s form edit a deletion finding cannot be
`accepted`, so keeping it owed an argument.

The argument that turned out to be true is the run's own subject: the only round that
could carry the deletion is the seam's fifth, five is this repository's cap, and
spending a run's last allowance at a seam on a sentence that changes nothing an
implementer builds is exactly the trade #113 was filed to stop. The cap was not in the
engine yet and it still changed a disposition — which is the first evidence in this
run that the number is the right one to hand a human rather than a warning to log.

## 10. `drive` is now two tiers deep, and the anti-stall sentence is still failing at the same rate

Gate 1's own conductor drives its own run: `pgrep` shows two live processes at once,
`python3 ./spine issue113 drive --for 100000` (mine, holding the gate dispatch) and
`python3 ./spine issue113.g1 drive --for 590` (the gate's own). The verb composes down
a tier without anything being told to.

What has not changed is what kills its children. `.agent-work/issue113/g1/`'s
form-filler logs, in full:

    form-filler.work-aef4c.log:
      I'll wait for the background test suite to finish -- it will notify me
      automatically when done.
      I'll wait for that notification before checking status again.

    form-filler.work-a358a.log:
      The background bash task will notify me directly when it finishes; no need
      for a separate monitor. I'll wait for that notification.
      I'll just wait for the background test run's own completion notification
      rather than polling.

Four fillers, four deaths, one sentence — an agent that started the proof in the
background and then stopped, waiting for a notification nobody was going to send.
`docs/process-notes/issue99.md` note 28 counted twelve and called the anti-stall
sentence "seven for seven at failing"; `docs/process-notes/issue100.md` note 15 made
it three for three on the gate that built the spawn. This run makes it four for four
again, at the tier below.

Two things this run adds that the earlier counts could not:

1. **The restart cap absorbs it, and that is why the run did not notice.**
   `checks.FORM_FILLER_MAX_STARTS = 3`, and both stalled steps were restarted and
   completed on a later attempt — `work-aef4c` finished after two deaths, and
   `work-a358a` is on its third and last as I write this. From outside, a step that
   dies twice and lands on the third looks exactly like a step that took half an hour.
   The cost is invisible in the room and visible only in a log nobody opens unless a
   step goes spent.
2. **The one filler that did not stall is the one whose proof it ran in the
   foreground.** `form-filler.work-1.log` ends with a real summary — "The proof passed
   and my IMPLEMENT.toml submit was journaled ... Full suite: 607 passed (602 baseline
   + 5 new)" — and its round completed first time. The difference between the log that
   works and the three that do not is not the instruction; it is whether the agent put
   the proof in the background. That points the fix at the boundary #72 already names
   (a proof longer than the harness's foreground window) rather than at more words in
   a brief, which is what issue99 concluded from the other side and what this run's own
   evidence now supports at two tiers.

## 11. A failed proof leaves no output, and the room points at the file that does not have it

Gate 1's third work round failed its own check once and passed on a re-submit six
minutes later with no edit in between. What I could learn about the failure, from the
whole record, is this and only this:

    proof: `python3 -m pytest -q` exited 1
      a check is run by the engine, not filled in -- make it pass,
      or drop this step: ... spine issue113.g1 amend close work-a358a --reason ...

That is the entire contents of `.agent-work/issue113/g1/check.work-a358a.log` (232
bytes), and `check.work-a358a.result.json` holds one key, `refusal`, carrying the same
three lines. The in-flight room says "what it is printing:
/…/check.work-a358a.log" — and on a failure that file no longer holds what the proof
printed. Which test failed, and why, is gone.

I ran `python3 -m pytest -q` by hand immediately afterwards: 607 passed in 183.66s,
against the same tree, unedited. So the failing run is unreproducible *and*
unexplained, and the only two candidates left — a flake under contention, or the 240s
budget being crossed while three other agent processes were live — cannot be told
apart from the record. The engine journals a `check` entry and a `submit` entry, and
between them the thing a reader actually needs.

The other half is that the stale log is never truncated: at the time of writing,
`check.work-a358a.log` still says `exited 1` and is dated six minutes before the
`submit work-a358a` entry that proves the same check later passed. A reader who opens
the file the room named, after a pass, is told the step failed.

Both halves are triage candidates. The second is the sharper one: a record that
contradicts the journal is worse than a record that is missing, and this run's own
epic (#55, wave 5) is named "The record cannot quietly lie."

## 12. `drive` spawned a filler for the close form, which is the one form it must never drive

The epic's own closing-plan ruling 2 (#55, 2026-09-03): "`drive` walks a run from the
plan segment to its close form ... and so on until the run pauses on an ask or stands
on its close form, **where it stops and says so**. The understand segment stays live
with the principal, and the close form is the principal's, so open items are talked
through rather than filed past." issue100's own standing ruling 1 names the same two
exceptions.

What happened: the gate's adjudication released, the engine committed, and the run
stood on `execute`'s terminal step, `forms/CLOSE.toml`. `spine issue113`'s room read
`form filler: working -- already filling this form, nothing to type here`, and the
journal carries the receipt:

    form-filler-started  execute  1848339  alive=True  2026-09-05T20:12:54Z

`drive` did not stop at the close form. It spawned an agent to fill it. I killed both
the filler and the drive and filled close by hand.

Why it matters more than the missing `filler` key of note 5: that one fails safe and
hands the step back. This one fails the other way — it *completes* the step, and the
one form whose whole point is that a human talks the open items through gets filed
past by a fresh-context agent that has read only the room. The close form is where a
run's triage is written; a driven close is a run that triages itself.

The two exceptions are stated in a GitHub comment and in a previous run's process
notes. Neither is in the tree. `drive` has no way to know which forms are the
principal's, because nothing in the assembly says so — `terminal = true` is on the
close transition and would have served, and `carries`/`anchor` are already read at
mint time, so the fact is available and simply not consulted.

Triage candidate, and the sharpest one this run found: it is a silent completion of a
step the design reserves, on the verb this run exists to exercise.

## 13. The run's own review yield is the first measurement of the thing it built

`spine issue113 close` printed it, and the engine archived it beside the close form
(`YIELD.md`) rather than anyone tabulating it:

    review yield
      g1 review        r1  revise   1 finding   1 blocking
                       r2  revise   1 finding   1 blocking
                       r3  pass   2 findings   2 accepted
      consolidate      r1  revise   4 findings   4 blocking
                       r2  pass   2 findings   1 accepted 1 rejected
      plan-to-execute  r1  revise   6 findings   6 blocking
                       r2  revise   4 findings   4 blocking
                       r3  revise   3 findings   3 blocking
                       r4  pass   3 findings   1 beyond 1 rejected 1 accepted

Nine rounds across three seams, none of them at five. Under the cap this run ships,
nothing here would have paused — which is as much an answer about whether five is the
right number as issue99's nineteen was. issue99 hit nineteen at one seam; this run hit
four at the same seam and stopped because the artifact was finished, not because
anything stopped it.

The one place the number changed a disposition is note 9's: a `[delete]` finding at the
plan seam's fourth round, rejected rather than reworked, on the argument that the only
round left to carry it was the fifth. The cap was not in the engine yet and it already
priced a decision — the conductor reasoning under it before the code could enforce it.

Worth keeping for the proof run: a cap is not only a stop. Its first effect is on the
disposition of the round before it.

## 14. What `drive` did and did not do, in one place

It did, with no command typed between steps: three design-it-twice planner dispatches
and their closes; four plan-seam critic panels and their collections; two planner
rework dispatches; one route-form filler at the plan seam's first round; the gate
dispatch and the wait on it; the gate adjudication's own filler; and the engine's own
commit behind that adjudication's `advance`.

It did not: fill any route form after a seam's first round (#115, the missing `filler`
on a re-minted transition, at both tiers); notice that a dispatched child was alive and
had stopped working (#119); or stop at the close form, which it filled instead (#116).

Two of those three are silent. The `filler` one prints a refusal and hands the step
back, which is why it cost only automation. The close one completes the step, and the
liveness one waits forever. On this run the conductor caught both by looking rather
than by being told, and the cheapest fix for the pattern is the one #116 names: the
tree says nothing about which forms are the principal's, so the verb cannot know.
