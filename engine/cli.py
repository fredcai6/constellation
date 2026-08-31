"""`spine` -- the seven verbs.

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
import tomllib

from engine import boards
from engine import checks as checkrun
from engine import forms
from engine import journal
from engine import render
from engine import run as runmod

USAGE = """spine <work-id>                     where you are
spine <work-id> submit              hand in the filled response form
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
spine <work-id> trace               this run and its children, as one timeline"""

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
        words = _prose_words(root / fields[f["id"]])
        if words:
            journal.append(wid, "measure", segment=step["segment"], step=step["id"],
                           field=f["id"], path=fields[f["id"]], words=words)

def _resolve_command(text, root=None):
    """`palette:test args` -> the host repo's test command plus args. A proof
    chaining several named jobs with `&&` (`palette:test && palette:lines`)
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


def _response_path(st, step):
    name = pathlib.Path(step["form"]).stem + ".toml"
    return journal.location(st["id"]) / name


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


def _dispatch_status(wid, st, asm, step, blocked):
    """A dispatch step renders a brief, not a form: the engine launches
    nothing, so making the one right invocation is the whole job. The brief
    is what a conductor copies into whatever harness it dispatches."""
    dispatched = runmod.load_assembly(step["dispatches"])
    tier = _tier(step, asm)
    child_id = step.get("child") or f"{wid}.{step['id']}"
    open_cmd = f"spine open {step['dispatches']} --parent {wid} --step {step['id']}"
    worktree, branch = _tree_info(wid, st)
    lines = render.preamble(st, blocked, runmod.position(st, asm))
    lines.append(render.imperative(render.DISPATCH))
    lines.append("")
    lines.append(render.brief(child_id, dispatched.get("conductor", ""), tier,
                              _runner(tier), open_cmd, _finishing(dispatched),
                              worktree, branch))
    lines.append("")
    lines.append(render.legal_moves(wid))
    return "\n".join(lines)


