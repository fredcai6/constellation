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

## A gate's commit stages everything but the engine's own derived trees

`_commit_gate` and `_commit_open` stage the worktree with `.agent-work`,
`.worktrees`, `.code-map` and `map` excluded by pathspec, so the record and
the engine's own machinery never land in a commit regardless of whether the
host repository's own `.gitignore` says so.

## Imports and entry point

`engine/` is a package; modules import as `from engine import x`. The `spine`
script at the repo root puts the repo on `sys.path` and calls `cli.main`.
Install is a copy, so the installed tree keeps the same shape — if that ever
requires rewriting paths inside files, the shapes have diverged and the fix
is the layout, never an installer.

A form's `standards/...` citation is one such repo-relative path, and a
dispatched child works in whatever repository it was sent to, not this one
— so `render.brief` names the engine root (`render.engine_root`, `ROOT` in
`install.py`'s sense) on every dispatch, and a `standards/...` citation
resolves from that path rather than the child's own cwd.

## A worktree run has two copies of the engine, and a stated cut point

`spine` resolves its own engine from `__file__`, so `<top-level>/spine` loads
`<top-level>/engine/` and `<worktree>/spine` loads the worktree's own copy —
the moment an issue-tier run's worktree exists, an edit to the engine lands
in whichever tree an agent is standing in, and a command run from that tree
executes whichever copy it resolved from. A run is driven through the
top-level binary; that is correct, and the principal's own ruling that a run
does not convert itself mid-flight, holding by construction rather than by
discipline (#67).

A root run's worktree branch is cut from the remote's default branch, not
whatever the top-level checkout's current branch happens to be — resolved
fresh (`git ls-remote --symref origin HEAD`, then fetched) rather than
trusted from a possibly stale local ref, so the branch a fresh clone would
stand on is the branch the worktree is cut from. `--from <ref>` overrides
this outright, for a root run opened on purpose against work still in
flight on some other branch. With no remote default yet to ask for — a bare
remote before anything has been pushed to it — the cut point falls back to
the checkout's own `HEAD`. The run's own journal entry carries the cut
point as `from = "<ref>@<sha>"`, and the room's own header line for the run
says it, so an agent reads where its tree came from without going to look.

## A check runs in a process of its own, always

`submit` never runs a proof itself. It spawns `engine/checks.py` detached and
waits the **handback** (90 seconds) for it. Inside the window the caller reads
the runner's exit status and behaves exactly as the old foreground check did;
past it the caller journals `check-started` and returns, and the runner
appends the outcome when it has one.

One process holds the exit status, and that is the whole argument for the
guarantee a failing proof records no submit: the runner writes the `submit`
entry only on exit 0, and the caller — which never holds a result — has
nothing it could write. It also removes the interleaving question. Running
the proof in the caller and detaching it at the handback would put a result
in two processes at once, and choosing which of them journals would need an
atomic claim between them; one writer needs none.

`start_new_session=True` is insurance rather than the mechanism. #72 measured
a plain child outliving a dispatched agent's turn by 25 seconds and finishing
its work; what was lost was the caller, not the check. The session flag is
what survives a harness that kills the caller's whole process group, which
this one does not do and a stricter one would.

The runner is reached as `python -m engine.checks` with this tree's root on
`PYTHONPATH`, computed from `__file__` like every other root lookup here.
Install is a copy, so that resolves the same way in the repo and in an
installed tree, with no path rewritten.

An orphan — a `check-started` whose process is gone and whose result never
landed — is rendered as work to redo rather than a proof still in flight, and
`spine <wid> submit` runs it again. There is no reaper: nothing sweeps stale
entries, because nothing has to. A started entry records no submit, so an
abandoned one costs the record nothing, and the room tells the truth about it
from the pid alone. What that pid cannot tell apart is a recycled number: a
gone runner whose pid has been reused reads as alive and the re-run is
refused until it is not.

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

## Bundles reach a host's skill discovery through a flat symlink

`install.py` copies one self-contained tree (default `~/.claude/constellation/`)
because every internal reference is repo-relative: a form cites
`skills/interrogator/forms/UNDERSTAND.toml`, and `run.py` resolves assemblies
under the install root. Preserving the shape 1:1 is what keeps install a copy.

Claude Code discovers skills only at the flat `~/.claude/skills/<name>/
SKILL.md`, so after the copy, install places one symlink per bundle:
`~/.claude/skills/<name>` → `<install-root>/skills/<name>` (default
`--skills-dir`, alongside `--dest`). Discovery sees the flat layout, the
engine sees the tree, and nothing inside either is rewritten.

A symlink, not a second copy, carries each bundle across: a copy can drift
from the tree it was taken from the moment either side changes, where a link
cannot — it has no content of its own to fall out of step, only a path to the
one copy `install.py` already made. Re-running install is therefore always
safe: a link already pointing at the right target is left alone, one pointing
elsewhere is replaced, and a real directory found at that name is reported
and skipped rather than clobbered.

The test is the handoff's: repo shape and installed shape must not diverge,
because that divergence is what grew v1's installer to 3,219 lines — v1 is
deleted, so that figure is archival record, not a line count this tree
carries. A symlink keeps that test true by construction: the flat name is
never anything but a pointer to the one tree that exists.

## Rendering is a read; `wait` starts and restarts

Rendering a room is a read: `status`, and every internal call that walks a
room's text, moves nothing on disk and starts no process. `spine <work-id>
wait` is the one thing that starts a dispatch or panel step's child that has
never been dispatched at all, and the one thing that restarts a capped child
gone without returning, up to `checkrun.MAX_STARTS` attempts.

One asymmetry this run leaves on purpose: a board row's own excursion is
still opened by hand, by whoever reads the row and runs the `open` command
it prints, while a dispatch or panel step's child is not — that one starts
itself the moment `wait` is run against it.

The one added cost is a command a conductor now runs at every dispatch or
panel seam that did not need one before: `wait`, once per such seam, to see
the room move past whatever its child owes it, where the room used to start
that child on its own.

A child already dead and at its start cap will not be started again. The
ruling escape for that case has its own name now, the words the conductor
actually rules with: `drop it` — the conductor closes the step on what
stands, rather than holding out for a child nothing will start again.
