# Process notes — issue80, the merged-verdict run

Friction met while driving this run, recorded as it happened, in the shape of
`docs/process-notes/issue88.md`. Nothing here is doctrine. Where an entry
contradicts `docs/AGENT_GUIDE.md` or a form, the guide and the form are right
about the tree and this file is right about what the run met.

## 1. The engine dispatched the consolidate panel and said so, and the room's words did the work issue88 asked for

issue88's note 16 ends on the sharpest open question that run left: nothing
told the conductor the engine had started dispatching underneath it, so for
the last third of that run two agents were pointed at every form. The room I
was handed at the consolidate transition opens:

    The engine starts each panelist itself through the repository's own
    dispatch entry when one is configured; wherever a row below carries a
    command instead, you are the one who runs it...

and then three rows, each reading `panelist pN (working)`. That is the
telling issue88 said did not exist, and it arrived before I could make the
mistake it prevents. Worth recording that it worked, and worth recording what
it cost to make it work: the sentence is conditional ("when one is
configured"), and the four states are carried on the rows rather than in the
prose, so the reader has to hold both halves at once. It held for me because
my dispatch brief said the same thing in the same words. A conductor whose
brief did not would still have to infer "working means do not touch it" from
a bare parenthetical.

## 2. A seed question was wrong about its own subject, and the board is where that got fixed

I seeded q1 naming four `merged_verdict` call sites and labelling
`engine/cli.py:2608` as `_returned_verdict`. There are five, and 2608 is
`_summary`; `_returned_verdict` is at 894. I had written the seed off a grep
whose line numbers I read faster than its function boundaries.

Nothing refused this. A seed question is prose in a field, so a factually
wrong question is a legal one — the board caught it only because answering
the row meant opening each site, and the answer records the correction beside
the question that was wrong. That is the board working, not a defect. What is
worth noting is the asymmetry with a decision field: a wrong *value* refuses
at the submit; a wrong *question* rides all the way to the answer, and if the
row had been dispatched as an excursion instead of read in place, the child
would have gone looking for a fourth site that does not exist under that name
and reported back about the wrong function.

## 3. Answering a fact row honestly made the spec's hardest paragraph write itself

Two rows (q5, q11) had to distinguish "this voice lost its verdict" from
"this panel has no verdict word." Both look identical in the returns: no
`verdict` key either way. The only thing that separates them is the panel
spec — which form each panelist was dispatched under.

I did not know that when I seeded the row; the question as seeded just
enumerated five inputs and asked which must refuse. The distinction fell out
of answering it, and the tree-walk imperative ("every answer was asked what
it opened") is what turned it into q11 rather than a parenthesis inside q5.
That is one concrete instance of the walk earning its line: the parenthesis
would have been true and would not have been carried into the spec as its
own paragraph, and the spec's "hard part of the whole issue" section is that
paragraph.

## 4. `spine note` takes its kind as the first argument, and says so only by refusing

I typed `spine issue80 note "decision: ..."` with a nine-line ruling in the
string. The refusal:

    no note kind "decision: the consolidate seam's round one. All three
    critics returned revise and ... arriving in its own record." -- one of:
    blocked, resumed, observation, decision, triage

The whole note echoed back inside the error, exactly issue84 note 1 and
issue88 note 1's shape at a third site: a positional argument whose kind is
announced only by rejecting it, with the rejected value quoted in full. The
guess I made — that a note is one string and its kind is a prefix inside it —
is the same guess `decision:` reads as everywhere else in this tree, since a
`rejected: <reason>` call really is one string with its word in front.

The refusal is correct and cheap to recover from. What it costs is that the
recovery is a retype of the whole note, and the room that renders
`also legal: spine issue80 note ...` shows the ellipsis rather than the
shape. One word in that line — `note <kind> ...` — would have cost nothing.

## 5. A rework rewrites the same artifact path, so the record's own frozen field points at text the panel never read

`SPEC.toml`'s `spec` field is an artifact — a path. On a rework the form is
minted fresh but the artifact is not, so the obvious move is to rewrite
`spec.md` in place and resubmit. That would leave round one's `submit` entry
in the journal pointing at a file whose contents are round three's, and a
reader of the archive would see the panel's round-one findings sitting beside
a document that does not contain what they object to.

I wrote each round to its own path — `spec.md`, `spec-r2.md`, `spec-r3.md` —
so every frozen field points at the text its own panel actually read. Nothing
in the form, the assembly or the skill asks for this; the field's note says
only "in the work location". It is the same class as issue88's note 14, where
one instance's `plan.md` write landed on top of another's because the write
path does not conflict-check a file that did not exist at its own last read:
an append-only journal beside a mutable artifact means the record is only as
honest as the naming convention nobody wrote down.

The cost of the convention is one line in `carries`: the released round's
path is what joins prefill, so a later reader sees `spec-r3.md` and has to
notice the `-r3`. That is a cheaper confusion than the other one.

## 6. Three rounds, and the shape of what survived each

| Round | verdicts | findings | what they were about |
|---|---|---|---|
| 1 | revise x3 | 3 | all three on one obligation, one stale fact |
| 2 | revise x3 | 4 | one on my own round-one edit, two on a section I added in the rework, one on grounding |
| 3 | pass, pass, revise | 1 | one delete-this I ruled wrong |

The curve matches issue88's note 10 and sharpens one thing about it. Round
one's three findings were one finding: every panelist independently found the
same stale clause, which is what a cold panel is for and what a single
reviewer with three criteria would probably have found once and moved past.

Round two is the interesting one. Two of its four findings were against edits
I had made in the rework itself — a section I added to justify a deletion,
and two sentences I added to an obligation. Neither existed when round one
ran. So a rework does not only shrink the finding surface, it moves it: the
fix is new text, and new text is unreviewed text. That argues against the
instinct to make a rework generous. The round-two edit that survived
untouched was the one-clause deletion round one asked for; the two that drew
findings were both additions I made on my own initiative while I was in there.

Round three's single finding was a deletion argument I rejected on evidence.
Two of three passing with one contested deletion is what the three-round cap
is calibrated for, and it is worth saying that the cap was not what decided
the release — I judged the finding wrong, and would have released on it at
round one.

## 7. The `accepted` call is a trap the conductor has to route around by hand

Round three's finding said "delete obligation 13 outright." I disagreed. The
call vocabulary is `blocking | accepted | beyond | rejected: <reason>`, and
only `rejected` carries a reason.

`accepted` was the closest fit for what I actually thought at first — true in
its diagnosis, and the round stands anyway — but `accepted` on a delete-this
finding is exactly the open defect the tracker already carries: it reads to a
later agent as consent to the deletion, and three planners were about to read
this row. So the honest options collapsed to one: find out whether the
finding was actually true, and rule `rejected` with the command that refutes
it. Which I did, and it was refutable.

That is a good outcome reached by a bad route. The disposition I chose was
driven by what the vocabulary would be *read* as rather than by what I
believed, and it was only luck that the finding turned out refutable. Had it
been true-but-not-acted-on, I would have had to write `accepted` on a
deletion argument and hope, or invent a call the form does not offer. The
missing thing is not a fifth word: it is that `accepted` is the only call
with something to say and nowhere to say it.

## 8. The engine picked the rival plan, and the conductor had no place to pick

The plan segment's design-it-twice round dispatched three planners under
three constraints. All three returned. `spine issue80` then rendered the
critic panel already `working` on one of them, and `st["done"]["plan-1"]` was
`issue80.plan-1.p3` — the last to close.

That is issue #96, seen from the conductor's chair rather than read off the
glossary. I never saw the three plans before the critics were reading one of
them, and there is no step between the third planner's return and the panel's
dispatch where a pick could go. The engine's own return branch writes
`st["done"][e["step"]] = e` on the last arrival and the transition mints
immediately.

What that cost here is specific and worth writing down, because #96's own
issue text argues the general case and this is the concrete one. The three
rivals were not close:

  p1 (unconstrained) — two gates: gate 1 moves the fold and every caller
    together, gate 2 takes the two test obligations. Resolves obligation 10
    in the plan document with the fact that would reopen it.
  p2 (fewest gates) — one gate covering everything, obligation 12 closed as
    a subset test over every seam. The only one of the three that named
    `engine/render.py:612` as a literal-word site.
  p3 (smallest engine touch) — one gate that builds the fold beside the
    untouched `merged_verdict`, wired to nothing, with a three-gate horizon.

p3 is the one the engine kept, and p3's "prove it in isolation" shape is what
generated three rounds of critique and an impasse (note 9). p1's and p2's
cuts both wire the fold into its callers in the gate that builds it, which is
the shape the impasse ruling ended up asking for. The pick that was never
made was the one decision that would have saved the whole loop.

And the rivals are not recoverable through the machinery once the panel
starts: `_mint_projected_gate` copies its gate fields from the step's `done`
entry, so naming a different plan artifact in `PLAN_TO_EXECUTE`'s own `plan`
field would not change which gate gets projected. The conductor's only lever
is `rework`, which sends the surviving cut back — not `take that other one`.
The two rival plans still sit in the work location, complete and unread by
anything.

## 9. Three rounds of critique on one plan found one defect three times, and the fourth round cannot be told so

The plan seam's eight blocking findings across three rounds reduce to six
instances of one sentence: *this rule is stated in `purpose` and no case in
`scope` could fail if an implementation violated it.* Obligation 4's inert
panel, then the refusal-meets-clean combination, then the quiet-eligibility
mix, then the clean-word merge's missing table input — four different nouns,
one shape.

The cause is the gate's proof shape rather than the planner's attention. A
gate that builds a function in isolation has an enumeration for a proof, and
an enumeration can always be found short by one case. `REWORK.toml`'s own
`deleted` field says "Nothing cut" in both rounds, and PLAN.md grew +40% then
+28%, entirely by adding cases. Nothing was removed because nothing could be.

The impasse form is exactly where that diagnosis belongs, and its imperative
asks for it in as many words: "rule on the loop, not on the findings." I
ruled `rework` and wrote the diagnosis into `why`.

`why` reaches nobody. `_rework_prefill` (engine/cli.py) opens with
`if not step.get("panel"): return None, ""`, and the impasse step is the one
deciding step minted with no panel — the docstring says so on purpose, so the
outlet's own rework "carries the prefill that caused it" rather than
re-deriving it. The consequence is that a conductor's ruling on the loop is
recorded in the journal and delivered to no one. The fourth round arrives
holding the same blocking findings that produced the third, and answers them
the same way they were answered twice already: one more enumerated case.

Here the substantive half rode anyway, because round three's own p1 finding
happened to name the missing input rather than the missing case. That is
luck. The general shape is that the one form in the assembly written for a
conductor to rule on a pattern has no channel to send the pattern anywhere,
and the three verbs it offers (`advance`, `rework`, `up`) all act on the
round while the reasoning that chose between them stays behind.

The cheapest thing that would close it: `_rework_prefill` returning the
impasse submit's own `why` alongside the carried findings when the deciding
step is the impasse form. One branch, and the ruling becomes orders instead
of a diary entry.

## 10. The four-state read did the thing issue88 was written for, first try

`spine issue80` rendered `issue80.g1-a13c3 (gone without returning)` and
printed the brief and the respawn command beneath it. The gate's own journal
showed `submit work-1`, `submit select`, and two `dispatch-started` entries
for its review panelists — so the conductor had died after dispatching its
panel, with the work submitted and the panel alive.

That is issue88's note 12 with the answer attached. In that run the same
situation (a child that had stopped, a step that had not moved) was
diagnosable only because the subagent harness reported the agent completed
and its final text said it was waiting — both outside the engine. Here the
engine said it, in the room, in three words, and the recovery was mechanical:
respawn the one dead process, leave the two live ones alone.

Three details worth keeping.

The diff was flat across the whole work round — `engine/run.py` stayed at
+133 insertions from the poll before the round started to the poll after it
submitted. I nearly read that as "nothing happened," which is note 15a's
mistake again. It was wrong for a dull reason: the reminted gate's edit
replaced lines inside a block that was already entirely new relative to HEAD,
so the insertion count did not move. `git diff --stat` cannot see a change
inside an added block. Driving the function was what actually answered it —
`verdict_fold` now returns `('clean', 'revise')` for a revising panel in
either arrival order, and `('clean', 'pass')` where the table declares no row
for `revise`. Both defects closed, verified before I looked at any form.

The respawn is a subagent and the engine did not do it. `gone without
returning` prints a command for a human or a conductor to run; the engine
knows the process is dead and starts nothing. That is deliberate — a
respawning engine would race a conductor who is also respawning — but it
means the four-state read is a diagnosis without a treatment, and the
treatment is exactly the hand-dispatch the same room forbids in the state
next door. The distinction is one word in a row, and it is the whole
difference between correct and issue #105.

And the respawned conductor needs to be told two things the record does not
carry: that the engine now dispatches children itself, and that its own
panelists are already `working`. A conductor that reads only its own room
sees `panelist p1 (working)` and has to already know what that word costs to
ignore. I put both in the respawn prompt. Nothing in the tree would have.

## 11. The run's own `spine` died for four minutes because its gate was editing the engine

Polling the parent mid-way through the wiring gate's implement round:

    NameError: name 'merged_verdict' is not defined
      engine/run.py:577, in _holds_for_its_form
      called from engine/run.py:635, in state
      called from engine/cli.py:903, in cmd_status

The implementer had deleted `merged_verdict` and had not yet rewritten the
caller one function above it. For those minutes `spine issue80` — the
conductor's only view of its own run — did not run at all, because the engine
it runs on is the engine the child is editing.

That is issue #67's subject arriving live rather than as a claim, and it is
specific to a repo that builds itself with itself. Two things follow.

The four-state read cannot help here, and neither can anything else in the
journal: the failure is not a child dying, it is the reader failing. I fell
back to reading the gate's `journal.toml` with `tomllib` and `git status`
directly, neither of which imports `engine/`, and polled on `spine <wid>
>/dev/null; echo $?` until it exited zero. That worked, and it is worth
writing down as the only liveness read that survives its own subject.

And the right response was to wait, not to intervene. A tree that does not
import mid-round is the same class of observation as note 15a's empty working
tree: ambiguous between "the child broke it" and "the child is halfway
through." It resolved on its own within one poll. The rule I would keep: when
the engine under a run is the thing being changed, a broken tree is a
transient until a poll shows the child dead, and only then is it yours.

## 12. Two gate-conductors died mid-gate, and the two deaths needed opposite recoveries

`issue80.g1-a13c3` died after its review panel was dispatched: the work was
submitted, the panel was engine-started and detached, so the panelists
outlived their conductor and were still `working` when I respawned it. The
respawn had to be told *not* to touch them.

`issue80.g3` died mid-implement: its implementer was its own subagent, so the
implementer died with it, leaving 10 modified files, +355/-174, and an
untouched `IMPLEMENT.toml`. The respawn had to be told the opposite — that the
diff in the tree is unowned and partial, and that establishing what it is
against the gate's scope is the first job, before any form.

The difference is who started the child. An engine-started child is a detached
process with a `dispatch-started` record and survives its parent; a
hand-dispatched one is a subagent and does not. The room's four-state read
reports the conductor accurately in both cases and says nothing about which
kind of orphan it left, because the engine has no record of a hand-dispatched
child at all — issue88's note 16 makes that same point about uniqueness, and
this is the survivorship half of it.

Neither respawn could learn any of this from the record. Both prompts had to
carry it, written by hand, from `git status`, `git diff --stat`, and reading
the child's journal for what it did and did not submit.

## 13. Every gate-conductor in this run died, and the pattern is the shape of the work

Four gate runs, three dead conductors: `g1-a13c3` (died after dispatching its
review panel), `g3` (died mid-implement), `g4` (died on `select`). Only the
first gate, `g1`, ran to close under the process that started it.

Each death cost one respawn and, in two cases, one resume after the respawned
agent ended its turn waiting for its own panel — the anti-stall sentence in a
dispatch brief now four-for-four at failing to prevent the stall it names
(issue84 note 15, issue88 note 12, and twice here). What made each recovery
cheap was not the brief. It was that `spine issue80` said `gone without
returning` in the room, so the diagnosis took one command instead of an
inference from a subagent harness's own report.

What the four-state read does not survive is being the recovery as well as the
diagnosis. A respawn started by hand is a subagent with no `dispatch-started`
record, so the row keeps reading `gone without returning` for the rest of the
gate — the engine is still watching the dead pid. For `g3` and `g4` that meant
my only view of a live child was `git status`, the child's `journal.toml` read
with `tomllib`, and the step name. Correct, and entirely outside the mechanism
built to answer exactly that question.

## 14. Two seams looped and they looped differently, which is what the impasse form is for

The understand segment and the wiring gate's plan segment both reached three
critic rounds. They were not the same event.

Understand's three rounds returned three instances of one sentence — a rule
stated in the artifact with no case in its proof that could fail if it were
violated — with four different nouns. The cause was structural: the gate cut
under review proved a function in isolation, so its proof was an enumeration,
and an enumeration can always be found short by one case.

The wiring gate's five rounds returned eleven findings and repeated none. Each
answered the last and found somewhere nobody had looked: an unguarded form
load, then a grep that could not match its own targets, then a file missing
from the sweep meant to cover "anywhere in `engine/`", then — the sharpest —
that the guard round one had asked for would, wired into `state()`'s fold,
turn a harmless historical rename into a run nobody can read. That was a large
gate against a fourteen-obligation spec being surveyed, not one defect found
five times.

The impasse form's imperative is "rule on the loop, not on the findings," and
the two seams needed opposite rulings under it. Both got `rework`, and the
second one I ruled against my own stated inclination: I had written into the
first wiring impasse that another finding of the same class would end it, and
what round four returned was not that class, so the rule did not fire.

What the form asks for is exactly right and the record has nowhere to put the
answer — note 9, and issue #107 now.

## 15. Filing three issues at close was cheaper than carrying three notes

`CLOSE.toml`'s `triage` field takes issue refs, not descriptions, which forces
the question of whether a candidate is work before the run ends rather than
after. Three of this run's four candidates became #106, #107 and #108. The
fourth — the guarded `panel_forms` reader adding 36 uncached `forms.load`
reads to every `state()` fold, measured at 36ms on this run's own journal —
did not, and `standards/issue.md` is why: real, cheap, and harmless is the
easiest work in a backlog to justify and the least worth doing. It is in
`residue` with the condition that would change it.

Writing each of the three to the standard's own shape was what made two of
them sharper than the note they came from. #106's observation is three lines
of Python whose output is the whole defect; the note it grew from was a
paragraph of reasoning about a filter. The standard's insistence that a
`measured` type carries its command is what turned the second into the first.
