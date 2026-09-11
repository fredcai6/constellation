# Process notes — issue84, the `up` run

Written during the run that made `up` one thing (PR #85, epic #55 wave 5), by the
issue-conductor, as each thing happened rather than reconstructed at the close. It records
where the framework was unclear, where it misled an agent, and where an agent — including the
conductor — got something wrong and how it was caught.

It is kept because the run that produced it argued, in its own close, that this was the most
useful thing it made that is not code, and because a note in a gitignored work location is
available only to whoever is told about it. Read it before the next run of this shape.

Nothing here is doctrine. Where an entry contradicts `docs/AGENT_GUIDE.md` or a form, the
guide and the form are right about the tree and this file is right about what the run met.

# Process notes — issue84

Friction met while driving this run, recorded as it happened. First major run since the
consolidation, so the bar here is "did the tree tell me what to do without my guessing",
not "was I inconvenienced". Each entry says what happened, what I expected, and whether it
is already someone's issue.

## 1. `note` refuses after the whole note is typed, and status never names the kinds

`spine <id> note ...` is offered at the bottom of every step as `also legal: spine issue84
note ...`. The kind is a required first argument (`blocked | resumed | observation |
decision | triage`), but nothing at the step says so, and the refusal arrives only after the
note itself is parsed — so a long note is echoed back inside the error message rather than
recorded. Expected: the legal-line names the kinds, the way every decision field's note
names its own values. This is the same principle as "the sentence the agent is given and the
rule it is held to are one string", applied to a verb rather than a field.

## 2. A board row's display text is decided by key order in the file

`engine/boards.py:48` takes a row's label as "the first string after its id and status in
file order". Authoring rows programmatically, I emitted `recommend` before `question` once,
and the tree rendered my draft recommendation as the row's text for three rows. Nothing
refused it and nothing looked wrong until I read the tree. Expected: the row's label is the
`question` column by name, or the form fixes the order. This is the authoring-side face of
the same defect commitment 9 in this run's spec fixes from the reading side.

## 3. The seed form and the board disagree about a column's name

`OPEN.toml` seeds rows under `[[questions]]`; the board they land on calls them
`[[question]]`. Both work, and the mapping is obvious once seen, but `standards/prose.md`
rule 2 is one name for one thing, and this is one thing under two names inside one run's own
paperwork.

## 4. Submitting `open` prints the next segment's transition imperative

Submitting OPEN.toml printed the understand board *and* the consolidate step's imperative
("Read the understand board whole -- and crystallize a specification"), which reads as if
the board is already done and the spec is what is being asked for. The board's own imperative
is above it, so the information is right; the ordering is what misleads. A fresh conductor
following the last thing printed would skip the board.

## 5. A panelist's brief is rendered but not addressable

Dispatching each panelist means copying its brief out of `status`'s rendered text. There is
no way to ask for one panelist's brief alone, so a dispatcher greps a block out of a page
that also holds two other briefs. The briefs themselves are complete — this is only about
getting one out.

## 6. `run-a-gate` opens as a root run and can never finish

`spine open run-a-gate --title X` with no `--parent` succeeds. The gate runs normally, and
nothing can ever adjudicate its return. I did this deliberately, to drive the root-`up`
branch this issue is about, so it was useful here — but nothing warned that the run being
opened has no one to return to. Adjacent to #62 (`cmd_open` stamps a branch and worktree on
runs that have neither).

## 7. Three of four grounded panel findings came from misreading a board row

Across three review rounds, three separate cold panelists quoted a board row's `recommend`
field as this run's ruling and reasoned from it — twice concluding the run had decided the
opposite of what the principal actually said. `recommend` is the conductor's draft position,
written *before* the ask; `answer` is the principal's words and the only thing that binds.
They are siblings at a row's top level with nothing marking which is which.

