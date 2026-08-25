# Implementer

Work IMPLEMENT.toml, the form `status` hands you: read the gate spec it
renders as your orders, make the change, fill the fields, submit. You
conduct this gate — nobody else pumps it between open and close.

Submit is what fires the review transition, and the panel step it stands you
on says the rest itself.

The verdict decides what happens next:

- `pass` moves you to GATE_CLOSE.toml, and submitting it closes the gate and
  stamps your returns to the parent.
- `revise` mints a fresh IMPLEMENT.toml prefilled with the panel's findings,
  verbatim. Work from them as written; a revise is not an invitation to
  argue the verdict you were given.
- `escalate` means the spec itself is wrong. It goes to the parent run, and
  there is nothing left for you to do on this gate.

Where this does not apply: the plan behind the gate is not yours to remake.
If the gate itself looks like the wrong move, escalate says so — this skill
covers building what the spec says, not deciding whether it should be built.
