# Derived is code

Two rules, one consequence.

**Anything derivable from what the engine already holds is computed by the
engine, not stated as a rule for an agent to apply.**

**An agent doing mechanical work is the system failing at its job.** The point
of a secretary is to offload; every derivation left to an agent is work we
built the engine to remove and then didn't.

## The failure this prevents

An artifact — a form, an assembly, a status line, a refusal — makes a claim
about what the engine does, and the engine doesn't do it. A dozen instances in
one day. Five mechanisms:

| kind | example |
|---|---|
| **declared and unwired** | `validates = "board"` in the assembly while `boards.py` had no importer; `minted-by` read by nothing; a panel's `form` key ignored, so a critic got the reviewer's form |
| **promised and absent** | `GATE_CLOSE.toml` said the summary carries "the final verdict"; no verdict existed in the data model |
| **asserted and untrue** | `status` said "The board is worked" while rows were open, and never named the board file |
| **offered and broken** | `waived:` offered on a board row that only takes `deferred:`; `submit it: spine <wid>`, missing the verb, so typing it re-rendered status |
| **outlived** | `gate-executor` in five artifacts, in a commit whose message said it was dropped |

## Why this architecture generates them

Layer 2's bet is that doctrine lives in forms rather than code. That puts the
claim about behaviour in a different file, in a different language, changed by
a different edit, from the behaviour. In ordinary code `if validates:
check_board()` **is** the claim. Here we separated the promise from the
performance, and this defect class is the bill.

It is worth paying — doctrine at the point of use is why a fresh agent can act
from `status` alone. But it is a bill, not a free lunch, and it comes due
every time an artifact says something an edit forgot to make true.

## Why an agent cannot defend itself

A stale comment in code is checked against the code by the next reader. **An
agent reading a form has only the form.** That is the whole design of the room
description: nothing about the engine is resident between steps. So when a form
says the engine validates the board, an agent correctly relies on it, and is
wrong with no means of noticing.

That is why this is the worst failure available here. It attacks the one
property the design cannot lose: that an artifact is true when it is read.

## The rule that shrinks the class

Most of these exist because something derivable was written down instead of
computed. So: **if the engine can compute it, the engine computes it and
renders it.** A form states what a field *is*; it never states a rule the agent
must apply to data the engine already has.

Two live examples of getting this wrong, both ours:

- `UNDERSTAND.toml` tells the agent *"a row is askable when nothing in `after`
  is open and nothing has mooted it"* — a rule the agent applies by hand on
  every pass. The engine holds every row and can say which are askable now,
  which are waiting and on what, and what the board's progress is.
- `boards.summary()` counted rows by status and type. A deletion audit found it
  had no caller and removed it. The right fix was to give it one: unwired
  derivation is a missing call site, not dead weight.

A tight line budget makes deletion look cheaper than wiring. It is not, when
the thing deleted is work an agent would otherwise do by hand. **Lines spent
removing mechanical work from agents are the best lines in this engine.**

## What catches the rest

The mechanical kinds — declared-and-unwired, outlived, promised-and-absent —
are greppable, and `tests/test_promises.py` greps them. The behavioural kinds —
asserted-and-untrue, offered-and-broken — are not: every one was found by
driving the system by hand and typing the commands it printed.

`test_promises` has twice been extended by a defect it could not see:
`gate-executor` (it checked keys; that was a value) and panel forms (it checked
the key name, and `form` *is* read, just elsewhere). Both blind spots were the
same shape — **checking the shape of artifacts rather than the meaning of their
values.**