This is worth recording as process, not just as a finding, for two reasons. First, the rate:
a defect that produces a wrong reading in three of four grounded findings is not a subtle
one. Second, and more useful: the review loop kept *working correctly* while producing wrong
conclusions — every panelist grounded its claim in a real file at a real line, which is what
the criteria asked for. Grounding is not enough on its own when the ground itself is
ambiguous. The run's own record was the misleading artifact.

Already in scope: commitment 9 of this run's spec fixes it structurally.

## 8. A revise round cannot tell the panel what was already ruled

The skill is explicit that a panel's brief must not be sharpened between rounds — a cold
reader is the point. But a finding whose *premise* is false (not whose conclusion is
arguable) will recur every round, because each fresh panelist re-derives it from the same
ambiguous artifact. The conductor's disposition is journaled, and the next round's panelists
do not read it. There is no way to correct a factual premise without also telling the panel
what to think, and those are different things the tree currently cannot distinguish.

## 9. The spec loop has no impasse and no conductor override

`assemblies/run-an-issue/ASSEMBLY.toml`: the `plan` segment declares `impasse-after = 3` and
an impasse form, so a plan that keeps failing eventually reaches a conductor's own ruling —
advance, rework, or up. The `understand` segment declares neither. Its transition decides on
`resolution`, which is the merged verdict and is never typed by the conductor, and its
outcome table is `pass | revise` with no third word.

So the spec loop's only exit is the panel passing. A conductor who believes a finding's
premise is false has no move: it cannot advance over the objection, cannot rule the loop, and
cannot ask up — the issue tier's own `up` is the defect this run exists to fix, and it is not
declared on this transition in any case. Round three of this run's spec review is where that
became concrete rather than theoretical.

This is the strongest argument I met for this run's own commitment 2. `up` as a move
available wherever an agent stands is exactly what a conductor in this position needs, and it
needs no outcome row on this transition to be reachable — which is the whole point of the
move-not-a-value ruling.

Correcting something I told the principal earlier in the run: I said the engine offers three
rework rounds before asking the conductor to rule. That is true of the plan segment and not
of this one.

## 10. An abandoned child is indistinguishable from a working one

Twice in this run a dispatched panelist's harness died mid-step. The parent's own `status`
reports the panelist as `outstanding` in both cases -- the same word it uses for a panelist
that is still reading. Nothing in the parent distinguishes "this child is thinking" from
"this child will never come back", and the conductor learns the difference only by going and
looking at the child's own work location: an opened `journal.toml` with an untouched form
template means abandoned, a longer journal means progress.

The two abandonments differed in a way that mattered. One died after writing its whole
verdict but before submitting it, so the form held a complete, honest judgement the conductor
could carry through mechanically. The other two died having done nothing, so the work had to
be dispatched again. Telling those apart also required opening the child.

This is the live half of `#26`'s abandoning-a-dispatched-child concern, met for real. A
conductor cannot poll for it, because polling a child that is merely slow looks identical.
Worth noting the shape of a fix rather than only the complaint: what distinguishes the two
cases is whether anything has been written since the child opened, which is a fact the
parent could read from the child's own journal without opening it as a run.

Recorded also because of what it cost: without the principal happening to mention that a
stop may have caught the subagents, this run would have waited indefinitely on two panelists
that were never coming back, and the wait would have looked exactly like patience.

## 11. The three "independent" planners were not independent

The plan segment dispatches three planners at once under different constraints — the
design-it-twice shape — on the premise that three cuts drafted apart are worth more than one.
They were not drafted apart. The third planner's own return says so outright: it describes
its cut as "deliberately narrower than the other two panelists' cuts (both p1 and p2, visible
in this run's shared state...)". It read the other two and defined itself against them.

That is not misconduct: nothing told it not to, and the work is in the shared work location
where anything can read it. But it means the criteria did not produce three independent
readings of the spec; it produced one reading, one alternative, and one reaction. A panel
whose members can see each other converges toward whoever finished first, and the value of
the third voice is whatever it adds to the second rather than what it would have said alone.

