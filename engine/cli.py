"""`spine` -- the verbs `main()` dispatches.

Argument shape is deliberately flat: the work id comes first and is always
required, because an id inferred from the environment is how a dispatched
crew ends up driving its dispatcher's run. A bare `spine` prints the ledger,
never your run.
"""

import json
import math
import os
import pathlib
import re
import secrets
import shutil
import subprocess
import sys
import time
import tomllib

from engine import boards
from engine import checks as checkrun
from engine import drops as dropsmod
from engine import forms
from engine import journal
from engine import render
from engine import review_yield
from engine import run as runmod

USAGE = """spine <work-id>                     where you are
spine <work-id> submit              hand in the filled response form
spine <work-id> wait [--for N]      block while the current step's child is
    outstanding -- starting a never-dispatched one and restarting one gone
    without returning, capped -- then print status
spine <work-id> drive [--for N]     walk the run, pass after pass, through
    every step shape the engine can resolve on its own -- a gate dispatch or
    a panel (via `wait`'s own mechanism), a form step already in flight --
    stopping on an ask, a close form, a spent gate or panelist, a step
    before the plan segment, or its own bound running out
spine <work-id> up "<reason>"       pause: ask the parent for a decision this
    run cannot make itself
spine <work-id> note <kind> <text>  record an observation, block, or decision
spine <work-id> amend add --segment S --form F --reason "..."
spine <work-id> amend close <step-id> --reason "..."
spine <work-id> amend reorder <step-id> --before <step-id> --reason "..."
spine <work-id> amend proof <gate-id> --proof "<command>" --reason "<ruling>: ..."
    replace a gate's `proof`, the one close re-runs; cite the ruling
spine <work-id> amend waive <step-id> --reason "..."   waive the panelists
    still outstanding on a step; the step stands, its own form still yours
spine <work-id> close               terminal: legal once every step is done
spine open <assembly> --title T [--issue N] [--from <ref>]   an issue-tier
    open cuts its worktree's branch from the remote's default branch, fresh
    -- --from overrides the cut point, for a root run opened on purpose
    against work still in flight on some other branch
spine open <assembly> --parent <id> --step <step-id>   open a dispatched child
spine open <assembly> --parent <id> --row <row-id>     open an excursion from
    a board row -- the row is the brief, its return lands under the row, and
    it completes no step. Assemblies: find-prior-art, build-a-prototype,
    draw-a-picture
spine                               every open run
spine <work-id> trace               this run and its children, as one timeline
spine <work-id> trace --yield       ... plus the review yield: rounds per
    seam, findings per round, how each was called"""

GIT_TIMEOUT = 600  # a wedged git or gh reads through as a failed call, not a hang


def _check_id(wid):
    """A work id names a directory under .agent-work; anything that could
    climb out of it is refused rather than sanitized, because a sanitized id
    no longer addresses the run the caller asked for."""
    parts = str(wid).split(".")
    if (not wid or "/" in wid or "\\" in wid or pathlib.Path(wid).is_absolute()
            or any(p in ("", "..") for p in parts)):
        raise SystemExit(render.refusal("work id", f"{wid!r} is not a usable name -- "
                                        "letters, digits, and dots between parts"))
    return wid


# [named-search]
# Rationale: a subagent's cwd resets between bash calls (#67's second
#   finding), so a bare `spine <id> note ...` run from the wrong directory
#   used to read "no run named", which looks exactly like a typo'd id and
#   nothing like a lost note. Naming the roots the lookup actually walked
#   (`journal.searched_roots`) tells the two apart without widening the
#   search itself -- ruling 8 fixes the id as the address, never inferred
#   from cwd, and that holds in this direction too: the fix is a refusal
#   that says where it looked, not a wider look.
# Rejected: searching beyond the cwd's own roots (climbing to a parent
#   directory, say, or scanning `$HOME`). That is the inference ruling 8
#   refuses, aimed at a different word for the same reason -- an id found by
#   guessing the caller's real location is not addressed by the id any
#   more.
def _no_run(wid):
    """The refusal every verb raises when `runmod.state`/`journal.exists`
    finds no such work id: where the search looked, so a caller reads a
    wrong cwd off the message instead of guessing the id was misspelled --
    and a nonzero exit (`SystemExit`'s own, on a non-empty message), so a
    caller chained with `&&` stops rather than reading a run that never
    resolved."""
    raise SystemExit(render.located(
        f"no run named {wid}\n"
        f"  looked in: {journal.searched_roots()}\n"
        f"  run this from the checkout or the worktree that holds {wid}\n"
        f"  open runs: spine"))


def mint_id(issue=None, kind="issue"):
    """A tracker number when there is one -- it is already collision-free and
    it associates the run to the issue for free. Otherwise random: two
    worktrees allocating in parallel cannot see each other's next number.
    The kind is the assembly's last word -- issue, gate, idea."""
    if issue:
        return f"issue{issue}"
    while True:
        wid = f"{kind}{secrets.token_hex(2)}"
        # See: `cmd_open`'s write-guard rationale below -- the same on-disk
        #   question, not `journal.exists`'s in-scope one.
        if not journal.journal_path(wid).exists():
            return wid


def _palette(root=None):
    p = pathlib.Path(root or ".", "constellation.toml")
    return tomllib.load(open(p, "rb")) if p.exists() else {}


