# Issue

An issue is three things: **the problem**, **observations with baselines**, and **what fixed
means**. Implementation steps in an issue are a defect — the plan belongs to the run that picks
the issue up. Breadcrumbs (a possible fix, open questions) are optional, marked as hypotheses,
and discardable by any later reader.

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

## Breadcrumbs

A possible fix is evidence that *a* fix is feasible; it is never the fix, and following one
untested has converted a check that cannot pass into a check that cannot fail. Open questions
record what is unresolved and what would settle it — thinking out loud, not work items.