This is `#75` — a cold panel is not independent, a later panelist can read the earlier ones —
observed at the plan seam rather than the review seam where it was filed. Worth attaching to
that issue as a second site: it was filed about verdict panels, and design-it-twice has the
same exposure with more at stake, since a plan panel's whole justification is divergence.

Not fixed here; out of this run's scope by the principal's own ruling that #75 keeps its own
issue.

## 12. The plan panel was sharp where the spec panel was not, and the difference is the artifact

Two panels, same tier, same model, same posture file, dispatched the same way. The spec panel
took five rounds and two of its four grounded findings had false premises. The plan panel
returned three findings in one round, all three real, all three verified against the engine
by hand afterwards, and two of them naming defects that would have shipped green.

The difference is not panelist quality. It is what each panel could check against. A plan
names functions and line numbers, so a critic can go read `engine/cli.py:1943` and see for
itself whether `seg["step-form"]` has a fallback. A spec is prose about intent, and the only
record of the intent behind it was a board whose `recommend` and `answer` fields are
indistinguishable to a cold reader -- so a critic checking a spec against its own run's
reasoning was reading an artifact that misleads.

Two things follow. The panel mechanism works when the ground is checkable, which is worth
knowing before concluding that reviews are expensive. And the fix for the spec seam is not a
better critic or a fourth criterion; it is commitment 10, making the run's own record
unambiguous, which is already in this run's scope.

## 13. `verb` is a homonym before we add to it

The plan panel caught the run about to coin a second sense of "verb": `standards/glossary.md`
defines `pause`, `release`, `refill`, `rework`, `skip`, `remint` and `close` as *outcome
verbs*, resolved from an outcome table's `does` string. The word `up` needs is the other
kind -- a command an agent types, beside `status`, `submit`, `note`, `amend`, `close` and
`trace` in `main()`'s own dispatch table.

The tree already carries the collision without this run's help: `close` is both an outcome
verb and a command, meaning two unrelated things. So the glossary needs a name for the
command kind before `up` can be defined as one, and commitment 1's entry is where that lands.
This is the third homonym this run has turned up around one word -- `move`, `verb`, and `up`
itself -- which is some evidence that the naming discipline is doing real work and some that
the vocabulary has grown past what one glossary pass can hold.

## 14. A finding filed in `vocabulary` does not carry like one filed in `findings`

`CRITIC.toml` has two output fields: `findings`, which gates the verdict and prefills the
next round, and `vocabulary`, for terms inconsistent with the glossary. Two plan critics put
the same real defect in `vocabulary` -- that calling the new `up` a "verb" collides with the
glossary's `outcome verb` -- and the first rework round read straight past it, fixing every
`findings` item and leaving the naming untouched. It only landed on the second rework round
because the conductor called it out by hand in the dispatch.

That is a shape problem, not a planner's mistake. A homonym is precisely the defect this run
exists to close, and this repo's own prose standard makes one-name-one-thing a rule rather
than a nicety -- so a vocabulary finding is not a lesser kind of finding, but the form's two
fields make it read as one. Either `vocabulary` should prefill the next round the way
`findings` does, or a vocabulary finding that would ship a homonym belongs in `findings` and
the form should say so.

Worth adding: the collision it names already exists in the tree unmarked. `close` is both a
bare command an agent types and an outcome verb resolved from a `does` string -- two
unrelated mechanisms under one word, shipped and unremarked. The critics found the new
instance because they were looking; nothing found the old one.

## 15. A gate-conductor stalled waiting for its own background check

The gate-conductor started its proof check in the background and then ended its turn holding
for it — "Holding here while the gate's proof check runs in the background — I'll resume once
notified it's finished." Nothing was going to notify it. The check finished, the gate advanced
to `select` on its own, and the run sat there until the conductor above went looking.

The engine did nothing wrong: `spine issue84.g1` reported the true state the whole time. The
failure is that a dispatched agent treated "the check is running" as a reason to stop rather
than to poll, and a stopped agent is indistinguishable from a working one from above — the
same shape as note 10, arriving by a different route.