def _prose_words(path):
    """Words of prose in an artifact: fenced blocks, tables and indented code
    do not count.

    A plan that grows because its gates now carry their proofs inline has not
    accreted; a plan that grows because a settled alternative got re-argued
    has. Counting everything cannot tell those apart, and the count an agent
    is shown decides what it thinks it should cut."""
    try:
        text = pathlib.Path(path).read_text(encoding="utf-8")
    except OSError:
        return 0
    out, fenced = [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced or line.startswith(("    ", "\t")) or line.lstrip().startswith("|"):
            continue
        out.append(line)
    return len(" ".join(out).split())


def _check_artifact(wid, form, fields):
    """A `kind = "artifact"` field's value must be a path `_measure_artifacts`
    can read -- that is the contract the kind states, and `_prose_words`'s
    `except OSError: return 0` otherwise turns silently into nothing. Checked
    before anything is journaled, the same as `_check_vocabulary`: past that
    point the submit is durable, and a value the engine cannot read would
    advance the run with a silent zero where a measurement belongs, instead
    of failing where the mistake was actually made.

    A null answer is not refused: `waived:` and `unknown:` are legitimate
    non-answers on any field, and an `artifact` field carries no vocabulary
    of its own (`forms.enforced_vocabulary` only fires on `kind = "decision"`)
    to forbid them the way a decision field's does."""
    root = journal.root_for(wid)
    live = forms.without_nulls(fields)
    for f in form.get("fields", []):
        fid = f["id"]
        if f.get("kind") != "artifact" or fid not in fields:
            continue
        value = fields[fid]
        if not isinstance(value, str) or fid not in live:
            continue
        try:
            pathlib.Path(root / value).read_text(encoding="utf-8")
        except OSError:
            raise SystemExit(render.refusal(
                fid, f"{value!r} is not a readable path -- an artifact field's "
                "value is a file's location, not its content"))


# [per-step-name]
# Rationale: two files in a work location belong to a round rather than to a
#   run -- the response form the round is answered on, and the artifact the
#   round produces -- and both used to be named for the run alone, so every
#   round of a seam wrote over the one before it. #118 was that defect on the
#   form half. The artifact half never had an issue number because agents
#   worked around it by hand: issue80 and issue99 both have findings citing a
#   `spec-r2.md` a conductor invented, which leaves a stale `spec.md` beside
#   it and no convention saying which is current.
#   One rule, used by both, so a work location reads the same way whichever
#   file you are looking at and neither can drift from the other.
# Rejected: an incrementing suffix (`spec.2.md`). The step id is already the
#   round's own name, it is what the journal indexes by, and it makes the
#   copy answerable to a step rather than to a position in a sequence
#   nothing else counts.
def _per_step_name(path, step_id):
    """`<stem>.<step-id><suffix>` -- the one name a file a round owns takes.
    `SPEC.toml` at step `understand-a4d19` is `SPEC.understand-a4d19.toml`,
    and the `spec.md` that round wrote is `spec.understand-a4d19.md`."""
    path = pathlib.Path(path)
    return f"{path.stem}.{step_id}{path.suffix}"


# [archive-artifact]
# Rationale: an artifact field names a file the agent wrote, not one the
#   engine materialized -- `_check_artifact` only reads it and this function
#   only measures it -- so nothing kept the round's own copy and a rework
#   writing to the same path overwrote the spec it was reworking. The word
#   count journaled here says how the artifact moved and never what it said.
#   Taken at submit, beside the measurement, because that is the moment the
#   file stops being the round's working copy and becomes its answer.
# Rejected: asking the agent to name the file per round. That is the `-r2`
#   convention already invented twice, and it is a second thing to get right
#   in a form that has enough to say.
# Rejected: moving it rather than copying. The path the submitted field names
#   has to keep resolving -- a later reader follows the journaled value, and
#   the next round works from the file it points at.
def _archive_artifact(root, value, step_id):
    """Keep this round's copy of the artifact it produced, beside it and
    named for the round. A no-op for a path that is not there: a null answer
    (`waived:`) names no file, and an unreadable one has already been refused
    by `_check_artifact` before anything reached here."""
    src = root / value
    if not src.is_file():
        return
    shutil.copy2(src, src.with_name(_per_step_name(src, step_id)))


def _measure_artifacts(wid, step, form, fields):
    """Record each artifact field's prose length, so a later round can say how
    the artifact moved. Recorded, never enforced -- the engine has no opinion
    about the number and refuses nothing on it.

    A stored artifact path is already work-location-inclusive
    (`.agent-work/<work-id>/plan.md`), so it is read against the run's own
    tree -- `journal.root_for`, not `journal.location` -- or resolving it
    again would double the prefix and break every run, not only a worktree
    one."""
    root = journal.root_for(wid)
    live = forms.without_nulls(fields)
    for f in form.get("fields", []):
        if (f.get("kind") != "artifact" or not isinstance(fields.get(f["id"]), str)
                or f["id"] not in live):
            continue
        _archive_artifact(root, fields[f["id"]], step["id"])
        words = _prose_words(root / fields[f["id"]])
        if words:
            journal.append(wid, "measure", segment=step["segment"], step=step["id"],
                           field=f["id"], path=fields[f["id"]], words=words)

def _resolve_command(text, root=None):
    """`palette:test args` -> the host repo's test command plus args. A proof
    chaining several named jobs with `&&` (`palette:test && palette:map`)
    resolves each side on its own, so the second name is looked up rather
    than handed to the shell as a literal command it does not have.

    `root` is the run's own tree, not cwd -- a check both resolves and later
    runs there, so which command a `palette:` proof expands to stops
    depending on the shell the agent happens to be standing in.

    A shell line continuation (backslash, newline) is folded to one space
    before the split, which is what the shell itself does with it. Left in,
    `.strip()` on each `&&` piece removed the newline but kept the backslash,
    and the rejoin produced backslash-space: an escaped literal space glued
    onto the previous word, so a proof that exits 0 typed into a shell exited
    2 when the engine ran it (sports-market-manager issue156, 2026-09-23)."""
    folded = _CONTINUATION.sub(" ", text)
    return " && ".join(_resolve_one(part.strip(), root) for part in folded.split("&&"))


_CONTINUATION = re.compile(r"[ \t]*\\[ \t]*\r?\n[ \t]*")


def _resolve_one(text, root=None):
    if not text.startswith("palette:"):
        return text
    name, _, rest = text[len("palette:"):].partition(" ")
    commands = _palette(root).get("commands", {})
    cmd = commands.get(name)
    if not cmd:
        # Through `refusal` like every other one: raised bare, this named no
        # escape and no way forward, and `test_robustness`'s sweep of the
        # engine's refusals walked past it because it is not an entry point.
        raise SystemExit(render.refusal(
            "check", f"the command palette has no entry named {name!r}",
            escape=("entries: " + ", ".join(sorted(commands))) if commands else
                   "constellation.toml declares no [commands] at all"))
    return f"{cmd} {rest}".strip()


# [trial-proofs]
# Rationale: #122 -- a plan's `proof` reached a gate having been read by
#   three critics and run by nobody; issue116's read `constellation.toml's
#   `test` entry: ...`, died on its apostrophe at the gate's first submit,
#   after the whole diff was built, and no verb on either run could then
#   edit it. So the engine runs each `kind = "proof"` field once, where it is
#   written, through the same resolution the gate's own check will use
#   (`_resolve_command`, palette entries, the shell) against the run's tree
#   as it stands, and journals a `check` entry -- the kind the gate's own
#   runner writes, same shape: the command, its exit, the output tail --
#   which the conductor's route room reads (`render.proof_readings`) beside
#   the cut, from the child's own live journal (`[route-room-reads-the-
#   cut]` below) rather than a snapshot frozen at close time. Nothing here
#   refuses: exit 0 on an empty diff, a shell that cannot parse the string,
#   a palette name with no entry are each a reading the conductor rules on,
#   not a wall the planner meets. A palette miss is journaled as exit 127 --
#   the shell's own word for a command it cannot find, which is the same
#   fact one layer up -- with the refusal's text as the output.
# Rationale: #163 -- a string that never becomes a command is resolved and
#   journaled right here, synchronously, since there is no process worth
#   spawning for it; every field that does resolve is handed to
#   `checkrun.hand_in_trial` as one batch, detached at the cut exactly the
#   way `hand_in` detaches a gate's own checks (`[trial-detached]`,
#   engine/checks.py) -- the caller waits no longer than the handback, and a
#   proof that is right but slow keeps running after that wait gives up
#   rather than being killed and misread as a fourth, useless reading. Run
#   once, here: PLAN_TO_EXECUTE's own submit does not run it again, and the
#   gate's runner is what runs it to its full budget. A `budget` that is not
#   whole seconds is read as none -- the gate's own submit refuses that as
#   it always has; a trial refuses nothing.
def _trial_proofs(wid, step, form, fields, root):
    """Run every `proof`-kind field this submit carries, once, and journal
    each as a `check` entry on this step. Returns the entries this run's own
    journal now holds for it -- `[]` where the form declares no such field
    or every one of them is a status word rather than a command, and
    possibly short of every field where one outran the handback and is
    still running, detached, when this returns."""
    changed = _changed_since_cut(wid, root)
    resolved = []
    for f in form["fields"]:
        text = str(fields.get(f["id"], "") or "").strip()
        if f.get("kind") != "proof" or not text:
            continue
        if forms.leading_word(text) in ("waived", "unknown"):
            continue
        try:
            cmd = _resolve_command(text, root)
        except SystemExit as e:
            journal.append(wid, "check", step=step["id"], field=f["id"],
                           command=text, exit=127, output=str(e), trial=True,
                           changed=changed)
            continue
        resolved.append((f["id"], cmd))
    if resolved:
        try:
            budget = checkrun.budget_for(fields)
        except SystemExit:
            budget = checkrun.BUDGET
        checkrun.hand_in_trial(wid, step["id"], resolved, root, budget, changed)
    return list(runmod.state(wid)["proof_trials"])


# [trial-measures-its-tree]
# Rationale: #181 -- a trial's exit 0 was read as "passes on an empty diff"
#   wherever it ran, and a proof field is trialled at a gate's adjudication
#   and at a rework cut too, both against a tree already carrying work. The
#   reading asserted a fact nobody measured. So the trial measures it: the
#   paths the tree differs from its root run's cut point by, tracked or not,
#   the engine's own `.agent-work/` record aside. The reading then says what
#   was measured, and "proves nothing" belongs to a count of zero alone. The
#   cut point is read off the run's own opening entry: a child opens carrying
#   its parent's, since a dispatched child bound to its own id cannot read
#   the root journal it would otherwise come from.
def _changed_paths_since_cut(wid, root):
    """The paths the tree at `root` differs from its run's cut point by, or
    None where the run records no cut point or git cannot say -- the same
    read `_changed_since_cut` counts, kept here as the one place that reads
    the diff itself so a second caller wanting the paths (`[prior-drops]`)
    is a second reader of this, not a second `git diff`."""
    sha = (runmod.state(wid).get("from") or "").rpartition("@")[2]
    if not sha:
        return None
    tracked = _git(root, "diff", "--name-only", sha, "--")
    untracked = _git(root, "ls-files", "--others", "--exclude-standard")
    if tracked.returncode or untracked.returncode:
        return None
    paths = set(tracked.stdout.splitlines()) | set(untracked.stdout.splitlines())
    return {p for p in paths if p and not p.startswith(".agent-work/")}


def _changed_since_cut(wid, root):
    """How many paths the tree at `root` differs from its run's cut point by,
    or None where the run records no cut point or git cannot say."""
    changed = _changed_paths_since_cut(wid, root)
    return None if changed is None else len(changed)


def _tier(step, asm):
    """A dispatch step's model tier: its own prefill override, else the
    assembly segment's default."""
    seg = next((s for s in asm["segment"] if s["id"] == step["segment"]), {})
    return (step.get("prefill") or {}).get("model") or seg.get("model", "")


def _runner(tier):
    return _palette().get("models", {}).get(tier, "")


# [role-tier-conductor-is-structural]
# Rationale: the heavy-tier reservation is on the `conductor` indirection
#   itself, whatever it resolves to (`CONSOLIDATE.toml` round-3 key terms
#   binds this reading to the plan), and never on one spelled name --
#   checking the bare string before anything unwraps it holds for
#   `issue-conductor` and `gate-conductor` alike with no second table entry,
#   and for any future assembly's own conductor value with no change to this
#   function or its table. `standards/glossary.md`'s own `role` entry is why
#   a table keyed on resolved role names could not do this instead: a role
#   is by definition never the literal string `"conductor"`, so a table
#   keyed on role names could only ever hold this reservation for the one
#   name whoever built it happened to have in hand.
# Rejected: reading an assembly's own `conductor` field first and keying the
#   table on that. It would work for whichever assembly the caller passed in,
#   but this function takes no assembly and no step -- only the bare
#   `filler` string -- on purpose (see DIRECTION), so it never has that
#   field to read.
def _role_tier(filler):
    """A step's raw `filler` resolved to a model tier.

    `filler == "conductor"` -- the bare indirection itself -- is always
    `"heavy"`, checked before anything asks what any assembly's own
    `conductor` field would unwrap it to. Otherwise `filler` is looked up in
    `constellation.toml`'s own `[roles]` table; a `filler` that is neither
    is a refusal naming the missing role, never a spawn under an
    unspecified or default runner."""
    if filler == "conductor":
        return "heavy"
    roles = _palette().get("roles", {})
    tier = roles.get(filler)
    if not tier:
        raise SystemExit(render.refusal(
            "role", f"no role named {filler!r} in constellation.toml's [roles] table",
            escape=("entries: " + ", ".join(sorted(roles))) if roles else
                   "constellation.toml declares no [roles] at all"))
    return tier


# [dispatch-configured]
# Rationale: `o-single-dispatch-room` retires every reader of "is this
#   repository's palette configured" except one: `cmd_drive`'s own pre-loop
#   refusal (`o-drive-still-refuses-a-broken-tree`), which has to answer
#   that question before it starts spinning, not after a start already
#   failed. Every other caller this predicate used to feed -- the
#   dispatch/panel rooms, `cmd_submit`'s and `cmd_close`'s refusals -- now
#   renders or refuses the same way whether or not a `dispatch` entry
#   exists, so this predicate has exactly one reason left to be a named
#   function rather than inlined at its one remaining call site: a bare
#   `"dispatch" in _palette(tree).get("commands", {})` read twice would be
#   the drift this predicate exists to prevent, even at one caller.
def _dispatch_configured(tree):
    """Whether `tree`'s own `constellation.toml` names a `dispatch` entry.
    `cmd_drive`'s own pre-loop refusal is the only caller left."""
    return "dispatch" in _palette(tree).get("commands", {})


def _current_form(st):
    asm = runmod.load_assembly(st["assembly"])
    step = st["current"]
    # [panel-before-dispatch]
    # Rationale: design-it-twice's round-one panel (ruling 10, shelved #96)
    #   was the first step in the tree to carry both `dispatches` and
    #   `panel` -- checking `dispatches` first silently rendered it as a
    #   single-child brief, discoverable only once and then stuck, since a
    #   second open at the same untagged address refuses. The order stays
    #   correct for any future step that carries both, so it is left as is;
    #   `cmd_close`'s own pending-step guidance already checks panel first
    #   for the identical reason.
    if runmod.panel_outstanding(st, step):
        return asm, step, None  # rendered as N commands; the outcome is mechanical
    if runmod.paused(step):
        return asm, step, None  # a marker step: no form of its own to fall through to
    if step.get("dispatches"):
        return asm, step, None  # rendered as a command, not a form
    return asm, step, _load_form(asm, step["form"], st["id"], step["id"])


# [form-went-missing]
# Rationale: a journal is append-only and its `step` entries name form paths,
#   so renaming or moving a form strands every run already standing on it --
#   an ordinary, correct change, not a corrupt file, which is what separates
#   this from a torn journal. `forms.load` opening the path bare meant the
#   run could not be advanced, closed, or even looked at: `spine issue57.g4`
#   died with a FileNotFoundError after that gate renamed REVIEW_ROUND.toml.
#   The engine is a secretary; it refuses and names the way out.
# Rejected: falling back to a form of the same stem elsewhere in the tree. A
#   run would then quietly stand on a form nobody chose for it, which is the
#   contamination this file spends `_unique_id` and `_open_child`'s guard
#   avoiding, arriving by a helpful-looking route.
def _load_form(asm, ref, wid, step_id):
    path = runmod.resolve_form(asm, ref)
    if not path.exists():
        raise SystemExit(render.refusal(
            pathlib.Path(ref).name, f"this step's form is not in the tree -- {ref}",
            escape=f"restore it, or drop this step: spine {wid} amend close "
                   f"{step_id} --reason ..."))
    return forms.load(path)


# [response-path-by-step]
# Rationale: the live response path was named for the step's *form*
#   (`pathlib.Path(step["form"]).stem`), and `cmd_status` materialized one
#   only `if not dest.exists()`. Those two are right together only while a
#   form is filled once per run. At a seam they are not: round two opened
#   round one's *filled* form, and a conductor that edited the fields it
#   thought of carried the rest forward as this round's record (#118 -- six
#   occurrences on the issue96 run, twice landing a decision the round had
#   not made).
# Worse, two live processes could be handed the same path. `drive` spawns a
#   form-filler per step and never ends one; a filler that outlived its own
#   round would write the live form and submit, landing a stale ruling on
#   whatever step was current (measured once on the issue96 run, 34 minutes
#   after its round had closed).
# Naming by step makes both impossible by construction rather than by a
#   guard. Two fillers can never resolve to one file. A stale filler writes a
#   path nobody reads, and its `spine submit` resolves the current step's own
#   file -- blank, so it refuses in the words that already exist, or
#   correctly filled by the agent that owns it. It also gives a re-spawned
#   filler the right behaviour for free: a fresh step is a fresh path (new
#   work), while a filler restarted on the *same* step gets the same path and
#   picks up the in-progress form (adopting it). No flag, no option, no
#   declaration.
# Rejected: refusing a submit from a process whose step is no longer current
#   (via an env var stamped at spawn). It fixes the same defect with a new
#   refusal, and the engine defending its own checklist is what drove CLI
#   failure rates up before. Prefer mechanism over a guard.
# Rejected: archiving the file on submit (`1587ce5`). It clears the path
#   between rounds but leaves the two fillers sharing it, so it fixes the
#   record and not the collision.
def _response_path(st, step, *, root=None):
    """Where this step's own response form lands -- named for the step as
    well as the form by `_per_step_name`, the same rule the artifact copy
    beside it takes, so two rounds at one
    seam, or two seams sharing one form, never resolve to the same file.
    Resolved fresh against `journal.location(st["id"], root)` rather than
    any path frozen earlier, so a caller whose process starts somewhere else
    (`_form_filler_brief`, off the tree `_tree_info` names) still gets an
    absolute, correct path. `root=None` is `cmd_status`'s own case: resolve
    the same way it always has."""
    return journal.location(st["id"], root) / _per_step_name(
        step["form"], step["id"])


# [board-path]
# Rationale: mirrors `_response_path` exactly, for the same reason: a
#   board's own path is stored once, at `_mint` time, against whatever cwd
#   minted it (`engine/cli.py`'s two `journal.location(wid)` calls with no
#   `root` override) and never re-resolved -- correct for `cmd_status`,
#   whose caller is standing in that same tree, and wrong for a standalone
#   brief built for a filler whose process starts elsewhere. The stored
#   string is trusted only for its filename; the location itself is always
#   re-derived fresh.
def _board_path(wid, st, step, root=None):
    """This step's own board path, re-resolved against `root` (or, when
    `root` is `None`, `journal.location`'s own default -- the same reading
    `st["boards"][...]` already gives `cmd_status` today). `None` for a
    segment that carries no board at all."""
    stored = st["boards"].get(step["segment"])
    if not stored:
        return None
    return journal.location(wid, root) / pathlib.Path(stored).name


_WORKTREES_DIR = ".worktrees"  # sibling of the top-level checkout's tracked tree


def _git(cwd, *args):
    """One git call against an explicit directory -- never the process's own
    cwd, which a root open is about to move. Never raises: a missing git or
    a wedged process reads through the return code like any other git
    failure, so the caller has one shape to check rather than two."""
    try:
        return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              timeout=GIT_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as e:
        return subprocess.CompletedProcess(args, 1, "", str(e))


# [stage-exclude]
# Rationale: this repository's own ignore file keeps `.agent-work`,
#   `.worktrees`, `.code-map` and the rest of `map` out of *its* commits,
#   but a run's own commits land in whatever repository it opened against --
#   and that repository's own ignore file is not this engine's to depend on.
#   A host with no entry for `.agent-work` stages the whole record on every
#   commit `git add -A` alone makes (51 files of it, once, in the wild): the
#   rule in `docs/DERIVED_IS_CODE.md` is that nothing derived is ever
#   committed, so the engine holds the exclusion itself, as a pathspec,
#   rather than trust a file it does not own. One path under `map` is
#   carried anyway: `map/parents.jsonl` is authored, not derived -- the
#   exception `docs/AGENT_GUIDE.md` already records -- so a run that mints
#   an anchor and writes its own line there needs that line to reach the
#   commit rather than be held back by the same exclusion as its derived
#   siblings. A `git add -A` pathspec cannot re-include a literal path once
#   a broader exclude already covers it (tested: a directory-level
#   `:(exclude)` wins over a later, more specific include in the same
#   invocation), so the carry is a second, plain `add` naming that one file.
def _git_add_tracked(cwd):
    """Stage everything except the engine's own derived trees, with one
    carve-out. A commit made here never carries `.agent-work` (the run's
    record), `.worktrees` (nested issue-tier worktrees), `.code-map` or the
    rest of `map` (the code map), whether or not the repository being
    committed to ignores them itself -- except `map/parents.jsonl`, the
    map's authored portion, which is staged right after."""
    excludes = [f":(exclude){name}" for name in
                (".agent-work", ".worktrees", ".code-map", "map")]
    _git(cwd, "add", "-A", "--", ".", *excludes)
    _git(cwd, "add", "--", "map/parents.jsonl")


def _gh(cwd, *args):
    """One `gh` call against an explicit directory -- the same never-raises
    shape as `_git`, so `cmd_close` has one kind of failure to check for
    either. Intercepted on argv by the fast suite exactly where `_git` is
    not: a test that let this reach a real `gh` binary could open a real
    pull request against whatever `origin` happens to point at."""
    try:
        return subprocess.run(["gh", *args], cwd=str(cwd), capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              timeout=GIT_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as e:
        return subprocess.CompletedProcess(args, 1, "", str(e))


# [toplevel-checkout]
# Rationale: `--git-common-dir` always names the *main* checkout's `.git`,
#   even called from inside a linked worktree, because every worktree of one
#   repo shares it. That makes resolution safe to call again from inside a
#   worktree `open` itself just produced, without climbing back out first.
# Rejected: `--show-toplevel`. From inside a linked worktree it names the
#   worktree itself, so a second root run opened without leaving the first
#   would nest its worktree inside it instead of beside it.
def _toplevel_checkout(cwd):
    r = _git(cwd, "rev-parse", "--git-common-dir")
    if r.returncode != 0:
        return None
    return (pathlib.Path(cwd) / r.stdout.strip()).resolve().parent


# [cut-point]
# Rationale: a worktree cut from whatever branch the top-level checkout
#   happened to be on (#67) is cut from a commit that predates the run and
#   can never see work still in flight on some other local branch. The
#   remote's default branch is what a fresh clone would stand on, so it is
#   the one point every collaborator's next checkout actually agrees on --
#   fetched fresh (never trusted from a stale local `refs/remotes/origin/
#   HEAD`) so the sha it names is both current and one this checkout
#   actually holds the objects for, ready for `worktree add` to build on.
#   `--from` overrides it outright for the case #67 names: a root run
#   opened on purpose to exercise work still in flight on some other
#   branch, which is not a mistake for this to second-guess.
# Rejected: `refs/remotes/origin/HEAD` read locally with no fetch. It is
#   only ever written by `git clone` (or a deliberate `git remote set-head`)
#   -- absent here, and stale the moment the remote's own default branch
#   moves on -- so trusting it silently reintroduces the exact staleness
#   this exists to fix.
def _resolve_cut_point(top, from_ref):
    """What to cut the new worktree's branch from, as `(ref, sha)`: `--from`
    wins outright; otherwise the remote's default branch, fetched fresh;
    otherwise this checkout's own `HEAD`, when there is no remote default
    branch to ask for yet -- a bare remote before anything has been pushed
    to it."""
    if from_ref:
        r = _git(top, "rev-parse", "--verify", f"{from_ref}^{{commit}}")
        if r.returncode != 0:
            raise SystemExit(render.refusal(
                "from", f"{from_ref!r} does not resolve to a commit -- "
                f"{(r.stderr or r.stdout).strip()}",
                escape=f"pass a ref {top} already has -- a local branch, a "
                       f"tag, or a sha, fetched first if it is the remote's"))
        return from_ref, r.stdout.strip()
    symref = _git(top, "ls-remote", "--symref", "origin", "HEAD")
    branch = ""
    if symref.returncode == 0:
        for line in symref.stdout.splitlines():
            if line.startswith("ref:") and line.rstrip().endswith("HEAD"):
                branch = line.split()[1].removeprefix("refs/heads/")
                break
    if branch:
        fetched = _git(top, "fetch", "origin", branch)
        if fetched.returncode == 0:
            sha = _git(top, "rev-parse", "FETCH_HEAD")
            if sha.returncode == 0:
                return f"origin/{branch}", sha.stdout.strip()
    head = _git(top, "rev-parse", "HEAD")
    return "HEAD", head.stdout.strip()


# [push-before-journal]
# Rationale: the branch and worktree are made and pushed before anything is
#   journaled. A push failure then leaves nothing behind to clean up beyond
#   what this function undoes itself, so the caller's retry is the same
#   command again, not a cleanup followed by a command.
# Rejected: journaling the run first and pushing after -- a failed push
#   would then leave a run that `journal.exists` calls real, and `--id`
#   would have to be swapped for a retry instead of just repeated.
def _open_root_worktree(wid, assembly, title, from_ref=""):
    top = _toplevel_checkout(pathlib.Path.cwd())
    if top is None:
        raise SystemExit(render.refusal(
            "checkout", "not a git checkout",
            escape="open this from inside a git checkout of the project"))
    if not _git(top, "remote").stdout.strip():
        raise SystemExit(render.refusal(
            "remote", "the checkout has no remote",
            escape=f"add one: git -C {top} remote add origin <url>"))
    ref, sha = _resolve_cut_point(top, from_ref)
    worktree = top / _WORKTREES_DIR / wid
    made = _git(top, "worktree", "add", "-b", wid, str(worktree), sha)
    if made.returncode != 0:
        raise SystemExit(render.refusal(
            "branch", f"could not create {wid}'s worktree -- "
            f"{(made.stderr or made.stdout).strip()}"))
    # Run from `top`, not `worktree`: a relative remote URL (`origin
    # ../remote.git`) is resolved against the cwd `git push` runs in, and
    # it was set up relative to `top`, the checkout it was configured in --
    # not `worktree`, a directory `git worktree add` just created one level
    # deeper.
    pushed = _git(top, "push", "-u", "origin", wid)
    if pushed.returncode != 0:
        _git(top, "worktree", "remove", "--force", str(worktree))
        _git(top, "branch", "-D", wid)
        raise SystemExit(render.refusal(
            "push", f"push failed -- {(pushed.stderr or pushed.stdout).strip()}",
            escape=f"the branch and worktree just made are already removed -- "
                   f"retry: spine open {assembly} --id {wid} --title \"{title}\""))
    return worktree, f"{ref}@{sha[:8]}"


def _commit_open(wid, worktree):
    """The commit `open` makes once the run's own work area exists inside
    the worktree. `.agent-work` is excluded from what it stages, so the
    ordinary case stages nothing -- a journaled no-op, not a failure the
    agent has to explain."""
    _git_add_tracked(worktree)
    made = _git(worktree, "commit", "-m", f"open {wid}")
    if made.returncode != 0:
        journal.append(wid, "note", id=f"n{secrets.token_hex(2)}",
                       kind_detail="observation", about="commit",
                       text="open staged nothing to commit")


# [issue-tier-worktree]
# Rationale: `_mintable` already derives, from the assembly itself, every
#   name some segment declares as `dispatches` -- the run-an-issue shape,
#   the only one with gates to commit. Reusing it here means a new
#   issue-shaped assembly is in the issue tier the moment its plan segment
#   dispatches gates, with nothing to update beside this function.
# Rejected: a name list (`{"run-an-issue"}`) kept beside this check -- a new
#   issue-shaped assembly would silently sit outside git until someone
#   remembered to add its name here.
# See: ruling 8, docs/V2_DESIGN.md -- "git is the issue tier's, and the
#   engine's"; an idea or an excursion produces a spec, not a diff.
# `_DISPOSE_MINT` joined `_BOARD_MINT` as a second engine-named mint (#56):
# both sit in every assembly's `_mintable(asm)` whether or not that
# assembly's own forms use them, so both are subtracted here -- an
# assembly is issue tier on a real
# `dispatches` name, never on an engine literal alone. Adding a mint to
# `_mintable` without adding it here reads every assembly, run-a-gate
# included, as issue tier, which is git and a worktree where commitment 7
# says none belong; `tests/test_archive_close.py::
# test_a_non_issue_tier_close_never_reaches_git_or_gh` is what says so loudly.
def _issue_tier(asm):
    return bool(_mintable(asm) - {_BOARD_MINT, _DISPOSE_MINT})


def cmd_open(argv):
    if not argv or argv[0].startswith("--"):
        raise SystemExit("spine open <assembly> --title T [--issue N]\n  assemblies: "
                         + ", ".join(runmod.assemblies()))
    assembly = argv[0]
    parent = _opt(argv, "--parent")
    if parent:
        return _open_child(assembly, parent, _opt(argv, "--step"), _opt(argv, "--row"))
    title = _opt(argv, "--title") or ""
    issue = _opt(argv, "--issue")
    from_ref = _opt(argv, "--from") or ""
    wid = _check_id(_opt(argv, "--id") or mint_id(issue=issue, kind=assembly.rsplit("-", 1)[-1]))
    # [write-guard-is-not-scope]
    # Rationale: this guard asks "is this name already taken", never "can I
    #   resolve this id from here" -- `journal.exists`, since #112 gate 2,
    #   answers the second question, narrowed to a bound process's own
    #   subtree, and swapping it in here would hand a `--id` typed inside a
    #   bound process a name already taken by a run outside that subtree,
    #   its own parent included, the moment this line wrote through it.
    #   `journal_path(wid).exists()` reads no caller identity and no
    #   session -- the same plain on-disk check `exists` itself used before
    #   that gate -- so a bound caller gets the identical "already exists"
    #   refusal an unbound one always got, never a new, differently-worded
    #   one, keeping o3's no-predicate shape intact for the write side too.
    # Rejected: leaving `journal.exists` here and adding a second predicate
    #   to widen it back for a write guard. That is a second mode on the
    #   one function every resolver bottoms out on, which is exactly the
    #   shape #112 gate 2 exists to avoid needing anywhere.
    if journal.journal_path(wid).exists():
        raise SystemExit(render.located(f"{wid} already exists\n  where it stands: spine {wid}"))
    asm = runmod.load_assembly(assembly)
    on_issue_tier = _issue_tier(asm)
    landed = ""
    cut_point = ""
    if on_issue_tier:
        worktree, cut_point = _open_root_worktree(wid, assembly, title, from_ref)
        os.chdir(worktree)  # the work location this mints lands inside the worktree
        landed = (f"\n  now inside the worktree -- if this shell has not followed:\n"
                  f"  cd {worktree}\n")
    journal.append(wid, "run", title=title, assembly=assembly,
                   conductor=asm.get("conductor", ""), branch=wid,
                   worktree=str(pathlib.Path.cwd()), **{"from": cut_point})
    for step in runmod.skeleton(asm):
        journal.append(wid, "step", **step)
    if on_issue_tier:
        _commit_open(wid, pathlib.Path.cwd())
    print(f"opened {wid}\n{landed}")
    return cmd_status([wid])


_PANEL_TAG = re.compile(r"^(.+)\.(p\d+)$")  # "<step-id>.pN" addresses one panelist


# [round-artifact]
# Rationale: a panelist reads what the round it judges produced, and for
#   every panel declared on a transition that is the most recent other step
#   in the panel's own segment. Fields marked record-only stay behind: they
#   are the producer's account of a previous round, and a reviewer told what
#   was wrong last time is aimed at those spots and steered off everything
#   else -- a finding that was not really fixed gets found again, which is
#   the check working rather than a gap in it. Which fields are record-only
#   is the producing form's own answer, not the panel step's.
# Rejected: leaving this inline in `_open_child`. `_mint`'s panelists branch
#   needs the identical answer -- a panel minted into a segment away from the
#   work it judges (run-a-gate's `review`) has to carry the artifact across
#   at the mint, because by dispatch time its own segment holds nothing but
#   earlier review rounds -- and two walks over the same rows drift.
def _round_artifact(asm, st, seg_id, step_id):
    """What this segment's most recent other round produced, record-only
    fields stripped."""
    prior = [s for s in st["steps"] if s["segment"] == seg_id and s["id"] != step_id]
    if not prior:
        return {}
    last = prior[-1]
    form = (_load_form(asm, last["form"], st["id"], last["id"])
            if last.get("form") else {})
    private = {f["id"] for f in form.get("fields", []) if f.get("record-only")}
    return {k: v for k, v in st["done"].get(last["id"], {}).get("fields", {}).items()
            if k not in private}


# [open-obligations]
# Rationale: a gate claims the obligations it was cut against at its close
#   (GATE_CLOSE.toml's `claims`), by the execution-state board's own row ids
#   -- and those ids reached a gate only where the planner happened to write
#   them into `purpose` ("Obligations 18 and 19"), a courtesy rather than a
#   mechanism. So every child a board-holding run dispatches opens with the
#   rows still unsettled in its orders, id beside text, under `obligations`.
#   `boards.unsettled` decides which those are: a settled row is nobody's to
#   claim again, but a row a gate claimed `open:` must still be in the next
#   gate's orders, or the run structurally cannot end but nothing dispatched
#   ever knows to close it. The path is re-resolved against the parent's
#   root the way `_board_path` does, since the stored string is whatever cwd
#   minted it.
# Rejected: a gate spec item the planner fills with the ids. That is the row
#   id typed a second time, by the hand that reads the board least; the
#   board already holds it, and the secretary carries what is already written.
def _open_obligations(pst, proot):
    """`{"obligations": "o1 -- <text>; o2 -- <text>"}` for the rows still
    unsettled on the parent's execution-state board; `{}` where the run
    holds no such board or every row is settled."""
    stored = pst["boards"].get("execution-state", "")
    if not stored:
        return {}
    path = journal.location(pst["id"], proot) / pathlib.Path(stored).name
    if not path.exists():
        return {}
    rows = [r for r in boards.rows(path) if boards.unsettled(r)]
    if not rows:
        return {}
    return {"obligations": "; ".join(f"{r.get('id', '')} -- {r.get('obligation', '')}"
                                     for r in rows)}


# [landed-since-cut]
# Rationale: 2026-09-26 -- a re-cut after a gate lands was promised "what
#   has landed" as prefill and received none, so each planner went looking:
#   issue191's fifth planner read the third gate's PLAN.md, the route forms
#   and the fourth adjudication, and wrote its cut as an amendment to them
#   ("earlier plans' facts still hold and are not repeated"). What has
#   landed is a fact the tree and the board already hold -- the commits
#   past the run's cut point, each gate's own subject, and the rows its
#   adjudications settled -- so the engine hands it over the way
#   `_open_obligations` hands over what is still open, and each cut is
#   written from the spec and the state as they stand.
# Rejected: carrying the previous cut's plan or horizon forward. That is
#   the amendment chain itself; the gate ahead answers to the code and
#   spec now, not to what an earlier cut expected them to be.
def _landed(pst, proot):
    """`{"landed": ...}`: the commits the run's tree holds past its cut
    point, oldest first, then the execution-state rows already settled with
    their word; `{}` where nothing has landed yet or git cannot say."""
    sha = (pst.get("from") or "").rpartition("@")[2]
    lines = []
    if sha:
        log = _git(proot, "log", "--reverse", "--format=%h %s", f"{sha}..HEAD")
        if log.returncode == 0:
            lines = [ln for ln in log.stdout.splitlines() if ln.strip()]
    stored = pst["boards"].get("execution-state", "")
    path = journal.location(pst["id"], proot) / pathlib.Path(stored).name if stored else None
    if path and path.exists():
        lines += [f"{r.get('id', '')} -- {r.get('status', '')}"
                  for r in boards.rows(path) if not boards.unsettled(r)]
    return {"landed": "\n".join(lines)} if lines else {}


def _open_child(assembly, parent, pstep_id, row_id=""):
    """A child is dispatched, never composed: its id, its orders, and the
    tier it runs under all come from the parent's step. A panelist is the
    same mechanism one entry finer -- `<step-id>.pN` names which panel
    entry, and the tag rides the work id so several children can share one
    parent step without colliding. An excursion is the same mechanism from
    a board row: the row is its brief, and its return lands under the row
    rather than completing any step.

    The row_id branch (an excursion) stays here, unsplit: `_spawn_outstanding`
    never opens a board row, so `_mint_child` -- the silent core below,
    which `_spawn_outstanding` calls directly -- carries only the
    dispatch/panelist half. This wrapper mints through that core, then
    keeps the two lines only a caller reading its own stdout needs: the
    "opened ..." announcement and the room `cmd_status` renders for it.
    """
    if row_id:
        pst = runmod.state(parent)
        if pst is None:
            _no_run(parent)
        proot = journal.root_for(parent)
        return _open_excursion(assembly, parent, pst, row_id, proot)
    wid = _mint_child(assembly, parent, pstep_id)
    print(f"opened {wid} -- dispatched by {parent} at {pstep_id}\n")
    return cmd_status([wid])


# [child-cannot-act-on-its-parent]
# Rationale: the run this anchor names (spec.md's Chain of purpose) is that
#   a dispatched child is never left holding its own `open` -- the engine
#   has already computed it and can run it itself. This is the mechanism
#   that makes that true: the whole of `_open_child`'s old body, minus its
#   trailing print and `cmd_status` tail, pulled out so `_spawn_outstanding`
#   can mint an engine-spawned child's run directly, before that child's
#   process ever starts, without also inheriting the wrapper's stdout.
def _mint_child(assembly, parent, pstep_id):
    """The silent minting core: mints `parent`'s next dispatch-step child or
    panelist -- its `run`, `prefill`, and `step` journal entries -- and
    returns the bare minted work id. Prints nothing; `_open_child`'s wrapper
    calls this for its own non-excursion branch and keeps its own "opened
    ..." print and `cmd_status` tail, while `_spawn_outstanding` calls this
    directly so the run it is about to work already exists by the time that
    child's process ever starts.

    A child's work location nests inside its parent's actual location, never
    cwd -- the two never agree unless the caller happened to be standing in
    the parent's own worktree, and a child minted elsewhere would strand
    itself outside the tree the archive move (g4) physically walks. The
    child does not exist in either root yet, so two-root resolution cannot
    find it either; `proot`, read off the parent (which does exist), is
    handed to the child's first journal entry instead.
    """
    pst = runmod.state(parent)
    if pst is None:
        _no_run(parent)
    proot = journal.root_for(parent)
    m = _PANEL_TAG.match(pstep_id or "")
    step_id, tag = (m.group(1), m.group(2)) if m else (pstep_id, "")
    n = int(tag[1:]) if tag else 0
    pstep = next((s for s in pst["steps"] if s["id"] == step_id), None)
    if pstep is None or not (pstep.get("dispatches") or
                             (tag and pstep.get("panel") and 1 <= n <= len(pstep["panel"]))):
        raise SystemExit(render.refusal(
            pstep_id or "step", "not a dispatch step or a panelist",
            escape="steps here: " + ", ".join(s["id"] for s in pst["steps"])))
    wid = _check_id(pstep.get("child") or f"{parent}.{pstep_id}")
    if journal.exists(wid):
        raise SystemExit(render.located(f"{wid} already exists\n  where it stands: spine {wid}"))
    pasm = runmod.load_assembly(pst["assembly"])
    if tag:
        panelist = pstep["panel"][n - 1]
        assembly = "give-a-verdict"
        seg = next((s for s in pasm["segment"] if s["id"] == pstep["segment"]), {})
        tier = panelist.get("model") or seg.get("model", "")
        # A panelist gets the artifact and its criteria. The artifact is the
        # segment's own most recent other round -- the latest implement,
        # cycles included -- and the panel step's own prefill rides on top
        # where its mint carried one (a `rework-panel` round's blocking
        # findings: the orders its reader checks the artifact against).
        # It reads the same state the planner cut from -- what is still
        # open and what has landed -- since "the right next chunk" is a
        # question about both.
        prefill = {**(pst.get("prefill") or {}),
                   **_open_obligations(pst, proot), **_landed(pst, proot),
                   **_round_artifact(pasm, pst, pstep["segment"], step_id),
                   **(pstep.get("prefill") or {}),
                   "criteria": panelist.get("criteria", "")}
        title = f"verdict: {step_id}"
    else:
        tier = _tier(pstep, pasm)
        # The run's own prefill (`carries`, e.g. consolidate's spec) is what
        # every later dispatch was promised -- ASSEMBLY.toml says so in
        # place. Before this a non-panelist child saw only its own step's
        # prefill, so a first-round dispatch minted with none (the plan
        # segment's `plan-1`, which carries nothing of its own) opened blind
        # to the spec it exists to plan from. The step's own keys still win
        # on collision, so a gate child's spec -- which duplicates nothing
        # the run-level prefill holds -- is unaffected.
        prefill = {**(pst.get("prefill") or {}), **(pstep.get("prefill") or {}),
                   **_open_obligations(pst, proot), **_landed(pst, proot)}
        title = prefill.get("purpose", pstep_id)
    asm = runmod.load_assembly(assembly)
    journal.append(wid, "run", title=title, assembly=assembly,
                   conductor=asm.get("conductor", ""), parent=parent,
                   parent_step=step_id, model=tier, root=proot,
                   branch=pst.get("branch", ""), **{"from": pst.get("from", "")})
    journal.append(wid, "prefill", fields=prefill)
    for step in runmod.skeleton(asm):
        # A panel names the form its panelist fills -- a critic reads a plan
        # with the critic's form, not the reviewer's. Without this the panel's
        # own `form` key is declared and unread.
        if tag and panelist.get("form"):
            step = {**step, "form": panelist["form"]}
        # A panelist's role is its own `worker` -- a critic is told it is a
        # critic by the room it stands in, not just by its brief. Without
        # this the dispatched child's step keeps give-a-verdict's literal
        # `reviewer` filler no matter which worker the panel entry names.
        if tag and panelist.get("worker"):
            step = {**step, "filler": panelist["worker"]}
        # A rework round's dispatch step carries a form override the same
        # way a panelist's entry does -- `_mint_segment_round` sets it to the
        # segment's rework-form so this child fills REWORK.toml instead of
        # the step-form its assembly declares by default.
        if not tag and pstep.get("form"):
            step = {**step, "form": pstep["form"]}
        journal.append(wid, "step", **step)
    return wid


# [excursion]
# Rationale: the row is the brief. Its string columns -- the idea or
#   question, the excursion's named question and budget -- are the child's
#   prefill, so nothing is typed twice and the board stays the record of
#   what was asked. The return is journaled with the row, never as the
#   step's: an excursion answers a row, and a row completes nothing.
# Rejected: the engine writing the return into the board. Two writers on one
#   file is the hazard a board avoids; the return renders, the agent folds.
def _open_excursion(assembly, parent, pst, row_id, proot):
    seg_id, row, col = next(((sid, r, boards.column(p)) for sid, p in pst["boards"].items()
                             for r in boards.rows(p) if r.get("id") == row_id), ("", None, ""))
    if row is None:
        raise SystemExit(render.refusal(row_id, "no board row by that id",
                                        escape=f"the board: spine {parent}"))
    wid = _check_id(f"{parent}.{row_id}")
    while journal.exists(wid):  # a second variant off the same row
        wid = _check_id(f"{parent}.{row_id}-a{secrets.token_hex(2)}")
    pasm = runmod.load_assembly(pst["assembly"])
    seg = next((s for s in pasm["segment"] if s["id"] == seg_id), {})
    prefill = {k: v for k, v in row.items()
               if k not in ("id", "status") and isinstance(v, str) and v.strip()}
    asm = runmod.load_assembly(assembly)
    journal.append(wid, "run", title=boards.label(row, col)[:72], assembly=assembly,
                   conductor=asm.get("conductor", ""), parent=parent,
                   parent_step=seg_id, row=row_id, model=seg.get("model", ""),
                   root=proot, **{"from": pst.get("from", "")})
    journal.append(wid, "prefill", fields=prefill)
    for step in runmod.skeleton(asm):
        journal.append(wid, "step", **step)
    print(f"opened {wid} -- an excursion from {parent}, row {row_id}\n")
    return cmd_status([wid])


def _finishing(asm, form_override=""):
    """What finishing a dispatched assembly means: the form its terminal
    step fills -- the last thing the child does before `close` stamps its
    return back to the step that dispatched it.

    A panel entry may name its own form, and `_open_child` honours it, so a
    brief that quoted the assembly's default would name a file the agent
    will not be given -- the brief lying about the step it just opened.
    """
    if form_override:
        return form_override
    seg = next((s for s in asm["segment"] if s.get("transition", {}).get("terminal")), None)
    return (seg.get("transition", {}).get("form", "")) if seg else ""


# [tree-info]
# Rationale: a dispatched child inherits its parent's tree (ruling 8), so the
#   worktree to name is simply where this run's own journal physically
#   lives -- `journal.root_for`, correct at any nesting depth without
#   climbing, since a gate or panelist nests inside its issue's own.
#   `_mint_child` now stamps `branch` on every dispatch/panel child's own
#   "run" entry, read off its parent's already-resolved state at mint
#   time -- knowable there without crossing any run's own boundary, which
#   is what lets a bound process's own review-panel or nested-gate render
#   (issue112 g2) name a branch without climbing across the boundary that
#   binding puts around it. This climb stays as the fallback for what that
#   stamp does not cover: a run minted before this change, or one opened
#   through a path that is not `_mint_child` (an excursion's own "run"
#   entry, `_open_excursion`, carries no `branch` either).
# Rejected: rewriting this climb away now that most runs carry the field
#   directly. A legacy run's own entry never gains `branch` retroactively,
#   so the climb is still the only way to answer for one -- deleting it
#   would blank that answer immediately rather than let it narrow over
#   time as older runs close.
def _tree_info(wid, st):
    """Where a dispatched child actually lands: this run's own worktree, and
    the branch stamped on the nearest issue-tier ancestor -- climbed to
    because only a root run's own opening entry carries one."""
    worktree = str(journal.root_for(wid).resolve())
    branch, seen, parent = st.get("branch", ""), {wid}, st.get("parent", "")
    while not branch and parent and parent not in seen:
        seen.add(parent)
        pst = runmod.state(parent) or {}
        branch, parent = pst.get("branch", ""), pst.get("parent", "")
    return worktree, branch


# [already-dispatched]
# Rationale: "already spawned" (commitment 19) is read the same way
#   `checks.hand_in`'s own in-flight check reads "a proof is already
#   running" -- a scan of the run's own journal for the entry that a spawn
#   attempt writes, keyed to the one field a caller can already tell apart
#   panelists by (`child`), not a second piece of state invented to track
#   what the journal already records. Keyed to the record itself, not just
#   membership, because commitment 12's per-child status needs that same
#   record's own `pid` to read against `checkrun.alive`. One scan per
#   rendering (the panel loop calls this once, before its per-panelist
#   loop, rather than once per child) since nothing a render does can move
#   a record that only a completed spawn appends -- and after this gate no
#   render ever folds a freshly-spawned record into this dict at all,
#   because no render spawns anything any more (`_dispatch_child` is a pure
#   read; `cmd_wait`'s own pre-loop spawn is the only caller left that
#   starts a child). Whatever that pre-loop needs from a single scan across
#   its own per-child loop is `cmd_wait`'s own call, not restated here.
#   `_dispatch_start_counts` sits directly beside this function, over the
#   same journal entries, answering a related but distinct question -- a
#   count, not a "latest record" mapping.
def _dispatch_records(wid):
    """Every child id that already carries a `dispatch-started` record on
    `wid`'s own journal, mapped to that record -- rendering this room again
    must not spawn a second process for any of them, and each one's own
    `pid` is what tells "working" from "gone without returning" apart."""
    return {e.get("child"): e for e in journal.read(wid) if e.get("kind") == "dispatch-started"}


# [dispatch-start-counts]
# Rationale: how many times a child has ever started (first start plus any
#   restarts) is a different fact from `_dispatch_records`'s "latest
#   record" -- `_startable`'s cap needs a total, not the most recent pid --
#   so it is its own map, shaped and computed the same way
#   (`{child_id: count}`, one pass over `journal.read(wid)`), not folded
#   into `_dispatch_records` itself. Threaded through as a parameter to
#   every function that reads it, exactly as `_dispatch_records` already
#   is, so a caller that needs both facts scans the journal for each of
#   them once, not once per downstream function.
# [starts-count-since-the-last-answer]
# Rationale: #180 -- the cap stops a child that keeps dying with nothing new
#   to go on, and it counted every start the child ever had. issue156.g1
#   spent two starts on an engine defect and one on a session limit, and
#   once its ask was answered with the fix no verb could start it again: the
#   cap read three deaths that had already been explained as three reasons
#   not to try. An answered ask that resumes a child is the new input the
#   cap is waiting for, so a child's count starts over at that submit.
def _dispatch_start_counts(wid):
    """`{child_id: count}` -- how many `dispatch-started` records `wid`'s
    own journal carries for each child since the last answer that resumed
    it; `_startable`'s own cap reads this, not `_dispatch_records`."""
    counts, resumes = {}, {}
    for e in journal.read(wid):
        kind = e.get("kind")
        if kind == "dispatch-started":
            counts[e.get("child")] = counts.get(e.get("child"), 0) + 1
        elif kind == "step" and e.get("resumes"):
            resumes[e["id"]] = e["resumes"]
        elif kind == "submit" and e.get("step") in resumes:
            counts.pop(resumes[e["step"]], None)
    return counts


# [form-filler-records]
# Rationale: a form-step filler is addressed by the step it fills, never a
#   child id -- there is no child, only a process reading and writing the
#   same run's own response form -- so `form-filler-started` (`step`, `pid`,
#   `log`) is keyed by `step` the way `_dispatch_records` keys its own
#   record by `child`. Nothing appends this kind of entry yet (gate 4's
#   horizon): this is the read half of commitment 7's contract, proven on
#   its own before any real spawn writes one.
def _form_filler_records(wid):
    """Every step id that already carries a `form-filler-started` record on
    `wid`'s own journal, mapped to that record -- the same "latest record"
    shape `_dispatch_records` gives per child, keyed by step instead."""
    return {e.get("step"): e for e in journal.read(wid) if e.get("kind") == "form-filler-started"}


# [gate-route]
# Rationale: the one room that disposes of a review over a diff -- where
#   rejected calls from earlier runs touching the same files are worth
#   showing (`[prior-drops]`). It is run-a-gate's `work` transition: a
#   two-voices step with a form and a panel, in an assembly below the issue
#   tier, whose consolidate and plan-to-execute rooms read a spec or a cut,
#   never a diff. An impasse's `advance` stands the same form with no panel
#   on the step, so the transition's declaration is what is read.
def _gate_route(asm, seg, step):
    t = seg.get("transition", {})
    return (bool(step.get("form")) and step.get("form") == t.get("form")
            and bool(t.get("panel")) and not _issue_tier(asm))


def _filled_step(wid):
    """The step of `wid` this process was spawned to fill, or `None` when it
    is not a form filler on this run."""
    run, _, step_id = os.environ.get(checkrun.FILLS_ENV, "").rpartition(":")
    return step_id if run == wid and step_id else None


def _filling(wid, step_id):
    """Is this process the form filler spawned for `step_id` itself?"""
    return _filled_step(wid) == step_id


def _filler_alive(wid, step_id):
    """Is `step_id`'s own latest form filler a live process right now?"""
    record = _form_filler_records(wid).get(step_id)
    return record is not None and checkrun.alive(record.get("pid"))


def _form_filler_start_counts(wid):
    """`{step_id: count}` -- how many `form-filler-started` records `wid`'s
    own journal carries for each step that has ever had a filler started at
    all; the same total shape `_dispatch_start_counts` gives per child."""
    counts = {}
    for e in journal.read(wid):
        if e.get("kind") == "form-filler-started":
            counts[e.get("step")] = counts.get(e.get("step"), 0) + 1
    return counts


# [startable]
# Rationale: `IMPASSE.toml`'s own ruling on this gate's third round names
#   the shape every prior round's gap shared -- "a guard whose halves live
#   in two places, written as though it lived in one" -- and binds the
#   fourth round: a fourth instance of a clause missing from one copy of a
#   distributed guard means the cut, not the plan, is the defect. So the
#   whole rule -- never once returned; and, among the rest, either never
#   dispatched at all or dead and not yet spent -- is stated once, here,
#   and every site that asks "may this child still be started" reads this
#   function rather than carrying its own copy of some of its clauses.
#   Exactly three call sites read it, and an editor growing this rule owes
#   a re-read to all three: `_spawn_outstanding`'s own guard (the write
#   path), `_outstanding_state`'s own `name_wait` test (the read path),
#   and `_dispatch_child`'s own "gone without returning" branch
#   (the render path, where three of the four clauses are already decided
#   by the branches standing above it and the call is made anyway,
#   precisely so that branch cannot drift out of sync if `_startable` ever
#   grows a clause). Update two of the three and leave the third behind
#   and the guard's halves live in two places again, written as though
#   they lived in one -- in the very function cut to end that.
#   `_wait_spawn` carries no fragment of this rule at all -- it offers
#   every descriptor to `_spawn_outstanding` unconditionally, which is
#   what makes "one predicate, three callers" true rather than "one
#   predicate plus one more hand-copied filter that happens to agree with
#   it today."
def _startable(is_returned, record, count):
    """May this child still be started (a fresh start or a restart)? Never
    once `is_returned`; otherwise `True` when `record` is `None` (never
    dispatched at all), or when its pid is dead and `count` has not yet
    reached `checkrun.MAX_STARTS`."""
    if is_returned:
        return False
    if record is None:
        return True
    return not checkrun.alive(record.get("pid")) and count < checkrun.MAX_STARTS


# [spawn-once-per-render]
# Rationale: the record-check/call/catch/log sequence is identical for a
#   dispatch step's one child and a panel step's each outstanding
#   panelist -- only which child id drives it differs -- so it is factored
#   out here as its own function rather than inlined into `_wait_spawn`'s
#   own loop body, which calls it once per descriptor regardless of
#   whether that descriptor came from a dispatch step or a panel step.
#   A `DispatchFailure` is caught, not let escape:
#   rendering a room is a read, and a harness that fails to start is a
#   fact about that child, not a reason to crash the render for every
#   other child (or child-less caller) standing in the same room.
#   `spawn_dispatch` itself never writes anything to `log` on that path --
#   the process never started, so nothing of its own reached the file --
#   so the failure's reason is the one thing worth appending there, since
#   the log is where commitment 18 says a person already looks for this
#   child's story.
# Rejected: journaling the failure too. `spawn_dispatch`'s own contract
#   already draws this line -- no journal entry for anything short of a
#   running, journaled process -- and a failure record here would need its
#   own "already tried, don't retry" reading nowhere else asks for; a
#   repository whose entry is simply broken keeps failing, and keeps
#   logging why, on every `wait` call until someone fixes the entry.
# [mint-follows-start]
# Rationale: `o-mint-follows-start` -- whether this child can be started at
#   all is decided once, by attempting the start itself through
#   `checkrun.spawn_dispatch`, which now raises for every one of the four
#   ways that attempt can fail (no `dispatch` entry, a malformed one, an
#   unfilled placeholder, or the process failing to start) rather than
#   letting only the first of them be screened in advance. `_mint_child`
#   moves to after that call succeeds -- never ahead of it, and never for a
#   child whose start just failed -- so a tree that cannot actually run what
#   it would mint leaves no run/prefill/step behind for a start that never
#   happened. `journal.exists(child_id)` still guards the mint itself, the
#   same restart guard as before: a child whose harness died after minting
#   successfully once does not mint a second time.
# Rejected: validating the palette's `dispatch` entry ahead of the mint (the
#   three causes that need no live process to detect) and minting before
#   attempting the fourth (the process itself failing to start). That would
#   still leave a mint standing for a start that goes on to fail at the one
#   cause left uncovered -- exactly the gap this obligation closes -- for no
#   benefit: `spawn_dispatch`'s own Popen call is not slow enough that
#   deferring the mint past it costs anything worth trading that gap for.
def _spawn_outstanding(wid, child_id, brief_text, tier, tree, records, counts, is_returned,
                       assembly, pstep_id):
    """Start `child_id`'s harness process through this repository's own
    `dispatch` palette entry -- a fresh start or a restart, whichever
    `_startable(is_returned, records.get(child_id), counts.get(child_id,
    0))` allows. A no-op, with nothing journaled, minted, or logged, once
    that predicate reads false: `child_id` already returned, or it is still
    alive, or it is dead-and-spent (`counts` has reached
    `checkrun.MAX_STARTS`). Otherwise the one attempt this call makes is the
    single decision that covers every reason a start can fail
    (`o-mint-follows-start`): `checkrun.spawn_dispatch` either produces a
    live, journaled process or raises `DispatchFailure`, and only on the
    former does this mint the child's run at all (`journal.exists(child_id)`
    guarding a restart from minting twice) -- so a failed attempt, of any of
    its four causes, leaves no run behind for the harness that never
    started. The log basename is the child id's own tail past the leading
    `wid.` -- not merely its last dotted segment, which two different panel
    steps in the same run would both give `p1` -- so it stays distinct per
    child inside `wid`'s own work location, which is all commitment 18 asks.

    Returns the journal entry a successful attempt wrote, `None` for every
    other outcome (not startable, or the attempt failed) -- so `cmd_wait`,
    its one caller in `engine/` after this gate, can tell a genuine spawn
    from a no-op without a second pass over the journal, reading it
    straight off the return rather than rescanning."""
    if not _startable(is_returned, records.get(child_id), counts.get(child_id, 0)):
        return None
    tail = child_id[len(wid) + 1:] if child_id.startswith(wid + ".") else child_id
    log = journal.location(wid) / f"dispatch.{tail}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    try:
        entry = checkrun.spawn_dispatch(_palette(tree).get("commands", {}), brief_text,
                                        _runner(tier), tree, wid, child_id, log)
    except checkrun.DispatchFailure as e:
        with open(log, "a", encoding="utf-8") as f:
            f.write(f"{e.reason}: {e.detail}\n")
        return None
    if not journal.exists(child_id):
        _mint_child(assembly, wid, pstep_id)
    return entry


# [child-status]
# Rationale: shared by a dispatch step's lone child and each of a panel
#   step's several (commitment 11 -- each read against its own history,
#   never the step's record as a whole) since the read is identical for
#   both: report which of the four states -- not dispatched, working, gone
#   without returning, returned -- actually holds off whatever `records`
#   already carries, modeled the way `_in_flight_status` above already
#   turns a journaled pid plus `checkrun.alive` into "still running" vs.
#   "gone with no result" for a check's own proof. This function never
#   spawns (gate 2's own move, commitments 13-15 -- `cmd_wait` is the sole
#   spawner now), so a spawn attempt that failed and a child never
#   attempted at all read the same word here, "not dispatched",
#   distinguished only by whether that child's own log holds a reason
#   (commitment 13) -- neither this function nor its caller needs to tell
#   them apart.
# Rejected: two copies of this, one inlined at each of `_dispatch_status`
#   and `_panel_status`. A second, identical fork here would be the same
#   duplication one level up.
# [one-room-not-two]
# Rationale: `o-single-dispatch-room` -- a child's row never carries a
#   hand-typed command, in any of its four states: `spine <work-id> wait`
#   is what starts or restarts it, whether or not the palette carries a
#   `dispatch` entry, so there is nothing left for this function to brief.
#   The row states plainly when its own starts are spent, since that is
#   still real information a reader needs even though there is no command
#   left to offer about it.
def _dispatch_child(wid, child_id, records, counts, is_returned):
    """One child's status word: not dispatched, working, returned, gone
    without returning, or -- once `counts` reaches `checkrun.MAX_STARTS` --
    gone without returning with its own starts spent. Never a brief beside
    it: `spine <work-id> wait` is the only move that starts or restarts a
    child, so no row types one for the reader to copy. A pure read off
    `records` and `counts` -- this call spawns nothing; `cmd_wait` is the
    only caller left that starts or restarts a child (commitments 13-15,
    23-28)."""
    if is_returned:
        return "returned"
    record = records.get(child_id)
    if record is None:
        return "not dispatched"
    if checkrun.alive(record.get("pid")):
        return "working"
    if _startable(is_returned, record, counts.get(child_id, 0)):
        return "gone without returning"
    return "gone without returning -- starts spent"


# [child-descriptor]
# Rationale: `cmd_wait`'s own pre-loop spawn (commitments 13-15) needs the
#   same role/tier/open_cmd/finish_form a render already derives to build
#   the brief `_spawn_outstanding` hands the dispatch harness, so that
#   derivation is pulled out here rather than written a third time inline
#   in `cmd_wait` -- the shared shape this gate's own `direction` field
#   names, so gate 3's dead-pid restart rewrite extends this seam instead
#   of re-deriving it. Two functions, not one, because a dispatch step and
#   a panel step are already told apart by their own callers (branch order:
#   `panel_outstanding` before `dispatches`, `_current_form`) before either
#   is ever reached -- a single combined helper would have to re-guess
#   which key a step carrying both (round one's own design panel) means by
#   re-checking `dispatches` first, silently wrong for a panel step that
#   also happens to dispatch.
def _dispatch_descriptor(wid, asm, step):
    """The one child a dispatch step names, as `(role, tier, open_cmd,
    finish_form)` -- everything `_dispatch_child` needs besides the child
    id and tree info to read or brief that child."""
    dispatched = runmod.load_assembly(step["dispatches"])
    open_cmd = f"spine open {step['dispatches']} --parent {wid} --step {step['id']}"
    return dispatched.get("conductor", ""), _tier(step, asm), open_cmd, _finishing(dispatched)


# [form-filler-brief]
# Rationale: a dispatch step's child is a whole other run, briefed once and
#   opened as a process elsewhere; a form-step filler is not -- it is this
#   same run, standing on this same step, except that whoever fills it may
#   be a process `wait` starts rather than the caller reading `status`
#   directly. That filler needs the identical room `cmd_status` renders for
#   a live conductor standing on this step, plus the four lines (role,
#   tier, runner, tree) a spawned process needs and a live one already
#   knows from its own surroundings -- which is exactly `render.status`'s
#   new standalone-brief parameters. `tier` is read off the step's own raw
#   `filler` through `_role_tier`, not off `hat`'s unwrapped name: the two
#   are different answers to different questions (a model tier for
#   `filler == "conductor"` is always `heavy`, resolved before anything
#   unwraps it; the posture and role line shown are `hat`'s own answer, the
#   assembly's real conductor). `worktree`/`branch` come from `_tree_info`,
#   never cwd, because the filler's own process is not presumed to be
#   standing in this run's tree the way `cmd_status`'s caller is. Both the
#   response form and the board -- if this segment carries one -- are
#   re-resolved against that same tree via `_response_path`/`_board_path`'s
#   shared `root` parameter, for the identical reason: a path frozen at
#   mint time against some other cwd is not this filler's to trust.
# Rejected: computing `role` a second way here rather than reading it off
#   `_room_kwargs`. `_room_kwargs` already derives it via `runmod.hat`, the
#   same call `cmd_status` makes for a live conductor standing on the
#   identical step -- a second, hand-written call here could drift from it
#   for no reason.
def _form_filler_brief(wid, st, asm, step, form):
    """The room a form-step filler stands in: `cmd_status`'s own room,
    off the shared `_room_kwargs` derivation, plus the role/tier/runner/tree
    lines a spawned process needs and `cmd_status`'s own live caller does
    not. No caller yet (gate 4's horizon) -- this is the contract alone."""
    worktree, branch = _tree_info(wid, st)
    root = pathlib.Path(worktree)
    tier = _role_tier(step.get("filler", ""))
    runner = _runner(tier)
    dest = _response_path(st, step, root=root)
    if not dest.exists():
        forms.materialize(form, dest, work_id=wid,
                          submit=render.located(f"spine {wid} submit"),
                          drafts=_drafts(st, step, form))
    kwargs = _room_kwargs(wid, st, asm, step, form, dest, root=root)
    return render.status(st, form, dest, tier=tier, runner=runner,
                         worktree=worktree, branch=branch, **kwargs)


# [waived-is-not-a-descriptor]
# Rationale: every reader of a panel step's children -- `cmd_wait`'s spawn
#   and poll, the two refusals, the room's rows -- takes its child ids from
#   this one function, so a waived panelist left out here is left out of
#   all of them at once: never spawned by a later `wait`, never counted
#   outstanding, never named as who is still owed. `_dispatch_child`'s four
#   states stay four; a waived child is not a child the step reads at all.
# Rejected: a fifth `_dispatch_child` state, "waived". Four callers would
#   each grow a branch to skip it, which is the guard-in-two-places shape
#   `_wait_spawn`'s own rationale already refuses.
def _panel_descriptors(wid, asm, step):
    """Each panelist a panel step still waits for, as `(child_id, role,
    tier, open_cmd, finish_form)` -- a panelist's role is its own `worker`,
    not the give-a-verdict assembly's conductor: `_open_child` stamps that
    worker onto the dispatched child's step as its `filler`, so the panel
    entry is the source of truth, not just the brief that names it. A
    panelist a `waive` amend covers is left out: the step no longer waits
    for it, so nothing here may start, poll, or name it."""
    seg = next((s for s in asm["segment"] if s["id"] == step["segment"]), {})
    verdict_asm = runmod.load_assembly("give-a-verdict")
    waived = set(step.get("waived") or [])
    out = []
    for i, panelist in enumerate(step["panel"], start=1):
        tag = f"p{i}"
        child_id = f"{wid}.{step['id']}.{tag}"
        if child_id in waived:
            continue
        tier = panelist.get("model") or seg.get("model", "")
        open_cmd = f"spine open give-a-verdict --parent {wid} --step {step['id']}.{tag}"
        out.append((child_id, panelist.get("worker", ""), tier, open_cmd,
                    _finishing(verdict_asm, panelist.get("form", ""))))
    return out


# [outstanding-state]
# Rationale: the same "how many outstanding" read `wait`'s own predicate
#   already answers (`_wait_outstanding`) is reused here rather than
#   redefined, so a room's own line and `wait`'s own block are provably the
#   same population, not two readings that could drift apart. `count`
#   alone does not say whether typing `wait` would do anything: a zero
#   count arises both when every unresolved child is gone-and-spent (dead,
#   with `counts` already at `checkrun.MAX_STARTS` -- `wait` will not
#   restart any of them) and when at least one unresolved child is
#   startable (never dispatched, or dead-and-not-spent). `name_wait` reads
#   `_startable` -- the identical predicate `_spawn_outstanding` calls, not
#   a second, independent reading of "startable" -- so a child already in
#   `returns_by_child` reads `is_returned = True` and cannot make
#   `name_wait` true on its own account regardless of what its own record
#   or count say; there is no separate copy of that disjunct left to have
#   forgotten the clause. `records` and `counts` are supplied by the
#   caller, not re-fetched here: `_dispatch_status`/`_panel_status` already
#   hold both for their own call to `_dispatch_child`, while `cmd_submit`'s
#   and `cmd_close`'s refusal sites are callers with no such call of their
#   own -- a refusal renders no row, so neither ever calls
#   `_dispatch_child` -- and fetch `records`/`counts`
#   (`_dispatch_records`/`_dispatch_start_counts`) solely to make this
#   call.
def _outstanding_state(wid, child_ids, returns_by_child, records, counts):
    """`(count, name_wait)` for `child_ids`: how many `wait` still has to
    poll for (`_wait_outstanding`'s own count), and whether typing `wait`
    would start or restart anything at all."""
    count = len(_wait_outstanding(wid, child_ids, returns_by_child))
    name_wait = count > 0 or any(
        _startable(cid in returns_by_child, records.get(cid), counts.get(cid, 0))
        for cid in child_ids)
    return count, name_wait


def _dispatch_status(wid, st, asm, step, blocked):
    """A dispatch step renders a brief, not a form: `wait`, never this
    render, starts this step's child through the repository's own
    `dispatch` palette entry -- rendering this room only reads whatever
    `wait` has already done. The room renders exactly one way regardless of
    whether the palette is configured (`o-single-dispatch-room`): the
    child's own row carries no brief, ever, and the line above it stating
    how many are outstanding is never withheld -- naming `wait` where it is
    genuinely the next move (commitments 18, 19), or, where nothing remains
    live or startable, naming the ruling escape to drop the step instead
    (commitment 30)."""
    child_id = step.get("child") or f"{wid}.{step['id']}"
    records = _dispatch_records(wid)
    counts = _dispatch_start_counts(wid)
    status = _dispatch_child(
        wid, child_id, records, counts, child_id in st["returns_by_child"])
    lines = render.preamble(st, blocked, runmod.position(st, asm))
    lines.append(render.imperative(render.DISPATCH))
    lines.append("")
    count, name_wait = _outstanding_state(
        wid, [child_id], st["returns_by_child"], records, counts)
    lines.append(render.outstanding_line(wid, count, name_wait, step["id"]))
    lines.append("")
    lines.append(f"  {child_id} ({status})")
    lines.append("")
    lines.append(render.legal_moves(wid))
    return "\n".join(lines)


def _panel_status(wid, st, asm, step, blocked):
    """A panel step renders each panelist's own row -- copied, never
    composed -- with each panelist's own status (commitment 12); no
    panelist row, in any state, carries a brief (`o-single-dispatch-room`)
    -- `wait` is what starts or restarts one, whether or not the palette is
    configured. A panelist's role is its own `worker`, not the
    give-a-verdict assembly's conductor: `_open_child` stamps that worker
    onto the dispatched child's step as its `filler`, so the panel entry is
    the source of truth, not just the brief that would have named it. The
    room always carries one line above the panelist rows stating how many
    are outstanding and, where `wait` is genuinely the next move, naming it
    (commitments 18, 19) -- or, where nothing remains live or startable,
    naming the ruling escape instead: dropping the step, unless the step is
    also its conductor's own route form, in which case dropping it would
    drop that form too, and the escape waives the panel instead
    (commitment 30, and issue811's ruling)."""
    records = _dispatch_records(wid)
    counts = _dispatch_start_counts(wid)
    descriptors = _panel_descriptors(wid, asm, step)
    lines = render.preamble(st, blocked, runmod.position(st, asm))
    lines.append(render.imperative(render.PANEL))
    lines.append("")
    child_ids = [d[0] for d in descriptors]
    count, name_wait = _outstanding_state(
        wid, child_ids, st["returns_by_child"], records, counts)
    two_voices = bool(step.get("panel") and step.get("form"))
    lines.append(render.outstanding_line(wid, count, name_wait, step["id"], two_voices))
    lines.append("")
    for child_id, _role, _tier, _open_cmd, _finish_form in descriptors:
        tag = child_id.rsplit(".", 1)[-1]
        panelist = step["panel"][int(tag[1:]) - 1]
        status = _dispatch_child(
            wid, child_id, records, counts, child_id in st["returns_by_child"])
        lines.append(f"  panelist {tag} ({status})"
                     f" -- criteria: {panelist.get('criteria', '')}")
        lines.append("")
    lines.append(render.legal_moves(wid))
    return "\n".join(lines)


# [paused-status]
# Rationale: a paused run's own marker has no form, no panel, no dispatch --
#   the three shapes `_current_form` already renders -- so it needs a fourth
#   room of its own rather than falling through to any of them. Named apart
#   from `_dispatch_status`/`_panel_status` for the same reason those two are
#   apart from each other: each kind of step says one true thing about
#   itself, and a shared room would have to say the true thing for all three
#   or none.
def _paused_status(wid, st, asm, blocked):
    """What a paused run says about itself: nothing to fill here, the ask its
    own `up` sent is standing at the parent instead, and the answer arrives
    as this run's own next round rather than anything typed on this step."""
    parent = st.get("parent")
    lines = render.preamble(st, blocked, runmod.position(st, asm))
    if parent:
        lines.append(render.located(
            "  paused -- this gate ruled up. The ask it sent is standing at "
            f"its parent, not here: spine {parent}\n"
            "  nothing to fill on this run until the parent answers -- the "
            "answer arrives as this gate's own next round."))
    else:
        lines.append("  paused, with no parent left to carry the ask it sent "
                     "-- see the blocked note above.")
    lines.append("")
    lines.append(render.legal_moves(wid))
    return "\n".join(lines)


# [in-flight-room]
# Rationale: apart from `_paused_status` and the two dispatch rooms for the
#   reason those are apart from each other -- each kind of step says one true
#   thing about itself. What this one says is that the step is not done, its
#   proof is running, and since when. An orphan says the opposite thing and
#   has to be told apart here rather than rendered as a proof that will never
#   land: a check whose process is gone and whose result never arrived is
#   work to redo, not work to wait for. Its own outstanding line is
#   unconditional, the same as the dispatch/panel line now is
#   (`o-single-dispatch-room`) -- because a step's proof is spawned through
#   the check-runner/`HANDBACK` mechanism, a path with nothing to do with
#   whether `commands.dispatch` is configured: a repository with no
#   `dispatch` entry at all can still have a proof genuinely in flight. The
#   two halves name `wait` differently now, and both are true: the orphan
#   half still never names it -- a dead process has nothing left to poll,
#   so claiming `wait` is the move would promise a block that never comes
#   -- while the running half now does, because `cmd_wait`'s own final
#   branch blocks on exactly this case (`runmod.in_flight`, polled the
#   same shape as its spawn branches, minus the spawn -- there is nothing
#   to start, the detached runner is already going). That running half
#   used to carry its own cadence paragraph, spelled out by hand because
#   there was no verb to carry it instead: three headless gate-conductors
#   in this run read the old text ("see where it landed: spine <wid>") as
#   a destination rather than an act, concluded a background process would
#   tell them when the room changed, and stopped acting; nothing was
#   coming. The fix was never a softer destination, it was an act with a
#   cadence -- and a blocking verb IS that act: the cadence that used to
#   live in a reader's own discipline (render this room again, by hand,
#   every minute or two, until it says something else) now lives in the
#   engine's own poll loop instead, which is why the paragraph that used to
#   spell it out by hand is gone from the running branch -- the discipline
#   moved, it was not dropped. A later reader must not "tidy" this room
#   back into a bare pointer with no verb and no loop behind it: that is
#   the exact shape that already killed three runs.
# Rejected: leaving `wait` refusing to block here on the strength of
#   issue99's own spec -- commitment 29's in-flight row, resting on
#   commitment 6 -- whose stated reason was "`wait` blocks only on children
#   it can see as processes, so the block is empty whenever there is no
#   process to watch." That premise is false for a proof: `check-started`
#   journals a pid, this same function calls `checkrun.alive()` on it two
#   lines up, and `cmd_drive`'s own in-flight branch already polls that
#   pid (`if runmod.in_flight(st, step): time.sleep(checkrun.WAIT_POLL);
#   continue`) rather than refusing to -- `drive` already does the
#   blocking thing `wait` used to refuse to do, on the same pid. Giving
#   `wait` the same loop is not overturning that ruling, it is applying
#   the ruling's own stated reason to a case -- a proof's pid -- the
#   ruling's own text did not consider even though it already satisfies it.
def _in_flight_status(wid, st, asm, entry, blocked):
    """What a run whose proof is still running says about itself."""
    running = checkrun.alive(entry.get("pid"))
    lines = render.preamble(st, blocked, runmod.position(st, asm))
    for c in entry.get("commands") or []:
        lines.append(f"  {c.get('field', 'check')}: {c.get('command', '')}")
    lines.append("")
    lines.append(render.outstanding_line(wid, 1 if running else 0, running))
    lines.append("")
    if running:
        lines.append(render.located(
            f"  proof in flight since {entry.get('at', '')} (pid {entry.get('pid')}), "
            f"budget {entry.get('budget')}s -- this step is not done and nothing "
            "was recorded for it. The engine journals the submit itself when the "
            "proof passes, and refuses here when it fails.\n"
            f"  what it is printing: {entry.get('log', '')}"))
    else:
        lines.append(render.located(
            f"  proof started {entry.get('at', '')} (pid {entry.get('pid')}) and its "
            "process is gone with no result -- the check was killed or the machine "
            "went away. Nothing was recorded for this step, so nothing has to be "
            "undone.\n"
            f"  run it again: spine {wid} submit\n"
            f"  what it printed: {entry.get('log', '')}"))
    lines.append("")
    lines.append(render.legal_moves(wid))
    return "\n".join(lines)


def _onward(st):
    """Where this run's returns land -- read off its own opening entry, which
    has held the answer since `open` wrote it.

    A parent whose journal is gone gets nothing: `close` already says the
    return was not delivered, and offering a command that fails on top of
    that is worse than offering none.

    `journal.unbound()`: `st`'s own `parent` is this run's own recorded
    fact, not a caller-named id (see `[return-delivery-is-not-a-fresh-
    resolution]`, `engine/journal.py`) -- without it, a bound child's own
    closed status would always read as if its parent's journal were gone.
    """
    parent, pstep = st.get("parent"), st.get("parent_step")
    if not (parent and pstep):
        return None
    with journal.unbound():
        return (parent, pstep) if journal.exists(parent) else None


def _board_state(path):
    """Everything `render._board` needs, computed once here rather than in
    the render layer -- `render.py` formats what it is given, it does not go
    read a board itself."""
    if not path:
        return None
    found, col = boards.rows(path), boards.column(path)
    return {"path": path, "prose": boards.prose(path), "summary": boards.summary(path),
            "tree": [(d, r.get("id", ""), str(r.get("status", "")), boards.label(r, col))
                     for d, r in boards.tree(found)],
            "askable": [(r.get("id", ""), boards.label(r, col)) for r in boards.askable(found)],
            "held": [(r.get("id", ""), "held by " + ", ".join(ids))
                     for r, ids in boards.held(found)],
            "clusters": boards.clusters(found)}


# [returned-verdict]
# Rationale: a panel that ruled anything but the quiet word is the reason
#   the room the reader is standing in exists -- the outlet a looped revise
#   minted, or the fresh round a plain one did. The verdict itself was
#   engine-side only: findings arrived as prefill and the word the panel
#   merged on never did, so the reader had to infer it.
# Rejected: naming every returned panel, the quiet word included. A quiet
#   verdict is the room arriving normally; saying so is noise on every step
#   after it. Rejected also: a bare equality check against the literal word
#   `pass` left in place, #46's whole complaint -- rename the reviewer's
#   passing value in its forms and that check would silently stop
#   suppressing it. `declared_does` is the same reader `_holds_for_its_form`
#   and `_act_on_verdicts` already use: `release` (or an undeclared word --
#   the interior design panel's own case, which carries no verdict field at
#   all and so never resolves here either way) is the quiet class, and the
#   outcome table says which word that is, not this function.
# Rejected: suppressing a refusal the way an inert clean word is suppressed.
#   A word the panel's own form does not declare is the one thing this line
#   exists to put in front of the conductor -- the table has nothing to say
#   about it, so asking the table whether to print it is asking the wrong
#   question, and the answer would be silence on exactly the round somebody
#   has to rule on.
def _returned_verdict(st, asm):
    """The most recently returned panel's folded verdict, when its declared
    act is not `release`. Read from the last panel step that has a full
    house of returns, so a re-fired panel still waiting on its own critics
    reports the round that actually ruled, not silence. A refusal is named
    (`unreadable p2`) whatever the table says; a quiet panel -- no voice's
    form declaring a vocabulary -- is silent, as it is today."""
    for s in reversed(st["steps"]):
        rs = st["returns"].get(s["id"]) or []
        if s.get("panel") and not rs and s.get("waived"):
            return ""  # every voice waived: the last panel to rule here ruled nothing
        if s.get("panel") and rs and not runmod.panel_outstanding(st, s):
            _, spec = runmod.deciding_spec(asm, s)
            outcome = runmod.verdict_fold(rs, runmod.panel_forms(asm, s), spec)
            if outcome[0] == "clean" and \
                    runmod.declared_does(spec, outcome[1]) in (None, "release"):
                return ""
            return runmod.verdict_record(outcome)
    return ""


# [drafts]
# Rationale: a return used to reach the parent's form only as text in the
#   room, and the conductor retyped what it accepted -- so an adjudication
#   asked for `dispositions` and the conductor derived them afresh, the
#   gate's own question answered a second time with a bigger model, while
#   the gate's purpose went unasked. A plan field that declares
#   `drafted-by` now opens holding the returned field's own blocks, and the
#   parent's whole move on it is to accept or contest each. This reads the
#   same `returns_by_child` entry `_room_kwargs` already renders; the
#   template is written once, at the first `status`, so the draft lands
#   exactly where the answer is typed.
# Rejected: rendering the claims under "your orders" as prefill. Prefill is
#   the parent's word to the child, read-only; a child's claim flowing up is
#   a return, and calling it prefill would ship a homonym.
def _drafts(st, step, form):
    """`{field id: rows}` for every `plan` field on `form` whose `drafted-by`
    names a list of blocks the step's child returned; `{}` otherwise."""
    ret = st["returns_by_child"].get(step.get("child", "")) if step.get("child") else None
    returned = (ret or {}).get("fields") or {}
    out = {}
    for f in form["fields"]:
        if f.get("kind") != "plan" or not f.get("drafted-by"):
            continue
        rows = returned.get(f["drafted-by"])
        if isinstance(rows, list) and rows and all(isinstance(r, dict) for r in rows):
            if f.get("board") == "execution-state":
                rows = [_gate_claim(r) for r in rows]
            out[f["id"]] = rows
    return out


# [a-gate-claims-done-or-not]
# Rationale: a gate knows whether it did the work, not where unfinished
#   work goes. issue165's g3 claimed `handed-off: ... is gate 4's` and
#   sports-market-manager #219's g3 claimed `deferred: ... their own gate
#   (G4)`, with no such gate planned; each conductor accepted the drafted
#   claim, and each run reached close with a deliverable unbuilt. So the
#   draft opens any gate word but `satisfied` or `open` as `open`, the
#   gate's own text kept after the colon: accepting it keeps the work in
#   this run, and settling it elsewhere is the conductor typing `deferred`.
#   The gate's return in the journal keeps what it wrote.
# Rejected: refusing a gate's close that claims another word, or a
#   `deferred` that cites no ruling. A refusal stops a finished gate over
#   a word the parent can simply read as not done.
def _gate_claim(row):
    said = str(row.get("disposition", "")).strip()
    if not said or said.partition(":")[0].strip() in ("satisfied", "open"):
        return row
    return {**row, "disposition": f"open: {said}"}


# [room-kwargs]
# Rationale: `cmd_status`'s own derivation of everything `render.status`
#   needs beyond `st`/`form`/`response_path` themselves -- the returned
#   child's fields folded flat, the board (now via `_board_path`, re-derived
#   fresh rather than trusted from whatever cwd minted it), prefill, in-hand
#   fields, the returned verdict, blocks, position, prior drops, the role,
#   row returns -- lifted out here so `_form_filler_brief` can build the
#   identical room off the same derivation rather than a second hand-copy
#   of it. `dest` is a parameter, not recomputed, because both callers
#   already have it (`cmd_status` from its own `_response_path` call,
#   `_form_filler_brief` from its own with `root` given) and `in_hand`'s
#   read is the only thing here that needs it. `form` is threaded through
#   for the same reason `_current_form`'s whole triple is -- a caller
#   holding it need not pick it apart to call this.
#
#   `filler_status` (gate 3's own new read) is computed here too, on the
#   same `step["id"]` both callers already hold, rather than as a second
#   keyword either has to derive by hand: `_form_filler_brief` builds the
#   room for a filler about to start, before any record of it exists, so
#   it reads back `""` there and renders the ordinary form -- exactly what
#   a filler that has not yet run needs to be told. `cmd_status`'s own call
#   is the one that can actually see a live or spent record.
def _room_kwargs(wid, st, asm, step, form, dest, root=None):
    """Everything `render.status` needs besides `st`, `form` and
    `response_path` -- `cmd_status`'s own derivation, callable a second time
    by `_form_filler_brief` for a room whose board (if any) resolves against
    `root` instead of whatever cwd minted it."""
    filler_record = _form_filler_records(wid).get(step["id"])
    filler_count = _form_filler_start_counts(wid).get(step["id"], 0)
    if runmod.principal_fills(step):
        filler_status = "principal"
    elif _filling(wid, step["id"]):
        filler_status = ""  # the filler reading its own room: the form is its to fill
    elif filler_record is not None and checkrun.alive(filler_record.get("pid")):
        filler_status = "working"
    elif filler_record is not None and filler_count >= checkrun.FORM_FILLER_MAX_STARTS:
        filler_status = "spent"
    else:
        filler_status = ""
    # [route-room-reads-the-cut]
    # Rationale: a route step has no child of its own, so its room used to
    #   show the panel's verdict and nothing of the round it was ruling on;
    #   the critics saw the cut (`_round_artifact` fills their prefill) and
    #   the conductor did not. Now that the plan seam's panel reads fresh
    #   cuts only (`[panel-rounds]`), an incorporated round is routed by the
    #   conductor alone, and the cut has to be in the room it is routed
    #   from. So a step with no child reads the segment's most recent round
    #   that was dispatched and has returned -- the same walk
    #   `_panel_judged_rework` makes for `horizon` -- and renders its return
    #   as the round's own; the trial its `proof` got at the cut
    #   (`[trial-proofs]`) rides in that return's `checks` and renders as
    #   readings rather than exit codes. A step whose segment holds no such
    #   round (consolidate: the spec-writer fills in place; run-a-gate's
    #   route: panelists carry no `child` key) reads nothing, as before.
    child = step.get("child", "")
    disposed = ""
    if not child:
        # A dispatch step's child id is the same derivation `cmd_submit` and
        # `_open_child` make: its own `child` key where a mint wrote one, else
        # `<wid>.<step-id>` -- `skeleton()`'s plan-1 carries no key at all.
        prior = [s for s in st["steps"]
                 if s["segment"] == step["segment"] and s["id"] != step["id"]
                 and s.get("dispatches")]
        disposed = next((cid for s in reversed(prior)
                         for cid in (s.get("child") or f"{wid}.{s['id']}",)
                         if cid in st["returns_by_child"]), "")
    ret = st["returns_by_child"].get(child or disposed) if (child or disposed) else None
    returns = {**ret.get("summary", {}), **ret.get("fields", {})} if ret else None
    proofs = []
    proof_wait = None
    if returns and disposed:
        returns.pop("proof_trials", None)
        # Not the frozen snapshot `_summary` took at the child's own close
        # time: `[trial-wait]` (`cmd_wait`, below) is exactly the case where
        # a proof outran the handback and is still running, detached, when
        # that child closes -- its later `check` entries land in the child's
        # journal after the close already happened, and a snapshot taken at
        # close can never pick them up. Reading that journal fresh instead
        # -- always in scope from here, a child id is a dotted extension of
        # whatever this process is bound to -- is what lets a reading that
        # lands after the round closed still reach this room the next time
        # it is rendered.
        cst = runmod.state(disposed)
        if cst:
            proofs = render.proof_readings(cst.get("proof_trials") or [])
            pending = runmod.outstanding_trial(cst)
            if pending and checkrun.alive(pending.get("pid")):
                proof_wait = {"wid": disposed, "pid": pending.get("pid"),
                              "log": pending.get("log", "")}
        # A planner's cut has no review verdict, change or deviations of its
        # own; a blank line under each would say nothing to the conductor.
        returns = {k: v for k, v in returns.items() if v not in ("", None)}
    if returns:
        # Every structured value the summary can carry, spelled out rather
        # than left as a raw list -- str() on a list prints Python reprs, not
        # something a conductor can act on. A field's own form answer that
        # already overrode the summary's list by the time it lands here is a
        # string, so only a survivor gets rendered; the isinstance check is
        # what tells the two apart.
        for key, fn in (("checks", render.checks), ("proof_trials", render.proof_readings),
                        ("cycles", render.cycles), ("amends", render.amends)):
            if isinstance(returns.get(key), list):
                returns[key] = "; ".join(fn(returns[key])) or "none"
        # A child's own plan field returns as a list of blocks too --
        # GATE_CLOSE.toml's `claims` -- and has no renderer of its own, so
        # whatever list survives the four above prints block by block.
        for key, val in list(returns.items()):
            if isinstance(val, list):
                returns[key] = "; ".join(render.blocks(val)) or "none"
    # Rendered whenever the segment has a board; `validates` decides only
    # whether submit refuses on it. The ideas board is read at every cycle
    # and refused at none.
    board = _board_state(_board_path(wid, st, step, root))
    # [prior-drops]
    # Rationale: a finding has two destinations (docs/PURPOSE.md) -- done
    #   now, or dropped with its reason recorded where a later run can find
    #   it. The record already exists: a `rejected` call is a row on the
    #   submit entry that ruled it, in the run's own journal, archived under
    #   `<top>/.agent-work/archive/` once that run closes. Reading it back
    #   here is the "where a later run can find it" half of the ruling --
    #   nothing new is written, `engine/drops.py` only reads what already
    #   landed. Whether a `rejected` finding recurring here is worth acting
    #   on is the conductor's own call to make, at the seam calls are made;
    #   this only puts the prior ones in front of it, narrowed to the files
    #   this gate's own diff touches so the list is what could plausibly
    #   repeat and not every drop the archive has ever recorded.
    #   Shown at the route room and not at open: `_changed_paths_since_cut`
    #   needs a cut point and a tree to diff against, and open stands before
    #   either exists -- the files a finding could repeat on are not known
    #   until there is a diff.
    # Rejected: a stored `drops.toml`, or a field an agent fills. The record
    #   is already the archived journals; a second file is a second place
    #   for the two to drift, and this reads straight off the first.
    seg = next((s for s in asm["segment"] if s["id"] == step["segment"]), {})
    drops = []
    if _gate_route(asm, seg, step):
        cut_root = root if root is not None else journal.root_for(wid)
        top = _toplevel_checkout(cut_root) or cut_root
        touched = _changed_paths_since_cut(wid, cut_root)
        drops = dropsmod.touching(dropsmod.rejected_calls(top), touched)
    prefill = {**(st.get("prefill") or {}), **(step.get("prefill") or {})}
    # A `carries` transition folds its plan fields into the run's prefill as
    # lists of blocks (consolidate's `obligations`), and str() on one of
    # those is a Python repr under "your orders" -- the same spelling-out
    # the returns above get.
    prefill = {k: ("; ".join(render.blocks(v)) or "none") if isinstance(v, list) else v
               for k, v in prefill.items()}
    # One read of the response form: what is still marked `working:` and what
    # already carries an answer are two derivations of the same parse.
    filled = forms.filled_or_empty(dest)
    return {
        "prefill": prefill,
        "returns": returns,
        "returns_from": child or disposed,
        "proofs": proofs,
        "proof_wait": proof_wait,
        "verdict": _returned_verdict(st, asm),
        "waived": runmod.waived_panel(step),
        "blocked": runmod.blocks(st),
        "position": runmod.position(st, asm),
        "board": board,
        "in_hand": forms.in_hand(filled),
        "answered": forms.answered(filled),
        "drops": drops,
        "role": runmod.hat(asm, step, st),
        "row_returns": st["row_returns"],
        "filler_status": filler_status,
    }


def cmd_status(argv):
    wid = argv[0]
    st = runmod.state(wid)
    if st is None:
        _no_run(wid)
    # [filler-ends-at-its-submit]
    # Rationale: a spawned form filler is started for one step, and its
    #   headless brief says its turn ends when the room says its step is
    #   done. Handed the next step's room instead -- by its own `submit`, or
    #   by the `wait` it held on its detached proof -- it read that room as
    #   its own and carried the run on: issue71's select filler, on a heavy
    #   runner, went on to hold the whole gate's review. Once the step it
    #   was started for is no longer current, every room it asks for says
    #   so, and nothing else.
    filled = _filled_step(wid)
    if filled and not (st["open"] and st.get("current") and st["current"]["id"] == filled):
        print(render.filler_done(filled))
        return 0
    if not st["open"] or st["awaiting_close"]:
        print(render.status(st, {}, "", position=runmod.position(st, None),
                            onward_to=_onward(st)))
        return 0
    asm, step, form = _current_form(st)
    if runmod.panel_outstanding(st, step):  # checked before `dispatches`: see _current_form
        print(_panel_status(wid, st, asm, step, runmod.blocks(st)))
        return 0
    if runmod.paused(step):
        print(_paused_status(wid, st, asm, runmod.blocks(st)))
        return 0
    if step.get("dispatches"):
        print(_dispatch_status(wid, st, asm, step, runmod.blocks(st)))
        return 0
    started = runmod.in_flight(st, step)
    if started:
        print(_in_flight_status(wid, st, asm, started, runmod.blocks(st)))
        return 0
    dest = _response_path(st, step)
    if not dest.exists():
        forms.materialize(form, dest, work_id=wid,
                          submit=render.located(f"spine {wid} submit"),
                          drafts=_drafts(st, step, form))
    kwargs = _room_kwargs(wid, st, asm, step, form, dest)
    print(render.status(st, form, dest, **kwargs))
    return 0


# [wait-outstanding]
# Rationale: the process-only definition commitment 3 draws -- a live-pid
#   `dispatch-started` record with no `return` yet -- is read straight off
#   the journal via `_dispatch_records` rather than through
#   `_dispatch_child`, because `_dispatch_child` is a pure read now and only
#   `_spawn_outstanding` still spawns -- called once, before this predicate
#   is ever asked anything, by `cmd_wait`'s own pre-loop spawn (commitments
#   13-15 make `wait` the sole spawner). This predicate itself starts
#   nothing: by the time it first runs, `cmd_wait` has already made its one
#   spawn attempt per child, so what it reads here is always the record
#   that attempt left behind (or found already there). A child with no
#   record at all reads exactly the same as one that already returned or
#   whose pid died -- not outstanding -- which is what lets a
#   never-dispatched child whose own spawn attempt failed, and a palette
#   with no `dispatch` entry at all, fall out of this predicate for free
#   rather than needing a branch of their own.
def _wait_outstanding(wid, child_ids, returns_by_child):
    """Which of `child_ids` `wait` still has to poll: a live-pid
    `dispatch-started` record with no return landed for that child yet."""
    records = _dispatch_records(wid)
    return [cid for cid in child_ids
            if cid not in returns_by_child
            and cid in records and checkrun.alive(records[cid].get("pid"))]


def _wait_bound(argv):
    """The bound this call's own `wait` obeys: the default
    (`checkrun.WAIT_BOUND`) unless overridden with `--for <seconds>`
    (commitment 8)."""
    raw = _opt(argv, "--for")
    if raw is None:
        return checkrun.WAIT_BOUND
    try:
        seconds = int(raw)
    except ValueError:
        seconds = 0
    if seconds <= 0:
        raise SystemExit(render.refusal(
            "for", f"{raw!r} is not a number of seconds",
            escape="pass whole seconds -- --for 30"))
    return seconds


# [wait-spawn]
# Rationale: `IMPASSE.toml`'s own ruling on this gate's third round names a
#   guard whose halves live in two places, written as though it lived in
#   one, as the shape every prior round's gap shared -- and a second,
#   partial copy of `_startable` sitting here, beside this call, guessing
#   which of its clauses are worth pre-checking, is exactly that shape.
#   So `_wait_spawn` carries no guard of its own at all, not even the
#   `returns_by_child` half a prior round kept: it offers every descriptor
#   to `_spawn_outstanding` unconditionally, and `_spawn_outstanding`'s own
#   `_startable` guard is the one and only place that decides. The small
#   cost is `render.brief` (pure string formatting, no journal or process
#   I/O) getting built for a handful of children `_spawn_outstanding` will
#   no-op on -- cheap, and the price of never having a second copy of the
#   rule to fall out of sync with the first. `records` and `counts` are
#   still computed once, before the loop, and threaded through rather than
#   re-scanned per child.
# Rationale: `o-child-never-opens-its-own-run` means an engine-spawned
#   process's own brief never names an `open` command at all, on a fresh
#   dispatch or a restart alike -- so `render.brief` takes no `open_cmd`.
#   `assembly` and `pstep_id` -- the two extra fields `_spawn_outstanding`
#   needs to mint the run itself, once the process it briefs has actually
#   started (`o-mint-follows-start` -- never ahead of that, and never for a
#   start that failed) -- ride the same widened descriptor `cmd_wait`
#   builds, so this loop still threads one tuple per child rather than a
#   second, parallel list.
def _wait_spawn(wid, st, descriptors):
    """One spawn attempt for each `(child_id, role, tier, open_cmd,
    finish_form, assembly, pstep_id)` in `descriptors`, offered
    unconditionally to `_spawn_outstanding` -- `cmd_wait`'s own pre-loop
    start, making `wait` the sole spawner, respawner, and (per
    `o-child-never-opens-its-own-run`) minter of a child (commitments
    13-15, 23-28). The brief handed to the spawned process names no `open`
    command: `_spawn_outstanding` mints the run itself once that process is
    confirmed running, so there is nothing left for the process to open."""
    worktree, branch = _tree_info(wid, st)
    records = _dispatch_records(wid)
    counts = _dispatch_start_counts(wid)
    for child_id, role, tier, _open_cmd, finish_form, assembly, pstep_id in descriptors:
        is_returned = child_id in st["returns_by_child"]
        brief_text = render.brief(child_id, role, tier, _runner(tier),
                                  finish_form=finish_form, worktree=worktree, branch=branch)
        _spawn_outstanding(wid, child_id, brief_text, tier, worktree,
                           records, counts, is_returned, assembly, pstep_id)


# [wait-verb]
# Rationale: reproduces `cmd_status`'s own branch order (911-933) by hand
#   rather than asking `_current_form` which branch matched -- today it
#   only ever returns `None` for a panel, paused or dispatch step and a
#   loaded form for the rest, so a caller still has to re-run the same
#   checks to tell those apart. This gate's own `direction` field asks
#   whether that is worth pulling into a shared helper first; written by
#   hand a fourth time here, it was no harder to keep correct than the
#   three copies already standing (`cmd_status`, `cmd_submit`,
#   `cmd_close`), which itself answers the question for now -- left as a
#   note for whichever later gate needs the branch a second time.
# Rejected: leaving a dispatch or panel step whose child has never been
#   dispatched at all to render immediately with nothing outstanding, the
#   way gate 1 left it (`GATE_TRANSITION.toml`, finding 1: a prior render
#   already in `wait`'s own trailing `cmd_status` call started such a
#   child, not `wait` itself). This gate closes that gap: `cmd_wait`'s own
#   pre-loop spawn starts such a child itself, before the poll loop begins,
#   so `wait` no longer depends on some render already in its own call
#   chain to have started it first.
def cmd_wait(argv):
    wid = argv[0]
    bound = _wait_bound(argv[1:])
    st = runmod.state(wid)
    if st is None:
        _no_run(wid)
    # [trial-wait]
    # Rationale: a plan step's own `proof` that outran the handback keeps
    # running, detached (`checkrun.hand_in_trial`), but the step it belongs
    # to submitted immediately and does not wait on it -- so it is already
    # `done`, the run may already be `awaiting_close` or even closed, and
    # neither ever reaches the ordinary in-flight branch below, which is
    # keyed to the run's own *current* step. Checked first, ahead of every
    # other shortcut this function takes, for exactly that reason: this is
    # the one outstanding thing a closed run can still have. Same loop
    # shape as the ordinary in-flight branch, no spawn -- `hand_in_trial`
    # already started the detached runner, there is only the pid to hold
    # for.
    trial = runmod.outstanding_trial(st)
    if trial and checkrun.alive(trial.get("pid")):
        deadline = time.monotonic() + bound
        while True:
            fresh = runmod.state(wid)  # re-folded every cycle, never cached
            entry = runmod.outstanding_trial(fresh)
            if not entry or not checkrun.alive(entry.get("pid")):
                break
            if time.monotonic() >= deadline:
                break
            time.sleep(checkrun.WAIT_POLL)
        return cmd_status([wid])
    if not st["open"] or st["awaiting_close"]:
        return cmd_status([wid])
    asm, step, _ = _current_form(st)
    started = runmod.in_flight(st, step)
    if runmod.panel_outstanding(st, step):  # checked before `dispatches`: see _current_form
        # A panelist's own dispatched assembly is always "give-a-verdict"
        # (`_mint_child`'s own panel branch overwrites whatever it is
        # handed), and its `pstep_id` is the panel tag riding the step id --
        # `<step-id>.pN` -- the same shape `_panel_descriptors`' own
        # `open_cmd` already builds, read back off each descriptor's own
        # `child_id` rather than recomputed a second way.
        descriptors = [(*d, "give-a-verdict", f"{step['id']}.{d[0].rsplit('.', 1)[-1]}")
                       for d in _panel_descriptors(wid, asm, step)]
    elif runmod.paused(step):
        return cmd_status([wid])
    elif step.get("dispatches"):
        child_id = step.get("child") or f"{wid}.{step['id']}"
        descriptors = [(child_id, *_dispatch_descriptor(wid, asm, step),
                        step["dispatches"], step["id"])]
    elif started and checkrun.alive(started.get("pid")):
        # a step's proof, not a child -- `checks.hand_in` already spawned
        # the detached runner before this call ever ran (that is what
        # `check-started` means), so there is nothing to spawn here, only
        # to hold for. Same loop shape as the spawn branches above with no
        # `_wait_spawn` call, because there is nothing to start. See
        # `[in-flight-room]` above `_in_flight_status` for why this is not
        # the same room refusing to block that an earlier ruling left in
        # place, and for the cadence this loop now carries instead.
        # `runmod.in_flight` alone is not the loop condition: it stays
        # populated for an orphan too (nothing but a `submit` or `check`
        # entry ever clears it, and a dead proof writes neither), so
        # `checkrun.alive` is what tells a live wait from an orphan that
        # will never land -- checked fresh each cycle, not just at entry.
        deadline = time.monotonic() + bound
        while True:
            fresh = runmod.state(wid)  # re-folded every cycle, never cached
            entry = runmod.in_flight(fresh, step)
            if not entry or not checkrun.alive(entry.get("pid")):
                break
            if time.monotonic() >= deadline:
                break
            time.sleep(checkrun.WAIT_POLL)
        return cmd_status([wid])  # renders no view of its own (commitment 2)
    elif _filler_alive(wid, step["id"]) and not _filling(wid, step["id"]):
        # [wait-holds-for-filler]
        # Rationale: a childless form step whose own filler is a live
        #   process is outstanding work, exactly as a child or a proof is,
        #   and the room already names `wait` as the move beside it. Left
        #   rendering at once, `wait` spun: issue71's select filler called it
        #   197 times in 30 minutes, every call a full turn on a heavy runner.
        #   Held on the same terms `drive` already holds a live filler --
        #   sleep, re-derive, never spawn a second filler on top of it. The
        #   hold ends when the step is no longer current, its filler is gone,
        #   or the bound runs out.
        # Rejected: spawning a filler here for a step that never had one.
        #   That is `drive`'s walk; `wait` holds for what is already started.
        deadline = time.monotonic() + bound
        while True:
            fresh = runmod.state(wid)  # re-folded every cycle, never cached
            now = fresh.get("current") if fresh and fresh["open"] else None
            if not now or now["id"] != step["id"] or not _filler_alive(wid, step["id"]):
                break
            if time.monotonic() >= deadline:
                break
            time.sleep(checkrun.WAIT_POLL)
        return cmd_status([wid])
    else:
        # a childless form step has no child and no proof either, and an
        # orphaned proof (started, but its process is gone with no result
        # ever recorded) has nothing left to poll -- both render
        # immediately, the orphan naming no `wait` either (DO NOT CHANGE:
        # genuinely nothing to wait for there).
        return cmd_status([wid])
    child_ids = [d[0] for d in descriptors]
    _wait_spawn(wid, st, descriptors)
    deadline = time.monotonic() + bound
    while True:
        fresh = runmod.state(wid)  # re-folded every cycle, never cached (commitment 10)
        if not _wait_outstanding(wid, child_ids, fresh["returns_by_child"]):
            break
        if time.monotonic() >= deadline:
            break
        time.sleep(checkrun.WAIT_POLL)
    return cmd_status([wid])  # renders no view of its own (commitment 2)


# [drive-for-override]
# Rationale: `--for <seconds>` overrides `checkrun.DRIVE_BOUND` the same way
#   `_wait_bound` overrides `checkrun.WAIT_BOUND` -- parse, validate, refuse
#   on anything short of a whole positive number of seconds. Copied rather
#   than shared with `_wait_bound` itself, differing only in which constant
#   is the default: this gate's own "nothing existing in this file is
#   edited, only added to" makes that duplication the direct and reasonable
#   consequence of its own scope, not an oversight -- a one-line signature
#   change to `_wait_bound` to take a default is the alternative, left for
#   whichever round next touches `_wait_bound` itself to pick with its own
#   diff in hand.
def _drive_bound(argv):
    """The bound this call's own `drive` obeys: the default
    (`checkrun.DRIVE_BOUND`) unless overridden with `--for <seconds>`."""
    raw = _opt(argv, "--for")
    if raw is None:
        return checkrun.DRIVE_BOUND
    try:
        seconds = int(raw)
    except ValueError:
        seconds = 0
    if seconds <= 0:
        raise SystemExit(render.refusal(
            "for", f"{raw!r} is not a number of seconds",
            escape="pass whole seconds -- --for 30"))
    return seconds


# [drive-form-filler]
# Rationale: the spawn/poll/stop-spent triad for a childless form step's own
#   filler, drawn as its own function rather than a fourth inline block
#   inside `cmd_drive`'s own loop -- that loop already reads three step
#   shapes (panel, dispatch, this one) side by side, and a block this size
#   would bury the branch order the loop's own shape depends on. Returns
#   whether `cmd_drive` should stop (`True`, at the cap with nothing alive)
#   rather than stopping itself, because only the caller's own loop can
#   turn that into the right statement -- `return cmd_status(...)`, not a
#   bare `continue` -- the same split `cmd_drive`'s dispatch/panel branches
#   already draw between "spent" and "keep walking" a few lines below this
#   one. Reads `_form_filler_records`/`_form_filler_start_counts` rather
#   than `_dispatch_records`/`_dispatch_start_counts`: a form-step filler
#   fills this same run's own response form, never a dispatched child of
#   its own, so it is addressed by the step it fills (gate 3's own read
#   half, wired to a real spawn here for the first time).
# Rejected: reusing `_startable` for the startable/spent split. That
#   predicate's first clause is `is_returned` -- "has this child already
#   returned" -- a question with no answer for a form filler, which has no
#   return of its own at all; the step it stands on simply stops being
#   current once its response form is submitted. Restating the two clauses
#   `_startable` actually shares with this shape (dead pid, count against a
#   cap) directly is clearer than passing a manufactured `False` into a
#   predicate whose name promises a check this call can never trigger.
def _drive_form_filler(wid, st, asm, step, form):
    """One spawn attempt, or a stop signal, for a childless form step's own
    filler. `True` when this step's own filler is dead and
    `checkrun.FORM_FILLER_MAX_STARTS` has already been reached -- spent,
    nothing left for `drive` to start or poll, the caller's cue to render
    and stop. `False` otherwise: a live pid needs only `cmd_drive`'s own
    sleep-and-retry (never a fresh spawn on top of a filler already
    working), and everything else -- never started, or dead and short of
    the cap -- gets one spawn attempt through the repository's own
    `dispatch` palette entry, wrapped in the identical
    `try`/`except checkrun.DispatchFailure` discipline `_spawn_outstanding`
    already holds: a failure's reason is appended to this step's own log
    and left there for `cmd_drive`'s own retry next pass, never raised
    past this call."""
    record = _form_filler_records(wid).get(step["id"])
    count = _form_filler_start_counts(wid).get(step["id"], 0)
    if record is not None and checkrun.alive(record.get("pid")):
        return False
    if record is not None and count >= checkrun.FORM_FILLER_MAX_STARTS:
        return True
    worktree, _branch = _tree_info(wid, st)
    tier = _role_tier(step.get("filler", ""))
    brief_text = _form_filler_brief(wid, st, asm, step, form)
    log = journal.location(wid) / f"form-filler.{step['id']}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    try:
        checkrun.spawn_form_filler(_palette(worktree).get("commands", {}), brief_text,
                                   _runner(tier), worktree, wid, step["id"], log)
    except checkrun.DispatchFailure as e:
        with open(log, "a", encoding="utf-8") as f:
            f.write(f"{e.reason}: {e.detail}\n")
    return False


# [drive-verb]
# Rationale: three conditions end the call before it ever starts walking --
#   an unresolvable work id, a run already closed outright or standing on
#   `awaiting_close` (the same combined guard `cmd_status` and `cmd_wait`
#   already use), and a repository whose palette carries no `[commands]
#   dispatch` entry at all: without a `dispatch` entry `wait`'s own
#   mechanism starts nothing for any step, so `drive` would only ever spin
#   to its own bound doing nothing, and refusing outright says so instead
#   of spinning quietly. `_dispatch_configured` survives `o-single-dispatch-
#   room` for exactly this one call-ending check -- every other room and
#   refusal that used to read it now computes its own outstanding state
#   unconditionally instead.
#
#   A fourth condition -- the current step's own segment sitting earlier
#   than `plan` in the run's own assembly (`open`, `understand`;
#   `execution-state` too, but it is never `current` by construction,
#   `ASSEMBLY.toml:118-123`) -- is read fresh every pass, the same as every
#   other branch below, rather than only once before the loop: nothing
#   about it can become true again once past `plan`, but re-deriving it
#   costs nothing and keeps this function from carrying two different
#   reading disciplines side by side. An assembly with no `plan` segment at
#   all (`run-a-gate`, `give-a-verdict` -- every child a gate-dispatch or
#   panel step here actually walks) has nothing to compare against, so the
#   check does not apply to it.
def cmd_drive(argv):
    """Walk `wid` through every step shape the engine can resolve on its
    own, re-deriving the current step fresh every pass exactly as
    `cmd_status`/`cmd_wait` already do -- never a cached shape -- until one
    of commitment 9's stop conditions is reached or `bound` runs out: an ask
    carried up (`paused`), the run standing on its own close form
    (`awaiting_close`), a form its principal fills (`runmod.principal_fills`:
    the close form itself, or an ask standing in this run's own journal), a
    gate or panelist spent past `checkrun.MAX_STARTS` with nothing else
    outstanding for that step, or a childless form step's own filler spent
    past `checkrun.FORM_FILLER_MAX_STARTS` -- each stops and renders rather
    than crash or spin."""
    wid = argv[0]
    bound = _drive_bound(argv[1:])
    st = runmod.state(wid)
    if st is None:
        _no_run(wid)
    if not st["open"] or st["awaiting_close"]:
        return cmd_status([wid])
    worktree, _branch = _tree_info(wid, st)
    if not _dispatch_configured(worktree):
        raise SystemExit(render.refusal(
            "dispatch", "this repository's palette has no [commands] dispatch "
            "entry -- drive has nothing of its own to start",
            escape=f"work it by hand: spine {wid}"))
    deadline = time.monotonic() + bound
    while True:
        if time.monotonic() >= deadline:
            return cmd_status([wid])
        st = runmod.state(wid)  # re-folded every pass, never cached (commitment 2)
        if not st["open"] or st["awaiting_close"]:
            return cmd_status([wid])
        asm, step, form = _current_form(st)
        seg_order = [s["id"] for s in asm["segment"]]
        if "plan" in seg_order and \
                seg_order.index(step["segment"]) < seg_order.index("plan"):
            raise SystemExit(render.refusal(
                step["segment"], f"{wid} is standing on the {step['segment']} "
                f"segment -- drive starts at the plan segment",
                escape=f"work it by hand: spine {wid}"))
        if runmod.panel_outstanding(st, step):  # checked before `dispatches`: see _current_form
            child_ids = [d[0] for d in _panel_descriptors(wid, asm, step)]
        elif runmod.paused(step):
            return cmd_status([wid])
        elif step.get("dispatches"):
            child_ids = [step.get("child") or f"{wid}.{step['id']}"]
        else:
            if runmod.principal_fills(step):
                return cmd_status([wid])  # the principal's own form -- rendered, never driven
            if runmod.in_flight(st, step):
                time.sleep(checkrun.WAIT_POLL)
                continue
            if _drive_form_filler(wid, st, asm, step, form):
                return cmd_status([wid])  # spent -- nothing left to spawn or poll
            time.sleep(checkrun.WAIT_POLL)
            continue
        # [drive-bounds-its-own-wait]
        # Rationale: `cmd_wait` with no `--for` blocks up to `checkrun.WAIT_BOUND`
        #   (90s) per call, regardless of how little of `drive`'s own deadline is
        #   left -- measured, `--for 6` cost 91.2s wall-clock against a live child
        #   that never returns. `--for` here passes what remains of `deadline`,
        #   rounded up so a fractional remainder never truncates to the `0` that
        #   `_wait_bound` refuses, capping the nested call's own worst case to one
        #   `WAIT_POLL` past `drive`'s bound rather than to `WAIT_BOUND`'s.
        remaining = max(1, math.ceil(deadline - time.monotonic()))
        cmd_wait([wid, "--for", str(remaining)])
        fresh = runmod.state(wid)  # re-read post-`wait`, never the pre-call snapshot
        if all(cid in fresh["returns_by_child"] for cid in child_ids):
            continue  # resolved -- the next pass picks up whatever is now current
        records = _dispatch_records(wid)      # fresh, never the pre-call descriptors
        counts = _dispatch_start_counts(wid)  # ditto
        count, name_wait = _outstanding_state(
            wid, child_ids, fresh["returns_by_child"], records, counts)
        if count == 0 and not name_wait:
            return cmd_status([wid])  # spent -- nothing left for wait to start or poll
        # `cmd_wait`'s own inner loop returns instantly when nothing it just
        # tried to spawn or poll is alive (e.g. a spawn attempt failed short
        # of the cap) -- sleep here so that shape spins harmlessly rather
        # than busy-looping for the whole of `bound`.
        time.sleep(checkrun.WAIT_POLL)


def cmd_submit(argv):
    wid = argv[0]
    st = runmod.state(wid)
    if st is None or not st["open"] or st["awaiting_close"]:
        raise SystemExit(render.located(
            f"{wid} has no current step"
            + (f" -- close it: spine {wid} close" if st and st["awaiting_close"] else "")))
    asm, step, form = _current_form(st)
    if runmod.panel_outstanding(st, step):  # checked before `dispatches`: see _current_form
        escape = f"who is outstanding: spine {wid}"
        child_ids = [d[0] for d in _panel_descriptors(wid, asm, step)]
        records = _dispatch_records(wid)
        counts = _dispatch_start_counts(wid)
        _, name_wait = _outstanding_state(
            wid, child_ids, st["returns_by_child"], records, counts)
        if name_wait:
            escape = f"spine {wid} wait"
        if step.get("form"):
            # A two-voices step has a form of its own to stand on once its
            # panel is waived; a panel-only step has nothing left, so
            # `amend close` stays its way out.
            escape += (f"; or waive the rest: spine {wid} amend waive {step['id']} "
                       "--reason ...")
        raise SystemExit(render.refusal(
            step["id"], "a panel step is not submitted -- the panelists' verdicts "
            "complete it, or a waiver does", escape=escape))
    if runmod.paused(step):
        raise SystemExit(render.refusal(
            step["id"], "paused -- the ask it sent is standing at its parent, not here",
            escape=(f"see it: spine {st.get('parent')}" if st.get("parent")
                   else "no parent left to see it at -- see the blocked note above")))
    if step.get("dispatches"):
        child_id = step.get("child") or f"{wid}.{step['id']}"
        records = _dispatch_records(wid)
        counts = _dispatch_start_counts(wid)
        _, name_wait = _outstanding_state(
            wid, [child_id], st["returns_by_child"], records, counts)
        escape = (f"spine {wid} wait" if name_wait else
                  f"drop it: spine {wid} amend close {step['id']} --reason ...")
        raise SystemExit(render.refusal(
            step["id"], "a dispatch step is not submitted -- it completes when "
            "its child closes", escape=escape))
    # A second submit while the first one's proof is still running would start
    # a second runner against the same step, and two runners can both reach
    # exit 0. Refused while the process is alive; once it is gone with no
    # result, submitting again is exactly the re-run the room offers.
    started = runmod.in_flight(st, step)
    if started and checkrun.alive(started.get("pid")):
        raise SystemExit(render.refusal(
            step["id"], f"its proof has been running since {started.get('at', '')} "
            f"(pid {started.get('pid')}) -- the engine journals the submit itself "
            "when it passes", escape=f"where it stands: spine {wid}"))
    dest = _response_path(st, step)
    if not dest.exists():
        raise SystemExit(render.located(f"no response form yet — run: spine {wid}"))
    filled = forms.parse(dest)

    fields = {}
    for f in form["fields"]:
        fid, kind = f["id"], f.get("kind", "evidence")
        if kind == "check":
            continue  # the engine runs these; they are never on the template
        # The escape both refusals below offer is the field's own: a decision
        # field refuses the nulls, so it is offered the values its note lists.
        vocab = forms.enforced_vocabulary(f)
        if fid not in filled:
            if f.get("optional"):
                continue
            raise SystemExit(render.refusal(fid, "no answer",
                                            escape=render.escape_for(vocab)))
        # A field the agent marked as still in hand. Submitting it would
        # record work-in-progress as an answer, and the next reader could not
        # tell the difference -- so say what is still open and let the agent
        # finish it, or close it honestly with one of the values it does take.
        if str(filled[fid]).strip().startswith("working:"):
            raise SystemExit(render.refusal(
                fid, str(filled[fid]).strip(),
                escape=render.escape_for(vocab, verb="finish")))
        fields[fid] = filled[fid]

    # Everything the engine can refuse on is settled before the check starts,
    # and so before anything is journaled. A check is the one part of a submit
    # that can outlive its caller, and a refusal raised after the caller has
    # been handed back is one nobody is standing there to read. `_outcome` is
    # called here as that guard -- its answer also gates `validates` and
    # `_check_release_artifacts` below -- and whichever process completes
    # the submit computes it again.
    _check_plan(asm, form, fields)
    _check_vocabulary(asm, step, form, fields)
    _check_calls(form, fields)
    _check_artifact(wid, form, fields)
    outcome = _outcome(asm, step, fields, st)
    _check_release_artifacts(form, fields, outcome)
    _check_projection(asm, step, st, fields)
    _check_one_look(asm, st, outcome, fields)

    # `validates = "board"` only gates a release (`_releases`): a rework or
    # an up leaves this segment unfinished, and the board it validates is
    # not done until the round it is validated against actually passes.
    if step.get("validates") == "board" and _releases(outcome):
        board = st["boards"].get(step["segment"], "")
        problems = boards.validate(board) if board else []
        if problems:
            raise SystemExit(render.refusal(pathlib.Path(board).name,
                                            "\n  ".join(problems), escape=""))

    # A check both resolves and runs against this run's own tree -- not
    # against whatever directory the invoking shell happens to be standing
    # in, which a worktree can silently disagree with.
    check_root = journal.root_for(wid)
    # A plan's own `proof` fields are run once here, before the submit lands
    # -- reported to the planner now and to the conductor's route room later,
    # refused never (`[trial-proofs]`).
    trialled = _trial_proofs(wid, step, form, fields, check_root)
    for block in render.proof_readings(trialled):
        print("\n".join("  " + line for line in block.split("\n")) + "\n")
    # A proof that outran the handback is still running, detached
    # (`checkrun.hand_in_trial`); this submit never waits on it, but the
    # planner reading this same turn should not be left guessing why no
    # reading printed for it.
    pending = runmod.outstanding_trial(runmod.state(wid))
    if pending:
        print(render.located(
            f"  a proof outran the {checkrun.HANDBACK}s handback and is still "
            f"running (pid {pending.get('pid')}) -- the reading lands once it "
            f"does, at the route form: spine {wid} wait\n"
            f"  what it is printing: {pending.get('log', '')}") + "\n")
    # A check's command comes from the orders: the step's own prefill when it
    # has one, else the run's -- a dispatched child carries its spec at the
    # run level, and its first step is minted before that spec exists. The
    # budget rides in beside it, from the same orders. A `waived:` one is an
    # order with nothing to run -- a gate cut with no `gate-proof`.
    orders = {**(st.get("prefill") or {}), **(step.get("prefill") or {})}
    commands = [(f["id"], _resolve_command(orders.get(f["id"], ""), check_root))
                for f in form["fields"] if f.get("kind") == "check"
                and forms.leading_word(str(orders.get(f["id"], ""))) not in forms.NULL_WORDS]
    commands = [(fid, cmd) for fid, cmd in commands if cmd]
    if not commands:
        complete_submit(wid, step["id"], fields, [])
    elif checkrun.hand_in(wid, step, fields, commands, check_root,
                          checkrun.budget_for(orders)) == "in-flight":
        return cmd_status([wid])  # the room says the proof is still running
    print(f"submitted {step['id']}\n")
    return cmd_status([wid])


# [complete-submit]
# Rationale: a submit is not one journal entry -- it mints the next step,
#   folds a `carries` transition's fields into the run's prefill, and performs
#   whatever outcome the decision field selected. All of that has to happen
#   where the check's exit status is held, or a proof that passes after its
#   caller has gone lands a submit and leaves the run standing on a step
#   nothing minted. So the tail is one function and both processes call it.
# Rejected: letting the detached runner append the `submit` entry alone and
#   having the next `spine <wid>` mint from it. That makes the fold finish an
#   act it did not perform, and every verb would then have to be ready to
#   complete a submit it was not asked to make.
def complete_submit(wid, step_id, fields, ran):
    """Journal the submit and everything it sets off.

    Called by whichever process holds the check's exit status: the detached
    runner where the step has a check, `cmd_submit` itself where it has none.
    The step is re-derived from the journal rather than passed in, because the
    two callers are different processes and the journal is all they share --
    and a step that is no longer current is the one interleaving that must
    never write a submit.
    """
    st = runmod.state(wid)
    if st is None or not st.get("current") or st["current"]["id"] != step_id:
        raise SystemExit(render.refusal(
            step_id, "is no longer this run's current step -- something else "
            "advanced it while its check ran; nothing was recorded"))
    asm, step, form = _current_form(st)
    outcome = _outcome(asm, step, fields, st)
    journal.append(wid, "submit", step=step["id"], fields=fields,
                   checks=ran or None)
    _measure_artifacts(wid, step, form, fields)

    # A transition marked `carries` folds its fields into the run's own
    # prefill, so everything dispatched afterwards gets them. Consolidate is
    # the case this exists for: a panelist's prefill is built from prior steps
    # in its own segment, so without this the run's understanding never crosses
    # a segment boundary and the coldest reader in the run -- the one the
    # understanding was written for -- is the only one who never sees it.
    # Gated on `_releases` the same as `validates = "board"` above: a rework
    # or an up submits `resolution` and maybe `calls`, never a real `spec`,
    # and folding those into prefill would carry a blank field over whatever
    # a prior release already put there.
    # `true` folds every field the step submitted; a list of field ids folds
    # only those, for a step whose fields do not all age the same way. `open`
    # is the case that exists for: `authority` is the principal's own orders
    # and has to reach every later dispatch, while `questions` beside it is a
    # seed list the board supersedes the moment it is worked -- a frozen copy
    # of it in every child's prefill reads as orders that it is not.
    carries = step.get("carries")
    if carries and _releases(outcome):
        held = (fields if carries is True else
                {k: v for k, v in fields.items() if k in carries})
        journal.append(wid, "prefill",
                       fields={**(st.get("prefill") or {}), **held})
    _mint(wid, asm, step, form, fields)
    _mint_projected_gate(wid, asm, step, st, fields)
    _resume_paused_child(wid, step, fields)
    if outcome:
        _perform(wid, asm, *outcome, fields, step)


def _check_plan(asm, form, fields):
    """A plan field must be a list of blocks, and what it says it mints must be
    something `_mint` performs. Both checked before anything is journaled: a
    submit is durable the moment it lands, so minting that dies -- or that
    silently finds no branch -- afterwards would leave a run that looks
    advanced and has no work in it."""
    for f in form["fields"]:
        if f.get("kind") != "plan" or f["id"] not in fields:
            continue
        rows = fields[f["id"]]
        if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
            raise SystemExit(render.refusal(
                f["id"], "must be one or more [[" + f["id"] + "]] blocks, not a "
                "single value -- nothing was recorded"))
        mintable = _mintable(asm)
        if f.get("mints") and f["mints"] not in mintable:
            raise SystemExit(render.refusal(
                f["id"], f"mints = {f['mints']!r} is nothing this engine mints -- "
                "the form is wrong, not your answer; nothing was recorded",
                escape="one of: " + ", ".join(sorted(mintable))))


# [check-vocabulary]
# Rationale: a `decision` field -- one whose value the engine acts on -- is
#   checked against the alternatives its own note declares, read off by
#   `forms.enforced_vocabulary` -- so the enum the agent is told and the enum
#   the engine enforces are one string and cannot drift, and the refusal can
#   name the list the agent already read. The kind is what makes the note
#   load-bearing: punctuation alone would enum an ordinary prose note.
# Rejected: a table of field ids and their legal values kept here. It is the
#   same list written twice, and the copy that matters is the one in the form:
#   the engine would go on enforcing the old list against a reworded note.
def _decided_here(asm, step):
    """The field this step's assembly already declares outcomes for, if any.

    `_outcome` refuses an undeclared value on that field, and refuses it
    better: the assembly pairs each value with what it *does*, so the values
    and the acts are declared together and the engine names neither. This
    check stands down there rather than running first and refusing on
    stricter terms -- one field, one enforcer.
    """
    return runmod.deciding_spec(asm, step)[1].get("decides")


# [call-vocabulary]
# Rationale: `_check_vocabulary` reaches a form's own `[[field]]` entries and
#   stops there, so the one value in the tree the engine acts on from inside a
#   `kind = "plan"` row -- a per-finding `call` -- was never checked against
#   anything. `_blocking_calls` compares `leading_word(...) == "blocking"`, so
#   a call the vocabulary does not contain (a typo, `accept`, `blocking-ish`)
#   read as not-blocking and the finding it belonged to was silently dropped
#   from the round's orders, while `review_yield` tallied the bogus word into
#   the yield table without comment. That is the silent-default class the
#   verdict fold was made to refuse rather than guess at, and the lesson was
#   applied there and not here.
# Rejected: enforcing every plan item whose note happens to contain ` | `.
#   That is exactly the mistake `[field-vocabulary]` names -- deriving an enum
#   from punctuation alone turns an ordinary prose note into an enum nothing
#   declared and no one can see. An item earns enforcement the same way a
#   field does, by declaring `kind = "decision"`, which is why the three route
#   forms' `call` items now do.
def _check_calls(form, fields):
    """A per-finding call the engine cannot act on refuses instead of
    releasing the step -- the same rule `_check_vocabulary` holds a decision
    field to, applied to a decision item inside a `kind = "plan"` row.

    Read off the item's own declared vocabulary rather than a list written
    here, so a route form that reworded its calls cannot leave this enforcing
    the old one."""
    for f in form["fields"]:
        rows = fields.get(f["id"])
        if f.get("kind") != "plan" or not isinstance(rows, list):
            continue
        for item in f.get("item", []):
            vocab = forms.enforced_vocabulary(item)
            if not vocab:
                continue
            allowed = [alt.split("<")[0].strip().lower() for alt in vocab]
            for row in rows:
                if not isinstance(row, dict) or item["id"] not in row:
                    continue
                word = forms.leading_word(row[item["id"]])
                if word not in allowed:
                    raise SystemExit(render.refusal(
                        f'{f["id"]}.{item["id"]}',
                        f"{word or 'empty'!r} is not a call this step can act on",
                        escape="one of: " + " | ".join(vocab)))


def _check_vocabulary(asm, step, form, fields):
    """A value the engine cannot act on refuses instead of releasing the step.

    Checked before anything is journaled, because past that point the submit
    is durable and an unhandled value walks the run forward having performed
    nothing -- the silent advance this check exists to end. Matching is exact:
    the acts downstream compare whole strings, so `advance, I think` is a value
    nothing performs. A placeholder alternative (`name <x>`) matches on its
    literal prefix alone, so a value naming a runtime argument is still a
    known move; once a field declares `decides`, this check stands down for
    it and `_outcome` owns the argument itself.
    """
    decided = _decided_here(asm, step)
    for f in form["fields"]:
        vocab = forms.enforced_vocabulary(f)
        if not vocab or f["id"] not in fields or f["id"] == decided:
            continue
        value = str(fields[f["id"]]).strip()
        word = forms.leading_word(value)
        if word not in [alt.split("<")[0].strip().lower() for alt in vocab]:
            raise SystemExit(render.refusal(
                f["id"], f"{word or 'empty'!r} is not a value this step can act on",
                escape="one of: " + " | ".join(vocab)))


def _mint_transition(wid, seg, prefill=None):
    """One fresh transition step for a segment: a board segment's refill,
    and the impasse's advance. A transition with a form is a step someone
    fills, so this mints it; one with no form has nothing to mint, and the
    run walks on.

    What it mints is the form alone, never a panel: an impasse ruling
    `advance` at run-a-gate's `work` stands the conductor on the route form
    to dispose of the live revise, and the ruling's own note says a fourth
    fresh-context reader is the loop, not the way out of it.
    """
    t = seg.get("transition", {})
    form = t.get("form", "")
    if form:
        journal.append(wid, "step", id=f"{seg['id']}-a{secrets.token_hex(2)}",
                       segment=seg["id"], form=form, filler=t.get("filler", "conductor"),
                       prefill=prefill or {}, anchor=t.get("anchor", False),
                       terminal=t.get("terminal", False), validates=t.get("validates", ""),
                       source="mint")


# [declared-outcomes]
# Rationale: a transition releases, refills, or goes elsewhere, and which
#   word does which is the assembly's to say: `decides` names the field,
#   `[[outcome]]` rows pair a `value` with what it `does` -- release; refill
#   [<segment>]; skip <segment>; transition [<segment>]; rework [<segment>];
#   remint <field>; close; several joined by ";". The engine matches the field's
#   first word, refuses one nothing declares naming those it can act on, and
#   performs the verbs. No assembly's words appear here. `transition` and
#   `rework` are the impasse's two moves, absorbed alongside the rest (#32)
#   -- an offered `ruling` is now a `decides` field like any other, and
#   `remint`/`close` are gate adjudication's, absorbed the same way.
# See: #32 -- gate adjudication still carries its own interpreter.
def _outcome(asm, step, fields, st):
    """(segment, does) for the outcome this submit selects; None when the
    step declares none or the field is nulled. Checked before the submit
    lands, so a value the engine cannot act on -- or a runtime argument that
    does not resolve -- never advances the run.

    A declared value may carry a placeholder (`name <x>`): matched on the
    word before the `<`, the same rule `_check_vocabulary` already used for
    it. Where a value does carry one, the rest of the field's own text is
    the argument, and its legal values are this step's own segment's
    not-done, non-terminal steps that do not share this step's `child` --
    the deciding step can never name its own pair, closing one step of a
    pair takes the other with it (a pair is exactly the steps sharing a
    `child`), and the segment's own terminal step is never a target (it has
    no `child` of its own, and is what closing the run means, not something
    a decision inside it drops). Neither idea is this field's; both are
    `_mint_gates`' own data, read structurally rather than declared or
    hardcoded.
    """
    seg, spec = runmod.deciding_spec(asm, step)
    field = spec.get("decides")
    if not field or field not in fields:
        return None
    raw = fields[field]
    value = forms.leading_word(raw)
    if value.startswith(("waived", "unknown")):
        return None
    outcomes = spec.get("outcome", [])
    legal = {o["value"].split("<")[0].strip().lower(): o for o in outcomes}
    if value not in legal:
        raise SystemExit(render.refusal(
            field, f"{value or 'empty'!r} is not an outcome this step declares",
            escape="one of: " + " | ".join(o["value"] for o in outcomes)))
    chosen = legal[value]
    declared = chosen["value"]
    if "<" in declared:
        parts = str(raw).split(None, 1)
        target = parts[1].strip() if len(parts) > 1 else ""
        pending = [s["id"] for s in st["steps"] if s["segment"] == step["segment"]
                  and s["id"] not in st["done"] and not s.get("terminal")
                  and s.get("child") != step.get("child")]
        if not target:
            raise SystemExit(render.refusal(
                field, f"{value} needs a gate id -- {declared}",
                escape="pending: " + (", ".join(pending) or "none")))
        if target not in pending:
            raise SystemExit(render.refusal(
                field, f"{target!r} is not a pending gate",
                escape="pending: " + (", ".join(pending) or "none")))
    does = runmod.declared_does(spec, value)
    for verb in filter(None, (v.strip() for v in does.split(";"))):
        word, _, argfield = verb.partition(" ")
        if word == "remint" and not fields.get(argfield):
            raise SystemExit(render.refusal(
                argfield, "remint needs a new gate spec -- a remint with no "
                "spec is a drop wearing the wrong name"))
    return seg, does


# [releases]
# Rationale: `validates = "board"` and `carries = true` are both declared on
#   consolidate's own transition, and both used to be safe to fire on every
#   submit of that step because there was only ever one -- the panel's own
#   `pass` was the only verdict that ever reached a submitted form at all,
#   a bare `revise` refilling the spec-writer round directly with no
#   conductor submit in between. Ruling 3's 2026-09-03 follow-up gave
#   consolidate the plan seam's own shape: the step now also reaches an
#   ordinary submit on a `rework` or an `up`, neither of which finishes this
#   segment -- the board is not done until the spec passes, and there is no
#   spec yet to carry. Both checks gate on this so a rework or an up submit
#   is refused on its own merits alone, never because the board it does not
#   need yet is still open, and never carries a blank field over whatever
#   prefill already held.
_HOLDS_OPEN = ("rework", "incorporate", "rewrite", "pause")


def _releases(outcome):
    """True where this submit's own outcome finishes the deciding step's
    segment, rather than sending the round back (`rework`, `incorporate`,
    `rewrite`) or up (`pause`) -- the verbs that leave it still open. `None` -- no decided field, or a
    null the engine reads as waived/unknown -- releases too: nothing here
    holds the round open on its account."""
    if not outcome:
        return True
    _, does = outcome
    return not any(v.strip().split(" ", 1)[0] in _HOLDS_OPEN
                  for v in does.split(";") if v.strip())


# [release-needs-its-artifact]
# Rationale: `plan` on PLAN_TO_EXECUTE.toml and `spec` on CONSOLIDATE.toml
#   went optional so a `rework` or an `up` -- neither releasing anything --
#   could leave them blank. The same optional flag let a `pass`, or a
#   recorded `revise`, leave the same field blank and release anyway:
#   `carries` and `_mint_projected_gate` (both gated on `_releases`) found
#   nothing to carry or project and silently did nothing, so a round the
#   record calls released produced no evidence it had -- #87's class, the
#   silent kind epic wave 5 is closing one instance of at a time. Generic
#   off `kind = "artifact"` and `_releases`, never a form name: the next
#   route form to grow an optional artifact field inherits this for free.
# Rejected: refusing on any blank artifact field regardless of `_releases`.
#   A `rework` or an `up` has nothing intact to carry -- that blank is the
#   correct answer, not a gap -- and PLAN_TO_EXECUTE.toml and
#   CONSOLIDATE.toml both say so in the field's own note.
def _check_release_artifacts(form, fields, outcome):
    """On a submit whose own outcome `_releases`, every `kind = "artifact"`
    field the form declares must be answered -- `waived:`/`unknown:` still
    count, the same escape any other field takes; only a field truly blank
    (absent from `fields`, which is what `forms.parse` leaves once it
    strips an empty slot) refuses. A `rework` or an `up` never reaches this
    check at all: `_releases` is what tells the two apart."""
    if not _releases(outcome):
        return
    for f in form.get("fields", []):
        if f.get("kind") == "artifact" and f["id"] not in fields:
            raise SystemExit(render.refusal(
                f["id"], "a release needs it -- blank here and the round "
                "releases with nothing carried or projected, silently"))


# [blocking-calls]
# Rationale: the deciding form's own per-finding `calls` is what makes a
#   rework round's prefill the *blocking* findings rather than all of them --
#   docs/V2_DESIGN.md's route row, "rework -> do with the blocking findings
#   as prefill". A finding the conductor accepted or rejected is a record,
#   not an order for the next round, and handing it forward verbatim is how
#   a round gets worked on something already ruled settled. Read off the
#   submitted fields alone, never off a form or
#   assembly name: run-an-issue's consolidate and plan-to-execute,
#   explore-an-idea's spec, and run-a-gate's own `work`-segment impasse
#   ruling all reach the same `rework` verb submitting no such table, and
#   `None` here is exactly what leaves their carry-everything behaviour
#   untouched.
# Rejected: filtering the panel's own concatenated findings text by matching
#   each call against it. A call is prose a conductor wrote about a finding,
#   not a handle on it; substring-matching it back onto the panelists' blob
#   guesses, and the round it guesses wrong for is the one nobody re-reads.
#   Taking the conductor's own quoted block instead is why ROUTE.toml's
#   `finding` item says to quote rather than number.
def _blocking_calls(fields, word="blocking"):
    """The `word`-called blocks of a submitted `calls` table (`blocking`
    unless the caller names another word, or a tuple of words), verbatim and
    in the order the conductor ruled them -- `None` where the submit carried
    no such table at all.

    `None` and `""` are different answers: no table means carry what the panel
    returned, a table calling nothing `word` means carry nothing.
    """
    rows = (fields or {}).get("calls")
    if not isinstance(rows, list):
        return None
    words = (word,) if isinstance(word, str) else word
    return "\n\n".join(
        str(r.get("finding", "")).strip() for r in rows
        if isinstance(r, dict) and forms.leading_word(r.get("call", "")) in words)


# [seam-findings-history]
# Rationale: issue113's run-level round-cap owes its ask the findings of
#   every round it counted, not only the round that tripped it (C1-findings)
#   -- the same "blocking calls narrowed where the round's own done-entry
#   carried a `calls` table, else every panelist's own non-empty `findings`
#   joined and attributed" rule `_panel_judged_rework` already applies to
#   the live round, walked here over the steps the cap's own count
#   (`review_yield.seam_round_steps_since_release`) handed it instead of
#   the one step `_perform` is deciding. Living beside `_blocking_calls`
#   rather than in `review_yield.py` reuses that reader directly rather
#   than a second copy of its own narrowing rule.
# The calls an ask still owes its reader: every word that sends a finding
# on to work -- a gate review's `blocking`, a spec or plan seam's `writer`
# -- and none that disposes of it (`accepted`, `rejected`).
_OPEN_CALLS = ("blocking", "writer")


def _seam_findings_history(st, round_steps):
    """The findings of each round in `round_steps`, oldest first, each block
    formatted exactly as `_panel_judged_rework` formats the current round's
    own findings prefill -- blocking calls narrowed where that round's own
    done-entry carried a `calls` table, else every panelist's own
    non-empty `findings` joined and attributed."""
    return "\n\n".join(
        _round_findings(st, rstep, st["done"].get(rstep["id"], {}).get("fields"),
                        carry=_OPEN_CALLS)
        for rstep in round_steps)


def _round_findings(st, step, fields, carry="blocking"):
    """One round's own findings block, as the next round or an ask reads it:
    the panel's returns, each attributed to the voice that raised it -- or,
    where the deciding submit carried a per-finding `calls` table, its
    blocking-called blocks alone (`_blocking_calls`) -- with the conductor's
    own `orders` (the route forms' 2026-09-05 field) ahead of either, marked
    as the conductor's. A status word there (`waived: none`) is no order and
    carries nothing. A round with no panel and no orders reads as `""`.
    One writer for `_panel_judged_rework`'s live round and
    `_seam_findings_history`'s landed ones, so an ask reads each round the
    way the round after it did."""
    findings = "\n\n".join(
        f"[{r['child'].rsplit('.', 1)[-1]}] {(r.get('fields') or {}).get('findings', '')}"
        for r in st["returns"].get(step["id"], []))
    called = _blocking_calls(fields, carry)
    if called is not None:
        findings = called
    orders = str((fields or {}).get("orders", "") or "").strip()
    if orders and forms.leading_word(orders) not in ("waived", "unknown", "working"):
        findings = f"[conductor] {orders}\n\n{findings}" if findings else f"[conductor] {orders}"
    return findings


# [impasse-ruling-carries]
# Rationale: #107 -- the impasse form is the one form in the assembly written
#   for a conductor to rule on a *pattern* rather than a round ("Rule on the
#   loop, not on the findings"), and its `ruling` note makes a `rework`
#   legitimate only where the conductor "can name what that round changes
#   that the last three did not". `why` is where that naming goes, and
#   nothing read it: the impasse step is minted with no panel, deliberately
#   (a fourth fresh-context reader is the loop, not the way out), so
#   `_panel_judged_rework`'s guard returned nothing and `_perform` fell back
#   to the impasse step's *own* prefill -- the findings it was minted with.
#   The round the ruling created therefore arrived holding exactly what the
#   round before it held. From the reworking planner's seat an impasse rework
#   and an ordinary one were indistinguishable, which is close to engineering
#   a fourth identical round out of the mechanism whose whole purpose is
#   escaping the third.
#   The sibling path already did this right and is what makes it a defect
#   rather than intent: an impasse `up` hands the same submit's fields to
#   `_pause_gate`, so the conductor's reasoning reaches the tier above. Same
#   form, same submit, one plumbed and one not.
# Rejected: changing the `panel` guard itself. Carrying the ruling is a
#   different question from re-deriving the panel's findings -- the guard is
#   right about the second -- so the branch returns the ruling rather than
#   the guard learning a second job (#107's own breadcrumb says the same).
# Rejected: reading the ruling out of the journal at the next round's mint.
#   The fields are in hand here, and a second reader of the same submit is a
#   second thing to keep in step with the form.
def _impasse_ruled_rework(step, fields):
    """The prefill an impasse ruling's own `rework` mints its round with: the
    findings that caused the impasse, with the conductor's `why` ahead of
    them and marked as the conductor's -- `_panel_judged_rework`'s own
    `orders` idiom, applied to the one deciding step that carries no panel.

    `None` where the ruling wrote no `why` the next round can act on, which
    leaves the carry-what-caused-it behaviour this had before exactly as it
    was."""
    carried = step.get("prefill") or {}
    why = str((fields or {}).get("why", "") or "").strip()
    if not why or forms.leading_word(why) in ("waived", "unknown", "working"):
        return None
    ruled = f"[conductor] {why}"
    findings = str(carried.get("findings", "") or "").strip()
    return {**carried,
            "findings": f"{ruled}\n\n{findings}" if findings else ruled}


# [panel-judged-rework]
# Rationale: a rework decided at a segment's own route step is the same act
#   whichever voice decided it -- the merged verdict resolving to `rework`
#   (explore-an-idea's spec) or a conductor's form submitting on the step
#   (run-a-gate's review, run-an-issue's consolidate and plan-to-execute).
#   Both owe the fresh round whatever the round was judged on as prefill,
#   and both spend the segment's `impasse-after` count. So both live here,
#   on the verb, rather than at either caller: run-a-gate's review resolves
#   `revise` to `release` now, so the panel-return path never reaches
#   `rework` for it again and an outlet checked only there would silently
#   stop firing.
# Rationale: the guard reads the step, not only its panel. A route step with
#   no panel is real now -- run-an-issue's plan seam mints its critic panel
#   on fresh cuts only (`panel-rounds`, ASSEMBLY.toml), so an incorporated
#   PLAN_TO_EXECUTE round is the conductor's form alone -- and a
#   conductor sending such a round back owes the next round its `orders`
#   and spends the count exactly as a panel-judged one does. Keying on
#   `panel` alone read that step as the impasse ruling and carried nothing.
# Rejected: duplicating the check on the ordinary submit path. Two counts
#   that happen to agree is the shape that drifts, and the round past the
#   allowance is exactly the round nobody re-tests by hand.
# See: `_blocking_calls` -- `fields` is the deciding submit's own, defaulted
#   so a caller with no table to filter by reads as one.
def _panel_judged_rework(wid, asm, seg, step, fields=None):
    """(prefill, outlet) for a rework decided at `seg`'s own route step: the
    panel's findings concatenated, never summarised, and attributed to the
    panelist that raised them -- or, where the deciding submit carried a
    per-finding `calls` table, the blocking-called blocks of that table
    alone (`_blocking_calls`) -- with the conductor's own `orders` ahead of
    them, plus any `horizon` the round just judged wrote, which
    `skills/planner/SKILL.md` promises the next round arrives holding. A
    route step with no panel carries the orders alone. `outlet` is the
    segment's impasse form once `impasse-after` rounds have already landed
    on this artifact -- `0` makes the first send-back itself the ruling --
    so a conductor rules on the send-back rather than the run looping.

    Where `step` is neither a panel step nor the segment's own route form
    the outlet is always `""` -- an impasse ruling's own `rework` never
    spends the count, which is what makes the outlet a way out rather than
    a wall -- and the prefill is `_impasse_ruled_rework`'s: what caused the
    impasse, with the conductor's own `why` ahead of it (#107), or `None`
    where the ruling wrote no `why` the round can act on, which is the
    plain carry this had before.

    The guard is two reads of the step itself. `panel` is written onto the
    step's own journal entry identically however the step came to exist --
    by `skeleton()` from a statically declared `[segment.transition]`
    (consolidate, plan-to-execute, run-a-gate's review, explore-an-idea's
    spec) or by `_mint_segment_round` on a later round. The other half is the
    step standing on the segment's own transition form (`deciding_spec`'s
    own test), which is what a panel-less route round is. The one step
    neither matches is the impasse ruling: a single-conductor decision
    minted with no `panel` key, on the segment's `impasse-form`, under
    every caller.
    """
    on_route_form = bool(step.get("form")) and \
        step.get("form") == seg.get("transition", {}).get("form")
    if not step.get("panel") and not on_route_form:
        return _impasse_ruled_rework(step, fields), ""
    st = runmod.state(wid)
    findings = _round_findings(st, step, fields)
    # The round just judged is the segment's own most recent non-panel step --
    # the same lookup a panelist's own prefill uses (`_open_child`) to find
    # the artifact it is reviewing. Carried under the producing form's own
    # key, not a name this engine chose, so `test_promises.py`'s mint sweep
    # does not hold this call to it the way it holds `findings`.
    prior = [s for s in st["steps"] if s["segment"] == seg["id"] and s["id"] != step["id"]]
    produced = st["done"].get(prior[-1]["id"], {}).get("fields", {}) if prior else {}
    carried = {"horizon": produced["horizon"]} if produced.get("horizon") else {}
    # `impasse-after = 0` is a declaration, not an absence: the opening round
    # was never sent back (`rework_rounds` reads 0 there), so 0 >= 0 makes
    # the first send-back the ruling. A segment declaring no `impasse-after`
    # at all never reaches the outlet, as before.
    after = seg.get("impasse-after")
    looped = after is not None and runmod.rework_rounds(st, asm, seg["id"]) >= after
    return {"findings": findings, **carried}, (seg.get("impasse-form", "") if looped else "")


# [one-look]
# Rationale: ruling, 2026-09-25 -- a spec or a plan gets one round of
#   reviewers. After it, the writer incorporates what the panel said by its
#   own judgement, free to reject any of it, and the run moves on; only a
#   severe deficiency -- one that changes which problem is being solved, or
#   the fundamental thing the next step codes -- sends the artifact back,
#   and then it is rewritten from scratch, holding forward-looking orders
#   and never the last draft or its findings.
#   Severity is the conductor's reading of the round, not a finding's label
#   (Tommy, 2026-09-30): the panel finds, the conductor judges each finding
#   against the whole artifact, and a rewrite can be several kept findings
#   read together. So the calls say only whether a finding holds (`writer`
#   or `rejected`), and a rewrite carries the conductor's `orders` alone --
#   the synthesis is theirs to state. Measured before: issue219 (sonnet
#   conductor) called 36 plan findings `severe` one by one, 9 of them ones
#   the critic had itself marked "not a gap", and all 5 rewrites opened
#   "Same next chunk".
#   Measured before the
#   ruling: `rework` carried each round's blocking findings into the next
#   draft and a cold panel read every draft, so the spec grew every round
#   (issue120: 13KB to 32KB over ten rounds on a 5KB issue) and each
#   rework's own additions were the next panel's findings. Spec review went
#   from 10% of a run's tokens to 29%.
#   `incorporate` is the default word after a review: one pass by the
#   writer, carrying the findings, and no panel on the round it mints, so
#   the conductor releases what comes back. `rewrite` is a fresh artifact:
#   `restarts`, a panel of its own, and the conductor's `orders` as its
#   whole prefill.
# Rejected: keeping `rework` and tuning `impasse-after`. The word means
#   "another pass with the findings", which is incorporate's half and not
#   rewrite's, and a count cannot tell a writer's pass from a fresh start.
def _check_one_look(asm, st, outcome, fields):
    """Refuse, before the submit lands, the send-back the ruling above does
    not allow: a second incorporation of the same artifact. A `rewrite`
    needs orders to be written from."""
    if not outcome:
        return
    seg, does = outcome
    verbs = {v.strip().split(" ")[0] for v in does.split(";")}
    if "incorporate" in verbs:
        if runmod.rework_rounds(st, asm, seg["id"]) >= 1:
            raise SystemExit(render.refusal(
                "resolution", "this artifact has already incorporated its review "
                "-- the next word is a release",
                escape="pass, or rewrite if what came back is severely wrong"))
    if "rewrite" in verbs:
        orders = str((fields or {}).get("orders", "") or "").strip()
        if not orders or forms.leading_word(orders) in ("waived", "unknown", "working"):
            raise SystemExit(render.refusal(
                "orders", "a rewrite starts from these alone -- say what must "
                "be done, forward",
                escape="write the orders, or incorporate instead"))


def _round_capped(wid, asm, seg, tseg):
    """Pause `tseg` up and return True where this seam has sent back
    `round-cap` rounds in a row with none released -- issue113's run-level
    ceiling, shared by every verb that sends a round back."""
    cap = seg.get("round-cap")
    if not cap:
        return False
    st = runmod.state(wid)
    since = review_yield.seam_round_steps_since_release(st, seg, asm)
    if len(since) < cap:
        return False
    why = (f"{review_yield.seam_label(seg)} has sent back {len(since)} "
           f"rounds in a row with none released, at its round-cap of {cap}")
    _pause_gate(wid, tseg, why, {"why": _seam_findings_history(st, since)})
    return True


# [rewrite-cap]
# Rationale: ruling, 2026-09-25 (after one look landed): a spec or a plan
#   gets one major rewrite, then the question goes up. Counting rounds could
#   not say that -- an incorporation and a rewrite's own look are rounds too
#   -- so these seams count rewrites instead, since the seam last released
#   or since a pause's answer opened a round (the answer is the ruling).
#   Incorporation needs no cap of its own: it is refused a second time on
#   one artifact, and only a rewrite or an answer makes a new one.
def _rewrite_capped(wid, asm, seg, tseg):
    """Pause `tseg` up and return True where this seam has already been
    rewritten `rewrite-cap` times since it last released."""
    cap = seg.get("rewrite-cap")
    if not cap:
        return False
    st = runmod.state(wid)
    since = review_yield.seam_round_steps_since_release(st, seg, asm)
    rewrites = sum(1 for s in since if s.get("rewrite"))
    if rewrites < cap:
        return False
    why = (f"{review_yield.seam_label(seg)} has been rewritten {rewrites} "
           f"time{'s' if rewrites != 1 else ''} since it last released, at its "
           f"rewrite-cap of {cap}, and a finding still calls for another")
    _pause_gate(wid, tseg, why, {"why": _seam_findings_history(st, since)})
    return True


def _incorporated(wid, seg, step, fields):
    """The prefill an `incorporate` mints its writer's round with: every
    finding the panel returned, attributed -- or, where the conductor's
    `calls` table is present, the ones it called `writer` -- the conductor's
    own `orders` ahead of them, and any `horizon` the judged round wrote."""
    st = runmod.state(wid)
    prior = [s for s in st["steps"] if s["segment"] == seg["id"] and s["id"] != step["id"]]
    produced = st["done"].get(prior[-1]["id"], {}).get("fields", {}) if prior else {}
    prefill = {"findings": _round_findings(st, step, fields, carry="writer")}
    if produced.get("horizon"):
        prefill["horizon"] = produced["horizon"]
    return prefill


# [impasse-verbs]
# Rationale: `advance` and `rework` used to be handled by a stand-alone
#   impasse actor, a reader outside the outcome mechanism. Absorbing the
#   ruling as an ordinary `decides` field meant `_perform` needed two verbs
#   nothing else spells:
#   `transition` mints the segment's own transition alone (what `advance`
#   does, over a live revise -- the panel's findings stay the record that
#   says so), and `rework` refills through the segment's rework-form -- or
#   its step-form where none is declared, run-a-gate's work -- carrying
#   forward the deciding step's own prefill (what caused the impasse) rather
#   than the ruling fields just submitted (the verdict on it). The submitted
#   fields still reach `_panel_judged_rework`, but only so a conductor's own
#   per-finding `calls` can narrow the panel's findings to the blocking ones
#   (`_blocking_calls`); an impasse ruling carries no such table and is
#   unaffected. `up` is not a third verb either: every row that still
#   declares it as a value (`work`/`review` in `run-a-gate`, `understand`'s
#   and `plan`'s own impasse in `run-an-issue`) spells it `pause` (or
#   `pause <target>`), the same case below the bare `up` CLI verb
#   (`cmd_up`) also reaches -- see `[pause-gate]` for why both
#   spellings are kept, ruled rather than left to accumulate (issue84.g2).
#   Gate adjudication added two more the same way: `remint` mints a fresh
#   dispatch/adjudication pair from the plan
#   field the deciding step's own form carries, and `close` closes the
#   not-done step this step's segment holds whose id matches the decided
#   field's own argument, and every step paired with it by `child`.
# Rejected: naming the verbs `advance`/`rework` to match the outcome values.
#   Verbs and values are already separate vocabularies elsewhere (`cycle`'s
#   value is `cycle`, its verb is `refill`); reusing the impasse's words here
#   would read that coincidence as a rule.
# See: #32 -- gate adjudication still carries its own interpreter.
def _perform(wid, asm, seg, does, fields, step):
    """The outcome's verbs, in order, against freshly folded state -- the
    deciding submit is already journaled, so `skip` and `close` never touch
    it. An amend's reason is the agent's own words -- the decided field's
    raw submitted text -- not the assembly's `does` string, which is a
    mechanism label no principal reading the amend log asked for.

    `skip` never closes a terminal step: `execute`'s own terminal step sits
    not-done for the whole time its gates run, exactly like every other step
    `skip` sweeps, so without this a replan mid-run would amend-close the run's
    own close step along with the gates it means to drop -- a run the amend
    log says is done and CLOSE.toml never filled. No existing `skip` target
    reaches a terminal step, so this narrows nothing already relied on."""
    field = _decided_here(asm, step)
    reason = str(fields.get(field, does)).strip() if field else does
    for verb in filter(None, (v.strip() for v in does.split(";"))):
        word, _, target = verb.partition(" ")
        tseg = next((s for s in asm["segment"] if s["id"] == (target or seg["id"])), seg)
        if word == "skip":
            st = runmod.state(wid)
            for s in st["steps"]:
                if (s["segment"] == tseg["id"] and s["id"] not in st["done"]
                        and not s.get("terminal")):
                    journal.append(wid, "amend", action="close", segment=tseg["id"],
                                   step=s["id"], reason=reason, anchor=s.get("anchor", False))
        elif word == "refill" and tseg.get("interior") == "board":
            _mint_transition(wid, tseg, prefill=fields)
        elif word == "refill":
            # A refill is a fresh artifact -- "the plan recut", "a fresh
            # first cut" -- so the send-back count starts over.
            _mint_segment_round(wid, asm, tseg["id"], prefill=fields, restarts=True)
        elif word == "transition":
            _mint_transition(wid, tseg)
        elif word == "incorporate":
            if _round_capped(wid, asm, seg, tseg):
                continue
            _mint_segment_round(wid, asm, tseg["id"],
                                prefill=_incorporated(wid, tseg, step, fields),
                                form=tseg.get("rework-form", ""))
        elif word == "rewrite":
            if _round_capped(wid, asm, seg, tseg) or _rewrite_capped(wid, asm, seg, tseg):
                continue
            rewrite = {"orders": str(fields.get("orders", "")).strip()}
            _mint_segment_round(wid, asm, tseg["id"], prefill=rewrite,
                                restarts=True, rewrite=True)
        elif word == "rework":
            if _round_capped(wid, asm, seg, tseg):
                continue
            judged, outlet = _panel_judged_rework(wid, asm, tseg, step, fields)
            if outlet:
                journal.append(wid, "step", id=f"{tseg['id']}-a{secrets.token_hex(2)}",
                               segment=tseg["id"], form=outlet, filler="conductor",
                               # The count the outlet fired on, so the room
                               # states it and the form need not name a number
                               # that goes stale the next time `impasse-after`
                               # changes -- which is how it last went stale.
                               prefill={**judged, "arrival": "rework-rounds",
                                        "sent-back": str(runmod.rework_rounds(
                                            runmod.state(wid), asm, tseg["id"]))},
                               anchor=False, terminal=False, validates="", source="mint")
                continue
            _mint_segment_round(wid, asm, tseg["id"],
                                prefill=step.get("prefill") or {} if judged is None else judged,
                                form=tseg.get("rework-form", ""))
        elif word == "pause":
            _pause_gate(wid, tseg, reason, fields)
        elif word == "remint":
            _mint_gates(wid, seg, fields.get(target) or [])
        elif word == "close":
            parts = str(fields.get(field, "")).split(None, 1)
            target_id = parts[1].strip() if len(parts) > 1 else ""
            st = runmod.state(wid)
            hit = next((s for s in st["steps"] if s["id"] == target_id), None)
            if hit:
                for s in st["steps"]:
                    if s.get("child") == hit.get("child") and s["id"] not in st["done"]:
                        journal.append(wid, "amend", action="close", segment=s["segment"],
                                       step=s["id"], reason=reason,
                                       anchor=s.get("anchor", False))
        elif word == "commit":
            _commit_gate(wid, asm, step)
        elif word == "settle":
            _settle_execution(wid, asm)


# [pause-gate]
# Rationale: `up` used to `release` -- mint nothing, so the run walked past
#   whatever decided it straight to its own terminal step. The gate spec is
#   what's wrong here, not the diff, and the only hand that can fix a spec is
#   whoever wrote it: the parent that dispatched this run. Pausing carries
#   the ask up as a step the parent's own `state()` already stands on --
#   `_ordered`'s existing grouping-by-segment does the placing, once the
#   reorder below moves it before the pair the parent already holds live --
#   rather than a return the parent would have to go open this child to
#   read. Nothing here touches `state()`'s own fold: the ask is an ordinary
#   step, the marker is an ordinary step, and both are recognized by the
#   plain keys they carry.
#
#   issue84.g1 folded three once-separate silent-return branches -- no
#   parent at all, the parent's journal gone, the parent no longer holding
#   the dispatching step -- into one fact from the asker's own side: is
#   there anywhere else to stand this ask. A single `pstep` lookup below is
#   `None` for any of the three reasons, and that one value drives both
#   downstream decisions -- where the ask is minted, and whether the parent
#   also needs a reorder -- rather than three branches each repeating the
#   same two consequences. When nothing is reachable the ask mints into
#   `wid`'s own journal instead, in `tseg`'s segment: `resumes=wid` already
#   names the run the answer resumes, and when nothing is reachable that
#   run is this one -- the amend-close the caller already did (see
#   `cmd_up`) retired whatever this ruling was made at, though not
#   necessarily every sibling already sitting in the same segment (see
#   issue84.g2's own addition below).
# Rejected: closing this run and returning through the ordinary `cmd_close`
#   path the way an advance does. That return only reaches the parent once
#   this run itself closes, and a run closed on `up` is a run gone quiet --
#   not one standing on a live ask the parent can see without opening it.
# Rejected: keeping the three silent notes (issue84.g1) and minting an ask
#   alongside them. A note and an ask about the same event is one fact told
#   twice, and the second telling is the only one anybody standing at the
#   run can act on -- the note would be dead weight from the moment this
#   landed.
#
# issue84.g2 added three more fixes here, all because they live in this
# same function. First, the ask's own prefill used to key the paused unit
# under `"gate"` and describe it in prose as one -- true only of the
# reachable-parent path above, and wrong once an issue run itself, not only
# a gate under it, could self-mint the same ask. `"paused"` names the unit
# generically, whatever tier it runs at, and `attempted` falls back through
# the dispatched orders' own `scope`/`purpose`, then the run's own `title`,
# then `wid` itself, so a root run opened with none of the three still
# renders something a principal can read rather than an empty string.
#
# Second, a sibling-ordering defect that turns out not to be self-mint-only
# at all: a step-form segment's own transition (`review`, `understand`'s
# own consolidate) mints untouched, at `open`, alongside that segment's
# round-one interior step (`skeleton()`), and ruling `up` before that round
# ever submits leaves the transition sitting there not-done -- in `wid`'s
# own journal, in `tseg`'s segment, regardless of whether the ask above
# landed there too or went to a reachable parent instead, because the
# marker below always lands in `wid`'s own journal. At plain append order
# the untouched sibling would still precede the marker (and, self-minted,
# the ask) in `_ordered`'s own within-segment order, so `wid`'s own
# `state()["current"]` would resolve to the stale sibling -- driven live
# against a *reachable-parent* gate ruled `up` from its own first round:
# the parent correctly stood on the ask, but the child's own `cmd_status`
# showed `review`, not `paused`. Reordering the marker (and, self-minted,
# the ask) ahead of the sibling is the one fix both shapes need.
#
# Third, that reorder held only through the pause moment: `_resume_paused_
# child`'s own `_mint_segment_round` call is sibling-blind, plain-appending
# the fresh round behind whatever already stood in the segment -- so once
# the marker closes, the sibling it only ever leapfrogged (never itself
# reordered) resurfaces ahead of the fresh round the same way. The marker
# now carries the sibling's id forward (`sibling`, `""` when none was
# found) so `_resume_paused_child` can reorder the fresh round ahead of it
# too, once it knows one exists.
# Rejected: closing the untouched sibling outright, the way `cmd_up`
#   already closes whatever `current` stood on. It is not what was ruled
#   on -- ruling `up` from `work-1` says nothing about `review` -- and
#   closing it would strand the ordinary round `review` exists to receive
#   once the paused segment resumes and completes.
def _pause_gate(wid, tseg, reason, fields, resume_form="", resume_filler=""):
    """`up`'s own verb: an ask minted where whoever answers it can see it --
    the parent standing on the step that dispatched this run, reordered
    before the still-live pair so it is what the parent's own `state()`
    stands on next, filled by the parent's conductor; or -- nothing
    reachable there -- this run's own journal, reordered ahead of any
    untouched sibling transition instead (see `[pause-gate]`), filled by
    the run's principal and never by a process `drive` starts.
    A marker minted here either way, in the segment the answer resumes,
    reordered ahead of the same sibling regardless of which path the ask
    took -- the marker is what every path's own `state()` must find."""
    st = runmod.state(wid)
    pwid, pstep_id = st.get("parent"), st.get("parent_step")
    pstep = None
    # `journal.unbound()`: `pwid` is this run's own recorded parent, not a
    # caller-named id (see `[return-delivery-is-not-a-fresh-resolution]`,
    # `engine/journal.py`) -- without it, a bound child's own `up` could
    # never reach the parent that dispatched it and would always fall to
    # this run's own journal instead.
    with journal.unbound():
        if pwid and journal.exists(pwid):
            pst = runmod.state(pwid)
            pstep = next((s for s in pst["steps"] if s["id"] == pstep_id), None)
    ask_wid, ask_seg = (pwid, pstep["segment"]) if pstep else (wid, tseg["id"])
    orders = st.get("prefill") or {}
    ask = {"paused": wid,
           "attempted": (orders.get("scope") or orders.get("purpose")
                        or st.get("title") or wid),
           "ask": reason}
    calls = fields.get("calls")
    if isinstance(calls, list) and calls:
        ask["findings"] = "\n\n".join(
            f"[{r.get('call', '')}] {r.get('finding', '')}"
            for r in calls if isinstance(r, dict))
    elif fields.get("why"):
        ask["findings"] = fields["why"]
    ask_id = f"{ask_seg}-a{secrets.token_hex(2)}"
    # [ask-filler-is-who-it-stands-before]
    # Rationale: an ask landing in the parent's journal is the parent's
    #   conductor's to answer; one landing in this run's own journal -- the
    #   issue tier, or a parent nothing here can reach -- is its principal's,
    #   outside the engine. It read `conductor` either way, and `drive` took
    #   that literally: issue811's first run (2026-09-06) spawned the run's
    #   own conductor into the round-cap's ask and it ruled CONTINUE on
    #   itself twice before the human saw the question. Who holds the pen is
    #   the whole fix; nothing reads the answer.
    # Rejected: checking the answer's content. Structure that audits an
    #   agent's behaviour goes (docs/AGENT_GUIDE.md); the filler is structure
    #   that decides who answers.
    journal.append(ask_wid, "step", id=ask_id, segment=ask_seg,
                   form="skills/gate-conductor/forms/ASK.toml",
                   filler="conductor" if pstep else runmod.PRINCIPAL,
                   prefill=ask, resumes=wid, anchor=False, terminal=False,
                   validates="", source="mint")
    if pstep:
        journal.append(pwid, "amend", action="reorder", segment=pstep["segment"],
                       step=ask_id, before=pstep_id, reason=reason, anchor=False)
    # The untouched open-minted sibling `tseg`'s own segment may already
    # hold (`review`, `understand`'s own consolidate) -- present whether or
    # not the ask above landed in this same journal, since the marker below
    # always does. Left alone it would precede the marker (and, on the
    # self-mint path, the ask too) in `_ordered`'s own within-segment order.
    sibling = next((s["id"] for s in st["steps"]
                    if s["segment"] == tseg["id"] and s["id"] not in st["done"]
                    and not s.get("terminal")), None)
    if sibling and not pstep:
        journal.append(wid, "amend", action="reorder", segment=tseg["id"],
                       step=ask_id, before=sibling, reason=reason, anchor=False)
    # [marker-carries-resume-form]
    # Rationale: `resume_form`/`resume_filler` are stashed onto the marker
    #   itself, not derived again at resume time -- the marker is already
    #   the one journal entry every resume path (`_resume_paused_child`)
    #   reads to find its way back, and what a panelist's own step was
    #   overridden to at open (`_open_child`'s panel branch) is otherwise
    #   nowhere else durable to read it back from. Empty on the impasse's
    #   own `does = "pause"` rows (`_perform`), reproducing today's
    #   behaviour there exactly -- only `cmd_up`'s same-segment case ever
    #   supplies either.
    marker_id = f"{tseg['id']}-a{secrets.token_hex(2)}"
    journal.append(wid, "step", id=marker_id, segment=tseg["id"], paused=tseg["id"],
                   sibling=sibling or "", filler="conductor", anchor=False,
                   terminal=False, validates="", source="mint",
                   resume_form=resume_form, resume_filler=resume_filler)
    if sibling:
        journal.append(wid, "amend", action="reorder", segment=tseg["id"],
                       step=marker_id, before=sibling, reason=reason, anchor=False)


# [gate-commit]
# Rationale: `_issue_tier` is checked structurally, not the branch/worktree
#   fields alone -- `cmd_open` stamps both onto every root run's opening
#   entry, including a non-issue-tier one with no real branch behind it
#   (`branch=wid`, unconditional, even though no such git branch was ever
#   made). Trusting the fields without this check would let a misdeclared
#   outcome commit into whatever directory a non-issue run happened to open
#   from. `_commit_open`'s own rule for "nothing to land" is reused rather
#   than re-derived: a real commit failure and the ordinary nothing-staged
#   case both surface as one nonzero exit, and neither this verb nor that
#   one can tell them apart from the exit code alone. Both guards below
#   land that same journaled no-op rather than a refusal -- the corollary
#   (docs/V2_DESIGN.md) requires a check's escape be one journaled step
#   available to the agent being checked, and neither condition names a
#   field the agent can fill or a fix within its reach: `issue19`, opened
#   before the worktree feature existed, carries neither `branch` nor
#   `worktree` and never will unless a human replans it.
# Rejected: checking `st.get("branch")` truthiness alone -- a non-empty
#   string that names nothing real is exactly what a non-issue-tier run
#   carries, so a truthiness check would pass on the one case it exists to
#   catch.
def _gate_subject(gate_id, purpose):
    """The gate's own commit subject: `<gate_id>: ` followed by the first
    line of `purpose`, markdown emphasis stripped and a redundant leading
    `<gate_id>.`-style label dropped when the purpose already opens with
    one. A plan's purpose field is prose for a human reading the spec, not
    a commit subject, and sometimes carries both a label and emphasis
    meant for that reading rather than this one. Bounded to 100
    characters total -- the repository's own habit, not an imported
    convention -- so it still reads as a subject line rather than the
    prose it was drawn from. A subject over that bound is cut back to the
    nearest word boundary and ends with an ellipsis, so it reads as
    visibly truncated rather than a sentence that just stops mid-word."""
    first = purpose.splitlines()[0] if purpose else ""
    first = first.replace("**", "").replace("__", "").lstrip("#").strip()
    label = f"{gate_id}."
    if first.startswith(label):
        first = first[len(label):].strip()
    prefix = f"{gate_id}: "
    subject = f"{prefix}{first}"
    if len(subject) <= 100:
        return subject
    room = 100 - len(prefix) - 1
    truncated = first[:room].rstrip()
    if " " in truncated:
        truncated = truncated.rsplit(" ", 1)[0]
    return f"{prefix}{truncated}…"


# [rungs-are-transcribed-not-authored-early]
# Rationale: issue166 -- SPEC.toml used to write `map/parents.jsonl`'s row
#   at spec time, before any code carried the anchor, which dangled that row
#   for the whole run and turned the fast suite red for anyone who followed
#   the instruction. The spec still names the id, as structured data
#   (`rungs`), so the implementer transcribes rather than mints one; the
#   engine writes the row itself, mechanically, the moment the anchor
#   actually lands -- here, immediately before the gate that landed it is
#   committed, so the pointer and its target arrive in the same commit. A
#   secretary's move: an anchor that never lands writes no row, and nothing
#   here refuses a gate for failing to land one (docs/AGENT_GUIDE.md, "the
#   engine is a secretary, never a guard").
# Rejected: `from tools.code_map import parents` to read the anchor and
#   dangling sets. `engine/install.py`'s own `_plan` ships exactly
#   `assemblies`, `standards`, `engine`, `spine` and the skill bundles --
#   `tools/` is not among them, so an installed copy has no `tools/` on its
#   `PYTHONPATH` and that import raises `ModuleNotFoundError` the first time
#   a real reservation reaches this function. `docs/AGENT_GUIDE.md` also
#   names `tools/` as decoupled tooling; the engine depending on it inverts
#   the direction that decoupling is for. So this reads the git index and
#   `map/parents.jsonl` itself, narrowly -- not by importing the module that
#   already knows how, and not by copying its grammar wholesale.
def _reserved_rungs(wid):
    """This run's own `rungs` reservation, off its prefill -- folded there by
    consolidate's own `carries` the moment the spec released. `[(anchor id,
    (parent id, ...)), ...]`; absent, blank, or not a list all read as no
    reservation, the ordinary case -- most runs climb through code that
    already exists and reserve nothing."""
    st = runmod.state(wid)
    rows = (st.get("prefill") or {}).get("rungs")
    if not isinstance(rows, list):
        return []
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        anchor = str(row.get("anchor", "")).strip()
        if anchor:
            out.append((anchor, tuple(str(row.get("parents", "")).split())))
    return out


# The two authored shapes an anchor comment takes (standards/purpose.md): a
# line holding nothing but its bracketed slug, `# [id]` in Python or
# `<!-- [id] -->` in markdown -- and nothing looser, so a mention of the slug
# in prose or a docstring never counts as landing it.
_ANCHOR_LINE_PATTERNS = (
    r'^[ \t]*#[ \t]*\[{slug}\][ \t]*$',
    r'^[ \t]*<!--[ \t]*\[{slug}\][ \t]*-->[ \t]*$',
)


def _anchor_landed(worktree, anchor):
    """True when the staged tree -- what `_git_add_tracked` just staged --
    carries `anchor`'s own marker line. `git grep --cached` reads the index
    directly, so a brand-new file the gate's own diff just added is seen the
    moment it is staged, with no dependency on git having committed yet and
    none on `tools/code_map`."""
    slug = re.escape(anchor)
    args = ["grep", "--cached", "-I", "-q", "-E"]
    for pattern in _ANCHOR_LINE_PATTERNS:
        args += ["-e", pattern.format(slug=slug)]
    return _git(worktree, *args).returncode == 0


def _parents_jsonl_ids(path):
    """Every id `map/parents.jsonl` already carries a row for -- one JSON
    object per line, read directly rather than through
    `tools.code_map.parents.read_parents` (see the rationale above). A
    missing file reads as no rows, the ordinary state of a fresh worktree
    before this ever writes to it."""
    path = pathlib.Path(path)
    if not path.exists():
        return set()
    ids = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rid = json.loads(line).get("id")
        if rid:
            ids.add(rid)
    return ids


def _land_reserved_rungs(wid, worktree):
    """For each anchor this run reserved at consolidate, write
    `map/parents.jsonl`'s row the moment that anchor actually landed in this
    gate's own diff -- called from `_commit_gate`, after `_git_add_tracked`
    has staged the diff, and before the commit that follows. A reservation
    whose anchor never lands, or that already carries a row, writes nothing:
    this is a transcription of an authored fact, never a check on whether
    the gate landed it."""
    reserved = _reserved_rungs(wid)
    if not reserved:
        return
    path = pathlib.Path(worktree) / "map" / "parents.jsonl"
    have = _parents_jsonl_ids(path)
    landed = [(anchor, parent_ids) for anchor, parent_ids in reserved
             if anchor not in have and _anchor_landed(worktree, anchor)]
    if not landed:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for anchor, parent_ids in landed:
            f.write(json.dumps({"id": anchor, "parents": list(parent_ids)}) + "\n")
    _git(worktree, "add", "--", "map/parents.jsonl")


def _commit_gate(wid, asm, step):
    """One commit for the gate that just advanced: staged against the run's
    own worktree, on its own branch, the message naming the gate, carrying
    the gate spec's own purpose and scope verbatim in the body, and the
    gate's own work id as a trailer. Nothing staged is the ordinary case
    wherever a gate's proof left no tracked diff -- a journaled no-op,
    never a refusal and never an empty commit. Neither guard below ever
    reaches `git`: each is the same shape of no-op, so a run this verb
    cannot commit for advances instead of stopping on an escape it has no
    way to take."""
    child = step.get("child", "")
    if not _issue_tier(asm):
        journal.append(wid, "note", id=f"n{secrets.token_hex(2)}",
                        kind_detail="observation", about="commit",
                        text=f"{child or wid} is not an issue-tier run -- "
                             "no worktree or branch to commit a gate to")
        return
    st = runmod.state(wid)
    worktree, branch = st.get("worktree", ""), st.get("branch", "")
    if not worktree or not branch:
        journal.append(wid, "note", id=f"n{secrets.token_hex(2)}",
                        kind_detail="observation", about="commit",
                        text=f"{child or wid} has no branch or worktree "
                             "stamped -- nothing to commit to")
        return
    # Rationale: a gate's dispatch step still names its purpose after an
    #   amend closes it -- dispatch crashed and the work was finished by
    #   hand, or it was dropped -- but `state()["steps"]` folds a closed
    #   step out of the worklist entirely, the same gap `_minted_step_ids`
    #   documents for ids. Reading the raw journal instead means a gate
    #   closed before this commit runs still hands over the purpose its
    #   own mint recorded, rather than falling back to a bare child id.
    # Rejected: `st["steps"]`, the folded worklist -- right for what runs
    #   next, wrong for what a closed child still named.
    # See: [mint-ids-include-closed]
    gate = next((e for e in journal.read(wid)
                if e.get("kind") == "step" and e.get("child") == child
                and e.get("dispatches")), None)
    gate_id = gate["id"] if gate else child
    prefill = (gate.get("prefill") or {}) if gate else {}
    purpose = prefill.get("purpose", "")
    scope = prefill.get("scope", "")
    _git_add_tracked(worktree)
    _land_reserved_rungs(wid, worktree)
    message = (f"{_gate_subject(gate_id, purpose)}\n\n"
               f"{purpose}\n\n{scope}\n\n"
               f"Work-Id: {child or wid}")
    made = _git(worktree, "commit", "-m", message)
    if made.returncode != 0:
        journal.append(wid, "note", id=f"n{secrets.token_hex(2)}",
                       kind_detail="observation", about="commit",
                       text=f"{gate_id} staged nothing to commit")


# [settle-execution]
# Rationale: ruling 1 -- the engine decides the run is done, not the
#   conductor watching its own worklist run dry. `execute`'s advance used to
#   `commit` alone, so a run closed the moment its last gate's
#   dispatch/adjudication pair completed, whether or not anything the spec
#   committed to was ever satisfied -- "the run never closes because the
#   gate list ran out" is exactly the shape ruling 1 forbids. This is the one
#   new move: read the execution-state board every gate's advance already
#   passes through, and either refill the plan segment for another round
#   (`_mint_segment_round`, unchanged) or mint nothing, letting the run walk
#   on to its own terminal step. The engine reads dispositions and refuses
#   nothing here: `satisfied` and `deferred` count as settled, whatever
#   reason they carry, and a run that never seeded the board at all --
#   consolidate's `obligations` field is optional -- settles trivially, the
#   exact behaviour every run had before this gate. Any other row holds the
#   run open: the plan recuts and the run cannot reach its terminal step
#   while one stands, on purpose (#112 measured what silence used to cost
#   -- a run that drained to CLOSE.toml with two of its three obligations
#   unbuilt because every claimable word settled the row).
# Rejected: validating dispositions the way `validates = "board"` does for
#   the understand board. The principal's own ruling: execution state is
#   mechanical-lane fields, not a second gate the engine adjudicates.
# [satisfied-is-rechecked]
# Rationale: #74 -- a row read `satisfied` for the rest of the run on the
#   word of the gate that settled it, and rolling horizon means later gates
#   change the code earlier ones proved: issue57's o10 was satisfied at g2
#   and g4's first cut would have made it false, caught by a critic and by
#   nothing in the engine. So `satisfied` is not a word that stays true on
#   its own. At close each satisfied row's gate proof runs again against the
#   finished tree -- each distinct command once -- and a row whose proof no
#   longer passes becomes `open:` with the command and its exit, which
#   holds the run open and recuts its plan.
# Rejected: a close report listing dispositions whose code later gates
#   touched, for a human to judge. It would say "maybe" about every row a
#   later gate came near; the proof says which ones broke.
def _recheck_satisfied(wid, asm):
    st = runmod.state(wid)
    path = pathlib.Path(st["boards"].get("execution-state", ""))
    seg = next((s for s in asm["segment"] if s["id"] == "execution-state"), None)
    if not (seg and path.name and path.exists()):
        return
    gates = {s["id"]: s for s in st["steps"] if s.get("dispatches")}
    root = journal.root_for(wid)
    rows, ran, broke = boards.rows(path), {}, False
    for row in rows:
        orders = (gates.get(str(row.get("gate", ""))) or {}).get("prefill") or {}
        proof = str(orders.get("proof", "")).strip()
        if str(row.get("status", "")) != "satisfied" or not proof \
                or forms.leading_word(proof) in forms.NULL_WORDS:
            continue
        if proof not in ran:
            try:
                cmd = _resolve_command(proof, root)
                budget = checkrun.budget_for(orders)
            except SystemExit as e:
                ran[proof] = (proof, 127, str(e))
            else:
                print(f"re-running {row['gate']}'s proof: {cmd}")
                code, output = checkrun._run(cmd, str(root), budget)
                ran[proof] = (cmd, code, output)
            cmd, code, output = ran[proof]
            journal.append(wid, "check", step="close", command=cmd,
                           exit=-1 if code is None else code, output=output)
        cmd, code, _ = ran[proof]
        if code != 0:
            said = "did not finish" if code is None else f"exited {code}"
            row["status"] = (f"open: {row['gate']}'s proof no longer passes at close "
                             f"-- `{cmd}` {said}")
            broke = True
    if broke:
        _seed_board(runmod.resolve_form(asm, seg["board"]), path, rows)
        journal.append(wid, "board", segment=seg["id"], path=str(path), rows=rows)
        print(_REOPENED.format(wid=wid))


# [reopened-says-the-move]
# Rationale: issue87's close reopened a row whose gate proof carried a
#   clause about what that gate left alone (`git diff --exit-code <cut> --
#   <paths>`), which a later gate's planned work made false. The conductor
#   re-ran the substance, found it held, and marked the row satisfied by
#   hand in EXECUTION_STATE.toml -- the one write that skips this recheck.
#   Such a clause is a `gate-proof` now, which close never replays; close
#   still names the move for a `proof` that holds a clause of that kind.
_REOPENED = (
    "a satisfied obligation reopened at close -- its gate's proof no longer passes.\n"
    "  if the obligation broke: work the plan round it has minted.\n"
    "  if only a clause that held when the gate landed failed and the substance\n"
    "  still holds: record what you re-ran -- spine {wid} note observation '...'\n"
    "  -- and take it up: spine {wid} up \"<reason>\"")


def _settle_execution(wid, asm):
    st = runmod.state(wid)
    path = st["boards"].get("execution-state", "")
    if not path or not any(boards.unsettled(r) for r in boards.rows(path)):
        return
    plan = next((s for s in asm["segment"] if s["id"] == "plan"), None)
    if plan:
        # The board still has rows neither satisfied nor deferred, so the
        # plan is recut rather than reworked: a fresh artifact, and a fresh
        # count.
        _mint_segment_round(wid, asm, plan["id"], restarts=True)


# [mints]
# Rationale: "board rows" is the one mint value the engine itself names --
#   a board is engine vocabulary, no assembly declares one. Every other
#   value is an assembly name, legal exactly when some segment in this tree
#   dispatches it, so the set `_check_plan` refuses against is derived from
#   the assembly rather than kept as a second list beside the branches. A
#   third *kind* of mint still needs a branch added here -- that part a
#   tuple never bought.
_BOARD_MINT = "board rows"


# [dispose-mint]
# Rationale: `_BOARD_MINT` always writes a board fresh from the rows
#   submitted -- right for consolidate seeding execution-state the first
#   time, wrong for an adjudication settling rows that already exist:
#   reseeding from only the obligations the conductor named would drop
#   every column `_seed_board` never received and silently vanish every
#   obligation left unnamed. `_DISPOSE_MINT` reads the board's current rows
#   through `boards.rows` -- the same read `_settle_execution` (g5) already
#   trusts -- and writes back through `_seed_board` unchanged: only the
#   merge in `_mint` below is new, the row-writer is not.
# Rejected: a second row-writer that patches the TOML file's disposed rows
#   directly. The gate that added this field was scoped to reuse the mint
#   path rather than grow a second one, and `_seed_board` already renders a
#   board's own guidance and columns faithfully.
_DISPOSE_MINT = "dispositions"




def _mintable(asm):
    """The `mints` values legal in this assembly: `_BOARD_MINT`,
    `_DISPOSE_MINT`, plus every name a segment here declares as
    `dispatches`."""
    return ({_BOARD_MINT, _DISPOSE_MINT}
            | {s["dispatches"] for s in asm["segment"] if s.get("dispatches")})


# [board-segment]
# Rationale: picking the first `interior == "board"` segment was correct
#   while an assembly held at most one -- run-an-issue now holds two (its
#   understand board, and the execution-state board this gate adds), so
#   position alone would resolve a `mints = "board rows"` field to whichever
#   board happens to sort first, silently wrong for the other. A field names
#   its target explicitly (`board = "understand"`) the moment it could mean
#   either; the sole board still resolves with no name at all, so every
#   field that seeds one (explore-an-idea's own) is unchanged.
def _board_segment(asm, target):
    found = [s for s in asm["segment"] if s.get("interior") == "board"]
    if target:
        return next((s for s in found if s["id"] == target), None)
    return found[0] if len(found) == 1 else None


# [gate-id-for]
# Rationale: shared by `_commit_gate` and the dispose branch below -- both
#   need the gate that ran, not the child work id the adjudication step
#   itself carries as `child`. The dispatch step paired with that child (the
#   one with `dispatches` set) is minted with its own id as the gate's name;
#   where no such pairing is found the child id is the closest thing to a
#   name and stands in, same as `_commit_gate` always did before this was
#   pulled out.
def _gate_id_for(st, child):
    gate = next((s for s in st["steps"] if s.get("child") == child and s.get("dispatches")), None)
    return gate["id"] if gate else child


def _mint(wid, asm, step, form, fields):
    """A `plan` field's content becomes structure: board rows, updated board
    rows, or steps."""
    for f in form["fields"]:
        if f.get("kind") != "plan" or f["id"] not in fields:
            continue
        rows = fields[f["id"]]
        mints = f.get("mints")
        if mints == _BOARD_MINT:
            seg = _board_segment(asm, f.get("board"))
            if seg:
                path = journal.location(wid) / (pathlib.Path(seg["board"]).stem + ".toml")
                _seed_board(runmod.resolve_form(asm, seg["board"]), path, rows)
                journal.append(wid, "board", segment=seg["id"], path=str(path), rows=rows)
        elif mints == _DISPOSE_MINT:
            seg = _board_segment(asm, f.get("board"))
            if seg:
                st = runmod.state(wid)
                path = pathlib.Path(st["boards"].get(seg["id"], ""))
                if path.name and path.exists():
                    gate_id = _gate_id_for(st, step.get("child", ""))
                    named = {str(r.get("obligation", "")).strip(): r for r in rows}
                    merged = [{**row, "status": named[row["id"]].get("disposition", ""),
                               "gate": gate_id}
                              if row.get("id") in named else row
                              for row in boards.rows(path)]
                    _seed_board(runmod.resolve_form(asm, seg["board"]), path, merged)
                    journal.append(wid, "board", segment=seg["id"], path=str(path), rows=merged)
        elif mints:
            seg = next((s for s in asm["segment"] if s.get("dispatches") == mints), None)
            if seg:
                _mint_gates(wid, seg, rows)


# [mint-ids-include-closed]
# Rationale: `state()["steps"]` folds `amend close` out of the worklist --
#   right for what runs next, wrong for what an id may still name. A gate
#   closed by amend still named a real gate with a real spec; minting a
#   second gate under that id makes `trace`, `drop <gate-id>` and a later
#   `amend close` name two different gates with one string (#56). The raw
#   journal never drops a "step" entry, closed or not, so reading ids from
#   it rather than from the folded state is what keeps a closed id taken.
# Rejected: keeping the folded `state()["steps"]` and unioning in the ids
#   named by `amend close` entries. That re-derives, at the call site,
#   exactly what "every step this journal ever named" already is -- two
#   places to keep in sync instead of one source read directly.
def _minted_step_ids(wid):
    """Every step id this journal has ever named, live or closed by amend."""
    return {e["id"] for e in journal.read(wid) if e.get("kind") == "step"}


def _mint_gates(wid, seg, gates, start=1):
    """Each gate block becomes a dispatch step and, right after it, the
    adjudication step that will hold its returns -- the pair the execute
    segment's worklist is made of. The adjudication form is the dispatching
    segment's own declared `adjudication-form`, read the way `step-form` and
    `rework-form` already are -- not an engine constant, so which form a
    gate is adjudicated against is the assembly's to say.

    Ids are journal-aware: numbering by position was safe only while closing
    a gate freed its id. A remint no longer closes, so a derived id still
    live in the journal (its gate ran and stands) collides -- `done` is
    keyed by step id, and a duplicate would silently complete both. `start`
    is a caller's choice, not derived here: a remint wants position 1 again
    (redoing that gate's own slot, the collision-then-suffix is the point --
    see `test_remint_mints_a_gate_that_is_reachable_not_already_done`), while
    a plan round's own projection wants the next number in the sequence, not
    a fresh collision every round."""
    existing = _minted_step_ids(wid)
    for i, gate in enumerate(gates, start=start):
        gid = _unique_id(gate.get("id") or f"g{i}", existing)
        existing.add(gid)
        existing.add(f"{gid}-adjudicate")
        prefill = forms.without_nulls({k: v for k, v in gate.items() if k != "id"})
        child = f"{wid}.{gid}"
        journal.append(wid, "step", id=gid, segment=seg["id"], dispatches=seg["dispatches"],
                       prefill=prefill, child=child, anchor=False, terminal=False,
                       source="mint")
        journal.append(wid, "step", id=f"{gid}-adjudicate", segment=seg["id"],
                       form=seg["adjudication-form"], filler="conductor", child=child,
                       anchor=False, terminal=False, validates="", source="mint")


# [gate-projection]
# Rationale: #27 -- a gate spec used to be authored at plan-to-execute, after
#   the critic panel had already released, so no critic had ever read the
#   spec it judged; #7's four unrunnable specs are what that produced. The
#   plan round the panel just passed already carries the gate whole --
#   `_GATE_FIELDS` below -- so the transition projects it forward rather
#   than asking the conductor to retype what the panel already read. `plan`,
#   `horizon` and `key-terms` stay behind: the child executing one gate has
#   no use for the round's own account of itself or the shape of what comes
#   after it.
# Rejected: a `kind = "plan"` field on the transition's own form, the
#   conductor filling it by hand the way `gates` used to. That reproduces
#   the transcription bug one step later -- a second typing is a second
#   chance to drift from what the panel actually judged.
# `fields` -- ruling 3: the plan seam's route form now also reaches this
#   step's own submit on a `rework` or an `up`, where nothing has passed
#   critique and there is nothing to project. Before ROUTE.toml's shape
#   reached this transition, the step could only ever be submitted after a
#   pass -- a revise folded straight to a fresh round with no conductor
#   submit in between -- so this had nothing to gate on and gated on
#   nothing. Now it does: `_releases` is what a `pass` (or a recorded
#   `revise` the conductor chose not to send back) looks like next to a
#   `rework`/`up`, generic off the outcome rather than off any one form's
#   own artifact field name.
_GATE_FIELDS = ("purpose", "scope", "proof", "gate-proof", "budget", "model", "direction")


# [projected-source]
# Rationale: #87 -- an impasse `advance` mints this same transition, and the
#   step immediately behind it is then the ruling form, which carries only
#   `ruling` and `why`, never a gate field. The single-step read
#   `_mint_projected_gate` used to make found nothing there and returned
#   quietly: no gate minted, no refusal, the run walking on to a terminal
#   step with the ruling's own ok never having reached a child. Walking the
#   segment's own prior steps backward instead of reading only the one
#   immediately behind the transition finds the round the ruling actually
#   approved -- the most recent one that ever carried a gate field --
#   whichever form happens to sit between it and the transition.
#   `cmd_submit`'s pre-journal `_check_projection` calls this exact
#   function rather than re-deriving a subset of its guard in prose, so the
#   mint and the refusal that guards it can never drift from each other:
#   there is one guard, not two hand-written copies of the same conditions.
# Rejected: keying the applicability guard off `fields.get("plan")`, the
#   transition form's own field name for "did this release with something
#   to project." That bakes one form's own artifact field into a function
#   obligation 2 requires stay written off the transition's `projects`
#   declaration and the gate fields alone -- a second assembly growing a
#   projecting transition with a differently-named artifact field would
#   silently inherit nothing. `_releases(_outcome(...))` asks the same
#   question -- did this submit's own outcome finish the segment, not send
#   it back or up -- without naming any field at all.
def _projected_source(step, st, asm, fields):
    """`None` when this submit is not a projecting transition's own release
    -- the wrong step, a segment with no `projects`, or a `rework`/`up`
    that finishes nothing. Otherwise `(target, gate)`: `target` is the
    segment `projects` names, and `gate` is built from the most recent
    step in this same segment, walking backward from the transition, whose
    own submitted fields carry at least one of `_GATE_FIELDS` -- `{}`,
    legitimately, where the walk finds none."""
    seg = next((s for s in asm["segment"] if s["id"] == step.get("segment")), {})
    t = seg.get("transition", {})
    if (step.get("form") != t.get("form") or not t.get("projects")
            or not _releases(_outcome(asm, step, fields, st))):
        return None
    target = next((s for s in asm["segment"] if s.get("dispatches") == t["projects"]), None)
    if not target:
        return None
    prior = [s for s in st["steps"] if s["segment"] == step["segment"] and s["id"] != step["id"]]
    gate = {}
    for s in reversed(prior):
        source = st["done"].get(s["id"], {}).get("fields", {})
        candidate = {k: source[k] for k in _GATE_FIELDS if k in source}
        if candidate:
            gate = candidate
            break
    return target, gate


def _check_projection(asm, step, st, fields):
    """Where this submit is a projecting transition's own release, the
    backward walk `_projected_source` performs must actually find a round
    to project -- checked here, before `journal.append` makes the submit
    durable, so the true dead end (a segment with no round to project at
    all) refuses loudly and says what it could not project, in place of
    the silent nothing-minted `_mint_projected_gate` used to leave behind.
    Not applicable (`None`) and found something (a non-empty `gate`) both
    pass through untouched."""
    found = _projected_source(step, st, asm, fields)
    if found is None:
        return
    target, gate = found
    if not gate:
        raise SystemExit(render.refusal(
            step["id"], f"projects into {target['id']!r} but this segment "
            "has no round behind it that ever carried a gate field -- "
            "nothing here to project", escape=""))


def _mint_projected_gate(wid, asm, step, st, fields):
    """A transition step whose own segment declares `projects` mints one
    gate into the segment `projects` names, on submit -- built from this
    segment's own most recent interior return, never from anything typed on
    the transition's own form. A no-op off that step, where the segment it
    names is not one this assembly's own `_mint_gates` can reach, or where
    the walk finds no round to project -- `_check_projection` is what
    refuses that last case before this ever runs; here it is simply
    nothing to mint."""
    found = _projected_source(step, st, asm, fields)
    if found is None:
        return
    target, gate = found
    if gate:
        # Sequential, not position-1 every round: unlike a remint (still
        # redoing one gate's own slot, so colliding into a suffix is the
        # point), each plan round cuts the issue's next gate, and numbering
        # it g1, g2, g3... reads the same way the run does.
        cut_so_far = sum(1 for s in st["steps"]
                         if s.get("segment") == target["id"]
                         and s.get("dispatches") == target["dispatches"])
        _mint_gates(wid, target, [gate], start=cut_so_far + 1)


# [resume-paused-child]
# Rationale: a paused child's resume is not a submitted outcome -- the ask
#   form declares no `decides` field on purpose (see `_pause_gate`), since
#   the parent segment's own outcome table would try to resolve the answer
#   against values it never means (run-an-issue's `execute` segment,
#   `advance | remint | drop <gate-id> | replan`). This hook is the other
#   half: unconditional and decides-free, called beside `_mint_projected_gate`
#   on every submit, firing off the positive `resumes` key the pause verb
#   wrote rather than off anything the ask form's own fields declare.
# Rejected: routing the answer through `_outcome`/`_perform` the ordinary
#   way. That is exactly the collision named above -- the same submit would
#   have to satisfy two unrelated vocabularies on one field.
# See: `journal.py:201` -- `journal.append`'s own `mkdir(parents=True,
#   exist_ok=True)`, which is why this checks `journal.exists` before writing
#   anywhere in the child rather than after.
#
# issue84.g2's own review found the fix above only held through the pause
# moment: `_mint_segment_round` below is sibling-blind, plain-appending the
# fresh interior step and its fresh transition, so once the marker closes
# the untouched sibling `_pause_gate` only ever leapfrogged -- never itself
# reordered -- resurfaces ahead of the fresh round in `_ordered`'s own
# within-segment order. Driven live: a conductor answering the ask was
# handed `review`'s or `understand`'s own stale prompt instead of the fresh
# round's. Fixed by carrying the sibling forward on the marker itself
# (`_pause_gate`'s own `sibling` key, `""` when none was found) and
# reordering every step this mint just appended to the segment ahead of it,
# in mint order, mirroring the same move against the newly-live pair
# instead of the ask.
# Rejected: reordering only the fresh interior step. `_mint_segment_round`
#   also mints a fresh transition (`review`, or the two-voices panel step a
#   board segment's understand re-mints) whenever the segment declares one,
#   and leaving that one behind the sibling reproduces the exact defect one
#   step later -- `current` would resolve correctly to the interior step
#   this round, then wrongly to the sibling the moment that step submits.
def _resume_paused_child(pwid, step, fields):
    """Fires only when the step just submitted is an ask `_pause_gate` wrote
    -- named by its own positive `resumes` key, naming the child to write
    into. A no-op on every ordinary submit, ask included until it carries
    that key."""
    child = step.get("resumes")
    if not child:
        return
    if not journal.exists(child):
        journal.append(pwid, "note", id=f"n{secrets.token_hex(2)}",
                       kind_detail="observation", about="resume",
                       text=f"{child}'s journal is gone -- the answer was recorded here, "
                            "but there is no child left to resume")
        return
    cst = runmod.state(child)
    marker = cst["current"] if cst else None
    if not marker or not runmod.paused(marker):
        return  # already resolved some other way, or the marker moved
    tseg_id = marker["paused"]
    sibling = marker.get("sibling", "")
    before_ids = {s["id"] for s in cst["steps"] if s["segment"] == tseg_id}
    casm = runmod.load_assembly(cst["assembly"])
    journal.append(child, "amend", action="close", segment=marker["segment"],
                   step=marker["id"], reason="resumed by the parent's answer",
                   anchor=marker.get("anchor", False))
    # A panelist's own step was overridden at open (`_open_child`'s panel
    # branch) to its panel entry's form/worker -- e.g. a critic's
    # CRITIC.toml, not give-a-verdict's bare default. `_pause_gate` stashed
    # that override on the marker as `resume_form`/`resume_filler`, since
    # nothing else durable carries it back to here; empty on every ordinary
    # (non-panelist, or cross-segment) resume, reproducing today's behaviour.
    _mint_segment_round(child, casm, tseg_id, prefill=fields,
                        form=marker.get("resume_form", ""),
                        filler=marker.get("resume_filler", ""), resumed=True)
    if sibling:
        steps = runmod.state(child)["steps"]
        fresh = [s for s in steps if s["segment"] == tseg_id and s["id"] not in before_ids]
        old = next((s for s in steps if s["id"] == sibling), None)
        # [resume-supersedes-the-sibling]
        # Rationale: #123 -- the fresh round carries its own transition, so a
        # sibling of the same kind left open was a second copy of it: once the
        # fresh round's review landed, `current` fell through to the stale one
        # and a second review round was minted on the same diff. The sibling
        # was untouched when the pause captured it, and its replacement now
        # stands, so it is closed. A sibling the fresh round did not replace
        # -- an ask left owed by `up` (`[an-ask-outlives-its-up]`) -- stays,
        # behind the fresh round.
        if old and any(_same_kind(f, old) for f in fresh):
            journal.append(child, "amend", action="close", segment=tseg_id, step=sibling,
                           reason="superseded by the resumed round",
                           anchor=old.get("anchor", False))
        else:
            for f in fresh:
                journal.append(child, "amend", action="reorder", segment=tseg_id,
                               step=f["id"], before=sibling,
                               reason="the resumed round stands ahead of the sibling "
                                      "the pause already leapfrogged, not behind it again",
                               anchor=False)


def _same_kind(a, b):
    """Whether two steps stand for the same thing in a segment: the same form
    to fill and the same panel to fire, or neither."""
    return ((a.get("form") or "") == (b.get("form") or "")
            and bool(a.get("panel")) == bool(b.get("panel")))


def _unique_id(base, existing):
    """`base` if it is free, else `base` with a random distinguishing suffix
    -- readable in the common case, and a collision (which would silently
    complete every step sharing the id) becomes structurally impossible
    rather than merely unlikely. Random, not counted, matching `amend add`
    and the verdict refill: a counted suffix only needs to be right once,
    read at the moment of the check, and a check-then-suffix window is
    exactly the race that produces the duplicate this guards against."""
    if base not in existing:
        return base
    while True:
        candidate = f"{base}-a{secrets.token_hex(2)}"
        if candidate not in existing:
            return candidate


def _seed_board(template, dest, rows):
    """Write the board with every word of its guidance intact, seed rows below.

    The template's blank row is commented out rather than dropped: its inline
    notes are where the column-by-column doctrine lives (what `type` means,
    never self-answering a decision, how to carry options to a principal), and
    a board is worked over many turns by agents who may arrive fresh. The
    instructions belong at the artifact, not in a doc read once.
    """
    from engine import tomlw
    text = template.read_text(encoding="utf-8").rstrip()
    table = re.search(r"^\[\[(\w+)\]\]", text, re.M)
    head, sep, example = text.partition(table.group(0))
    quoted = "\n".join(
        line if line.startswith("#") else f"# {line}" if line.strip() else "#"
        for line in (sep + example).splitlines()
    )
    # The template's blank row is the convention: what the rows are called,
    # how an id is spelled, which status a fresh row starts in.
    blank = tomllib.loads(sep + example)[table.group(1)][0]
    prefix = re.match(r"[a-z]*", str(blank.get("id", ""))).group(0) or "r"
    body = ""
    for i, r in enumerate(rows):
        row = {"id": f"{prefix}{i+1}", "status": blank.get("status", "open"), **r}
        body += tomlw.table(table.group(1), row) + "\n"
    dest.write_text(f"{head.rstrip()}\n\n# --- the columns, and what they mean ---\n"
                    f"{quoted}\n\n# --- the board ---\n\n{body}", encoding="utf-8")


# [up-target]
# Rationale: a bare `up` names no per-assembly target -- unlike `run-a-gate`'s
#   own two `does = "pause"` / `does = "pause work"` rows, which hand
#   `_pause_gate` a `tseg` a human already picked when the assembly was
#   written -- so it has to find one itself, from the one thing every
#   assembly declares regardless of shape: its own segment order. Backward
#   from the current step's own segment, itself included, stopping at the
#   first segment declaring a `step-form` -- the same predicate `skeleton()`
#   (engine/run.py) already uses to decide whether a segment mints an
#   interior step at all, so every segment this can land on is one
#   `skeleton()` already treats as legitimate. `interior` is deliberately
#   not part of the test: a segment with `interior = "board"` and a
#   `step-form` (run-an-issue's `understand`) is exactly as resumable as one
#   with `interior = "steps"` -- its own live `rework` outcome already
#   proves that today -- so checking `interior` too would refuse over a
#   segment nothing else in the tree treats as unusual.
# Rejected: also requiring `interior in ("steps", "board")`. All three
#   critics on this gate's own plan flagged that as wrong for the identical
#   reason `skeleton()`'s own rejected-alternative comment already gives:
#   it would skip `understand` for its board interior and wrongly continue
#   toward `open`, which has no `step-form` at all, ending in a refusal over
#   a segment that is not actually the problem.
def _up_target(asm, seg_id):
    """The segment a bare `up` pauses at: `seg_id` itself, or the nearest
    one before it in declared order that carries a `step-form` -- `None` if
    none do, all the way back to `open`."""
    order = asm["segment"]
    idx = next((i for i, s in enumerate(order) if s["id"] == seg_id), None)
    if idx is None:
        return None
    return next((s for s in reversed(order[:idx + 1]) if s.get("step-form")), None)


# [bare-up]
# Rationale: the amend-close runs before `_pause_gate` is ever called, and
#   before `_up_target` failing to resolve is even distinguished from it
#   resolving -- a refusal must leave nothing journaled that would strand
#   the run, so the target is found first and the close happens only once
#   there is somewhere for the ask to land. `state(wid)["current"]` is
#   closed here, not inside `_pause_gate`, because `_pause_gate` is also
#   called directly by `run-a-gate`'s own hand-named `does = "pause"` /
#   `"pause work"` rows (`_perform`), and those already run behind a
#   decided submit that `_perform`'s own docstring says never needs closing
#   -- the deciding submit is already journaled. A bare `up` has no such
#   submit: it is ruled instead of one, so the step it was ruled at is the
#   one thing here that still needs retiring.
def cmd_up(argv):
    if len(argv) < 2:
        raise SystemExit('spine <work-id> up "<reason the run cannot answer itself>"')
    wid, reason = argv[0], " ".join(argv[1:])
    st = runmod.state(wid)
    if st is None:
        _no_run(wid)
    if not st["open"] or st["awaiting_close"]:
        raise SystemExit(render.located(f"{wid} has no current step to rule up"))
    cur = st["current"]
    asm = runmod.load_assembly(st["assembly"])
    tseg = _up_target(asm, cur["segment"])
    if tseg is None:
        raise SystemExit(render.refusal(
            cur["id"], f"nothing at or before {cur['segment']!r} declares a step-form "
            "-- there is no round for an answer to resume",
            escape=f"drop it instead: spine {wid} amend close {cur['id']} --reason ..."))
    # [an-ask-outlives-its-up]
    # Rationale: #180 -- a conductor standing on an ask that resumes a paused
    #   child, and ruling it up, closed that ask here; the ask was the only
    #   thing carrying the child's resume, so the answer from above reached
    #   this run and never the child. An ask a conductor cannot answer yet is
    #   still owed: it stays, the new ask stands in front of it, and once
    #   that answer comes back the ask is where the conductor lands next.
    if not cur.get("resumes"):
        journal.append(wid, "amend", action="close", segment=cur["segment"], step=cur["id"],
                       reason=reason, anchor=cur.get("anchor", False))
    # A panelist ruling `up` mid-verdict resumes into its own panel-entry
    # form/worker, not give-a-verdict's bare default -- read straight off
    # `cur`, which `_open_child`'s panel branch already overrode at open.
    # Only when the target IS the current step's own segment and that
    # segment has no real interior, so the round that resumes is `cur`'s own
    # kind of step (`[fresh-round-is-the-only-round]`). A segment with an
    # interior resumes into its step-form: a conductor ruling `up` from
    # run-a-gate's route form, `work`'s own transition, resumes an implement
    # round, never another route form.
    resume_form, resume_filler = "", ""
    if tseg["id"] == cur["segment"] and tseg.get("interior") not in ("steps", "board"):
        resume_form, resume_filler = cur.get("form", ""), cur.get("filler", "")
    _pause_gate(wid, tseg, reason, {}, resume_form=resume_form, resume_filler=resume_filler)
    print(f"paused {wid}\n")
    return cmd_status([wid])




def cmd_note(argv):
    if len(argv) < 2:
        raise SystemExit(f"spine <work-id> note <{'|'.join(render.NOTE_KINDS)}> <text>")
    wid, kind, text = argv[0], argv[1], " ".join(argv[2:])
    if kind not in render.NOTE_KINDS:
        # `note block ...` used to print success and do nothing at all: only
        # the exact word is acted on, so a near-miss must not look like a hit.
        raise SystemExit(f"no note kind {kind!r} -- one of: {', '.join(render.NOTE_KINDS)}")
    st = runmod.state(wid)
    if st is None:
        _no_run(wid)
    # `note resumed n1` names the block it clears; the rest of the words are
    # the note. Counting existing notes to pick an id collides when two
    # sessions note at once, and a shared id would clear the wrong block.
    about = argv[2] if kind == "resumed" and len(argv) > 2 else ""
    if about:
        text = " ".join(argv[3:])
    journal.append(wid, "note", id=f"n{secrets.token_hex(2)}", kind_detail=kind,
                   text=text, about=about,
                   step=(st["current"] or {}).get("id", ""))
    print(f"noted {kind}" + (f" — cleared {about}" if about else ""))
    return 0


def cmd_amend(argv):
    if len(argv) < 2:
        raise SystemExit("spine <work-id> amend add|close|reorder|waive|proof ... --reason \"...\"")
    wid, action = argv[0], argv[1]
    reason = _opt(argv, "--reason")
    if not reason:
        raise SystemExit(render.refusal("reason", "amend needs --reason"))
    st = runmod.state(wid)
    if st is None:
        _no_run(wid)
    if action == "add":
        return _amend_add(wid, st, argv[2:], reason)
    if action == "close":
        return _amend_close(wid, st, argv[2], reason)
    if action == "reorder":
        return _amend_reorder(wid, st, argv[2], reason, _opt(argv, "--before"))
    if action == "waive":
        return _amend_waive(wid, st, argv[2], reason)
    if action == "proof":
        return _amend_proof(wid, st, argv[2], reason, _opt(argv, "--proof"))
    raise SystemExit(f"unknown amend action {action!r} -- add | close | reorder | waive | proof")


def _amend_add(wid, st, argv, reason):
    seg = _opt(argv, "--segment")
    if not seg:
        raise SystemExit(render.refusal("segment", "amend add needs --segment"))
    form_ref = _opt(argv, "--form")
    if not form_ref and "--transition" not in argv:
        raise SystemExit(render.refusal("form", "amend add needs --form, or --transition"))
    asm = runmod.load_assembly(st["assembly"])
    if not any(s["id"] == seg for s in asm["segment"]):
        raise SystemExit(render.refusal(
            "segment", f"no segment named {seg!r}",
            escape="segments: " + ", ".join(s["id"] for s in asm["segment"])))
    if "--transition" in argv:
        # The segment's transition as the assembly declares it today -- form
        # and panel both. A run stops depending on its template at open, so
        # this is how a live run catches up with a template that grew a
        # panelist: one journaled amend, loud if the step it replaces was
        # anchored.
        segment = next(x for x in asm["segment"] if x["id"] == seg)
        t = segment.get("transition", {})
        sid = f"{seg}-a{secrets.token_hex(2)}"
        step = {"id": sid, "segment": seg, "filler": t.get("filler", "conductor"),
                "anchor": t.get("anchor", False), "terminal": t.get("terminal", False),
                "validates": t.get("validates", ""),
                "carries": t.get("carries", False), "source": "amend"}
        if t.get("form"):
            step["form"] = t["form"]
        if t.get("panel"):
            step["panel"] = t["panel"]
        journal.append(wid, "step", **step)
        journal.append(wid, "amend", action="add", segment=seg, step=sid, reason=reason,
                       anchor=step["anchor"])
        print(f"amended: added {sid} to {seg}\n")
        return cmd_status([wid])
    # Random, not counted: two sessions amending at once both compute the same
    # next number, and duplicate ids are worse than ugly -- `done` is keyed by
    # step id, so one submit would silently complete every step sharing it.
    sid = f"{seg}-a{secrets.token_hex(2)}"
    # a dispatched run's own prefill (its orders) rides its amended steps too --
    # that is how a `check` field on the interior's own form (IMPLEMENT.toml's
    # `proof`) finds the gate spec's command without a --prefill flag to type.
    journal.append(wid, "step", id=sid, segment=seg, form=form_ref, filler="conductor",
                   prefill=st.get("prefill"), anchor=False, terminal=False,
                   validates="", source="amend")
    journal.append(wid, "amend", action="add", segment=seg, step=sid, reason=reason,
                   anchor=False)
    print(f"amended: added {sid} to {seg}\n")
    return cmd_status([wid])


def _pending(st):
    """The steps an amend can still touch -- named at every refusal, because
    the ids are right here and making the agent go look them up is the whole
    thing this engine exists not to do."""
    return "pending: " + (", ".join(
        s["id"] for s in st["steps"] if s["id"] not in st["done"]) or "none")


def _amend_close(wid, st, step_id, reason):
    step = next((s for s in st["steps"] if s["id"] == step_id), None)
    if step is None:
        raise SystemExit(render.refusal(step_id, "no such step", _pending(st)))
    if step_id in st["done"]:
        raise SystemExit(render.refusal(
            step_id, "already complete -- history is not amendable", _pending(st)))
    journal.append(wid, "amend", action="close", segment=step["segment"], step=step_id,
                   reason=reason, anchor=step.get("anchor", False))
    print(f"amended: closed {step_id}\n")
    return cmd_status([wid])


def _amend_reorder(wid, st, step_id, reason, before):
    step = next((s for s in st["steps"] if s["id"] == step_id), None)
    if step is None:
        raise SystemExit(render.refusal(step_id, "no such step", _pending(st)))
    if not before:
        raise SystemExit(render.refusal("before", "amend reorder needs --before"))
    if step_id in st["done"]:
        raise SystemExit(render.refusal(
            step_id, "already complete -- history is not amendable", _pending(st)))
    journal.append(wid, "amend", action="reorder", segment=step["segment"], step=step_id,
                   before=before, reason=reason, anchor=step.get("anchor", False))
    print(f"amended: reordered {step_id} before {before}\n")
    return cmd_status([wid])


# [amend-proof]
# Rationale: a minted gate's `proof` had no way to change. issue126's was
#   written for bash and ran in dash (#191); issue164's named a test a
#   principal's ruling deleted; issue165's asserted `>= 6` where the ruling
#   said `>= 5`. Each time close re-ran the stored text and reopened the
#   obligation, and the only way on was note, up, a fresh plan round and a
#   gate that restated the work. `amend close` on the child's check step
#   did not help: close reads the gate's spec, not that step. So the ruling
#   becomes one journaled amend that the fold writes into the gate's spec,
#   and every re-read the engine makes of it -- close's recheck, and the
#   dispatch of a gate not yet started -- reads the new text. Done gates
#   are allowed: the proof is read again after its gate has run, so that is
#   where an erratum is found. `proof` only: `gate-proof` is never read
#   once its gate has landed.
# Rejected: delivering the text into a gate child already running. Neither
#   issue164 nor issue165 needed it; it waits for a run that does.
def _amend_proof(wid, st, step_id, reason, proof):
    gates = [s for s in st["steps"]
             if s.get("dispatches") and "proof" in (s.get("prefill") or {})]
    step = next((s for s in gates if s["id"] == step_id), None)
    if step is None:
        raise SystemExit(render.refusal(
            step_id, "no gate by that id",
            escape=f"gates: {', '.join(s['id'] for s in gates) or 'none'}"))
    if not (proof or "").strip():
        raise SystemExit(render.refusal(
            "proof", "amend proof needs the replacement",
            escape=f'spine {wid} amend proof {step_id} --proof "<command>" --reason "<ruling>: ..."'))
    journal.append(wid, "amend", action="proof", segment=step["segment"], step=step_id,
                   proof=proof, was=str((step.get("prefill") or {}).get("proof", "")),
                   reason=reason, anchor=step.get("anchor", False))
    print(f"amended: {step_id}'s proof is now `{proof}`\n")
    return cmd_status([wid])


# [waive-leaves-the-step-standing]
# Rationale: a principal's ruling that a round goes unreviewed -- "hand
#   this gate off to be built rather than review it again", issue811 on
#   f1Brainz, 2026-09-07 -- had no verb. The conductor `amend close`d the
#   two-voices step, the only step the panel hangs on, which took the route
#   form behind it too: the run walked to its close form with the gate
#   never projected, and the conductor re-added `forms/PLAN_TO_EXECUTE.toml`
#   by hand three times over three gates, once under a wrong form reference.
#   This verb is the ruling as one journaled amend: the panelists still
#   outstanding are named waived with the reason, the step stops waiting for
#   them (`panel_expected`, engine/run.py), and its own form stays the
#   conductor's to fill. Nothing already running is touched -- a live
#   panelist finishes and its return lands nowhere (`state`'s return
#   branch), and a later `wait` never starts it (`_panel_descriptors`).
# Rejected: validating the reason. It is journaled for the tier above to
#   read, the same as every other amend's; the engine is a secretary.
# Rejected: allowing it on a panel-only step. That step is its panel; with
#   every voice waived nothing is left to complete it, which is what `amend
#   close` already says in one entry.
def _amend_waive(wid, st, step_id, reason):
    step = next((s for s in st["steps"] if s["id"] == step_id), None)
    if step is None:
        raise SystemExit(render.refusal(step_id, "no such step", _pending(st)))
    if step_id in st["done"]:
        raise SystemExit(render.refusal(
            step_id, "already complete -- history is not amendable", _pending(st)))
    if not step.get("panel"):
        raise SystemExit(render.refusal(step_id, "no panel to waive", _pending(st)))
    if not step.get("form"):
        raise SystemExit(render.refusal(
            step_id, "a panel-only step is its panel -- nothing would be left to fill",
            escape=f"drop it instead: spine {wid} amend close {step_id} --reason ..."))
    asm = runmod.load_assembly(st["assembly"])
    outstanding = [cid for cid, *_ in _panel_descriptors(wid, asm, step)
                   if cid not in st["returns_by_child"]]
    if not outstanding:
        raise SystemExit(render.refusal(
            step_id, "its panel has returned in full -- nothing outstanding to waive",
            escape=f"fill its form: spine {wid}"))
    journal.append(wid, "amend", action="waive", segment=step["segment"], step=step_id,
                   reason=reason, anchor=step.get("anchor", False), waived=outstanding)
    print(f"amended: waived {len(outstanding)} of {step_id}'s panel -- "
          + ", ".join(c.rsplit(".", 1)[-1] for c in outstanding) + "\n")
    return cmd_status([wid])


# [rework-round-is-a-dispatch]
# Rationale: a segment that declares `dispatches` (the plan segment)
#   dispatches every round, not only the one `skeleton()` seeds -- ruling 6
#   bars the conductor from drafting what it judges on a rework round exactly
#   as it does on the first. The mint mirrors `skeleton()`'s own branch:
#   `dispatches` in place of `form`, with the caller's `form` (the
#   rework-form) carried as an override for `_open_child` to apply, since the
#   dispatched assembly's own transition still names its step-form by
#   default.
# Rejected: a second dispatched assembly just for rework. `cut-a-gate`
#   already reads whichever form its dispatch step names; teaching it a
#   second shape to reach the same form would be a second thing to keep in
#   sync with the planner's skill for no behaviour gained.
def _mint_segment_round(wid, asm, seg_id, prefill=None, form="", filler="",
                        restarts=False, resumed=False, rewrite=False):
    """Mint one fresh round of a segment: its step-form (or the form the
    caller names -- a revise passes the segment's rework form) as a fresh
    interior step, plus its transition -- with its panel on the rounds the
    transition declares it for (`[panel-rounds]` below) --
    both read from the assembly, never copied from whatever minted last.
    The shared move a revise and a replan both need: the segment reopened
    for another pass.

    `resumed` stamps the fresh transition as the round a paused seam's
    answer opened, which is where the round-cap's count starts over (#177:
    the answer is the ruling the cap exists to obtain).

    `rewrite` stamps the fresh transition as a rewrite's round, which is
    what `[rewrite-cap]` counts.

    `restarts` says which kind of round this is, and only the caller knows:
    a `rework` is another pass at the artifact standing (the default), a
    `refill` is a fresh one, and a fresh one is what a `fresh` panel reads
    (`[panel-rounds]`). It is journaled as `sent_back` so
    `run.rework_rounds` reads the fact rather than inferring it from which
    form was minted -- see `[rework-rounds]` (engine/run.py) for the case
    that inference got wrong.

    Two independent random tags, not one shared: a transition's id defaults
    to its segment's id (run-an-issue's "plan" names both), and
    `f"{seg_id}-a{tag}"` would then equal `f"{step_id}-a{tag}"` for the same
    tag -- one mint silently overwriting the other in the journal.
    """
    seg = next(s for s in asm["segment"] if s["id"] == seg_id)
    t = seg.get("transition", {})
    # [verdict-shaped-segment-round]
    # Rationale: mirrors `skeleton()`'s own gate (engine/run.py:176) exactly
    #   -- a segment with no real interior (give-a-verdict's `verdict`) is
    #   already one `open` never mints an interior step for, so a resume
    #   must not mint one either. Before this, a resumed panelist got TWO
    #   fresh steps (an interior round nothing declared plus the transition
    #   round) instead of one, driven live and confirmed against the proof.
    # Rejected: gating on `form` the way `skeleton()`'s local variable does.
    #   Every caller into this function already guarantees a step-form or a
    #   form override, so `interior` alone is the live half of that test
    #   here.
    has_interior = seg.get("interior") in ("steps", "board")
    if has_interior:
        prior = runmod._rounds(runmod.state(wid), seg_id)
        sent_back = 0 if restarts else (prior[-1]["sent_back"] + 1 if prior else 1)
        step = {"id": f"{seg_id}-a{secrets.token_hex(2)}", "segment": seg_id,
                "filler": seg.get("worker", "conductor"), "prefill": prefill or {},
                "anchor": False, "terminal": False, "validates": "", "source": "mint",
                "sent_back": sent_back}
        # `form` is set either way -- a replan's dispatch carries its own
        # step-form even though that names the child assembly's own default
        # and so overrides nothing. `rework_rounds` (run.py) reads this
        # field on every mint regardless of `dispatches`, and a step that
        # omitted it whenever the value was the non-override default
        # silently broke the replan-resets-the-count case the moment a
        # replan started dispatching.
        step["form"] = form or seg["step-form"]
        if seg.get("dispatches"):
            step["dispatches"] = seg["dispatches"]
        journal.append(wid, "step", **step)
    # The segment's transition, re-minted for the fresh round: its panel where
    # it declares one, its form where it declares one, both where it is a
    # two-voices step. Neither key is assumed: a board segment's refill
    # declares a form and no panel, explore-an-idea's spec a panel and no form.
    # `anchor`/`terminal` are read off the transition itself rather than
    # hardcoded False: no existing step-form segment's transition declares
    # `terminal = true`, so this is a pure extension for every one of them,
    # and it is what lets `verdict`'s own resumed round keep being the
    # segment's one terminal step -- without it `cmd_close` found no
    # terminal step and the panelist's actual ruling never reached its
    # parent.
    # `validates` and `carries` are read off the transition for the same
    # reason `anchor`/`terminal` are: `skeleton()` (engine/run.py) gives round
    # one both keys, every reader of them is a bare `step.get(...)`, and a
    # fresh round that omitted them skipped the guards its assembly declares
    # with no refusal and no journal trace (#110).
    fresh = {"id": f"{seg_id}-a{secrets.token_hex(2)}", "segment": seg_id,
             "filler": t.get("filler", "conductor"),
             "anchor": t.get("anchor", False), "terminal": t.get("terminal", False),
             "validates": t.get("validates", ""), "carries": t.get("carries", False),
             "source": "panel"}
    # [panel-rounds]
    # Rationale: a transition says which rounds its panel is minted for.
    #   `every` (the default) re-fires the panel on each fresh round;
    #   `fresh` mints it on each fresh artifact -- the opening round
    #   (`skeleton()`'s, which reads the panel unconditionally) and every
    #   round the caller says `restarts`: a rewrite, a replan's refill, the
    #   re-cut after a gate lands -- and never on a pass over findings (an
    #   incorporate) or a resumed round, which stand the conductor's form
    #   alone (`[one-look]`). run-an-issue's two seams declare `fresh`
    #   (ruling, 2026-09-26: each gate's cut answers to the code and spec
    #   as they stand, so each gets its own cold read). It replaces
    #   `opening`, which panelled the run's first cut alone: later gates'
    #   cuts went unread and were written as amendments to the first.
    # Rejected: a mint-time rule keyed on the segment or its `dispatches`.
    #   Which rounds a panel reads is the assembly's call about its own
    #   seam, and an engine rule would have to name the seam to make it.
    if t.get("panel") and (restarts or t.get("panel-rounds", "every") != "fresh"):
        fresh["panel"] = t["panel"]
    # [rework-panel]
    # Rationale: a transition may declare the readers every round after its
    #   opening one gets instead of its full panel. run-a-gate's does: a
    #   rework round is read by one reviewer for the blocking findings and
    #   for anything the rework made false, the two things a later round
    #   ever found. That reader is handed the findings on this round's own
    #   prefill -- the same blocks the rework was -- since a panelist reads
    #   its orders there. A fresh artifact (`restarts`) keeps the full
    #   panel.
    # Rejected: an agent choosing each round's readers on a form (run-a-gate's
    #   old `select`). Its fills copied the same blocks nearly every time, on
    #   a heavy runner; what is fixed belongs to the assembly.
    if fresh.get("panel") and t.get("rework-panel") and not restarts:
        fresh["panel"] = t["rework-panel"]
        if prefill:
            fresh["prefill"] = prefill
    if t.get("form"):
        fresh["form"] = t["form"]  # the two-voices shape survives a fresh round
    if resumed:
        fresh["resumed"] = True
    if rewrite:
        fresh["rewrite"] = True
    # [fresh-round-is-the-only-round]
    # Rationale: when the segment has no real interior, this transition
    #   round is the ONLY round minted -- so it is what the resuming
    #   panelist actually fills, and `form`/`filler`/`prefill` all have to
    #   spend themselves here instead of on an interior step that will not
    #   exist. A segment WITH a real interior is completely unaffected: it
    #   keeps spending `form` on the interior round above (the existing
    #   rework-form-override path), and `filler`/`prefill` are never read
    #   here for it. Confirmed against the proof: without `prefill` landing
    #   here too, a resumed panelist's answer to its own `up` never reached
    #   the round it was answering for.
    if not has_interior:
        if form:
            fresh["form"] = form
        if filler:
            fresh["filler"] = filler
        if prefill:
            fresh["prefill"] = prefill
    if t.get("panel") or t.get("form"):
        journal.append(wid, "step", **fresh)


# [act-on-verdicts]
# Rationale: a merged verdict is resolved the same way a submitted decision
#   field is -- looked up against the deciding spec's own declared `outcome`
#   rows and handed to `_perform`, for every transition alike. `resolution`
#   and `outcome` are the two-voices shape's own doing (PLAN.toml family);
#   `_decided_here` picks it out the same way it already does for a real
#   submit, by matching the step's form against the transition's -- true
#   even for a panel-only step submitting no form of its own (run-a-gate's
#   review, explore-an-idea's spec), since both sides of that match are then
#   simply absent. A panel submits no fields, so `{field: verdict}`
#   synthesises the pair the merged verdict itself answers. `pass`'s
#   declared verb is `release`, which `_perform` matches nothing for -- the
#   same deliberate no-op `up` already spells at a segment's own outlet --
#   so a clean verdict still mints nothing and the run advances by its own
#   step order, never by an act here.
# Rejected: keeping the old fallback -- a bare equality check against the
#   literal word `revise` -- in front of this. It did two jobs at once:
#   short-circuiting a pass (now `release`'s job) and keeping the
#   three-rounds impasse check from firing on anything but a revise (now
#   `_perform`'s own `rework` verb owns that, so both voices that can decide
#   a rework spend the same count) -- and a transition that declares no
#   outcome at all now simply does nothing, the same inertness `release`
#   spells for one that does. Comparing the merged word against a literal anywhere in this
#   function would leave one more place dispatching on the vocabulary the
#   outcome table now owns end to end.
# See: assemblies/run-an-issue/forms/PLAN_TO_EXECUTE.toml
def _act_on_verdicts(pwid, step_id):
    """Once every panelist named by `step_id` has returned, the transition
    acts on the merged verdict through the deciding spec's own declared
    `outcome` rows -- `{decides-field: verdict}` synthesised in place of a
    submitted field, since a panel submits none, and nothing acted on at
    all where the transition declares no `decides`. Pass's declared verb is
    `release`, a no-op `_perform` does not match: for a panel-only step
    there is nothing more to mint, the verdict itself rides the summary up
    to whoever adjudicates next; for a two-voices step, `state()` has
    already left it open instead, so this is inert twice over and the form
    is what releases it -- run-a-gate's review, run-an-issue's consolidate
    and plan-to-execute all declare both of their verdicts that way now, so
    every one of their rounds is disposed of by a conductor. A verb that
    acts -- `rework`, which explore-an-idea's spec still declares for
    `revise`, having no route form of its own -- is `_perform`'s from here,
    findings and the segment's own outlet included, since a conductor form
    deciding the same rework reaches that verb by the ordinary submit and
    owes the round exactly the same two things."""
    pst = runmod.state(pwid)
    step = next((s for s in pst["steps"] if s["id"] == step_id), None)
    if not step or not step.get("panel") or runmod.panel_outstanding(pst, step):
        return
    # `.get`: a waived panelist closing late lands nothing in `returns`, and
    # a panel waived whole has no key here at all -- the fold below reads
    # an empty round as quiet and this returns without acting.
    returns = pst["returns"].get(step_id) or []
    asm = runmod.load_assembly(pst["assembly"])
    _, spec = runmod.deciding_spec(asm, step)
    # A refusal and a quiet panel both perform nothing: neither is a word the
    # table declares a verb for, and synthesising one anyway is how an
    # unreadable round would come to mint a real next step. Record-only, like
    # the other six sites -- a panel-only step is already `done` by the time
    # this runs, verdict aside, so nothing here is what walks the run on.
    kind, verdict = runmod.verdict_fold(returns, runmod.panel_forms(asm, step), spec)
    if kind != "clean":
        return
    seg = next((s for s in asm["segment"] if s["id"] == step.get("segment")), {})
    t = seg.get("transition", {})
    # [panel-owner]
    # Rationale: this reads `decides` only when `step` really is the
    #   transition (plan-to-execute, consolidate, run-a-gate's review), never
    #   falling back to `_decided_here`'s segment table: that fallback exists
    #   for a conductor's direct submit on a segment-grain form (an impasse
    #   ruling), not for a panel's synthesised verdict.
    # Rejected: calling `_decided_here` here as before. Its fallback made a
    #   panel step minted apart from its transition have its merged verdict
    #   checked against the segment's own outcome table -- a value that
    #   table never declares, so closing the panel's own step refused.
    field = t.get("decides") if step.get("form") == t.get("form") else ""
    outcome = _outcome(asm, step, {field: verdict}, pst) if field else None
    if not outcome:
        return
    seg, does = outcome
    # The fresh round's prefill and the segment's own three-round outlet are
    # `_perform`'s `rework` verb to apply (see `[panel-judged-rework]`), not
    # this caller's: a conductor's form submitting on this same step reaches
    # that verb by the ordinary route and owes the round exactly the same
    # two things.
    _perform(pwid, asm, seg, does, {field: verdict}, step)


def _summary(st):
    """The mechanical record a `close` writes -- assembled from the journal,
    never typed: how many steps landed, how many were minted or amended into
    each segment beyond its first (the implement/review loop count), the
    review panel's verdict where this run had one, the change and deviations
    the last implement step wrote, every check the engine ran, the tier this
    run was dispatched under, and one line per amend."""
    cycles = {}
    for s in st["steps"]:
        if s.get("source") in ("mint", "amend"):
            cycles[s["segment"]] = cycles.get(s["segment"], 0) + 1
    # A panel is a panel whether or not its step also carries a form: the
    # two-voices transition's critics rule on the plan exactly as a
    # panel-only review rules on a diff, and skipping them wrote the empty
    # string into the close summary of every run three critics had judged.
    # The last panel-bearing step in journal order wins, and this loop --
    # unlike the review yield's -- would also reach a panel whose voices are
    # dispatched under a form declaring no verdict at all, design-it-twice's
    # rival-planner panel (ruling 10, shelved #96) having been the tree's one
    # worked example. Such a round settles nothing about a verdict, so it
    # reports `""`: neither the tuple the fold hands back nor a clean word
    # carried forward from some earlier panel this one has superseded.
    verdict = ""
    asm = runmod.load_assembly(st["assembly"]) if st.get("assembly") else None
    for s in st["steps"]:
        if s.get("panel") and asm:
            rs = st["returns"].get(s["id"]) or []
            if rs:
                _, spec = runmod.deciding_spec(asm, s)
                verdict = runmod.verdict_record(
                    runmod.verdict_fold(rs, runmod.panel_forms(asm, s), spec))
    amends = [{"action": a.get("action", ""), "step": a.get("step", ""),
               "segment": a.get("segment", ""), "reason": a.get("reason", ""),
               "anchor": a.get("anchor", False)} for a in st.get("amends", [])]
    # Rationale: an implement step is the step whose fields carry `change`,
    #   which holds for IMPLEMENT.toml in whatever assembly declares it. The
    #   last submitted one wins, because a revise round rewrites the diff and
    #   the earlier round's account of it is stale.
    # Rejected: keying off the assembly, the segment id or the form path.
    #   That special-cases every run which fills no such form -- run-an-issue
    #   closing, a gate released up through IMPASSE -- where both keys are
    #   simply empty here instead.
    change, deviations = "", ""
    for entry in reversed(list(st["done"].values())):
        fields = entry.get("fields") or {}
        if "change" in fields:
            change = fields.get("change", "")
            deviations = fields.get("deviations", "")
            break
    return {
        "steps_completed": len(st["done"]),
        "cycles": [{"segment": seg, "count": n} for seg, n in cycles.items()],
        "verdict": verdict,
        "change": change,
        "deviations": deviations,
        "checks": list(st.get("checks", [])),
        "proof_trials": list(st.get("proof_trials", [])),
        "model": st.get("model", ""),
        "amends": amends,
    }


# [returned-decision]
# Rationale: a `decides` field is not only a panel's -- a two-voices step's
#   own ruling, and gate adjudication's `plan-holds`, are exactly as
#   returnable as a panel's merged verdict, and both should reach a return
#   through the one mechanism rather than a second one hardcoding which
#   field name to look for. Read off the most recent done step that
#   declares one, since an earlier round's decision (an impasse ruled, three
#   gates back) is stale the moment a later one lands.
# Rejected: reading only the terminal step. A run can close having decided
#   nothing on its own terminal form -- run-a-gate's GATE_CLOSE has no
#   `decides` field -- while an earlier step (its own impasse ruling) did;
#   the terminal step is the wrong place to stop looking.
# Rejected: walking `st["steps"]` backwards, which is what this did while a
#   run's beats and its segment list ran in the same order. run-a-gate's
#   loop crosses back -- work, review, work again -- so the last *step* is
#   an earlier *answer* than a decision made in the segment above it, and a
#   gate that ruled `up` at its impasse returned the previous round's
#   `rework` instead. `st["done"]` is built in journal order, which is when
#   each answer actually landed.
def _last_decision(st, asm):
    """The value of the last `decides` field this run itself answered, or
    the empty string when it never declared one."""
    steps = {s["id"]: s for s in st["steps"]}
    for sid in reversed(list(st["done"])):
        step = steps.get(sid)
        if step is None:
            continue
        field = _decided_here(asm, step)
        value = (st["done"][sid].get("fields") or {}).get(field, "") if field else ""
        if value:
            return value
    return ""


# [close-pushes-before-anything-moves]
# Rationale: mirrors `_open_root_worktree`'s own push-before-journal choice,
#   aimed at the same remote and the same blip. Nothing is journaled closed
#   and nothing is moved until the branch is pushed and the PR exists, so a
#   failure here leaves an intact run the same `spine <id> close` retries --
#   never a run journaled closed, archived and swept with no PR and no
#   defined recovery.
# Rejected: journaling `closed` first and pushing after. A failed push or PR
#   would then leave `st["closed"]` true, and this function's own guard two
#   lines up would refuse the retry with "already closed" -- an escape that
#   does not work, which the corollary rules out.
#
# [close-publishes-what-the-branch-holds]
# Rationale: #176 -- close assumed it was the only thing that ever opened a
#   PR and that a run always had a diff. A conductor who had already opened
#   the PR met `gh pr create` refusing a second one, and a run ruled "not
#   needed" met it refusing a branch with no commits; either way the refusal
#   named a retry that could never succeed. So close reads the branch rather
#   than assuming it: no commits past the cut is a run with nothing to
#   publish, and an open PR on the branch is the run's PR. A PR close does
#   open is a draft carrying the run's own disposition -- merging is the
#   owner's act, and the body is what the run concluded, not a bare id.
#
# [a-merged-pr-is-the-runs-pr]
# Rationale: tennis_elo issue163 -- the principal merged the run's PR before
#   close ran. Only an open PR was looked for, so close asked `gh pr create`
#   for a branch main already held, and the refusal's retry could never
#   succeed. A PR merged from the branch is the run's PR as much as an open
#   one is. A PR closed unmerged is not: it was set aside, and the run's
#   work still needs one.
def _publish(wid, top, st, body):
    """The run's PR URL once the branch is pushed and a PR exists for it, or
    "" when the branch holds no commits past the run's cut point."""
    branch = st["branch"]
    if _commits_past_cut(top, st) == 0:
        return ""
    pushed = _git(top, "push", "origin", branch)
    if pushed.returncode != 0:
        raise SystemExit(render.refusal(
            "push", f"push failed -- {(pushed.stderr or pushed.stdout).strip()}",
            escape=f"the run is untouched -- retry: spine {wid} close"))
    found = _gh(top, "pr", "list", "--head", branch, "--state", "all",
                "--json", "url,state")
    if found.returncode == 0:
        prs = json.loads(found.stdout or "[]")
        live = [p["url"] for p in prs if p.get("state") in ("OPEN", "MERGED")]
        if live:
            return live[0]
    pr = _gh(top, "pr", "create", "--draft", "--head", branch,
             "--title", st.get("title") or wid,
             "--body", f"{body}\n\nWork-Id: {wid}".lstrip())
    if pr.returncode != 0:
        raise SystemExit(render.refusal(
            "pr", f"gh pr create failed -- {(pr.stderr or pr.stdout).strip()}",
            escape=f"the branch is pushed and the run is otherwise untouched -- "
                   f"retry: spine {wid} close"))
    return pr.stdout.strip()


def _commits_past_cut(top, st):
    """How many commits the run's branch holds past its cut point, or None
    where the run records no cut point or git cannot say."""
    sha = (st.get("from") or "").rpartition("@")[2]
    if not sha:
        return None
    counted = _git(top, "rev-list", "--count", f"{sha}..{st['branch']}")
    return int(counted.stdout.strip()) if counted.returncode == 0 else None


# [archive-then-sweep]
# Rationale: the work location lives inside the worktree
#   (`<worktree>/.agent-work/<wid>`), so it has to be moved out before the
#   worktree is removed -- removing it first would delete the record this
#   is trying to preserve, not merely the tree around it. `os.chdir(top)`
#   before the remove for the same reason `cmd_open` chdirs into the
#   worktree it just made: the worktree being removed may be this very
#   process's own cwd, and a process left standing in a directory that no
#   longer exists is not a state anything after it can rely on.
def _sweep_to_archive(wid, top, dest, worktree):
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(journal.location(wid)), str(dest))
    os.chdir(top)
    _git(top, "worktree", "remove", "--force", str(worktree))


# [fold-measures]
# Rationale: `_measure_artifacts` writes into the submitting run's own
#   journal, and `render.drift` reads two points from that same run's own
#   state -- true while a segment's rounds were forms on one worklist, false
#   the moment a round became a dispatch: a fresh child every round means
#   neither the child (one round, then gone) nor the parent (never wrote the
#   entry itself) ever holds two. Folding the closing child's own measures
#   into the parent, under the parent's dispatching step, is what lets
#   `render.drift` see a sequence again -- attributed to that step's own
#   segment, not the child's, since the child's segment name (`cut`) means
#   nothing in the parent's assembly and would never match `st["current"]`.
def _fold_measures(cst, pwid, pstep_id):
    """A closing child's own `measure` entries, re-homed onto the parent
    step that dispatched it. A no-op when the parent step cannot be found
    (its journal predates this, or was hand-edited) or the child recorded
    nothing -- an artifact too short to measure leaves nothing to fold."""
    if not cst["measures"]:
        return
    pst = runmod.state(pwid)
    pstep = next((s for s in pst["steps"] if s["id"] == pstep_id), None)
    if not pstep:
        return
    for m in cst["measures"]:
        journal.append(pwid, "measure", segment=pstep["segment"], step=pstep_id,
                       field=m.get("field"), path=m.get("path"), words=m.get("words"))


def cmd_close(argv):
    wid = argv[0]
    st = runmod.state(wid)
    if st is None:
        _no_run(wid)
    if st.get("closed"):
        raise SystemExit(f"{wid} is already closed")
    asm = runmod.load_assembly(st["assembly"])
    pending = [s for s in st["steps"] if s["id"] not in st["done"]]
    # [close-settles-too]
    # Rationale: `_settle_execution` (`[settle-execution]`) only ever fires
    #   from inside the execute segment's own outcome table -- `advance`'s
    #   `commit; settle` and `drop <gate-id>`'s `close; settle` (#95) -- so
    #   it never runs at all when execute's worklist empties by some other
    #   route: a projecting transition whose mint lands nothing (#141 was
    #   one cause of that), or a step closed directly by `amend close` --
    #   this same function's own escape for a stuck step, below. A run can
    #   then reach CLOSE.toml with an obligation still `open` on the
    #   execution-state board and no live step left to close it, and
    #   nothing has ever read the board to notice (#143). `cmd_close` is
    #   where every route to the terminal step converges -- the terminal
    #   form is already submitted and nothing else is pending -- so the
    #   read belongs here too, once, before the run is allowed to finalize.
    #   `_settle_execution` still refuses nothing on the board's own
    #   content: an open row mints a fresh plan round exactly as it already
    #   does mid-run, and the `pending` recheck below reports it through
    #   the ordinary "not complete" refusal below -- no new refusal text,
    #   no second escape to maintain.
    # Rejected: refusing here with bespoke wording naming the open row.
    #   The refusal below already says a pending step by name and how to
    #   work it; a second, differently-worded refusal for the same fact --
    #   "not complete" -- would be two things to keep saying the same
    #   thing.
    if not pending:
        _recheck_satisfied(wid, asm)
        _settle_execution(wid, asm)
        st = runmod.state(wid)
        pending = [s for s in st["steps"] if s["id"] not in st["done"]]
    if pending:
        step = pending[0]
        drop_it = f"drop it: spine {wid} amend close {step['id']} --reason ..."
        waive_it = f"waive it: spine {wid} amend waive {step['id']} --reason ..."
        # The escape offered besides `how` -- the one that always exists --
        # is `drop_it` by default, and stays that for every kind below
        # except a two-voices panel step: `amend close` there would drop
        # the conductor's own route form along with the panel it is
        # escaping, exactly the move issue811's ruling cost three hand
        # repairs, so its always-exists escape waives the panel instead
        # (`outstanding_line`'s own rule, engine/render.py).
        escape = drop_it
        # The way past a pending step depends on what kind it is: a step whose
        # panel is still outstanding has no form to fill yet -- true whether
        # or not it has one at all -- a dispatch step has no form either, and
        # offering the wrong escape is worse than offering none.
        if runmod.panel_outstanding(st, step):
            how = f"its panelists complete it: spine {wid}"
            if step.get("panel") and step.get("form"):
                escape = waive_it
            pasm = runmod.load_assembly(st["assembly"])
            child_ids = [d[0] for d in _panel_descriptors(wid, pasm, step)]
            records = _dispatch_records(wid)
            counts = _dispatch_start_counts(wid)
            _, name_wait = _outstanding_state(
                wid, child_ids, st["returns_by_child"], records, counts)
            if name_wait:
                how = f"spine {wid} wait"
        elif runmod.paused(step):
            how = (f"its ask is standing at its parent, not here: spine {st.get('parent')}"
                  if st.get("parent") else
                  "its ask has no parent left to stand on -- see the blocked note above")
        elif step.get("dispatches"):
            child_id = step.get("child") or f"{wid}.{step['id']}"
            records = _dispatch_records(wid)
            counts = _dispatch_start_counts(wid)
            _, name_wait = _outstanding_state(
                wid, [child_id], st["returns_by_child"], records, counts)
            how = f"spine {wid} wait" if name_wait else drop_it
        else:
            how = f"fill its form and submit it: spine {wid} submit"
        suffix = "" if how == escape else f"\n  or {escape}"
        raise SystemExit(render.refusal(
            step["id"], "not complete", escape=f"{how}{suffix}"))
    # Structural, like `_commit_gate`'s own guard: `_issue_tier` alone is not
    # enough, since `cmd_open` stamps `branch`/`worktree` onto every root
    # run's opening entry, issue-tier or not. Both together name exactly the
    # runs g1 actually gave a pushed worktree to.
    archiving = _issue_tier(asm) and bool(st.get("worktree")) and bool(st.get("branch"))
    top = dest = worktree = pr_url = None
    if archiving:
        worktree = pathlib.Path(st["worktree"])
        top = worktree.parent.parent  # <top>/.worktrees/<wid> -- g1's own fixed layout
        dest = top / ".agent-work" / "archive" / pathlib.Path(*wid.split("."))
        if dest.exists():
            raise SystemExit(render.refusal(
                "archive", f"{dest} already exists -- {wid} reused",
                escape=f"move it aside, then retry: spine {wid} close"))
    terminal = next((s for s in st["steps"] if s.get("terminal")), None)
    fields = st["done"][terminal["id"]].get("fields", {}) if terminal else {}
    if archiving:
        pr_url = _publish(wid, top, st, str(fields.get("disposition") or ""))
    summary = _summary(st)
    decision = _last_decision(st, asm)
    journal.append(wid, "closed", fields=fields, summary=summary, decision=decision)
    if st.get("parent") and st.get("parent_step"):
        # `journal.unbound()`: `st["parent"]` is this closing run's own
        # recorded parent, not a caller-named id (see `[return-delivery-is-
        # not-a-fresh-resolution]`, `engine/journal.py`) -- without it, a
        # bound dispatched child (every review panelist and nested gate)
        # could never deliver its own return, and would always fall to the
        # "parent not found" branch below instead.
        with journal.unbound():
            parent_exists = journal.exists(st["parent"])
            if parent_exists:
                _fold_measures(st, st["parent"], st["parent_step"])
                journal.append(st["parent"], "return", step=st["parent_step"], child=wid,
                               row=st.get("row", ""), fields=fields, summary=summary,
                               decision=decision)
                _act_on_verdicts(st["parent"], st["parent_step"])
        if not parent_exists:
            # Writing anyway would create the parent's journal from nothing --
            # a run with no opening, no title, no assembly, sitting in the
            # ledger. Say the return went nowhere instead.
            journal.append(wid, "note", id=f"n{secrets.token_hex(2)}",
                           kind_detail="blocked", about="",
                           text=f"parent {st['parent']} not found -- return not delivered")
            print(f"warning: parent {st['parent']} not found -- return not delivered")
    # The run's own review yield -- rounds per seam, findings per round, how
    # each was called -- written beside CLOSE.toml so `_sweep_to_archive`
    # carries it into the archive with everything else this run produced,
    # and printed here so a conductor sees it without opening the archive.
    # Computed, never asked for: `docs/DERIVED_IS_CODE.md`'s first instance
    # for a lesson rather than a field (#16).
    yield_table = render.review_yield(review_yield.run_yield(wid))
    if yield_table:
        (journal.location(wid) / "YIELD.md").write_text(yield_table + "\n",
                                                        encoding="utf-8")
        print(yield_table + "\n")
    print(f"closed {wid}\n")
    result = cmd_status([wid])
    if archiving:
        _sweep_to_archive(wid, top, dest, worktree)
        # A shell that was standing inside the worktree this just removed is
        # now stranded in a directory that no longer exists -- `os.chdir`
        # above only moves this process, the same asymmetry `cmd_open`'s own
        # "if this shell has not followed" already names for the open side.
        if not pr_url:
            # Nothing past the cut: the branch is the base under another
            # name, so it goes, here and on the remote open pushed it to.
            _git(top, "branch", "-D", st["branch"])
            _git(top, "push", "origin", "--delete", st["branch"])
        published = pr_url or f"no commits past the cut -- no PR; branch {st['branch']} deleted"
        print(f"{published}\narchived to {dest}\n  worktree removed: {worktree}\n"
              f"  if this shell was standing inside it:\n  cd {top}\n")
    return result


def cmd_ledger():
    # Both roots: this checkout's own `.agent-work`, then each sibling
    # worktree's -- a run opened at the issue tier works inside one, and
    # bare `spine` from the top level must still list it. `archive` is
    # never a worktree's own -- `cmd_close` only ever makes one in the
    # top-level checkout's `.agent-work` -- so skipping that one name here
    # is enough: without it, a closed and archived run would still surface,
    # under a mangled id (`archive.<wid>`, `relative_to` walking straight
    # through the extra path segment) rather than not at all.
    rows = []
    for root in journal.agent_work_roots():
        for j in sorted(root.glob("**/journal.toml")):
            rel = j.parent.relative_to(root)
            if rel.parts[:1] == ("archive",):
                continue
            wid = str(rel).replace("/", ".")
            # [one-bad-journal]
            # Rationale: this is the only verb that folds runs it was not
            #   asked about, so it is the only one where a journal nobody
            #   named can decide what happens. `.agent-work` is where
            #   hand-written debris accumulates, and one stub with no
            #   `segment` on a step entry used to raise out of `_ordered` and
            #   take the ledger down for every run -- hit by three agents
            #   independently during #43. The ledger is how an agent finds
            #   its own run; losing all of them to one file it did not write
            #   is the worst trade this verb can make.
            # Rejected: skipping quietly. An agent would then look for a run
            #   the ledger will never show, with nothing to point at.
            try:
                st = runmod.state(wid)
            except Exception as e:
                print(f"{j}: could not be folded and is not listed -- "
                      f"{type(e).__name__}: {e}", file=sys.stderr)
                continue
            if not st:
                continue
            i, n, seg = runmod.position(st, None)
            rows.append({"id": wid, "assembly": st.get("assembly", ""),
                         "where": f"{seg} ({i}/{n})" if st["open"] else "closed",
                         "title": st.get("title", "")})
    print(render.ledger(rows))
    return 0


def cmd_trace(argv):
    """A run and everything it dispatched, as one timeline.

    Deliberately not offered in `status`'s legal moves. A run's agents are
    fresh on purpose -- nothing about the engine is resident between steps,
    and history is exactly what a room description withholds. This verb is
    for whoever is debugging the engine from outside a run, which is a
    different reader with different needs.
    """
    wid = argv[0]
    if not journal.exists(wid):
        _no_run(wid)
    # Relative to this run's own `.agent-work` -- not a literal cwd-relative
    # one -- since a traced run's tree may be a worktree's rather than here.
    agent_work = journal.root_for(wid) / ".agent-work"
    rows = []
    for path in sorted(journal.location(wid).glob("**/journal.toml")):
        run = str(path.parent.relative_to(agent_work)).replace(os.sep, ".")
        rows += [(e.get("at", ""), run, i, e)
                 for i, e in enumerate(journal.read(run))]
    # Stamps are second-resolution, so ties need a tiebreak, and the tie that
    # matters is a child's `closed` against the `return` it causes in its
    # parent -- the exact seam this verb exists to debug. Deepest run first
    # puts cause before effect there; within one run, file order still rules.
    rows.sort(key=lambda r: (r[0], -r[1].count("."), r[1], r[2]))
    print(render.trace(wid, rows))
    if "--yield" in argv:
        table = render.review_yield(review_yield.run_yield(wid))
        if table:
            print("\n" + table)
    return 0


def _opt(argv, name):
    return argv[argv.index(name) + 1] if name in argv else None


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    if not argv:
        return cmd_ledger()
    if argv[0] == "open":
        return cmd_open(argv[1:])
    if argv[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0
    verb = argv[1] if len(argv) > 1 else "status"
    verbs = {"status": cmd_status, "submit": cmd_submit, "note": cmd_note,
             "amend": cmd_amend, "close": cmd_close, "trace": cmd_trace, "up": cmd_up,
             "wait": cmd_wait, "drive": cmd_drive}
    if verb not in verbs:
        # `spine <id> sumbit` used to render the room and exit 0: only the exact
        # word is acted on, so a near-miss must not look like a hit.
        raise SystemExit(f"no verb {verb!r} -- one of: {', '.join(verbs)}\n\n{USAGE}")
    return verbs[verb]([argv[0]] + argv[2:])


if __name__ == "__main__":
    sys.exit(main() or 0)
