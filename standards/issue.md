# Issues and epics

An issue is three things: **the problem**, **observations with baselines**, and **what fixed
means**. Implementation steps in an issue are a defect — the plan belongs to the run that picks
the issue up. Breadcrumbs (a possible fix, open questions) are optional, marked as hypotheses,
and discardable by any later reader.

An issue is one verb, about fifteen obligations and two or three gates. Past that it is two
issues, and the split belongs to whoever writes the issue, not to the run that picks it up.

## Observations — the load-bearing half

For a defect, record what you saw, not what should be built. One block per occurrence; never
merge two occurrences into one summary.

- **What's wrong:** the undesirable behavior specific to this observation.
- **Expected:** what the behavior should have been — the other half of the discrepancy.
- **Conditions:** what enables the bad state, including which environment. Environment locates
  the observation; it is not optional color.
- **Type:** `measured` or `inferred` — and the *how* is mandatory for both. `measured` carries
  the command that produced the result; `inferred` carries what it was read off. A bare
  `inferred` with no source is the exact failure this field catches: a claim read off the code
  by eye, written as if measured, sends the next run at the wrong target.
- **Rev:** what state this was true of — a commit, a commit plus uncommitted worktree state, or
  a hash of an installed artifact. Finding a defect before committing is the normal case. If
  the baseline lives on a branch that will be squash-merged, pin it with a tag.

For an enhancement, replace observations with **desired** and **today instead** — an
enhancement with no current-behavior statement cannot be distinguished from something that
already works. Type and rev apply to the "today instead" claim.

## What fixed means

A checkable end state, not a vibe. Two agents reading it should not be able to disagree on
whether the issue is done.

## Re-measure before you plan

Every observation is a claim about a `rev`, and every issue is older than the code it
describes. A run's first move is to re-measure its own issue: run the command the observation
carries, against HEAD. Three outcomes, all of them legitimate ends for a run:

- **Still true** — plan the work, and the fresh number replaces the stale one.
- **No longer true** — close the issue with the re-measurement as its record.
- **True and inert** — the defect stands and nothing goes wrong because of it. Name the run
  that goes wrong without the fix; when nothing does, close it as inert.

The third is the one that costs. A defect that is real, cheap, and harmless is the easiest work
in a backlog to justify and the least worth doing: a change is paid for when it lands, and the
benefit was priced when it was filed.

## Breadcrumbs

A possible fix is evidence that *a* fix is feasible; it is never the fix, and following one
untested has converted a check that cannot pass into a check that cannot fail. Open questions
record what is unresolved and what would settle it — thinking out loud, not work items.

## Epic

An epic is what a `run-an-epic` run opens from, as an issue is what a `run-an-issue` run opens
from: one claim too large for a single run to hold, plus the evidence that the claim is true.

- **The claim** — one sentence naming a defect in the system rather than in a file. A defect
  statable against one file is an issue.
- **The evidence** — the measurements that establish the claim, each with its command and rev.
  Per-defect observations belong to the children.
- **What fixed means** — a checkable end state for the claim. An epic whose only completion
  condition is that its children are closed is a label.
- **Findings** — measured, recorded, and not yet work. A finding becomes work by being cut into
  a wave; it never becomes work by aging.

The epic-conductor cuts a wave from the findings, dispatches those issue runs, and adjudicates at the
wave transition before cutting the next. A finding enters a wave when it re-measures true and
someone can name the run that goes wrong without it. An epic may `stop` with findings unfiled.