Worth pairing with note 10 rather than filing apart, because together they say something
sharper than either alone: this tree has two ways for dispatched work to go quiet (the harness
dies, or the agent decides to wait) and no way for a parent to tell either from progress. The
`slow proof` work that landed at `1955cf2` gave a gate a way to declare that its proof takes a
while; what is missing is any signal that the agent holding that proof is still there.

Cheap mitigation used here: the dispatch brief now says outright not to end a turn waiting,
and to poll its own background work instead. That is a brief patching a gap rather than a
mechanism closing one, and it only works for agents this conductor dispatches by hand.

## 16. The conductor above nearly double-dispatched a live panel

Correcting note 15's diagnosis with what actually happened, because the mistake is more
instructive than the stall was.

The gate-conductor stalled a second time, saying it was waiting on both reviewers. Reading its
work location, one reviewer's form was an untouched template and the other held a findings
draft with no verdict — the same evidence that meant "abandoned" the last two times. So the
conductor above dispatched replacements for both.

Both originals were alive. One submitted a real `pass` verdict minutes later; the other was
still working, five minutes in. Two agents were briefly pointed at each of two forms, and had
they both finished, each would have submitted a verdict over the other's — a panel of two
voices returning four, with the record keeping whichever landed last. The replacements were
killed before that happened, but nothing structural prevented it.

The lesson is not "look harder before dispatching." It is that an unfilled form is not
evidence of anything. A form is written at the end of a child's work, so *every* child looks
abandoned for most of its life, and the one signal a parent has is indistinguishable between
"nothing has happened yet", "the harness died" and "the agent stopped to wait". Notes 10 and
15 each described one of those; this one is what happens when a conductor acts on the guess.

What would actually settle it is liveness, not artifacts: something a running child touches
because it is running, which a parent can read without opening the child as a run. Nothing in
the tree offers that today, and a conductor that dispatches on the artifact alone will
eventually do what this one nearly did.

## 17. The conductor typed a verdict into a field that acts, and lost a round to it

`PLAN_TO_EXECUTE.toml`'s `resolution` field is described in its own note as "the critic panel's
own merged verdict, carried onto this transition's outcome table -- not yours to argue, only to
record if you want the record explicit," and then, several lines later, "Typing anything but
`pass` mints a redundant rework round alongside the projection above, not a correction to it."

Reaching that form by way of an impasse ruling of `advance`, the conductor wrote the panel's
actual merged verdict -- `revise` -- into it, reading the first half of the note as licence to
record what happened. The field acted on it: the segment refilled, no gate was projected, and a
fresh interior round plus a fresh critic panel were minted. Recovering cost an amend-close and
a fifth panel round on an unchanged plan, three dispatched agents, all of it spent on a typo of
intent rather than on the work.

Two things about the shape, not the mistake:

The note tells the reader the field is descriptive in one sentence and destructive in another,
and the destructive sentence is the later one. The repo's own rule -- a `decision` field lists
its values in its note so the sentence the agent is given and the rule it is held to are one
string -- is honoured here in letter (`pass | revise` are listed) and undercut by the prose
around it, which invites recording rather than deciding.

And the field is only ever reachable with a value other than `pass` by the path this run took:
the note asserts "it reads `pass` every time you actually see this form," which is true when
the panel passes and false when an impasse advances over a live revise. That path exists --
this run walked it -- and the note is written as though it does not. The impasse ruling and the
transition's own outcome table disagree about what has been decided, and nothing reconciles
them; leaving the field blank is the only thing that works, which no sentence says.

## 18. Four wordings, three rounds, and the conductor propagated one himself

