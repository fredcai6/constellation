"""`spine` -- the verbs `main()` dispatches.

Argument shape is deliberately flat: the work id comes first and is always
required, because an id inferred from the environment is how a dispatched
crew ends up driving its dispatcher's run. A bare `spine` prints the ledger,
never your run.
"""

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
spine <work-id> close               terminal: legal once every step is done
spine open <assembly> --title T [--issue N]
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


def mint_id(issue=None, kind="issue"):
    """A tracker number when there is one -- it is already collision-free and
    it associates the run to the issue for free. Otherwise random: two
    worktrees allocating in parallel cannot see each other's next number.
    The kind is the assembly's last word -- issue, gate, idea."""
    if issue:
        return f"issue{issue}"
    while True:
        wid = f"{kind}{secrets.token_hex(2)}"
        if not journal.exists(wid):
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
        text = pathlib.Path(path).read_text()
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
    for f in form.get("fields", []):
        fid = f["id"]
        if f.get("kind") != "artifact" or fid not in fields:
            continue
        value = fields[fid]
        if not isinstance(value, str) or forms.leading_word(value) in ("waived", "unknown"):
            continue
        try:
            pathlib.Path(root / value).read_text()
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
    for f in form.get("fields", []):
        if f.get("kind") != "artifact" or not isinstance(fields.get(f["id"]), str):
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
    depending on the shell the agent happens to be standing in."""
    return " && ".join(_resolve_one(part.strip(), root) for part in text.split("&&"))


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
# Rationale: one source of truth for "does this repository's palette start a
#   child itself", reused by `_dispatch_child`'s two callers and by the
#   outstanding-line gating in each -- three inline `"dispatch" in
#   _palette(...).get("commands", {})` checks could drift; this predicate is
#   the one place that can't.
def _dispatch_configured(tree):
    """Whether `tree`'s own `constellation.toml` names a `dispatch` entry --
    the same read `_spawn_outstanding`'s own call to `checkrun.spawn_dispatch`
    already makes through `_palette(tree)`, asked here as a plain bool rather
    than attempted as a spawn."""
    return "dispatch" in _palette(tree).get("commands", {})


def _current_form(st):
    asm = runmod.load_assembly(st["assembly"])
    step = st["current"]
    # [panel-before-dispatch]
    # Rationale: round one's own design panel (ruling 10) is the first step
    #   in the tree to carry both `dispatches` and `panel` -- checking
    #   `dispatches` first silently rendered it as a single-child brief,
    #   discoverable only once and then stuck, since a second open at the
    #   same untagged address refuses. `cmd_close`'s own pending-step
    #   guidance already checks panel first for the identical reason.
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
                              text=True, timeout=GIT_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as e:
        return subprocess.CompletedProcess(args, 1, "", str(e))


def _gh(cwd, *args):
    """One `gh` call against an explicit directory -- the same never-raises
    shape as `_git`, so `cmd_close` has one kind of failure to check for
    either. Intercepted on argv by the fast suite exactly where `_git` is
    not: a test that let this reach a real `gh` binary could open a real
    pull request against whatever `origin` happens to point at."""
    try:
        return subprocess.run(["gh", *args], cwd=str(cwd), capture_output=True,
                              text=True, timeout=GIT_TIMEOUT)
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


# [push-before-journal]
# Rationale: the branch and worktree are made and pushed before anything is
#   journaled. A push failure then leaves nothing behind to clean up beyond
#   what this function undoes itself, so the caller's retry is the same
#   command again, not a cleanup followed by a command.
# Rejected: journaling the run first and pushing after -- a failed push
#   would then leave a run that `journal.exists` calls real, and `--id`
#   would have to be swapped for a retry instead of just repeated.
def _open_root_worktree(wid, assembly, title):
    top = _toplevel_checkout(pathlib.Path.cwd())
    if top is None:
        raise SystemExit(render.refusal(
            "checkout", "not a git checkout",
            escape="open this from inside a git checkout of the project"))
    if not _git(top, "remote").stdout.strip():
        raise SystemExit(render.refusal(
            "remote", "the checkout has no remote",
            escape=f"add one: git -C {top} remote add origin <url>"))
    worktree = top / _WORKTREES_DIR / wid
    made = _git(top, "worktree", "add", "-b", wid, str(worktree))
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
    return worktree


def _commit_open(wid, worktree):
    """The commit `open` makes once the run's own work area exists inside
    the worktree. `.agent-work` is gitignored, so the ordinary case stages
    nothing -- a journaled no-op, not a failure the agent has to explain."""
    _git(worktree, "add", "-A")
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
# `_DISPOSE_MINT` joined `_BOARD_MINT` as a second engine-named mint (#56),
# and `_PANEL_MINT` a third (#57): all three sit in every assembly's
# `_mintable(asm)` whether or not that assembly's own forms use them, so all
# three are subtracted here -- an assembly is issue tier on a real
# `dispatches` name, never on an engine literal alone. Adding a mint to
# `_mintable` without adding it here reads every assembly, run-a-gate
# included, as issue tier, which is git and a worktree where commitment 7
# says none belong; `tests/test_archive_close.py::
# test_a_non_issue_tier_close_never_reaches_git_or_gh` is what says so loudly.
def _issue_tier(asm):
    return bool(_mintable(asm) - {_BOARD_MINT, _DISPOSE_MINT, _PANEL_MINT})


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
    wid = _check_id(_opt(argv, "--id") or mint_id(issue=issue, kind=assembly.rsplit("-", 1)[-1]))
    if journal.exists(wid):
        raise SystemExit(render.located(f"{wid} already exists\n  where it stands: spine {wid}"))
    asm = runmod.load_assembly(assembly)
    on_issue_tier = _issue_tier(asm)
    landed = ""
    if on_issue_tier:
        worktree = _open_root_worktree(wid, assembly, title)
        os.chdir(worktree)  # the work location this mints lands inside the worktree
        landed = (f"\n  now inside the worktree -- if this shell has not followed:\n"
                  f"  cd {worktree}\n")
    journal.append(wid, "run", title=title, assembly=assembly,
                   conductor=asm.get("conductor", ""), branch=wid,
                   worktree=str(pathlib.Path.cwd()))
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


def _open_child(assembly, parent, pstep_id, row_id=""):
    """A child is dispatched, never composed: its id, its orders, and the
    tier it runs under all come from the parent's step. A panelist is the
    same mechanism one entry finer -- `<step-id>.pN` names which panel
    entry, and the tag rides the work id so several children can share one
    parent step without colliding. An excursion is the same mechanism from
    a board row: the row is its brief, and its return lands under the row
    rather than completing any step.

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
        raise SystemExit(render.located(f"no run named {parent}\n  open runs: spine"))
    proot = journal.root_for(parent)
    if row_id:
        return _open_excursion(assembly, parent, pst, row_id, proot)
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
        # panel step's own prefill where the mint that made the step carried
        # one across (run-a-gate's `review`, minted a segment away from the
        # work it reads), and otherwise the segment's own most recent other
        # round -- the latest implement, cycles included.
        prefill = {**(pst.get("prefill") or {}),
                   **(pstep.get("prefill")
                      or _round_artifact(pasm, pst, pstep["segment"], step_id)),
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
        prefill = {**(pst.get("prefill") or {}), **(pstep.get("prefill") or {})}
        title = prefill.get("purpose", pstep_id)
    asm = runmod.load_assembly(assembly)
    journal.append(wid, "run", title=title, assembly=assembly,
                   conductor=asm.get("conductor", ""), parent=parent,
                   parent_step=step_id, model=tier, root=proot)
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
    print(f"opened {wid} -- dispatched by {parent} at {pstep_id}\n")
    return cmd_status([wid])


# [excursion]
# Rationale: the row is the brief. Its string columns -- the idea or
#   question, the excursion's named question and budget -- are the child's
#   prefill, so nothing is typed twice and the board stays the record of
#   what was asked. The return is journaled with the row, never as the
#   step's: an excursion answers a row, and a row completes nothing.
# Rejected: the engine writing the return into the board. Two writers on one
#   file is the hazard a board avoids; the return renders, the agent folds.
def _open_excursion(assembly, parent, pst, row_id, proot):
    seg_id, row = next(((sid, r) for sid, p in pst["boards"].items()
                        for r in boards.rows(p) if r.get("id") == row_id), ("", None))
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
    journal.append(wid, "run", title=boards.label(row)[:72], assembly=assembly,
                   conductor=asm.get("conductor", ""), parent=parent,
                   parent_step=seg_id, row=row_id, model=seg.get("model", ""),
                   root=proot)
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
#   climbing, since a gate or panelist nests inside its issue's own. The
#   branch is not derivable that way -- only a root run's opening entry
#   carries one -- so it is read off the nearest ancestor that has it.
# Rejected: a `branch` stamped on every run, including nested ones. That
#   would repeat one fact at every depth for no reason two-root resolution
#   does not already give for free once `worktree` is derived structurally.
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
def _dispatch_start_counts(wid):
    """`{child_id: count}` -- how many `dispatch-started` records `wid`'s
    own journal carries for each child that has ever been started at all;
    `_startable`'s own cap reads this, not `_dispatch_records`."""
    counts = {}
    for e in journal.read(wid):
        if e.get("kind") == "dispatch-started":
            counts[e.get("child")] = counts.get(e.get("child"), 0) + 1
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
#   and `_dispatch_child`'s configured "gone without returning" branch
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
def _spawn_outstanding(wid, child_id, brief_text, tier, tree, records, counts, is_returned):
    """Start `child_id`'s harness process through this repository's own
    `dispatch` palette entry -- a fresh start or a restart, whichever
    `_startable(is_returned, records.get(child_id), counts.get(child_id,
    0))` allows. A no-op, with nothing journaled or logged, once that
    predicate reads false: `child_id` already returned, or it is still
    alive, or it is dead-and-spent (`counts` has reached
    `checkrun.MAX_STARTS`). Also a no-op when the palette carries no
    `dispatch` entry at all (`spawn_dispatch` returns `None` for a
    repository that never configured one, commitment 3's world). The log
    basename is the child id's own tail past the leading `wid.` -- not
    merely its last dotted segment, which two different panel steps in the
    same run would both give `p1` -- so it stays distinct per child inside
    `wid`'s own work location, which is all commitment 18 asks.

    Returns the journal entry a successful attempt wrote, `None` for every
    other outcome (not startable, no `dispatch` entry configured, or the
    attempt failed) -- so `cmd_wait`, its one caller in `engine/` after
    this gate, can tell a genuine spawn from a no-op without a second pass
    over the journal, reading it straight off the return rather than
    rescanning."""
    if not _startable(is_returned, records.get(child_id), counts.get(child_id, 0)):
        return None
    tail = child_id[len(wid) + 1:] if child_id.startswith(wid + ".") else child_id
    log = journal.location(wid) / f"dispatch.{tail}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    try:
        return checkrun.spawn_dispatch(_palette(tree).get("commands", {}), brief_text,
                                       _runner(tier), tree, wid, child_id, log)
    except checkrun.DispatchFailure as e:
        with open(log, "a", encoding="utf-8") as f:
            f.write(f"{e.reason}: {e.detail}\n")
        return None


# [respawn-command]
# Rationale: a "gone without returning" child's own respawn command is not
#   always the brief's original `open it:` line -- a harness that died mid-
#   step already ran that line once before it died, so its own run already
#   exists by the time this room offers it again, and both paths that serve
#   `spine open ... --parent ...` (`_open_child`'s and `cmd_open`'s own
#   refusals, engine/cli.py -- left untouched by this gate) refuse outright,
#   unconditionally, the moment that run already exists. Reading
#   `journal.exists(child_id)` -- the same predicate those refusals already
#   gate on -- decides which of two already-correct commands to print,
#   without adding a new primitive or touching what either refusal does.
# Rejected: always printing the brief's own `open it:` line. That is the
#   exact command the spec's own opening scenario shows raising `SystemExit`
#   with "already exists" in it the moment a reader actually types it.
# See: `_wait_spawn` is this function's second caller -- it runs this
#   answer unconditionally, before every spawn attempt, rather than behind
#   a guard of its own, since `_respawn_cmd` already reduces to `open_cmd`
#   for a child never opened.
def _respawn_cmd(child_id, open_cmd):
    """The command a reader types to dispatch `child_id` again: the brief's
    own `open it:` line when that child's run was never opened, `spine
    {child_id}` -- the resume command `_open_child`'s and `cmd_open`'s own
    refusal messages already name -- when it was opened and then died."""
    return f"spine {child_id}" if journal.exists(child_id) else open_cmd


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
# [dispatch-child-suppresses-not-dispatched-brief]
# Rationale: a repository whose palette carries a `dispatch` entry has
#   `wait` starting this child itself -- printing the brief's `open it:`
#   line there is printing a command the reader must not run (`wait` beat
#   it to it, or will the moment it is typed). `configured` is threaded
#   through rather than re-derived here so `_dispatch_status` and
#   `_panel_status` each compute it once, from the same `worktree` they
#   already derive, and both `_dispatch_child` and their own outstanding-line
#   gating read the identical bool. The same suppression now also covers a
#   gone-and-configured child once its own `counts` reaches
#   `checkrun.MAX_STARTS`: `wait` will not restart it either, so there is
#   nothing left for a hand-typed respawn command to offer, and the status
#   word itself -- "gone without returning -- starts spent" -- carries that
#   fact instead.
def _dispatch_child(wid, child_id, role, tier, open_cmd, finish_form,
                    worktree, branch, records, counts, is_returned, configured):
    """One child's row: `(status, brief_text)`. `brief_text` is `None` for
    "working" (commitment 14 -- never a manual dispatch command beside a
    live pid), for "returned" (renders exactly as it does today), for "not
    dispatched" when `configured` is true, and now for "gone without
    returning" too once `configured` is true -- in every configured case
    that row prints its own word (plus, for a gone child, whether its
    starts are spent) and nothing else, since `spine <work-id> wait` is
    what starts or restarts it, not a hand-typed command. An unconfigured
    repository keeps both briefs exactly as before (commitment 17). A pure
    read off `records` and `counts` either way -- this call spawns nothing
    and threads nothing back; `cmd_wait` is the only caller left that
    starts or restarts a child (commitments 13-15, 23-28)."""
    runner = _runner(tier)
    if is_returned:
        return "returned", None
    record = records.get(child_id)
    if record is None:
        if configured:
            return "not dispatched", None
        return "not dispatched", render.brief(child_id, role, tier, runner, open_cmd,
                                              finish_form, worktree, branch)
    if checkrun.alive(record.get("pid")):
        return "working", None
    if configured:
        # Reads `_startable` rather than hand-writing the cap comparison it
        # reduces to here (`is_returned` false, `record` not `None`, and its
        # pid already dead are all decided above): keeps this branch from
        # drifting out of sync with `_startable` if a future clause is added
        # to that predicate.
        if _startable(is_returned, record, counts.get(child_id, 0)):
            return "gone without returning", None
        return "gone without returning -- starts spent", None
    return ("gone without returning",
           render.brief(child_id, role, tier, runner, _respawn_cmd(child_id, open_cmd),
                        finish_form, worktree, branch))


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
                          submit=render.located(f"spine {wid} submit"))
    kwargs = _room_kwargs(wid, st, asm, step, form, dest, root=root)
    return render.status(st, form, dest, tier=tier, runner=runner,
                         worktree=worktree, branch=branch, **kwargs)