def _panel_status(wid, st, asm, step, blocked):
    """A panel step renders one brief per panelist -- copied, never
    composed -- with who has returned and who is still outstanding. A
    panelist's role is its own `worker`, not the give-a-verdict assembly's
    conductor: `_open_child` stamps that worker onto the dispatched child's
    step as its `filler`, so the panel entry is the source of truth, not
    just the brief that names it."""
    seg = next((s for s in asm["segment"] if s["id"] == step["segment"]), {})
    verdict_asm = runmod.load_assembly("give-a-verdict")
    returned = {r["child"].rsplit(".", 1)[-1] for r in st["returns"].get(step["id"], [])}
    worktree, branch = _tree_info(wid, st)
    lines = render.preamble(st, blocked, runmod.position(st, asm))
    lines.append(render.imperative(render.PANEL))
    lines.append("")
    for i, panelist in enumerate(step["panel"], start=1):
        tag = f"p{i}"
        tier = panelist.get("model") or seg.get("model", "")
        finishing = _finishing(verdict_asm, panelist.get("form", ""))
        outstanding = tag not in returned
        lines.append(f"  panelist {tag} ({'returned' if not outstanding else 'outstanding'})"
                     f" -- criteria: {panelist.get('criteria', '')}")
        if outstanding:
            child_id = f"{wid}.{step['id']}.{tag}"
            open_cmd = f"spine open give-a-verdict --parent {wid} --step {step['id']}.{tag}"
            lines.append(render.brief(child_id, panelist.get("worker", ""), tier,
                                      _runner(tier), open_cmd, finishing,
                                      worktree, branch))
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
#   work to redo, not work to wait for.
def _in_flight_status(wid, st, asm, entry, blocked):
    """What a run whose proof is still running says about itself."""
    running = checkrun.alive(entry.get("pid"))
    lines = render.preamble(st, blocked, runmod.position(st, asm))
    for c in entry.get("commands") or []:
        lines.append(f"  {c.get('field', 'check')}: {c.get('command', '')}")
    lines.append("")
    if running:
        lines.append(render.located(
            f"  proof in flight since {entry.get('at', '')} (pid {entry.get('pid')}), "
            f"budget {entry.get('budget')}s -- this step is not done and nothing "
            "was recorded for it. The engine journals the submit itself when the "
            f"proof passes, and refuses here when it fails.\n"
            f"  see where it landed: spine {wid}\n"
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
def _returned_verdict(st, asm):
    """The most recently returned panel's merged verdict, when its declared
    act is not `release`. Read from the last panel step that has a full
    house of returns, so a re-fired panel still waiting on its own critics
    reports the round that actually ruled, not silence."""
    for s in reversed(st["steps"]):
        rs = st["returns"].get(s["id"]) or []
        if s.get("panel") and rs and not runmod.panel_outstanding(st, s):
            verdict = runmod.merged_verdict(rs)
            _, spec = runmod.deciding_spec(asm, s)
            quiet = runmod.declared_does(spec, verdict) in (None, "release")
            return "" if quiet else verdict
    return ""


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
    board = _board_state(st["boards"].get(step["segment"]))
    prefill = {**(st.get("prefill") or {}), **(step.get("prefill") or {})}
    print(render.status(st, form, dest, prefill=prefill,
                        returns=returns, returns_from=step.get("child", ""),
                        verdict=_returned_verdict(st, asm),
                        blocked=runmod.blocks(st),
                        position=runmod.position(st, asm), board=board,
                        in_hand=forms.in_hand(dest) if dest.exists() else None,
                        triage_notes=[n for n in st["notes"] if n.get("kind_detail") == "triage"],
                        role=runmod.hat(asm, step, st), row_returns=st["row_returns"]))
    return 0


def cmd_submit(argv):
    wid = argv[0]
    st = runmod.state(wid)
    if st is None or not st["open"] or st["awaiting_close"]:
        raise SystemExit(render.located(
            f"{wid} has no current step"
            + (f" -- close it: spine {wid} close" if st and st["awaiting_close"] else "")))
    asm, step, form = _current_form(st)
    if runmod.panel_outstanding(st, step):  # checked before `dispatches`: see _current_form
        raise SystemExit(render.refusal(
            step["id"], "a panel step is not submitted -- the panelists' verdicts "
            "complete it", escape=f"who is outstanding: spine {wid}"))
    if runmod.paused(step):
        raise SystemExit(render.refusal(
            step["id"], "paused -- the ask it sent is standing at its parent, not here",
            escape=(f"see it: spine {st.get('parent')}" if st.get("parent")
                   else "no parent left to see it at -- see the blocked note above")))
    if step.get("dispatches"):
        raise SystemExit(render.refusal(
            step["id"], "a dispatch step is not submitted -- it completes when "
            "its child closes",
            escape=f"open its child: spine open {step['dispatches']} "
                   f"--parent {wid} --step {step['id']}"))
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

    if step.get("validates") == "board":
        board = st["boards"].get(step["segment"], "")
        problems = boards.validate(board) if board else []
        if problems:
            raise SystemExit(render.refusal(pathlib.Path(board).name,
                                            "\n  ".join(problems), escape=""))

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
    # called here as that guard and its answer thrown away; whichever process
    # completes the submit computes it again.
    _check_plan(asm, form, fields)
    _check_vocabulary(asm, step, form, fields)
    _check_artifact(wid, form, fields)
    _outcome(asm, step, fields, st)

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
    _measure_artifacts(wid, step, form, fields)

    # A transition marked `carries` folds its fields into the run's own
    # prefill, so everything dispatched afterwards gets them. Consolidate is
    # the case this exists for: a panelist's prefill is built from prior steps
    # in its own segment, so without this the run's understanding never crosses
    # a segment boundary and the coldest reader in the run -- the one the
    # understanding was written for -- is the only one who never sees it.
    if step.get("carries"):
        journal.append(wid, "prefill",
                       fields={**(st.get("prefill") or {}), **fields})
    _mint(wid, asm, step, form, fields)
    _mint_projected_gate(wid, asm, step, st)
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

    `(None, "")` where `step` is not that transition -- an impasse ruling's
    own `rework` carries the prefill that caused it and never spends the
    count, which is what makes the outlet a way out rather than a wall.

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
        return None, ""
    st = runmod.state(wid)
    findings = "\n\n".join(
        f"[{r['child'].rsplit('.', 1)[-1]}] {(r.get('fields') or {}).get('findings', '')}"
        for r in st["returns"].get(step["id"], []))
    called = _blocking_calls(fields)
    if called is not None:
        findings = called
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
#   unaffected. `up` needs neither: `release`, the field's own default, mints
#   nothing, and the run walks to its terminal step. Gate adjudication added two more the same
#   way: `remint` mints a fresh dispatch/adjudication pair from the plan
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
            _mint_segment_round(wid, asm, tseg["id"], prefill=fields)
        elif word == "transition":
            _mint_transition(wid, tseg)
        elif word == "rework":
            judged, outlet = _panel_judged_rework(wid, asm, tseg, step, fields)
            if outlet:
                journal.append(wid, "step", id=f"{tseg['id']}-a{secrets.token_hex(2)}",
                               segment=tseg["id"], form=outlet, filler="conductor",
                               prefill={**judged, "arrival": "rework-rounds"},
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
# Rejected: closing this run and returning through the ordinary `cmd_close`
#   path the way an advance does. That return only reaches the parent once
#   this run itself closes, and a run closed on `up` is a run gone quiet --
#   not one standing on a live ask the parent can see without opening it.
def _pause_gate(wid, tseg, reason, fields):
    """`up`'s own verb: an ask minted into the parent standing on the step
    that dispatched this run, reordered before the still-live pair so it is
    what the parent's own `state()` stands on next; a marker minted here, in
    the segment the parent's answer will resume."""
    st = runmod.state(wid)
    pwid, pstep_id = st.get("parent"), st.get("parent_step")
    if not pwid or not journal.exists(pwid):
        journal.append(wid, "note", id=f"n{secrets.token_hex(2)}", kind_detail="blocked",
                       about="", text="ruled up with no parent to ask -- nothing above this run")
        return
    pst = runmod.state(pwid)
    pstep = next((s for s in pst["steps"] if s["id"] == pstep_id), None)
    if pstep is None:
        journal.append(wid, "note", id=f"n{secrets.token_hex(2)}", kind_detail="blocked",
                       about="", text=f"parent {pwid} no longer holds {pstep_id} -- "
                                      "nothing to stand the ask on")
        return
    orders = st.get("prefill") or {}
    ask = {"gate": wid, "attempted": orders.get("scope") or orders.get("purpose", ""),
           "ask": reason}
    calls = fields.get("calls")
    if isinstance(calls, list) and calls:
        ask["findings"] = "\n\n".join(
            f"[{r.get('call', '')}] {r.get('finding', '')}"
            for r in calls if isinstance(r, dict))
    elif fields.get("why"):
        ask["findings"] = fields["why"]
    ask_id = f"{pstep['segment']}-a{secrets.token_hex(2)}"
    journal.append(pwid, "step", id=ask_id, segment=pstep["segment"],
                   form="skills/gate-conductor/forms/ASK.toml", filler="conductor",
                   prefill=ask, resumes=wid, anchor=False, terminal=False,
                   validates="", source="mint")
    journal.append(pwid, "amend", action="reorder", segment=pstep["segment"], step=ask_id,
                   before=pstep_id, reason=reason, anchor=False)
    marker_id = f"{tseg['id']}-a{secrets.token_hex(2)}"
    journal.append(wid, "step", id=marker_id, segment=tseg["id"], paused=tseg["id"],
                   filler="conductor", anchor=False, terminal=False, validates="",
                   source="mint")


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
        _mint_segment_round(wid, asm, plan["id"])


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
_GATE_FIELDS = ("purpose", "scope", "proof", "budget", "model", "direction")


def _mint_projected_gate(wid, asm, step, st):
    """A transition step whose own segment declares `projects` mints one
    gate into the segment `projects` names, on submit -- built from this
    segment's own most recent interior return, never from anything typed on
    the transition's own form. A no-op off that step, or where the segment
    it names is not one this assembly's own `_mint_gates` can reach."""
    seg = next((s for s in asm["segment"] if s["id"] == step.get("segment")), {})
    t = seg.get("transition", {})
    if step.get("form") != t.get("form") or not t.get("projects"):
        return
    target = next((s for s in asm["segment"] if s.get("dispatches") == t["projects"]), None)
    prior = [s for s in st["steps"] if s["segment"] == step["segment"] and s["id"] != step["id"]]
    if not target or not prior:
        return
    source = st["done"].get(prior[-1]["id"], {}).get("fields", {})
    gate = {k: source[k] for k in _GATE_FIELDS if k in source}
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
    casm = runmod.load_assembly(cst["assembly"])
    journal.append(child, "amend", action="close", segment=marker["segment"],
                   step=marker["id"], reason="resumed by the parent's answer",
                   anchor=marker.get("anchor", False))
    _mint_segment_round(child, casm, tseg_id, prefill=fields)


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
def _mint_segment_round(wid, asm, seg_id, prefill=None, form=""):
    """Mint one fresh round of a segment: its step-form (or the form the
    caller names -- a revise passes the segment's rework form) as a fresh
    interior step, plus its transition's panel -- both read from the
    assembly, never copied from whatever minted last. The shared move a
    revise and a replan both need: the segment reopened for another pass,
    carrying the same challenge that judges it.

    Two independent random tags, not one shared: a transition's id defaults
    to its segment's id (run-an-issue's "plan" names both), and
    `f"{seg_id}-a{tag}"` would then equal `f"{step_id}-a{tag}"` for the same
    tag -- one mint silently overwriting the other in the journal.
    """
    seg = next(s for s in asm["segment"] if s["id"] == seg_id)
    t = seg.get("transition", {})
    step = {"id": f"{seg_id}-a{secrets.token_hex(2)}", "segment": seg_id,
            "filler": seg.get("worker", "conductor"), "prefill": prefill or {},
            "anchor": False, "terminal": False, "validates": "", "source": "mint"}
    # `form` is set either way -- a replan's dispatch carries its own
    # step-form even though that names the child assembly's own default and
    # so overrides nothing. `rework_rounds` (run.py) reads this field on
    # every mint regardless of `dispatches`, and a step that omitted it
    # whenever the value was the non-override default silently broke the
    # replan-resets-the-count case the moment a replan started dispatching.
    step["form"] = form or seg["step-form"]
    if seg.get("dispatches"):
        step["dispatches"] = seg["dispatches"]
    journal.append(wid, "step", **step)
    # The segment's transition, re-minted for the fresh round: its panel where
    # it declares one, its form where it declares one, both where it is a
    # two-voices step. run-a-gate's `work` transition is the first to declare
    # a form and no panel -- `select` chooses the next round's readers rather
    # than carrying the last round's forward -- so neither key is assumed.
    fresh = {"id": f"{seg_id}-a{secrets.token_hex(2)}", "segment": seg_id,
             "anchor": False, "terminal": False, "source": "panel"}
    if t.get("panel"):
        fresh["panel"] = t["panel"]
    if t.get("form"):
        fresh["form"] = t["form"]  # the two-voices shape survives a fresh round
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
    is what releases it -- run-a-gate's review declares both of its verdicts
    that way, so its rounds are always disposed of by a conductor. A verb
    that acts -- `rework`, which run-an-issue's consolidate and
    plan-to-execute still declare for `revise` -- is `_perform`'s from here,
    findings and the segment's own three-round outlet included, since a
    conductor form deciding the same rework reaches that verb by the
    ordinary submit and owes the round exactly the same two things."""
    pst = runmod.state(pwid)
    step = next((s for s in pst["steps"] if s["id"] == step_id), None)
    if not step or not step.get("panel") or runmod.panel_outstanding(pst, step):
        return
    returns = pst["returns"][step_id]
    verdict = runmod.merged_verdict(returns)
    asm = runmod.load_assembly(pst["assembly"])
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
    verdict = ""
    for s in st["steps"]:
        if s.get("panel"):
            rs = st["returns"].get(s["id"]) or []
            if rs:
                verdict = runmod.merged_verdict(rs)
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
        # The way past a pending step depends on what kind it is: a step whose
        # panel is still outstanding has no form to fill yet -- true whether
        # or not it has one at all -- a dispatch step has no form either, and
        # offering the wrong escape is worse than offering none.
        if runmod.panel_outstanding(st, step):
            how = f"its panelists complete it: spine {wid}"
        elif runmod.paused(step):
            how = (f"its ask is standing at its parent, not here: spine {st.get('parent')}"
                  if st.get("parent") else
                  "its ask has no parent left to stand on -- see the blocked note above")
        elif step.get("dispatches"):
            how = f"open its child: spine open {step['dispatches']} --parent {wid} " \
                  f"--step {step['id']}"
        else:
            how = f"fill its form and submit it: spine {wid} submit"
        raise SystemExit(render.refusal(
            step["id"], "not complete",
            escape=f"{how}\n  or drop it: spine {wid} amend close {step['id']} --reason ..."))
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
             "amend": cmd_amend, "close": cmd_close, "trace": cmd_trace}
    if verb not in verbs:
        # `spine <id> sumbit` used to render the room and exit 0: only the exact
        # word is acted on, so a near-miss must not look like a hit.
        raise SystemExit(f"no verb {verb!r} -- one of: {', '.join(verbs)}\n\n{USAGE}")
    return verbs[verb]([argv[0]] + argv[2:])


if __name__ == "__main__":
    sys.exit(main() or 0)