The stale claim that `up` ends a run has now been found in four distinct phrasings, each by a
different review round, each after the previous round widened its sweep to be exhaustive:

  round 4  `assemblies/run-a-gate/forms/ROUTE.toml`      -- a prose paragraph
  round 6  `skills/issue-conductor/SKILL.md:32`          -- "send it up, which ends the run"
  round 7  `assemblies/run-an-issue/forms/IMPASSE.toml`  -- "refills nothing ... walk to its close"
  round 8  `assemblies/run-an-issue/ASSEMBLY.toml:55,169` -- "# mints nothing; the run walks to
                                                             its terminal step"

Round 7 answered round 6 by replacing a file list with a property -- a three-alternative regex
-- and asserted in the plan that it matched every wording in the corpus. Round 8 found a fourth
the regex does not match. So the lesson of note 14 repeats one level up: generalising from
"the files I know" to "the phrasings I know" is the same mistake with a bigger radius, and the
next round would likely find a fifth.

The part worth keeping is who wrote line 55. The conductor did, in the impasse commit made at
the principal's direction earlier in this run: the understand segment's `up` row was copied
from the plan segment's, comment and all, which propagated the stale sentence into a second
place inside the very run whose purpose is to delete it. Nothing caught it -- not the suite,
not the panel that reviewed that commit's own gate, not the conductor re-reading his own diff.
A cold critic four rounds later did.

Two conclusions, one cheap and one not. Cheap: the fix belongs in the wiring bullet, not the
regex -- whatever ruling lands on those rows, their trailing comments are part of the row and
change with it. Not cheap: a defect defined by what prose *means* cannot be swept by matching
what prose *says*, and every round of this has been an attempt to do that. The durable form is
a test that asserts the property from the outcome table's side -- the shape
`test_promises.py::test_a_declared_outcome_and_its_field_note_are_the_same_list` already has
for enum tokens, which is the one check in this family that has never missed anything.

## 19. The fifth site, and the prediction that was already written down

Note 18 ended by saying the next round would likely find a fifth wording. It did, one round
later: `engine/cli.py:1231`, inside `_perform`'s own `[impasse-verbs]` rationale block --
"`release`, the field's own default, mints nothing, and the run walks to its terminal step."
It is the same sentence as the two `ASSEMBLY.toml` row comments, and it sits inside the very
function this gate edits.

What makes it worth a note rather than a shrug is *why* every round missed it. The sweep's
phrase list was widened three times; that was never the failure. The sweep's ROOT was
`assemblies/` and `skills/` -- the corpus, the authored text an agent reads -- and this
sentence lives in engine code. Each round argued about which phrasings to match while the
boundary of where to look went unexamined, because "the corpus" is the natural unit for a rule
about authored prose, and the rule's real subject is any place the repo asserts what `up` does.

So the fix is not a fifth phrase or a fifth filename. It is one grep with a wider root, which
subsumes all four previous rounds of enumeration. That is the shape a durable check has to
take here, and it is cheaper than any of the enumerations that preceded it.

The general form, worth carrying past this run: when a sweep keeps missing instances, widen
the domain before enriching the pattern. Three rounds enriched the pattern and each was
overtaken. One round widened the domain and the question closed.

## 20. A rework round can write its form and its prose into different rounds' directories

Rework round five widened the stale-prose sweep to the whole repository. It wrote that
decision into two places: the narrative went into `plan-a3565/plan.md` -- the *previous*
round's directory, because that is the plan document being amended -- while the binding form
went into its own `plan-a0876/REWORK.toml`. Both are defensible in isolation. Together they
mean the round's reasoning and the round's contract live under different ids, and nothing
names the pairing.

The conductor then recovered from an unrelated engine defect by copying "the plan that
passed" from `plan-a3565`, took the prose-carrying directory, and reconstructed the gate from
round *four*'s scope and proof -- silently dropping the repo-wide sweep that was the whole
point of round five. Two panelists caught it independently within minutes, which is the system
working; but what they caught was the conductor being misled by the tree's own layout while
trying to repair the tree.

The tell was available and I did not look for it: `plan.md`'s mtime was fifteen minutes later
than the `journal.toml` of the round whose directory it sits in. A document younger than the
round it belongs to is a document that belongs to a later round.