def _panel_descriptors(wid, asm, step):
    """Each panelist a panel step names, as `(child_id, role, tier,
    open_cmd, finish_form)` -- a panelist's role is its own `worker`, not
    the give-a-verdict assembly's conductor: `_open_child` stamps that
    worker onto the dispatched child's step as its `filler`, so the panel
    entry is the source of truth, not just the brief that names it."""
    seg = next((s for s in asm["segment"] if s["id"] == step["segment"]), {})
    verdict_asm = runmod.load_assembly("give-a-verdict")
    out = []
    for i, panelist in enumerate(step["panel"], start=1):
        tag = f"p{i}"
        child_id = f"{wid}.{step['id']}.{tag}"
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
    """A dispatch step renders a brief, not a form: `wait`, not this
    render, starts this step's child through the repository's own
    `dispatch` palette entry when one is configured (commitments 13-15) --
    rendering this room only reads whatever `wait` has already done. A
    repository whose palette carries no such entry renders byte-for-byte
    as it always has, brief and all (commitment 17) -- there the reader is
    the one who starts the child, by hand, off the same brief. A configured
    repository suppresses that same brief for a "not dispatched" child and
    for a "gone without returning" one alike (commitment 22 -- `wait`
    starts or restarts either itself) and gains one line above the child's
    own row stating how many are outstanding and, where `wait` is
    genuinely the next move, naming it (commitments 18, 19) -- or, where
    nothing remains live or startable, naming the ruling escape to drop
    the step instead (commitment 30)."""
    child_id = step.get("child") or f"{wid}.{step['id']}"
    role, tier, open_cmd, finish_form = _dispatch_descriptor(wid, asm, step)
    worktree, branch = _tree_info(wid, st)
    configured = _dispatch_configured(worktree)
    records = _dispatch_records(wid)
    counts = _dispatch_start_counts(wid)
    status, brief_text = _dispatch_child(
        wid, child_id, role, tier, open_cmd, finish_form, worktree, branch,
        records, counts, child_id in st["returns_by_child"], configured)
    lines = render.preamble(st, blocked, runmod.position(st, asm))
    lines.append(render.imperative(render.DISPATCH))
    lines.append("")
    if configured:
        count, name_wait = _outstanding_state(
            wid, [child_id], st["returns_by_child"], records, counts)
        lines.append(render.outstanding_line(wid, count, name_wait, step["id"]))
        lines.append("")
    lines.append(f"  {child_id} ({status})")
    if brief_text:
        lines.append(brief_text)
    lines.append("")
    lines.append(render.legal_moves(wid))
    return "\n".join(lines)


