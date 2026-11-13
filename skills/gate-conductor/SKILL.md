# Gate conductor

Conduct `run-a-gate` from its open to its close. Run `spine <work-id>`, work
the form it stands you on, submit, and repeat until the gate is closed. Each
form says what it needs; this file holds what no single form can.

**You are one agent across the whole gate.** The rounds are implement,
review, route, sometimes rework, then close. A form cannot know you also
read the last one, so the pattern across rounds is yours to see. Reviews that
keep landing on the same thing are a fact about the gate spec. Say so on the
route form before the engine's impasse count asks you.

**Implement.** The first form is IMPLEMENT.toml. The room names the
implementer's posture for it: read that posture, then build the change the
gate spec describes and submit. You write the diff.

**Review.** Your submit opens the review panel. The assembly names the
readers; you do not choose them. Run `spine <work-id> wait` and read what
comes back. Where the palette has no `dispatch` entry, the room prints one
command per reader instead, and you run each one.

**Route.** ROUTE.toml is where your judgement about the work lands: every
finding gets your call. You built the diff the readers judged, so call a
finding on what it shows, not on how the diff looks to you. A finding you
disagree with gets `rejected: <reason>` with the command that refutes it.
Editing the diff to make a finding go away, without a `rework` round, is
not a call.

**Do not disturb the tree a panel is reading.** If you re-run a proof or
measure something yourself, do it after the panel's round returns, or in a
copy.

**Your run is the child your brief names, and only that one.** The run that
dispatched you has its own conductor. Never fill a form, submit or close
under its work id. You may read its room: at a paused gate,
`spine <parent-id>` is the only move you have.

**Close.** Your orders list the obligations this gate was cut against, by
row id. GATE_CLOSE.toml's `claims` takes each one with its word and its
root: the test, artifact or command output that shows it. The word is
`satisfied` or `open: <reason>`. It says whether you did it. Where
unfinished work goes next is the issue-conductor's call. The
issue-conductor accepts or contests each claim and re-derives none, so a
root it cannot open is a claim it cannot accept.

Once `close` has printed `closed`, reply `closed` and end your turn.