Worth stating as a rule rather than an anecdote: an artifact's directory is not evidence of
which round binds it. The form a round submits is the round's contract; a `plan.md` it edits
may live anywhere. Anything reading "the plan that passed" should read the form, and the form
should say which document it stands on -- `plan-a0876/REWORK.toml` does carry a `plan` field,
and reading that field rather than the directory name would have avoided this entirely.

## 21. Two tiers, one word, opposite rules about a panel between rounds

`skills/issue-conductor/SKILL.md:34` — "Never sharpen the panel's brief between rounds — a
panel reads from fresh context on purpose, and a sharpened brief tells it what to find."

`skills/gate-conductor/SKILL.md:27` — "Select fires again on every rework round. Choose for the
round in front of you, not the round that just failed: a panel inherited unchanged is the"
failure it names.

Both are right for their own tier, and the reason is real rather than a slip: an issue-tier
critic panel re-reads the same artifact round after round, so a cold read is the whole value
and any hint contaminates it; a gate-tier review panel reads a different diff each round, so a
panel chosen for the last diff is looking at the wrong thing. What the tree does not say
anywhere is that these are different rules for different reasons — they are two imperatives
about "the panel" that a conductor holding both would read as a contradiction.

Watching it in practice sharpens the point. Gate g2's third-round lens does not merely name a
dimension; its `criteria` recounts what the previous round's reviewer found, names the
functions to read, and instructs the reader to drive the engine rather than read it. That is a
good instruction and it found a real defect. It is also, word for word, what the issue tier
forbids. The gate tier's own latitude to re-choose does not obviously extend to briefing a
reader on the prior round's conclusion, and nothing marks where choosing a lens ends and
sharpening a brief begins.

The cheap fix is a sentence in each skill acknowledging the other, since both currently read as
universal. The real question underneath is whether "choose the lens" and "state what the lens
should look for" are separable at all — a criteria field is free text, so any lens can carry a
briefing, and the only thing stopping it is the conductor's own restraint.

## 22. `merged_verdict` fails open, so any dropped verdict becomes a pass

`engine/run.py:266` folds a panel's returns with: collect each return's `verdict` field, return
`"revise"` if the literal word appears, otherwise `"pass"`. The docstring's reasoning is sound
for the case it was written for -- revise outranks pass, one blocking finding decides the round
-- but the fallback is unconditional. A return whose `fields` are empty, whose verdict never
got written, or that failed in a way nobody modelled, folds to `pass`.

Gate 3's plan review turned this from a shape observation into a driven fact. A panelist that
rules `up` mid-verdict and resumes lands, under the plan's proposed lever, on a segment that
mints two same-form steps; the run still closes, the terminal lookup returns nothing, `fields`
comes back `{}`, and a reviewer who had ruled `revise` returns `pass` to the gate that
dispatched it. The panelist did its job, said the diff was wrong, and the record says the diff
was fine.

This belongs to the epic rather than to this run. It is the same defect class #55's wave 5 was
cut for -- a record asserting something no command contradicts -- but located in the fold
rather than in prose, and it is strictly worse than the prose cases because nothing about the
output looks unusual. A stale sentence can be greped. A verdict that silently became a pass
looks exactly like a verdict that was a pass.

The shape of a fix, not this run's to make: the fold should distinguish "every voice returned a
word I understand" from "some voice returned nothing", and refuse rather than default on the
second. `#80` is already open about `merged_verdict` holding the reviewer's vocabulary and is
the natural home.

Worth pairing with note 12: the panel mechanism is only as good as what it can check against,
and here the mechanism that aggregates the panel is itself the thing that cannot tell absence
from assent.

## 23. Correct reasoning about the wrong layer, twice settled by running it