def _panel_status(wid, st, asm, step, blocked):
    """A panel step renders each panelist's own row -- copied, never
    composed -- with each panelist's own status (commitment 12); a
    "working" or "returned" panelist carries no brief, and now neither
    does a "not dispatched" one, nor a "gone without returning" one, when
    the repository's palette carries a `dispatch` entry (commitment 22) --
    `wait` starts or restarts either itself, so only an unconfigured
    repository's "gone without returning" panelist still carries its own
    respawn brief. A panelist's role is its own `worker`, not the
    give-a-verdict assembly's conductor: `_open_child` stamps that worker
    onto the dispatched child's step as its `filler`, so the panel entry is
    the source of truth, not just the brief that names it. A configured
    repository also gains one line above the panelist rows stating how
    many are outstanding and, where `wait` is genuinely the next move,
    naming it (commitments 18, 19) -- or, where nothing remains live or
    startable, naming the ruling escape to drop the step instead
    (commitment 30)."""
    worktree, branch = _tree_info(wid, st)
    records = _dispatch_records(wid)
    counts = _dispatch_start_counts(wid)
    configured = _dispatch_configured(worktree)
    descriptors = _panel_descriptors(wid, asm, step)
    lines = render.preamble(st, blocked, runmod.position(st, asm))
    lines.append(render.imperative(render.PANEL))
    lines.append("")
    if configured:
        child_ids = [d[0] for d in descriptors]
        count, name_wait = _outstanding_state(
            wid, child_ids, st["returns_by_child"], records, counts)
        lines.append(render.outstanding_line(wid, count, name_wait, step["id"]))
        lines.append("")
    for panelist, (child_id, role, tier, open_cmd, finish_form) in zip(
            step["panel"], descriptors):
        tag = child_id.rsplit(".", 1)[-1]
        status, brief_text = _dispatch_child(
            wid, child_id, role, tier, open_cmd, finish_form, worktree, branch,
            records, counts, child_id in st["returns_by_child"], configured)
        lines.append(f"  panelist {tag} ({status})"
                     f" -- criteria: {panelist.get('criteria', '')}")
        if brief_text:
            lines.append(brief_text)
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
#   unconditional -- never gated on `_dispatch_configured` the way the
#   dispatch/panel line is -- because a step's proof is spawned through the
#   check-runner/`HANDBACK` mechanism, a path with nothing to do with
#   whether `commands.dispatch` is configured: a repository with no
#   `dispatch` entry at all can still have a proof genuinely in flight. It
#   never names `wait` as the move either way: `wait` renders this room
#   immediately without blocking on it, running or dead (commitment 6),
#   so claiming `wait` is the move would promise a block that never comes.
#   The running branch's own prose says plainly that nothing notifies the
#   reader -- three headless gate-conductors in this run read the old text
#   ("see where it landed: spine <wid>") as a destination rather than an
#   act, concluded a background process would tell them when the room
#   changed, and stopped acting; nothing was coming. The fix is not a
#   softer destination, it is an act with a cadence -- render this room
#   again, by hand, every minute or two, until it says something else. A
#   later reader must not "tidy" this back into a bare pointer: that is
#   the exact shape that already killed three runs.
def _in_flight_status(wid, st, asm, entry, blocked):
    """What a run whose proof is still running says about itself."""
    running = checkrun.alive(entry.get("pid"))
    lines = render.preamble(st, blocked, runmod.position(st, asm))
    for c in entry.get("commands") or []:
        lines.append(f"  {c.get('field', 'check')}: {c.get('command', '')}")
    lines.append("")
    lines.append(render.outstanding_line(wid, 1 if running else 0, False))
    lines.append("")
    if running:
        lines.append(render.located(
            f"  proof in flight since {entry.get('at', '')} (pid {entry.get('pid')}), "
            f"budget {entry.get('budget')}s -- this step is not done and nothing "
            "was recorded for it. The engine journals the submit itself when the "
            "proof passes, and refuses here when it fails.\n"
            f"  what it is printing: {entry.get('log', '')}\n"
            "  nothing notifies you when that happens -- no message arrives, and "
            "this room does not change on its own. Run this room's own command "
            f"again -- spine {wid} -- every minute or two, until it says "
            "something else."))
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
    """
    parent, pstep = st.get("parent"), st.get("parent_step")
    return (parent, pstep) if parent and pstep and journal.exists(parent) else None


def _board_state(path):
    """Everything `render._board` needs, computed once here rather than in
    the render layer -- `render.py` formats what it is given, it does not go
    read a board itself."""
    if not path:
        return None
    found = boards.rows(path)
    return {"path": path, "prose": boards.prose(path), "summary": boards.summary(path),
            "tree": [(d, r.get("id", ""), str(r.get("status", "")), boards.label(r))
                     for d, r in boards.tree(found)],
            "askable": [(r.get("id", ""), boards.label(r)) for r in boards.askable(found)],
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
        if s.get("panel") and rs and not runmod.panel_outstanding(st, s):
            _, spec = runmod.deciding_spec(asm, s)
            outcome = runmod.verdict_fold(rs, runmod.panel_forms(asm, s), spec)
            if outcome[0] == "clean" and \
                    runmod.declared_does(spec, outcome[1]) in (None, "release"):
                return ""
            return runmod.verdict_record(outcome)
    return ""


# [room-kwargs]
# Rationale: `cmd_status`'s own derivation of everything `render.status`
#   needs beyond `st`/`form`/`response_path` themselves -- the returned
#   child's fields folded flat, the board (now via `_board_path`, re-derived
#   fresh rather than trusted from whatever cwd minted it), prefill, in-hand
#   fields, the returned verdict, blocks, position, triage notes, the role,
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
    if step.get("terminal"):
        filler_status = "terminal"
    elif filler_record is not None and checkrun.alive(filler_record.get("pid")):
        filler_status = "working"
    elif filler_record is not None and filler_count >= checkrun.FORM_FILLER_MAX_STARTS:
        filler_status = "spent"
    else:
        filler_status = ""
    ret = st["returns_by_child"].get(step.get("child", "")) if step.get("child") else None
    returns = {**ret.get("summary", {}), **ret.get("fields", {})} if ret else None
    if returns:
        # Every structured value the summary can carry, spelled out rather
        # than left as a raw list -- str() on a list prints Python reprs, not
        # something a conductor can act on. A field's own form answer (e.g.
        # CLOSE.toml's `triage`) is a string that already overrode the
        # summary's list by the time it lands here, so only a survivor gets
        # rendered; the isinstance check is what tells the two apart.
        for key, fn in (("checks", render.checks), ("cycles", render.cycles),
                        ("amends", render.amends), ("triage", render.triage)):
            if isinstance(returns.get(key), list):
                returns[key] = "; ".join(fn(returns[key])) or "none"
    # Rendered whenever the segment has a board; `validates` decides only
    # whether submit refuses on it. The ideas board is read at every cycle
    # and refused at none.
    board = _board_state(_board_path(wid, st, step, root))
    prefill = {**(st.get("prefill") or {}), **(step.get("prefill") or {})}
    return {
        "prefill": prefill,
        "returns": returns,
        "returns_from": step.get("child", ""),
        "verdict": _returned_verdict(st, asm),
        "blocked": runmod.blocks(st),
        "position": runmod.position(st, asm),
        "board": board,
        "in_hand": forms.in_hand(dest) if dest.exists() else None,
        "triage_notes": [n for n in st["notes"] if n.get("kind_detail") == "triage"],
        "role": runmod.hat(asm, step, st),
        "row_returns": st["row_returns"],
        "filler_status": filler_status,
    }


def cmd_status(argv):
    wid = argv[0]
    st = runmod.state(wid)
    if st is None:
        raise SystemExit(render.located(f"no run named {wid}\n  open runs: spine"))
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
                          submit=render.located(f"spine {wid} submit"))
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
def _wait_spawn(wid, st, descriptors):
    """One spawn attempt for each `(child_id, role, tier, open_cmd,
    finish_form)` in `descriptors`, offered unconditionally to
    `_spawn_outstanding` -- `cmd_wait`'s own pre-loop start, making `wait`
    the sole spawner and respawner of a child (commitments 13-15, 23-28).
    Each brief's own command is `_respawn_cmd(child_id, open_cmd)`, correct
    for both a first start and a restart alike."""
    worktree, branch = _tree_info(wid, st)
    records = _dispatch_records(wid)
    counts = _dispatch_start_counts(wid)
    for child_id, role, tier, open_cmd, finish_form in descriptors:
        is_returned = child_id in st["returns_by_child"]
        brief_text = render.brief(child_id, role, tier, _runner(tier),
                                  _respawn_cmd(child_id, open_cmd),
                                  finish_form, worktree, branch)
        _spawn_outstanding(wid, child_id, brief_text, tier, worktree,
                           records, counts, is_returned)


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
        raise SystemExit(render.located(f"no run named {wid}\n  open runs: spine"))
    if not st["open"] or st["awaiting_close"]:
        return cmd_status([wid])
    asm, step, _ = _current_form(st)
    if runmod.panel_outstanding(st, step):  # checked before `dispatches`: see _current_form
        descriptors = _panel_descriptors(wid, asm, step)
    elif runmod.paused(step):
        return cmd_status([wid])
    elif step.get("dispatches"):
        child_id = step.get("child") or f"{wid}.{step['id']}"
        descriptors = [(child_id, *_dispatch_descriptor(wid, asm, step))]
    else:
        # `runmod.in_flight` names a proof, not a child, and a childless
        # form step has no child at all -- neither is something `wait` has
        # anything to poll, so both render immediately (commitment 29).
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
#   already use), and, new here, a repository whose palette carries no
#   `[commands] dispatch` entry at all: `_dispatch_configured` is called
#   today only from inside already-branched refusal text, never as a
#   call-ending check on its own, so this is that check's first caller --
#   without a `dispatch` entry `wait`'s own mechanism starts nothing for any
#   step, so `drive` would only ever spin to its own bound doing nothing,
#   and refusing outright says so instead of spinning quietly.
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
    (`awaiting_close`), a gate or panelist spent past `checkrun.MAX_STARTS`
    with nothing else outstanding for that step, or a childless form step's
    own filler spent past `checkrun.FORM_FILLER_MAX_STARTS` -- each stops and
    renders rather than crash or spin."""
    wid = argv[0]
    bound = _drive_bound(argv[1:])
    st = runmod.state(wid)
    if st is None:
        raise SystemExit(render.located(f"no run named {wid}\n  open runs: spine"))
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
            if step.get("terminal"):
                return cmd_status([wid])  # its own terminal form -- the principal's, not driven
            if runmod.in_flight(st, step):
                time.sleep(checkrun.WAIT_POLL)
                continue
            if _drive_form_filler(wid, st, asm, step, form):
                return cmd_status([wid])  # spent -- nothing left to spawn or poll
            time.sleep(checkrun.WAIT_POLL)
            continue
        cmd_wait([wid])  # the spawn/poll/render mechanism, unchanged
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
        worktree, _branch = _tree_info(wid, st)
        if _dispatch_configured(worktree):
            child_ids = [d[0] for d in _panel_descriptors(wid, asm, step)]
            records = _dispatch_records(wid)
            counts = _dispatch_start_counts(wid)
            _, name_wait = _outstanding_state(
                wid, child_ids, st["returns_by_child"], records, counts)
            if name_wait:
                escape = f"spine {wid} wait"
        raise SystemExit(render.refusal(
            step["id"], "a panel step is not submitted -- the panelists' verdicts "
            "complete it", escape=escape))
    if runmod.paused(step):
        raise SystemExit(render.refusal(
            step["id"], "paused -- the ask it sent is standing at its parent, not here",
            escape=(f"see it: spine {st.get('parent')}" if st.get("parent")
                   else "no parent left to see it at -- see the blocked note above")))
    if step.get("dispatches"):
        escape = (f"open its child: spine open {step['dispatches']} "
                  f"--parent {wid} --step {step['id']}")
        worktree, _branch = _tree_info(wid, st)
        if _dispatch_configured(worktree):
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
    # A check's command comes from the orders: the step's own prefill when it
    # has one, else the run's -- a dispatched child carries its spec at the
    # run level, and its first step is minted before that spec exists. The
    # budget rides in beside it, from the same orders.
    orders = {**(st.get("prefill") or {}), **(step.get("prefill") or {})}
    commands = [(f["id"], _resolve_command(orders.get(f["id"], ""), check_root))
                for f in form["fields"] if f.get("kind") == "check"]
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
    # A `beyond` call is a triage candidate by every route form's own words;
    # journaling it as the note kind CLOSE.toml already asks for is what
    # carries it there without the conductor retyping it (`[beyond-calls]`).
    for candidate in _beyond_calls(fields):
        journal.append(wid, "note", id=f"n{secrets.token_hex(2)}",
                       kind_detail="triage", text=candidate, about="",
                       step=step["id"])
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
    if step.get("carries") and _releases(outcome):
        journal.append(wid, "prefill",
                       fields={**(st.get("prefill") or {}), **fields})
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
    fills, so this mints it; one with neither a form nor a `route-form` on
    its segment has nothing to mint, and the run walks on.

    `route-form` is read here for the same reason it exists at all: a
    segment whose transition is minted (run-a-gate's `review`) declares no
    static `form`, so a caller that read `form` alone would mint nothing for
    it -- and an impasse ruling `advance` would then walk the gate past the
    round it is ruling on with nothing to dispose of it. What it mints is
    the form alone, never a panel: the ruling's own note says a fourth
    fresh-context reader is the loop, not the way out of it.
    """
    t = seg.get("transition", {})
    form = t.get("form") or seg.get("route-form", "")
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
def _releases(outcome):
    """True where this submit's own outcome finishes the deciding step's
    segment, rather than sending the round back (`rework`) or up (`pause`) --
    the two verbs that leave it still open. `None` -- no decided field, or a
    null the engine reads as waived/unknown -- releases too: nothing here
    holds the round open on its account."""
    if not outcome:
        return True
    _, does = outcome
    return not any(v.strip().split(" ", 1)[0] in ("rework", "pause")
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
#   as prefill". A finding the conductor accepted, sent to triage as beyond,
#   or rejected is a record, not an order for the next round, and handing it
#   forward verbatim is how a round gets worked on something already ruled
#   settled. Read off the submitted fields alone, never off a form or
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
def _blocking_calls(fields):
    """The `blocking`-called blocks of a submitted `calls` table, verbatim and
    in the order the conductor ruled them -- `None` where the submit carried
    no such table at all, which is every caller but run-a-gate's route form.

    `None` and `""` are different answers: no table means carry what the panel
    returned, an all-non-blocking table means carry nothing.
    """
    rows = (fields or {}).get("calls")
    if not isinstance(rows, list):
        return None
    return "\n\n".join(
        str(r.get("finding", "")).strip() for r in rows
        if isinstance(r, dict) and forms.leading_word(r.get("call", "")) == "blocking")


# [beyond-calls]
# Rationale: every route form says a `beyond` finding "leaves as a triage
#   candidate", and until now nothing carried it: the conductor was expected
#   to remember, several rounds later at the close form, what it had called
#   beyond and retype it there. That is the transcription bug `[gate-projection]`
#   already refused once -- "a second typing is a second chance to drift from
#   what the panel actually judged" -- and the evidence that it leaks is in
#   the archives, where a planner with no triage channel of its own put a
#   triage candidate in `direction` instead.
#   The destination already exists and is already wired: a `triage` note is
#   journaled by `cmd_note`, rendered into every room, collected by `trace`,
#   and asked for by name on CLOSE.toml, whose own header promises the engine
#   appends "the run's triage notes -- the candidates raised". So a beyond
#   call becomes one of those notes at submit, and reaches the close form the
#   way every other candidate already does.
# Rejected: a new prefill key carried to the close step. It would arrive only
#   at close, so nothing between here and there could see it, and the run's
#   own room would stop showing a candidate the moment it was called -- the
#   note mechanism shows it from the submit that raised it onward.
def _beyond_calls(fields):
    """The findings a submitted `calls` table called `beyond`, verbatim -- the
    triage candidates this submit raises. `[]` where the submit carried no
    such table, which is every seam with no route form."""
    rows = (fields or {}).get("calls")
    if not isinstance(rows, list):
        return []
    return [str(r.get("finding", "")).strip() for r in rows
            if isinstance(r, dict) and forms.leading_word(r.get("call", "")) == "beyond"
            and str(r.get("finding", "")).strip()]


# [seam-findings-history]
# Rationale: issue113's run-level round-cap owes its ask every landed
#   round's own findings, not only the round that tripped it (C1-findings)
#   -- the same "blocking calls narrowed where the round's own done-entry
#   carried a `calls` table, else every panelist's own non-empty `findings`
#   joined and attributed" rule `_panel_judged_rework` already applies to
#   the live round, walked here over every step `review_yield.seam_round_steps`
#   names instead of the one step `_perform` is deciding. Living beside
#   `_blocking_calls` rather than in `review_yield.py` reuses that reader
#   directly rather than a second copy of its own narrowing rule.
def _seam_findings_history(wid, seg):
    """Every round landed at `seg`'s own seam, oldest first, each block
    formatted exactly as `_panel_judged_rework` formats the current round's
    own findings prefill -- blocking calls narrowed where that round's own
    done-entry carried a `calls` table, else every panelist's own
    non-empty `findings` joined and attributed."""
    st = runmod.state(wid)
    blocks = []
    for rstep in review_yield.seam_round_steps(st, seg):
        called = _blocking_calls(st["done"].get(rstep["id"], {}).get("fields"))
        if called is not None:
            blocks.append(called)
            continue
        blocks.append("\n\n".join(
            f"[{r['child'].rsplit('.', 1)[-1]}] {(r.get('fields') or {}).get('findings', '')}"
            for r in st["returns"].get(rstep["id"], [])))
    return "\n\n".join(blocks)


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
# Rationale: a rework decided at a transition its own panel returned to is
#   the same act whichever voice decided it -- the merged verdict resolving
#   to `rework` (run-an-issue's consolidate and plan-to-execute,
#   explore-an-idea's spec) or a conductor's form submitting on the step
#   that panel already returned to (run-a-gate's review). Both owe the fresh
#   round the panel's own findings as prefill, and both spend the segment's
#   `impasse-after` count. So both live here, on the verb, rather than at
#   either caller: run-a-gate's review resolves `revise` to `release` now,
#   so the panel-return path never reaches `rework` for it again and an
#   outlet checked only there would silently stop firing.
# Rejected: duplicating the check on the ordinary submit path. Two counts
#   that happen to agree is the shape that drifts, and the fourth round is
#   exactly the round nobody re-tests by hand.
# See: `_blocking_calls` -- `fields` is the deciding submit's own, defaulted
#   so a caller with no table to filter by reads as one.
def _panel_judged_rework(wid, asm, seg, step, fields=None):
    """(prefill, outlet) for a rework decided at `seg`'s own panel-bearing
    transition: the panel's findings concatenated, never summarised, and
    attributed to the panelist that raised them -- or, where the deciding
    submit carried a per-finding `calls` table, the blocking-called blocks of
    that table alone (`_blocking_calls`) -- plus any `horizon` the round just
    judged wrote, which `skills/planner/SKILL.md` promises the next round
    arrives holding. `outlet` is the segment's impasse form once
    `impasse-after` rounds have already landed on this artifact, so a
    conductor rules on the loop rather than the run finishing around it.

    Where `step` is not that transition the outlet is always `""` -- an
    impasse ruling's own `rework` never spends the count, which is what makes
    the outlet a way out rather than a wall -- and the prefill is
    `_impasse_ruled_rework`'s: what caused the impasse, with the conductor's
    own `why` ahead of it (#107), or `None` where the ruling wrote no `why`
    the round can act on, which is the plain carry this had before.

    The guard is `step.get("panel")` alone, and that is the whole question:
    is *this deciding step* a two-voices panel transition. `panel` is written
    onto the step's own journal entry identically however the step came to
    exist -- by `skeleton()` from a statically declared `[segment.transition]`
    (consolidate, plan-to-execute, explore-an-idea's spec) or by `_mint`'s
    panelists branch at run-a-gate's `select` -- so the check survives a
    transition moving from a declaration to a mint. The one step it must not
    match is the impasse ruling itself, and that step is a single-conductor
    decision minted with no `panel` key at all, under every caller.
    """
    if not step.get("panel"):
        return _impasse_ruled_rework(step, fields), ""
    st = runmod.state(wid)
    findings = "\n\n".join(
        f"[{r['child'].rsplit('.', 1)[-1]}] {(r.get('fields') or {}).get('findings', '')}"
        for r in st["returns"].get(step["id"], []))
    called = _blocking_calls(fields)
    if called is not None:
        findings = called
    # The conductor's own `orders` (the route forms' 2026-09-05 field) go
    # ahead of the findings, marked as the conductor's: a status word there
    # (`waived: none`) is no order and carries nothing.
    orders = str((fields or {}).get("orders", "") or "").strip()
    if orders and forms.leading_word(orders) not in ("waived", "unknown", "working"):
        findings = f"[conductor] {orders}\n\n{findings}" if findings else f"[conductor] {orders}"
    # The round just judged is the segment's own most recent non-panel step --
    # the same lookup a panelist's own prefill uses (`_open_child`) to find
    # the artifact it is reviewing. Carried under the producing form's own
    # key, not a name this engine chose, so `test_promises.py`'s mint sweep
    # does not hold this call to it the way it holds `findings`.
    prior = [s for s in st["steps"] if s["segment"] == seg["id"] and s["id"] != step["id"]]
    produced = st["done"].get(prior[-1]["id"], {}).get("fields", {}) if prior else {}
    carried = {"horizon": produced["horizon"]} if produced.get("horizon") else {}
    after = seg.get("impasse-after", 0)
    looped = bool(after) and runmod.rework_rounds(st, asm, seg["id"]) >= after
    return {"findings": findings, **carried}, (seg.get("impasse-form", "") if looped else "")


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
        elif word == "rework":
            cap = seg.get("round-cap")
            if cap:
                landed = len(review_yield.seam_rounds(runmod.state(wid), seg, asm))
                if landed >= cap:
                    why = (f"{review_yield.seam_label(seg)} has landed {landed} rounds "
                           f"in this run, at its round-cap of {cap}")
                    _pause_gate(wid, tseg, why,
                                {"why": _seam_findings_history(wid, seg)})
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
# at all: a step-form segment's own transition (`select`, `understand`'s
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
# showed `select`, not `paused`. Reordering the marker (and, self-minted,
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
#   on -- ruling `up` from `work-1` says nothing about `select` -- and
#   closing it would strand the ordinary round `select` exists to receive
#   once the paused segment resumes and completes.
def _pause_gate(wid, tseg, reason, fields, resume_form="", resume_filler=""):
    """`up`'s own verb: an ask minted where a conductor can see it -- the
    parent standing on the step that dispatched this run, reordered before
    the still-live pair so it is what the parent's own `state()` stands on
    next, or -- nothing reachable there -- this run's own journal, reordered
    ahead of any untouched sibling transition instead (see `[pause-gate]`).
    A marker minted here either way, in the segment the answer resumes,
    reordered ahead of the same sibling regardless of which path the ask
    took -- the marker is what every path's own `state()` must find."""
    st = runmod.state(wid)
    pwid, pstep_id = st.get("parent"), st.get("parent_step")
    pstep = None
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
    journal.append(ask_wid, "step", id=ask_id, segment=ask_seg,
                   form="skills/gate-conductor/forms/ASK.toml", filler="conductor",
                   prefill=ask, resumes=wid, anchor=False, terminal=False,
                   validates="", source="mint")
    if pstep:
        journal.append(pwid, "amend", action="reorder", segment=pstep["segment"],
                       step=ask_id, before=pstep_id, reason=reason, anchor=False)
    # The untouched open-minted sibling `tseg`'s own segment may already
    # hold (`select`, `understand`'s own consolidate) -- present whether or
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
def _commit_gate(wid, asm, step):
    """One commit for the gate that just advanced: `git add -A` staged
    against the run's own worktree, on its own branch, the message naming
    the gate and its spec purpose and carrying the gate's own work id as a
    trailer. Nothing staged is the ordinary case wherever a gate's proof
    left no tracked diff -- a journaled no-op, never a refusal and never an
    empty commit. Neither guard below ever reaches `git`: each is the same
    shape of no-op, so a run this verb cannot commit for advances instead
    of stopping on an escape it has no way to take."""
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
    gate = next((s for s in st["steps"]
                if s.get("child") == child and s.get("dispatches")), None)
    gate_id = gate["id"] if gate else child
    purpose = (gate.get("prefill") or {}).get("purpose", "") if gate else ""
    _git(worktree, "add", "-A")
    message = f"{gate_id}: {purpose}\n\nWork-Id: {child or wid}"
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
#   nothing here: any status but `open` counts as settled, whatever word or
#   reason it carries, and a run that never seeded the board at all --
#   consolidate's `obligations` field is optional -- settles trivially, the
#   exact behaviour every run had before this gate.
# Rejected: validating dispositions the way `validates = "board"` does for
#   the understand board. The principal's own ruling: execution state is
#   mechanical-lane fields, not a second gate the engine adjudicates.
def _settle_execution(wid, asm):
    st = runmod.state(wid)
    path = st["boards"].get("execution-state", "")
    if not path or boards.summary(path)["by_status"].get("open", 0) == 0:
        return
    plan = next((s for s in asm["segment"] if s["id"] == "plan"), None)
    if plan:
        # The board still has open rows, so the plan is recut rather than
        # reworked: a fresh artifact, and a fresh count.
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


# [panel-mint]
# Rationale: a panel is written once, at the mint that makes the step, and
#   every consumer sizes off it (`state`'s two-voices fold, `_panel_status`,
#   `panel_outstanding`) -- so a `select` beat that genuinely chooses who
#   reads a diff cannot be a field that grows a panel already standing. It
#   has to be an earlier transition whose submit mints the later one, panel
#   and conductor form together. That is this third mint kind: engine
#   vocabulary, like the two above it, because no assembly declares a
#   segment named `panelists`.
# Rejected: a `panel = "<segment>"` field beside it, the way `_BOARD_MINT`
#   takes `board`. `_board_segment`'s own history is the order to follow,
#   not the endpoint: sole-match resolution shipped first with no target
#   parameter at all, and the name branch was grafted on non-disruptively
#   only once run-an-issue actually grew a second board. run-a-gate has
#   exactly one segment this mint could mean, so a target field here would
#   be a parameter with one legal value and no reader to disagree with it.
# See: assemblies/run-a-gate/ASSEMBLY.toml -- the `review` segment's
#   `route-form`, which is what this mint matches on.
_PANEL_MINT = "panelists"


def _mintable(asm):
    """The `mints` values legal in this assembly: `_BOARD_MINT`,
    `_DISPOSE_MINT`, `_PANEL_MINT`, plus every name a segment here declares
    as `dispatches`."""
    return ({_BOARD_MINT, _DISPOSE_MINT, _PANEL_MINT}
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
        elif mints == _PANEL_MINT:
            # The sole segment declaring a `route-form` is the one this can
            # mean, so nothing names it. What lands is the two-voices shape a
            # static transition would have declared: the submitted blocks as
            # the panel, the segment's own route-form as the conductor's half,
            # and the round this submit closes carried across as prefill --
            # the panel sits a segment away from the work it reads, so the
            # artifact cannot be found from its own segment at dispatch time.
            # `source = "panel"`, the same word `_mint_segment_round` stamps
            # on a re-fired panel, so `_summary`'s cycle count keeps meaning
            # "rounds beyond the first".
            seg = next((s for s in asm["segment"] if s.get("route-form")), None)
            if seg:
                t = seg.get("transition", {})
                st = runmod.state(wid)
                journal.append(wid, "step", id=f"{seg['id']}-a{secrets.token_hex(2)}",
                               segment=seg["id"], form=seg["route-form"], panel=rows,
                               filler=t.get("filler", "conductor"),
                               prefill=_round_artifact(asm, st, step["segment"], step["id"]),
                               anchor=t.get("anchor", False), terminal=False,
                               validates="", source="panel")
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
        prefill = {k: v for k, v in gate.items() if k != "id"}
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
_GATE_FIELDS = ("purpose", "scope", "proof", "budget", "model", "direction")


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
# See: `journal.py:119` -- `journal.append`'s own `mkdir(parents=True,
#   exist_ok=True)`, which is why this checks `journal.exists` before writing
#   anywhere in the child rather than after.
#
# issue84.g2's own review found the fix above only held through the pause
# moment: `_mint_segment_round` below is sibling-blind, plain-appending the
# fresh interior step and its fresh transition, so once the marker closes
# the untouched sibling `_pause_gate` only ever leapfrogged -- never itself
# reordered -- resurfaces ahead of the fresh round in `_ordered`'s own
# within-segment order. Driven live: a conductor answering the ask was
# handed `select`'s or `understand`'s own stale prompt instead of the fresh
# round's. Fixed by carrying the sibling forward on the marker itself
# (`_pause_gate`'s own `sibling` key, `""` when none was found) and
# reordering every step this mint just appended to the segment ahead of it,
# in mint order, mirroring the same move against the newly-live pair
# instead of the ask.
# Rejected: reordering only the fresh interior step. `_mint_segment_round`
#   also mints a fresh transition (`select`, or the two-voices panel step a
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
                        filler=marker.get("resume_filler", ""))
    if sibling:
        fresh = [s["id"] for s in runmod.state(child)["steps"]
                if s["segment"] == tseg_id and s["id"] not in before_ids]
        for fid in fresh:
            journal.append(child, "amend", action="reorder", segment=tseg_id,
                           step=fid, before=sibling,
                           reason="the resumed round stands ahead of the sibling "
                                  "the pause already leapfrogged, not behind it again",
                           anchor=False)


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
    text = template.read_text().rstrip()
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
                    f"{quoted}\n\n# --- the board ---\n\n{body}")


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
        raise SystemExit(render.located(f"no run named {wid}\n  open runs: spine"))
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
    journal.append(wid, "amend", action="close", segment=cur["segment"], step=cur["id"],
                   reason=reason, anchor=cur.get("anchor", False))
    # A panelist ruling `up` mid-verdict resumes into its own panel-entry
    # form/worker, not give-a-verdict's bare default -- read straight off
    # `cur`, which `_open_child`'s panel branch already overrode at open.
    # Only when the target IS the current step's own segment: every
    # cross-segment case (`review` bubbling up to `work`) resumes at a
    # segment `cur` never stood on, so its form/filler say nothing true
    # about what should resume there -- neither is supplied, reproducing
    # today's behaviour exactly.
    resume_form, resume_filler = "", ""
    if tseg["id"] == cur["segment"]:
        resume_form, resume_filler = cur.get("form", ""), cur.get("filler", "")
    _pause_gate(wid, tseg, reason, {}, resume_form=resume_form, resume_filler=resume_filler)
    print(f"paused {wid}\n")
    return cmd_status([wid])


NOTE_KINDS = ("blocked", "resumed", "observation", "decision", "triage")


def cmd_note(argv):
    if len(argv) < 2:
        raise SystemExit(f"spine <work-id> note <{'|'.join(NOTE_KINDS)}> <text>")
    wid, kind, text = argv[0], argv[1], " ".join(argv[2:])
    if kind not in NOTE_KINDS:
        # `note block ...` used to print success and do nothing at all: only
        # the exact word is acted on, so a near-miss must not look like a hit.
        raise SystemExit(f"no note kind {kind!r} -- one of: {', '.join(NOTE_KINDS)}")
    st = runmod.state(wid)
    if st is None:
        raise SystemExit(render.located(f"no run named {wid}\n  open runs: spine"))
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
        raise SystemExit("spine <work-id> amend add|close|reorder ... --reason \"...\"")
    wid, action = argv[0], argv[1]
    reason = _opt(argv, "--reason")
    if not reason:
        raise SystemExit(render.refusal("reason", "amend needs --reason"))
    st = runmod.state(wid)
    if st is None:
        raise SystemExit(render.located(f"no run named {wid}\n  open runs: spine"))
    if action == "add":
        return _amend_add(wid, st, argv[2:], reason)
    if action == "close":
        return _amend_close(wid, st, argv[2], reason)
    if action == "reorder":
        return _amend_reorder(wid, st, argv[2], reason, _opt(argv, "--before"))
    raise SystemExit(f"unknown amend action {action!r} -- add | close | reorder")


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
                "validates": t.get("validates", ""), "source": "amend"}
        # The segment's `route-form` is the same fallback `_mint_transition`
        # reads, for the same reason and from the same place: a segment whose
        # transition step is minted rather than declared carries no `form` on
        # the transition at all -- `run-a-gate`'s `review` declares no
        # `[segment.transition]` table whatsoever. Reading only `t` here minted
        # a step with no form, which no agent can fill and `cmd_submit` cannot
        # load, wedging the run the way a renamed form does.
        form = t.get("form") or segment.get("route-form", "")
        if form:
            step["form"] = form
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
                        restarts=False):
    """Mint one fresh round of a segment: its step-form (or the form the
    caller names -- a revise passes the segment's rework form) as a fresh
    interior step, plus its transition's panel -- both read from the
    assembly, never copied from whatever minted last. The shared move a
    revise and a replan both need: the segment reopened for another pass,
    carrying the same challenge that judges it.

    `restarts` says which kind of round this is, and only the caller knows:
    a `rework` is another pass at the artifact standing (the default), a
    `refill` is a fresh one. It is journaled as `sent_back` so
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
    # two-voices step. run-a-gate's `work` transition is the first to declare
    # a form and no panel -- `select` chooses the next round's readers rather
    # than carrying the last round's forward -- so neither key is assumed.
    # `anchor`/`terminal` are read off the transition itself rather than
    # hardcoded False: no existing step-form segment's transition declares
    # `terminal = true`, so this is a pure extension for every one of them,
    # and it is what lets `verdict`'s own resumed round keep being the
    # segment's one terminal step -- without it `cmd_close` found no
    # terminal step and the panelist's actual ruling never reached its
    # parent.
    fresh = {"id": f"{seg_id}-a{secrets.token_hex(2)}", "segment": seg_id,
             "filler": t.get("filler", "conductor"),
             "anchor": t.get("anchor", False), "terminal": t.get("terminal", False),
             "source": "panel"}
    if t.get("panel"):
        fresh["panel"] = t["panel"]
    if t.get("form"):
        fresh["form"] = t["form"]  # the two-voices shape survives a fresh round
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
    returns = pst["returns"][step_id]
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
    # Rationale: a panel is not only a transition's now (ruling 10) -- an
    #   interior step's own design panel authors, it does not decide, and
    #   the segment it sits in still declares `decides` for its impasse
    #   ruling. `_decided_here`'s segment fallback exists for that direct
    #   submit, not for a synthesised panel verdict, so this reads `decides`
    #   only when `step` really is the transition, never falling back.
    # Rejected: calling `_decided_here` here as before. Its fallback made an
    #   interior design panel's merged "pass" get checked against the
    #   segment's own outcome table (advance | rework | up) -- a value that
    #   table never declares, so closing the last planner sibling refused.
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
    run was dispatched under, one line per amend, and every triage note --
    the candidates this run raised, so a parent adjudicating the return sees
    them without opening the child's journal."""
    cycles = {}
    for s in st["steps"]:
        if s.get("source") in ("mint", "amend"):
            cycles[s["segment"]] = cycles.get(s["segment"], 0) + 1
    # A panel is a panel whether or not its step also carries a form: the
    # two-voices transition's critics rule on the plan exactly as a
    # panel-only review rules on a diff, and skipping them wrote the empty
    # string into the close summary of every run three critics had judged.
    # The last panel-bearing step in journal order wins, and this loop --
    # unlike the review yield's -- reaches the design-it-twice panel too,
    # whose planners are dispatched under a form declaring no verdict at
    # all. That round settled nothing about a verdict, so it reports `""`:
    # neither the tuple the fold hands back nor a clean word carried
    # forward from some earlier panel this one has superseded.
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
    triage = [{"text": n.get("text", "")} for n in st["notes"]
              if n.get("kind_detail") == "triage"]
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
        "model": st.get("model", ""),
        "amends": amends,
        "triage": triage,
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
def _push_and_open_pr(wid, top, branch, title):
    pushed = _git(top, "push", "origin", branch)
    if pushed.returncode != 0:
        raise SystemExit(render.refusal(
            "push", f"push failed -- {(pushed.stderr or pushed.stdout).strip()}",
            escape=f"the run is untouched -- retry: spine {wid} close"))
    pr = _gh(top, "pr", "create", "--head", branch,
             "--title", title or wid, "--body", f"Work-Id: {wid}")
    if pr.returncode != 0:
        raise SystemExit(render.refusal(
            "pr", f"gh pr create failed -- {(pr.stderr or pr.stdout).strip()}",
            escape=f"the branch is pushed and the run is otherwise untouched -- "
                   f"retry: spine {wid} close"))
    return pr.stdout.strip()


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
        raise SystemExit(render.located(f"no run named {wid}\n  open runs: spine"))
    if st.get("closed"):
        raise SystemExit(f"{wid} is already closed")
    pending = [s for s in st["steps"] if s["id"] not in st["done"]]
    if pending:
        step = pending[0]
        drop_it = f"drop it: spine {wid} amend close {step['id']} --reason ..."
        # The way past a pending step depends on what kind it is: a step whose
        # panel is still outstanding has no form to fill yet -- true whether
        # or not it has one at all -- a dispatch step has no form either, and
        # offering the wrong escape is worse than offering none.
        if runmod.panel_outstanding(st, step):
            how = f"its panelists complete it: spine {wid}"
            worktree, _branch = _tree_info(wid, st)
            if _dispatch_configured(worktree):
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
            how = f"open its child: spine open {step['dispatches']} --parent {wid} " \
                  f"--step {step['id']}"
            worktree, _branch = _tree_info(wid, st)
            if _dispatch_configured(worktree):
                child_id = step.get("child") or f"{wid}.{step['id']}"
                records = _dispatch_records(wid)
                counts = _dispatch_start_counts(wid)
                _, name_wait = _outstanding_state(
                    wid, [child_id], st["returns_by_child"], records, counts)
                how = f"spine {wid} wait" if name_wait else drop_it
        else:
            how = f"fill its form and submit it: spine {wid} submit"
        suffix = "" if how == drop_it else f"\n  or {drop_it}"
        raise SystemExit(render.refusal(
            step["id"], "not complete", escape=f"{how}{suffix}"))
    asm = runmod.load_assembly(st["assembly"])
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
        pr_url = _push_and_open_pr(wid, top, st["branch"], st.get("title", ""))
    terminal = next((s for s in st["steps"] if s.get("terminal")), None)
    fields = st["done"][terminal["id"]].get("fields", {}) if terminal else {}
    summary = _summary(st)
    decision = _last_decision(st, asm)
    journal.append(wid, "closed", fields=fields, summary=summary, decision=decision)
    if st.get("parent") and st.get("parent_step"):
        if journal.exists(st["parent"]):
            _fold_measures(st, st["parent"], st["parent_step"])
            journal.append(st["parent"], "return", step=st["parent_step"], child=wid,
                           row=st.get("row", ""), fields=fields, summary=summary,
                           decision=decision)
            _act_on_verdicts(st["parent"], st["parent_step"])
        else:
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
        (journal.location(wid) / "YIELD.md").write_text(yield_table + "\n")
        print(yield_table + "\n")
    print(f"closed {wid}\n")
    result = cmd_status([wid])
    if archiving:
        _sweep_to_archive(wid, top, dest, worktree)
        # A shell that was standing inside the worktree this just removed is
        # now stranded in a directory that no longer exists -- `os.chdir`
        # above only moves this process, the same asymmetry `cmd_open`'s own
        # "if this shell has not followed" already names for the open side.
        print(f"{pr_url}\narchived to {dest}\n  worktree removed: {worktree}\n"
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
        raise SystemExit(render.located(f"no run named {wid}\n  open runs: spine"))
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
