# Prose

Make each sentence carry one grounded point in the plainest words that fit — in anything you
write, whether a human reads it, another agent does, or a later session does. Clarity,
concision, and grounded meaning are the whole job. No checklist: the predictable procedure is
one pass over your own draft against the rules below before you return it.

## The rules

**Words carry meaning.**

1. Use the plainest word that carries the exact meaning.
2. Use one name for one thing, and keep it the same throughout (`standards/glossary.md` is the
   source of truth).
3. Prefer the verb to its noun form — *decide*, not *make a decision*.
4. Choose each word for what it means, not the register it signals. Every word should be one
   the reader could act on.

**Sentences point at one thing.**

5. Write in the active voice and name who acts.
6. Give each sentence one main idea; start a new sentence at the second claim.
7. State it positively — *runs only when X*, not *fails unless X*.
8. Make every sentence advance a fact, a claim, or a next step.
9. Say what a thing *is*, not what it is "responsible for."

**Claims are grounded.**

10. Ground each claim in the thing itself — the number, the log, the benchmark, the diff. Show
    it rather than assert it.
11. When it is your judgment, say so plainly instead of borrowing vague authority.
12. State your confidence once, then commit. When the evidence points one way, make the call —
    no false balance, no flattery.
13. A run's writing stands on itself and the codebase: what another issue, ticket, or
    conversation knows is restated here in full, or it is not known — a gate spec, a plan, a
    spec, a consolidated understanding. A commit sha is the exception, because it points into
    the codebase rather than out of it. A reader that finds a gap dispatches an excursion or
    works the repository; it is never left holding a pointer it cannot follow. The rule starts
    where a run consolidates its understanding —
    before that, an agent records whatever it needs, tracker references included, on its board
    and in `spine <work-id> note observation ...` entries, which fold to the run's notes and
    reach no later reader.

**Structure serves the reader.**

14. Open on the substance and lead with the point when the reader needs it fast; let the
    context follow.
15. Give the background that helps; cut what only repeats.

## Dials, not laws

These rules illuminate the point of a sentence; they do not build an austere language. Active
voice (rule 5) is the default, but the passive is right when the actor is unknown or beside
the point. Break any rule here sooner than write something stilted.

## One name for one thing

Rule 2 holds only if names stay fixed across artifacts, agents, and sessions, so it is backed
by `standards/glossary.md` rather than memory. Consult it before naming a concept; when a term
is missing, propose a canonical one through the key-terms field rather than coining a synonym.
