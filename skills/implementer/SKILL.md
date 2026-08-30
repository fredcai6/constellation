# Implementer

Work IMPLEMENT.toml, the form `status` hands you: read the gate spec it
renders as your orders, make the change, fill the fields, submit. You
conduct this gate — nobody else pumps it between open and close.

## Author the intent layer

Two things you write as you work feed the code map, and both are **comments**
— `ast` discards comments, so a docstring reaches neither.

An **anchor** mints a stable id for one definition: a comment line holding
nothing but a bracketed kebab slug — lowercase letters, digits and single
hyphens, nothing else on the line — directly above a `def`, a `class`, or a
module- or class-level assignment.

A **tag** carries the content: a comment line opening `Rationale:`,
`Rejected:` or `See:`, above those same definitions or above an assignment
inside one. Further comment lines continue it; a second keyword starts
another tag.

```python
# [retry-budget]
# Rationale: three attempts absorbs a transient blip.
# Rejected: unbounded retry -- a dead host hangs the caller forever.
def retry_budget():
```

The two are separate predicates. Tags alone extract and render, but only the
anchor reaches `map/ids.jsonl`, so a decision worth naming takes both.

Write them on the change you are making, while you make it — the reason is in
your head exactly once, and this is the moment. What earns a pair is what a
later reader would otherwise reconstruct from scratch: a threshold, a chosen
approach, an alternative you weighed and dropped.

A near-miss is silent. `# [Bad_Slug]`, a slug with trailing text, and a slug
above a function-local assignment each extract to nothing and report nothing,
at exit 0. `palette:map` is how you see what landed — your slug in
`map/ids.jsonl`.

## Submit, and the verdict

Submit is what fires the review transition, and the panel step it stands you
on says the rest itself.

The verdict decides what happens next:

- `pass` moves you to GATE_CLOSE.toml, and submitting it closes the gate and
  stamps your returns to the parent.
- `revise` mints a fresh IMPLEMENT.toml prefilled with the panel's findings,
  verbatim. Work from them as written; a revise is not an invitation to
  argue the verdict you were given. There is no third verdict word: a
  reviewer who thinks the spec itself is wrong writes that as a revise
  finding, same as any other.

After a third revise the engine stops offering a fourth round and asks you to
rule instead: close the gate on the diff as it stands, run another round, or
send it up, which closes the gate and returns your ruling to the run that
dispatched you.

Where this does not apply: the plan behind the gate is not yours to remake.
If the gate itself looks like the wrong move, that ruling's `up` says so —
this skill covers building what the spec says, not deciding whether it
should be built.