Gate 4's simplicity critic filed a blocking finding: a blank line between `[ $PROOF_RC -eq 0 ]`
and the following `&& grep ...` closes bash's and-or list, so everything after it never runs and
the proof always fails. As bash, that is exactly right. As a claim about this tree, it is false:
a proof string never reaches the shell raw. `_resolve_command` (engine/cli.py:154) splits on
`&&`, calls `.strip()` on each part, and rejoins with `" && "` -- which removes precisely that
whitespace. Verified rather than argued: after resolution the text contains zero `&&` preceded
by a blank line, and `bash -n` reports no syntax error.

This is the second time in this run two agents made opposite mechanical claims and the only
thing that settled it was running it. The first was whether any test forces a form note's enum
list to track its outcome rows; one critic said nothing did, another had named the test that
does, and a one-line mutation decided it. Both times the losing argument was well-reasoned
about the wrong layer.

Worth stating as a rule for a conductor at an adjudication seam: when two grounded claims
conflict, do not weigh them. Both readers are competent and both can cite real lines; the
disagreement is evidence that the question is not answerable by reading. Run the thing. Every
instance of this in the run took one command, and every instance of trying to decide by
argument would have gone the wrong way at least once.

The tree already says this for a gate's returns -- root-verify, never believe. It does not say
it for a panel's findings, which is where both of these arose.

## 24. Conductors report and then stop, instead of dispatching the next step

Raised by the principal, and true of this conductor as much as of the dispatched ones.

The pattern: a step completes, the conductor writes an accurate account of what happened and
what comes next -- and then ends its turn without doing the next thing. The account is correct,
the record is honest, and the run has not moved. It takes an outside nudge to convert "here is
what I will do" into doing it. This run has several instances at the issue tier (reporting a
panel's verdicts and waiting rather than dispatching the rework) and several at the gate tier,
where two gate-conductors ended turns saying they would resume once their reviewers reported.

Worth separating from note 15, which looks similar and is not the same thing. There, an agent
stopped because it believed something would wake it. Here, nothing is being waited for -- the
next action is available immediately and simply is not taken. The first is a wrong belief about
the harness; the second is a habit of treating narration as the deliverable.

Two guesses at the cause, both testable by whoever fixes it. The forms reward reporting: every
step ends by asking what happened, so an agent that has written a good account has satisfied the
thing most recently asked of it. And `status` renders the next step as text to read rather than
as an act to perform -- "open it: spine open ..." is a line of output, not an obligation the
engine tracks as outstanding against the conductor.

The cheap mitigation is a sentence in each conductor skill: an account of a step is not the step;
if the next command is already rendered and nothing blocks it, run it in the same turn you
report. The better fix is probably that a run should be able to tell a conductor it is idle when
nothing is outstanding except a dispatch the conductor could make right now.

## 25. Is this much review worth it? The run's own round-by-round evidence

Raised by the principal as something to look back on, not to act on now: would the first review
round alone have caught the top 80%? This run is unusually good evidence because every seam ran
to convergence rather than being cut short, so the later rounds' yield is observable rather
than hypothetical.

