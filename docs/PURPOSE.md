# Purpose

**Status:** what Constellation is for. Rulings by Tommy, 2026-09-05. `standards/approach.md`
says how he builds in any repository and travels with the system; this page is about this one.
`docs/V2_DESIGN.md` says what the system is. Where a mechanism and this page disagree, ask
before building: one of them is wrong.

## What this is for

<!-- [purpose-keeps-the-why-attached] -->
**Constellation keeps the *why* attached to the work.**

Reasons go missing faster than code does, and an addition nobody can justify is also one
nobody can argue with, so the next agent builds beside it rather than through it. Three parts
carry that load:

<!-- [spec-gives-permission-to-stop] -->
- The spec gives an agent **permission to stop** — bounded tightly enough that *do as little
  as possible* is an instruction it can act on.
<!-- [critic-argues-from-a-position] -->
- A critic argues from a stated position, because a position is a why.
<!-- [delete-only-what-you-can-justify-or-refute] -->
- Cleanup depends on both. You can delete only what you can justify or refute.

It exists because models are trained to move fast and to add, and because their habits change
from release to release. This holds one engineering approach steady on top of a substrate that
does neither.

## Measure the machinery

Restraint holds where a number measures it, so prefer one that runs whether or not anyone
feels disciplined.

- **The cheapest model that can complete a step measures that step's complexity.** Run the
  light model and watch where it fails; that is where the form got clever.
- **A term enters `standards/glossary.md` once it has crossed to the human and he has used it
  back.** The file holds shared understanding, so its length tracks how much is genuinely
  shared.
- **A finding is done now, or dropped with its reason recorded where a later run finds it.**
  One that comes back three times has earned its way in.

These are the bar. None of them runs yet, and each is a filed issue.

## Good enough

<!-- [good-enough-is-only-decisions-left] -->
Constellation is good enough when Tommy takes an idea he cares about in **another repository**,
runs it through, and the only thing he does is make decisions. Three markers:

1. Integration tests cover the basic functions and pass on a light model.
<!-- [engine-changes-only-for-a-found-defect] -->
2. `engine/` changes only in answer to a defect a real run found.
3. It runs jobs for other repositories.

The second is the bar today rather than a future state. An engine is never finished, so the
exit is a baseline plus a queue opened deliberately.

The end state is a tool he picks up when he wants to and that otherwise runs without him, the
way his baseball stats site has run for years. Twenty of those, not one perfect one. Each
project reaches a state small enough, tested enough, and explained enough to walk away from,
and the parts he stopped caring about stay cheap to replace on the day he cares again.
