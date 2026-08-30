# Engine notes

Decisions made while building wave 2 that the spec does not state, kept here
because they are load-bearing and cheap to forget. Not doctrine — mechanics.

## A return completes a step

A child's `close` appends a `return` entry to the **parent's** journal. The
parent's fold treats a `return` for a step exactly as it treats a `submit`:
that step is done. Nothing polls, nothing collects, and no conductor reads a
child's journal to find out what happened. This is the whole nesting
mechanism, and it is why prefill-down/returns-up needed no machinery beyond
one entry kind.

## The mechanical half of a return is assembled, never typed

At close the engine builds the return summary from the journal itself: steps
completed, per-segment cycle counts, every check's command/exit/output, the
model tier the run was dispatched under, and one line per amend (segment,
reason, whether it touched an anchor). An agent can only add what the record
cannot carry. Trust-but-verify works because the verifiable half is
unfalsifiable by construction and the checks re-run.

## The skeleton is one step per segment transition

`open` mints exactly the transitions that have a form to fill. Interiors are
not minted — a worklist fills as work is discovered, a board is seeded as its
own entry. That is what "the skeleton is fixed, the interior is worked" means
in code: the fixed part is the only part that exists at open. A transition
declaring neither a form nor a panel mints no step at all -- run-a-gate's
`review`, whose step is minted later instead, by the `select` that names the
panel it carries.

## The board keeps its own instructions

Seeding a board copies the whole template and comments out its example row,
rather than keeping the header alone. The column notes are where the doctrine
lives — what `type` means, never self-answering a decision, how to carry
options to a principal — and a board is worked across many turns by agents
who may arrive fresh. Instructions live at the artifact.

## Imports and entry point

`engine/` is a package; modules import as `from engine import x`. The `spine`
script at the repo root puts the repo on `sys.path` and calls `cli.main`.
Install is a copy, so the installed tree keeps the same shape — if that ever
requires rewriting paths inside files, the shapes have diverged and the fix
is the layout, never an installer.

## Renaming a form while runs are open

A journal is append-only and its `step` entries name form paths, so a form's
path is part of the record of every run standing on it. Move or rename the
form and those runs cite something that is no longer there — including the
run doing the renaming, which is the usual way this is discovered.

The engine refuses rather than crashes: a step whose form is not in the tree
gets a refusal naming the form, with `amend close <step>` as the escape. That
keeps the run recoverable; it does not make the rename free.

The rule, in order of preference:

1. **Don't rename a form while a run stands on it.** Cheapest, and almost
   always available — a form's name is not usually load-bearing enough to be
   worth the churn mid-run.
2. **If a gate must rename one, it owns the migration**: land the new form and
   leave the old path in place for the life of the open runs, or close the
   affected steps by `amend` and remint them against the new form. Either way
   the gate's scope says which, because the gate is the only place that knows
   what is open.
3. **Never repoint a live run by editing its journal.** The journal is the
   record; a rewrite makes it a story about what should have happened.

`issue57.g4` renamed `REVIEW_ROUND.toml` to `ROUTE.toml` and stranded its own
run — `spine issue57.g4` died and the gate could not be routed or closed. The
refusal above is what that would meet today; rule 2 is what would have avoided
it.

## Open: how bundles reach a host's skill discovery

`install.py` copies one self-contained tree (default `~/.claude/constellation/`)
because every internal reference is repo-relative: a form cites
`skills/interrogator/forms/UNDERSTAND.toml`, and `run.py` resolves assemblies
under the install root. Preserving the shape 1:1 is what keeps install a copy.

But Claude Code discovers skills at `~/.claude/skills/<name>/SKILL.md`, which
is a *flat* layout — and flattening our tree to match would break every
skill-owned form reference. So the two shapes genuinely disagree, and the
disagreement is real rather than an implementation detail.

The three ways out, none chosen yet, all cutover decisions:

1. Install the tree, then place (or symlink) each `skills/<name>/` into
   `~/.claude/skills/` as well. Discovery sees the flat layout, the engine
   sees the tree, nothing is rewritten. Duplication is the cost.
2. Make a skill bundle genuinely self-contained — its forms live inside it and
   nothing cites across bundles. This is the "bundle-shaped" ruling taken
   literally, and it collides with the ownership rule that a form shared by two
   assemblies belongs to the assembly.
3. Teach `resolve_form` one install-root lookup. Cheapest in lines, but it is a
   path rewrite wearing a disguise, and the handoff named that reflex as the
   signal to re-read Layer 2.

Whichever wins, the test is the handoff's: repo shape and installed shape must
not diverge, because that divergence is what grew v1's installer to 3,219 lines.