What each seam's rounds actually returned:

  SPEC (understand), 5 rounds
    r1  3 revise, 4 findings: 1 real (a commitment nothing verified), 1 useful (name the
        sites), 2 FALSE -- both from misreading the board's `recommend` as the ruling
    r2  1 revise: unnumbered obligations outside the numbered list. Formatting, real
    r3  2 revise: the boundary gap -- the spec never said no outcome table changes. REAL,
        and a planner could have cut out-of-scope work without it
    r4  1 revise: a pronoun with no antecedent
    r5  clean

  GATE 1 plan, 3 rounds
    r1  3 revise: TWO would-have-shipped-broken defects -- KeyError resuming into an
        anchor-only segment, and no antecedent submit so `current` stayed on the declined step
    r2  3 revise, all converging: the stopping rule checked `interior == "steps"`, which
        would have refused `up` from the exact segment the run itself was stuck in. ALSO
        would have shipped broken
    r3  2 non-gating factual corrections

  GATE 2 plan, 9 rounds
    r1-r2  real: stale prose sites, a proof naming files rather than coverage
    r4     real: `git diff --quiet` with a multi-path pathspec is satisfied by ONE path
    r7-r8  real but small: the 4th and 5th instances of one stale sentence
    The long tail here was one defect class -- prose asserting behaviour -- that four rounds
    chased by enriching a pattern and one closed by widening the domain

  GATE 3 plan, 2 rounds
    r1  2 revise: the naive lever minted two rounds, resumed a critic into the wrong form,
        and SILENTLY INVERTED a revise verdict into a pass. The most serious finding of the run
    r2  clean

  GATE 4 plan, 2 rounds
    r1  2 revise: 1 real (the proof passed whether the field was nested or DELETED), 1 false
    r2  clean

  GATE REVIEWS
    g1  both passed -- and the conductor found a weak assertion at adjudication that both
        had missed
    g2  r1 found the resume-path defect a third, conductor-chosen lens was dispatched to look for
    g3  mutation testing showed a plausible wrong-key variant passes 436 tests and is caught
        only by the two new ones

What the data suggests, offered as a hypothesis rather than a conclusion:

Severity is heavily front-loaded. Every finding that would have shipped genuinely broken
behaviour came from a first or second round. Nothing after round 3 at any seam changed what the
software does -- rounds 4+ produced stale sentences, unnumbered obligations, a missing pronoun.

But "first round only" would not have been safe, for two specific reasons in this run's own
record. Gate 1's r2 finding (the `interior == "steps"` stopping rule) was a ship-broken defect
found in round two by all three panelists at once. And two of round one's four spec findings
were FALSE -- so a single-round regime would have acted on bad findings with no second voice to
catch them, which is the failure mode the extra rounds actually guarded against.

The cheapest thing to test against this: does round two earn its place because it catches what
round one missed, or because it corrects what round one got wrong? This run shows both, and
they imply different fixes -- more parallel lenses in one round versus a verification pass over
round one's findings.

Also worth measuring before concluding: the cost was not evenly distributed. Gate 2's plan took
9 rounds for one defect class that a domain widening closed in one; gate 3's took 2 rounds for
the run's most serious defect. Round count tracked how well the artifact was scoped, not how
much value the review added.

## 26. The conductor repeated the run's own most-repeated lesson, twice, while holding the note

Note 19 ends: "when a sweep keeps missing instances, widen the domain before enriching the
pattern." Note 18 lists four rounds that each enriched a regex and were each overtaken. Both
were written by this conductor.

Then, at the closing gate, the same conductor found `engine/cli.py`'s docstring still reading
"the seven verbs" after this run's own g1 made it eight, and added it to the gate's scope --
naming one file, having run no sweep at all. A panelist found a second site
(`tests/test_nesting.py:6`). The conductor then swept for `seven verbs` and reported two sites
as the complete set. A second panelist found a third: `README.md:32` says `7 verbs`, in digits.

So the failure repeated at two levels in immediate succession: first no domain sweep, then a
sweep whose pattern was the phrasing rather than the claim. The correct instrument was one
character of regex -- `(seven|[0-9]+) verbs?` -- and it took two panelists and two rounds to
arrive at what the conductor's own written note prescribes.

Two things worth taking from it rather than just the embarrassment.

Knowing the rule is not having the instrument. The lesson was recorded, recent, and authored by
the agent that broke it; what was missing at the moment of acting was not knowledge but the
habit of reaching for a domain-wide check before scoping anything. A rule that lives in a notes
file is available to a reader who goes looking, which an agent mid-task is not.

And the disposition matters more than the fix. The right answer was NOT to expand the closing
gate to three sites -- a third enumeration under the same pressure that produced the first two.
It was to drop the item entirely and sweep it once, completely, in its own pass. A partial fix
would have left the tree asserting three different verb counts with one of them freshly
corrected, which reads as authoritative and is the worse failure: it implies the other two were
checked.
