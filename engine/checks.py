"""A step's proof: run it, and hand the caller back before the harness cuts.

Two numbers bound one check, and they answer different questions.

**The handback** is how long `submit` holds its caller. A dispatched agent's
harness moves any foreground command still running at about 120 seconds into
the background, the agent's turn ends there, and nothing wakes it -- measured
on a real `run-a-gate` whose proof slept 150 seconds (#72). The proof itself
survived and completed; the caller was taken away from it. So the engine
returns control first, with a room the agent can act on. The number is the
engine's own: what a harness does to a foreground command is not something a
gate spec knows or should declare.

**The proof budget** is how long the proof may run before it is broken rather
than merely slow. That is what `CHECK_TIMEOUT = 600` was, and 600 is still the
default -- but a gate spec now declares its own with a `budget` key, because
one constant for every check in the system is #36, and inventing the handback
as a second hardcoded constant beside it would have been the same defect
twice.

The proof always runs in a detached process of its own, and that process is
the only writer of the outcome: the `submit` entry on exit 0, a `check` entry
on anything else. One writer is why no interleaving journals a submit twice,
and why a failing proof still records no submit -- the caller never holds the
result, so it can never write one. What the caller writes when it leaves is a
`check-started` entry, which the fold reads as a step still open with its
proof in flight.
"""

import json
import os
import pathlib
import shutil
import subprocess
import sys

from engine import journal
from engine import render

HANDBACK = 90  # seconds `submit` holds its caller -- see the module docstring
BUDGET = 600   # seconds a proof may run before it is broken, absent a declared one

# [wait-bound]
# Rationale: `wait` blocks in the same caller turn `HANDBACK` is about --
#   a harness that moves a foreground command to the background at ~120s
#   never wakes the agent to read what it prints, so the default bound
#   stays at or under `HANDBACK` itself rather than inventing a second
#   number that could run the caller past that cutoff. `--for <seconds>`
#   overrides it per call for whoever chooses to hold longer anyway.
WAIT_BOUND = 90  # seconds `wait` blocks by default before it renders anyway
WAIT_POLL = 1    # seconds between `wait`'s own re-folds of the journal

# [drive-bound]
# Rationale: `drive` is not held in the same caller turn `HANDBACK` bounds --
#   its own scenario is a principal at a terminal who opens a run, works the
#   understand board, submits consolidate, types `drive`, and comes back
#   later, not a dispatched conductor mid-turn a harness could strand past
#   `HANDBACK`. So its default is sized for that wait, not for the harness:
#   distinctly longer than `WAIT_BOUND` rather than capped at or under it.
#   `--for <seconds>` overrides it per call, the same as `WAIT_BOUND`.
DRIVE_BOUND = 3600  # seconds `drive` blocks by default before it renders anyway

# [max-starts]
# Rationale: a child that keeps dying without returning must not be
#   restarted forever -- `MAX_STARTS` is the total count of
#   `dispatch-started` records a single child may ever accumulate (first
#   start plus restarts), named here rather than left a bare literal at
#   `_startable`'s or `_dispatch_child`'s own call sites, the same rule
#   `WAIT_BOUND` and `WAIT_POLL` already follow. Set to 3: this
#   specification's own recommendation ("two restarts, three starts
#   total") taken as written.
MAX_STARTS = 3   # total dispatch-started records a child may ever accumulate

# [form-filler-max-starts]
# Rationale: a form-filler process is not a dispatched child -- it fills the
#   same run's own response form rather than running a whole other assembly
#   -- so its own restart accounting is kept apart from `MAX_STARTS` even
#   though the two are read the identical way (a per-key total of
#   `*-started` records). A single shared constant would tie the two caps
#   together for no reason: raising one to fit a slow dispatched child would
#   silently also raise how long a stuck form filler is retried, and the
#   reverse. Set to 3, `MAX_STARTS`'s own value taken as written for the
#   same "two restarts, three starts total" reading -- there is no second
#   recommendation for this shape, and no reason yet to diverge from the
#   first.
FORM_FILLER_MAX_STARTS = 3   # total form-filler-started records a step may ever accumulate

_ROOT = pathlib.Path(__file__).resolve().parent.parent


def budget_for(orders):
    """Seconds this step's proof may run: the gate spec's own `budget` where
    it declares one, else the default.

    A value that is not whole seconds refuses rather than falling back. A
    spec that meant fifteen minutes and typed `15m` has declared something,
    and silently running it under the default is how a declaration becomes
    decoration."""
    raw = orders.get("budget", "")
    if raw in ("", None):
        return BUDGET
    try:
        seconds = int(str(raw).strip())
    except ValueError:
        seconds = 0
    if seconds <= 0:
        raise SystemExit(render.refusal(
            "budget", f"{str(raw).strip()!r} is not a number of seconds",
            escape=f'declare whole seconds on the gate spec -- budget = "{BUDGET}"'))
    return seconds


def _paths(wid, step_id):
    """Where one step's check keeps its working files, in the run's own work
    location: the payload the detached runner reads, the result it leaves for
    the caller, and the log its own stdout and stderr go to. Never inherited
    from the caller -- a detached process writing into the agent's terminal
    is output arriving after the turn that could have read it."""
    loc = journal.location(wid)
    return (loc / f"check.{step_id}.json", loc / f"check.{step_id}.result.json",
            loc / f"check.{step_id}.log")


def in_flight_log(wid, step_id):
    return str(_paths(wid, step_id)[2])


# [one-writer]
# Rationale: the guarantee this whole file is arranged around is that a
#   failing proof records no submit. The runner is the only process that ever
#   holds an exit status, and it journals the submit only on exit 0 -- so the
#   guarantee is not enforced by a check anywhere, it is the shape of the
#   code. The caller cannot write a submit it has no result for.
# Rejected: running the proof in the foreground and detaching it at the
#   handback. Then two processes can hold the same result -- the runner
#   finishing in the instant the caller gives up on it -- and deciding which
#   of them journals needs an atomic claim between them. One writer needs no
#   claim.
def hand_in(wid, step, fields, commands, check_root, budget):
    """Run this step's checks in a process of its own, and wait no longer than
    the handback for them.

    Returns `"done"` when every check passed and the runner completed the
    submit, or `"in-flight"` when the handback expired first and the caller
    has been given back its turn. Refuses -- in the same words the foreground
    check always used -- when a check fails, and in new words when one outruns
    its budget.

    The effective wait is the smaller of the handback and the budget without
    computing one: a runner that outruns the budget kills the check and exits
    at that point itself, so a budget under the handback returns here on its
    own rather than being timed out from outside.
    """
    payload, result, log = _paths(wid, step["id"])
    payload.parent.mkdir(parents=True, exist_ok=True)
    result.unlink(missing_ok=True)
    # Absolute, both in the payload and in the record: the runner is a
    # different process and the entry is read by a person later, and neither
    # is standing in the directory these were relative to.
    where = str(pathlib.Path(check_root).resolve())
    payload.write_text(json.dumps({
        "wid": wid, "step": step["id"], "fields": fields, "commands": commands,
        "cwd": where, "budget": budget, "result": str(result.resolve())}),
        encoding="utf-8")
    proc = _spawn([sys.executable, "-m", "engine.checks", str(payload)], log)
    try:
        code = proc.wait(timeout=HANDBACK)
    except subprocess.TimeoutExpired:
        code = proc.poll()  # it may have landed in the instant we gave up
    if code is None:
        journal.append(wid, "check-started", step=step["id"], pid=proc.pid,
                       cwd=where, budget=budget, log=str(log.resolve()),
                       commands=[{"field": fid, "command": cmd}
                                 for fid, cmd in commands])
        return "in-flight"
    if code == 0:
        return "done"
    raise SystemExit(_said(result, wid, step["id"]))


# [trial-detached]
# Rationale: #163's own defect -- a fast suite this repository's own
#   `[commands]` palette declares takes 168s, `HANDBACK` is 90, and
#   `_trial_proofs` (engine/cli.py) used to run each `proof` field
#   synchronously with the command itself killed at
#   `min(budget, HANDBACK)`, so every correctly written proof that took
#   longer than the handback read as a fourth, useless reading: "no result
#   after 90s", the real exit status lost with the process that held it.
#   `hand_in`'s own shape already separates the two numbers correctly --
#   the handback bounds the caller's wait, never the check's own run -- so
#   the trial is spawned exactly the way `hand_in` spawns a gate's own
#   checks, through this near-identical twin, and the one place this
#   diverges from `hand_in` is on purpose: `[trial-proofs]`'s whole point is
#   that nothing here is ever refused, so this never raises. A proof that
#   lands within the handback journals its own reading before this
#   returns, exactly as `_trial_main` always has; one that does not leaves
#   `check-started` for the route form to find later, the same record
#   `hand_in` already leaves for a gate's own overrun, marked `trial=True`
#   so the fold (`engine/run.py`) can tell the two apart -- a plan step's
#   own submit does not wait on this the way a gate's submit waits on
#   `hand_in`'s, so the two cannot share one bookkeeping key.
def hand_in_trial(wid, step_id, commands, cwd, budget, changed=None):
    """Spawn every resolved `proof`-kind field this submit carries as one
    detached trial, and wait no longer than the handback for it to land.
    `commands` is `[(field_id, resolved_command), ...]`, already resolved by
    the caller -- a string that never became a command is the caller's own
    to journal, synchronously, since there is no process worth spawning for
    it.

    Returns `"done"` once every command in `commands` has run and journaled
    its own `check` entry -- the caller re-reads the journal for them,
    exactly as it would any other journaled fact -- or `"in-flight"` when
    the handback expired first, `check-started` already left behind for
    whoever reads this run next."""
    payload, _result, log = _paths(wid, step_id)
    payload.parent.mkdir(parents=True, exist_ok=True)
    where = str(pathlib.Path(cwd).resolve())
    payload.write_text(json.dumps({
        "wid": wid, "step": step_id, "commands": commands, "cwd": where,
        "budget": budget, "trial": True, "changed": changed}), encoding="utf-8")
    proc = _spawn([sys.executable, "-m", "engine.checks", str(payload)], log)
    try:
        code = proc.wait(timeout=HANDBACK)
    except subprocess.TimeoutExpired:
        code = proc.poll()  # it may have landed in the instant we gave up
    if code is None:
        journal.append(wid, "check-started", step=step_id, pid=proc.pid,
                       cwd=where, budget=budget, log=str(log.resolve()),
                       trial=True,
                       commands=[{"field": fid, "command": cmd}
                                 for fid, cmd in commands])
        return "in-flight"
    return "done"


def _spawn(argv, log, cwd=None, *, bind=None):
    """The detached runner, generalized to any argv: `Popen` it with output
    captured to `log` and nothing read from the caller's own stdin.
    `start_new_session` puts it in a session of its own, so a harness that
    kills the caller's whole process group does not take the child with it
    -- insurance rather than the mechanism, since a plain child already
    outlived a dispatched agent's turn when this was measured.

    Shared by `hand_in`'s own proof runner (`cwd=None`, inheriting the
    caller's) and `spawn_dispatch`'s child launch (`cwd=` the child's own
    tree) -- one `Popen` call carrying commitments 6, 17 and 18 for both,
    rather than a second copy of the same five keyword arguments.

    `PYTHONPATH` carries this tree's root rather than a rewritten path:
    install is a copy, so a module run this way is found the same way in
    the repo and in an installed copy. Harmless, not just convenient, for an
    argv that names no Python module at all -- an extra `PYTHONPATH` entry
    a non-Python harness never looks at costs it nothing.

    `bind`, when given, is the id of the child this argv itself runs as --
    stamped into `CONSTELLATION_BOUND` so that child's own work-id
    resolution (`engine/journal.py`'s `_in_scope`) reaches only itself and
    whatever it dispatches beneath itself. Omitted (`None`), the spawned
    process inherits whatever `CONSTELLATION_BOUND` this caller already
    carries, unchanged -- a form filler and a proof runner are not a
    distinct child with a subtree of its own, so neither passes `bind`."""
    env = {**os.environ,
           "PYTHONPATH": os.pathsep.join(
               p for p in (str(_ROOT), os.environ.get("PYTHONPATH", "")) if p),
           "CONSTELLATION_SESSION": os.environ.get(
               "CONSTELLATION_SESSION", str(os.getpid()))}
    if bind is not None:
        env["CONSTELLATION_BOUND"] = bind
    with open(log, "a", encoding="utf-8") as out:
        return subprocess.Popen(
            argv, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
            start_new_session=True, env=env, cwd=cwd)


# [dispatch-failure]
# Rationale: `o-absent-dispatch-raises` collapses what used to be two axes --
#   a genuinely absent `dispatch` key read as nothing to spawn and no
#   failure, every other case a reported, distinguishable failure -- into
#   one: every way a start can fail to produce a running, journaled process
#   raises this, absence included. `.reason` is one of the module-level
#   DISPATCH_* constants (not free text) so the four failure inputs stay
#   distinguishable from each other -- a caller branches on `exc.reason`,
#   never on `str(exc)`.
# Rejected: keeping the absent case a silent `None`, with only the other
#   three raising. That is the two-state rendering `o-single-dispatch-room`
#   deletes elsewhere in this same run -- a caller that catches
#   `DispatchFailure` already handles "no journal entry, reason logged" for
#   three of the four causes, so leaving the fourth a different shape is one
#   more place the old contract survives after the room it justified is
#   gone.
class DispatchFailure(Exception):
    """A `spawn_dispatch` attempt that produced no journal entry. `.reason`
    names which of the four failure inputs this was; `.detail` is the free
    text a person reads in a refusal or a log."""
    def __init__(self, reason, detail):
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


DISPATCH_ABSENT = "dispatch-absent"              # no `dispatch` key configured at all
DISPATCH_MALFORMED = "dispatch-malformed"       # entry present but not a list
DISPATCH_UNFILLED = "dispatch-unfilled"         # a recognized placeholder given no value
DISPATCH_SPAWN_FAILED = "dispatch-spawn-failed"  # Popen itself could not start the process

_DISPATCH_TOKENS = {"{brief}": "brief", "{runner}": "runner", "{tree}": "tree"}


# [spawn-dispatch]
# Rationale: `{brief}`/`{runner}`/`{tree}` are matched by exact whole-word
#   equality, never a substring or a general `{...}` parse -- a word that
#   merely contains braces (a real args element that happens to have some
#   other `{token}` in it) is data, not a placeholder, and commitment 2 asks
#   for whole-word substitution only. Checking the three names directly,
#   rather than stripping braces and looking the stripped name up in a set,
#   means an unrecognized brace-token (`{host}`, say) simply falls through
#   to "left untouched" with no special-casing -- it was never one of the
#   three names to begin with.
# Rejected: treating a missing `tree` (the one placeholder the docstring
#   calls optional -- "where present") differently from a missing `brief`
#   or `runner`. The purpose text describes all three the same way
#   ("a placeholder the caller supplied no value for"), and a caller that
#   forgets to pass a tree when the configured entry asks for one is the
#   same misconfiguration as forgetting a brief -- both are DISPATCH_UNFILLED,
#   not a fourth category.
def spawn_dispatch(commands, brief, runner, tree, wid, child_id, log):
    """Spawn one dispatched child's process from a `[commands]`-shaped
    mapping's `dispatch` entry, substituting `{brief}`, `{runner}` and
    `{tree}` into it as whole argv words, and journal the spawn keyed by
    `child_id` (commitment 9) -- never by `wid`'s current step, which a
    panel step shares across several children.

    Returns the journal entry `journal.append` wrote (identity, pid, start
    time) once the process is actually running.

    Raises `DispatchFailure` for every way this can fail to produce a
    running, journaled process: `commands` carries no `dispatch` key at all
    (a repository that has not configured one), the entry is present but
    not a list (today's single-string `[commands]` shape used verbatim
    would land here), a placeholder in it names one of
    `{brief}`/`{runner}`/`{tree}` but the caller passed `None` for that
    value, or the process itself fails to start (a nonexistent executable,
    most commonly). No journal entry is written in any of these cases --
    the append happens only after `_spawn` hands back a live `Popen`, so
    there is no window in which a partial entry could land.

    `tree` also becomes the spawned process's own working directory
    (commitment 7) regardless of whether the entry's text uses `{tree}` at
    all; `log` is where its stdout and stderr are captured, opened in
    append mode exactly like a check's own log."""
    if "dispatch" not in commands:
        raise DispatchFailure(DISPATCH_ABSENT, "no dispatch entry configured")
    entry = commands["dispatch"]
    if not isinstance(entry, list):
        raise DispatchFailure(
            DISPATCH_MALFORMED,
            f"the dispatch entry must be a list of words, not {type(entry).__name__} "
            f"-- {entry!r}")
    values = {"brief": brief, "runner": runner, "tree": tree}
    argv = []
    for word in entry:
        name = _DISPATCH_TOKENS.get(word)
        if name is None:
            argv.append(word)
            continue
        value = values.get(name)
        if value is None:
            raise DispatchFailure(
                DISPATCH_UNFILLED, f"{word} has no value supplied for this child")
        argv.append(str(value))
    try:
        proc = _spawn(argv, log, cwd=tree, bind=child_id)
    except OSError as e:
        raise DispatchFailure(DISPATCH_SPAWN_FAILED, str(e)) from e
    return journal.append(wid, "dispatch-started", child=child_id, pid=proc.pid,
                           tree=tree, log=str(pathlib.Path(log).resolve()))


# [dispatch-launch]
# Rationale: a form-filler process is started through the identical
#   `[commands] dispatch` entry a dispatched child already runs through --
#   same three placeholders, same malformed/unfilled/launch-failed ways to
#   fail -- so the substitution loop and the `Popen` call are lifted out
#   here rather than typed a second time inside `spawn_form_filler`. This
#   gate's own scope leaves `spawn_dispatch` itself untouched (its own copy
#   of this same logic is not rewired to call this function), so the two do
#   not literally share a call site today -- but they share this function's
#   text, which is the one thing that matters for the rule not to drift:
#   a future change to the substitution rule (a fourth placeholder, a
#   different failure mode) has exactly one place to land for a form
#   filler's own launch, not a second, hand-copied loop that could fall out
#   of step with `spawn_dispatch`'s.
# Rejected: rewriting `spawn_dispatch` to call this helper too. The gate
#   spec that asked for this function is explicit that `spawn_dispatch`
#   itself, and every one of its existing callers, is untouched this round.
def _dispatch_launch(commands, brief, runner, tree, log):
    """Substitute `{brief}`/`{runner}`/`{tree}` into the configured
    `dispatch` entry and launch it, returning the live `Popen`. Raises
    `DispatchFailure` for every way this can fail: no `dispatch` key
    configured at all, a malformed entry, an unfilled placeholder, or the
    process itself failing to start -- identical to `spawn_dispatch`'s own
    four failure modes, because this is the same substitution rule applied
    to a different journal record."""
    if "dispatch" not in commands:
        raise DispatchFailure(DISPATCH_ABSENT, "no dispatch entry configured")
    entry = commands["dispatch"]
    if not isinstance(entry, list):
        raise DispatchFailure(
            DISPATCH_MALFORMED,
            f"the dispatch entry must be a list of words, not {type(entry).__name__} "
            f"-- {entry!r}")
    values = {"brief": brief, "runner": runner, "tree": tree}
    argv = []
    for word in entry:
        name = _DISPATCH_TOKENS.get(word)
        if name is None:
            argv.append(word)
            continue
        value = values.get(name)
        if value is None:
            raise DispatchFailure(
                DISPATCH_UNFILLED, f"{word} has no value supplied for this child")
        argv.append(str(value))
    try:
        return _spawn(argv, log, cwd=tree)
    except OSError as e:
        raise DispatchFailure(DISPATCH_SPAWN_FAILED, str(e)) from e


# [spawn-form-filler]
# Rationale: keyed by `step`, never `child` -- a form-step filler is not a
#   child run, it is a process reading and writing this same run's own
#   response form, and `_form_filler_records`/`_form_filler_start_counts`
#   (`engine/cli.py`) already read `form-filler-started` on that assumption.
#   `tree` is not stored on the record the way `dispatch-started` stores it:
#   a filler never inherits a different tree than the run it is filling out
#   already carries (`_tree_info` gives the caller that, the same as it
#   does for every other spawn), so there is no second tree fact worth
#   journaling here.
def spawn_form_filler(commands, brief, runner, tree, wid, step_id, log):
    """Spawn one form-step filler process, through the same `[commands]`
    `dispatch` entry a dispatched child runs through, and journal the spawn
    keyed by `step_id` (`form-filler-started`, fields `step`/`pid`/`log`) --
    never `dispatch-started`, and never keyed by a child id, since this
    process fills no assembly of its own.

    Returns the journal entry a successful attempt wrote. Raises
    `DispatchFailure` for every way the attempt can fail, identical to
    `spawn_dispatch`'s own four failure modes -- no journal entry is
    written on that path either."""
    proc = _dispatch_launch(commands, brief, runner, tree, log)
    return journal.append(wid, "form-filler-started", step=step_id, pid=proc.pid,
                           log=str(pathlib.Path(log).resolve()))


def _said(result, wid, step_id):
    """What the runner left for the caller to say. A missing file means the
    runner died before it could refuse in its own words, which is still a
    refusal -- naming the log is what makes it actionable."""
    try:
        return json.loads(pathlib.Path(result).read_text(encoding="utf-8"))["refusal"]
    except (OSError, ValueError, KeyError):
        return render.refusal(
            "check", "the process running this step's check died without a result",
            escape=f"what it printed: {in_flight_log(wid, step_id)}")


def alive(pid):
    """Is the process that was running this check still there? A pid the
    caller may not signal is someone else's and is alive; anything this
    cannot answer reads as alive, because reporting a running proof as an
    orphan is the worse of the two mistakes. A zombie is an answerable case
    and answers "exited"."""
    pid = int(pid)
    # A child that exited but was never waited on is a zombie: `os.kill(pid, 0)`
    # still succeeds on it, which read a finished harness as `working` and made
    # a spawn test's answer depend on whether unrelated code had reaped it
    # first (#101). Reap it if it is ours, then read its state where /proc
    # says it; the state letter follows the parenthesised command name, whose
    # own parentheses are why the last `)` is the anchor.
    try:
        os.waitpid(pid, os.WNOHANG)
    except ChildProcessError:
        pass
    try:
        stat = open(f"/proc/{pid}/stat", encoding="utf-8").read()
        if stat[stat.rfind(")") + 2] in ("Z", "X"):
            return False
    except (OSError, ValueError, IndexError):
        pass
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except (OSError, ValueError, TypeError):
        return True
    return True


# -- the detached runner ------------------------------------------------------


# [trial-at-the-cut]
# Rationale: #122 -- a plan's `proof` was read by three critics and run by
#   nobody, so a prose proof failed only after the gate had built its whole
#   diff, where no verb could repair it. Running it once where it is
#   written, against the tree as it stands, is the one place that reading
#   costs a line. This is a report, never a refusal (`_trial_proofs`,
#   engine/cli.py journals whatever comes back), so it never stops at the
#   first failure the way `main`'s own gate-check loop does below -- every
#   `proof` field this submit carries gets its own run and its own `check`
#   entry, whatever the ones before it did.
# Rationale: #163 -- this used to run in the caller's own foreground,
#   bounded by the smaller of the gate's own `budget` and the handback, so a
#   proof that was right but slow (this repository's own fast suite, 168s
#   against a 90s handback) was killed before it could answer and read as a
#   fourth, useless reading: "no result after 90s". Now it is `hand_in_trial`
#   that bounds the *caller's wait* at the handback; this function is what
#   the detached process spawned for that trial runs, and it is bounded only
#   by `budget` itself -- the planner's own declaration of how long the
#   proof may run when it is right. A command that genuinely outruns
#   `budget` still reads as exit `-1`, `main`'s own shape for an overrun --
#   that reading is real and stays; only the handback's incidental cutoff is
#   gone.
def _trial_main(payload):
    """Run every proof this trial carries, in field order, journaling each as
    a `check` entry exactly as `_trial_proofs` (engine/cli.py) always has --
    and refusing nothing, whatever any of them does. Reused for both trial
    shapes `hand_in_trial` can produce: one whose whole batch lands inside
    the handback, and one that outruns it and keeps running here, detached,
    after the caller has already been handed back."""
    wid, step_id, budget = payload["wid"], payload["step"], payload["budget"]
    changed = payload.get("changed")
    for fid, cmd in payload["commands"]:
        code, output = _run(cmd, payload["cwd"], budget)
        _attempt(fid, cmd, code, output)
        if code is None:
            journal.append(wid, "check", step=step_id, field=fid, command=cmd,
                           exit=-1, output=f"no result after {budget}s", trial=True,
                           changed=changed)
        else:
            journal.append(wid, "check", step=step_id, field=fid, command=cmd,
                           exit=code, output=output, trial=True, changed=changed)
    return 0


# [timeout-streams-are-bytes]
# Rationale: `text=True` decodes what `subprocess.run` returns, never what
#   `TimeoutExpired` carries. CPython fills the exception from the pipes at
#   kill time, ahead of the text wrapper's own decode, so a proof that printed
#   anything before it was killed hands back `bytes` here while a silent one
#   hands back `None`. Concatenating `bytes` against a `str` raised out of the
#   handler, so the one path that exists to report an overrun reported nothing
#   at all -- and the overrun test never saw it because `sleep 20` prints
#   nothing, and empty `bytes` are falsy.
# Rejected: `str(e.stdout)` -- it renders the repr, `b'...'`, into the tail a
#   person reads.
def _as_text(stream):
    """One of `TimeoutExpired`'s streams as text: `bytes` decoded the way the
    run itself would have decoded them, and a stream that is not there as
    nothing."""
    if isinstance(stream, bytes):
        return stream.decode("utf-8", errors="replace")
    return stream or ""


# [proofs-run-in-bash]
# Rationale: #191 -- a proof is written and verified in bash, the shell every
#   agent's tool runs, and `shell=True` alone runs it in `/bin/sh`, which is
#   dash on Debian and Ubuntu. tennis_elo issue126's gate proof used `<(...)`:
#   it passed by hand and exited 2 on every submit, and a minted proof cannot
#   be edited. Running it in the shell it was written in makes that
#   difference impossible instead of reporting it.
# Rejected: POSIX-only proofs checked at the cut -- a rule every author has
#   to remember, enforced by a refusal, for a shell nobody writes in.
_SHELL = shutil.which("bash")


def _run(cmd, cwd, budget):
    """(exit, output) for one check; exit `None` when it outran the budget."""
    try:
        r = subprocess.run(cmd, shell=True, executable=_SHELL,
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           timeout=budget, cwd=cwd)
    except subprocess.TimeoutExpired as e:
        # What it printed before it was killed is the only account of a proof
        # that outran its budget, and `run` hands it back on the exception.
        return None, (_as_text(e.stdout) + _as_text(e.stderr))[-4000:]
    return r.returncode, (r.stdout + r.stderr)[-4000:]


def _failed(wid, step_id, fid, cmd, code):
    """The words a failing check has always refused in: a check is the
    engine's to run, so a failure is not the agent's answer to correct."""
    return render.located(
        f"{fid}: `{cmd}` exited {code}\n"
        f"  a check is run by the engine, not filled in -- make it pass,\n"
        f"  or drop this step: spine {wid} amend close {step_id} --reason ...")


# [budget-refusal-names-both]
# Rationale: #36 -- "fix the command, or drop this step" offers two escapes
#   that are both wrong for a check that is slow because it is correct, and
#   the timeout is exactly the case where the command may need nothing done
#   to it. The refusal has to separate "this command is wrong" from "this
#   command needs longer" and name the declaration that buys the time, or the
#   only readings left are the two that damage a correct proof.
def _overran(wid, step_id, fid, cmd, budget):
    return render.refusal(
        fid, f"`{cmd}` did not finish in {budget}s, its whole budget -- so "
             "either the command is wrong, or it is right and needs longer",
        escape=(f'needs longer: declare it on the gate spec -- budget = "{budget * 2}"\n'
                f"  wrong: fix the command, or drop this step: "
                f"spine {wid} amend close {step_id} --reason ..."))


# [proof-output-reaches-the-log]
# Rationale: #117 -- a failing proof left 232 bytes behind, all of them the
#   refusal, and which check failed was unrecoverable. On a failing exit the
#   output was never lost -- `_run` captures it and `main` journals it -- so
#   what was missing is the output at the path the in-flight room actually
#   names, which is the only place a reader is told to look. A proof killed at
#   its budget did lose it outright, and `_run` now takes it off the timeout
#   too. Every attempt writes its own header here,
#   whatever the exit, because the log is opened for append (`_spawn`) and a
#   passing attempt after a failing one otherwise reads as the failure still
#   standing -- the second half of #117, where the log contradicts the
#   journal.
# Rejected: truncating the log at the start of each attempt. `_spawn` is
#   shared with the dispatched-child path, where the accumulated log is the
#   record, so the fix has to make attempts distinguishable rather than make
#   the earlier one disappear.
def _attempt(fid, cmd, code, output):
    """Print one attempt into the log: what ran, how it ended, and what it
    printed. `code` is `None` for a proof that outran its budget."""
    ended = "no result" if code is None else f"exited {code}"
    print(f"--- {journal.stamp()} {fid}: `{cmd}` {ended} ---", flush=True)
    print(output if output else "(it printed nothing)", flush=True)


def _refuse(payload, text):
    """Leave the refusal where the caller reads it, and print it into the log
    so a check that was already handed back still says why it failed
    somewhere a person can find it."""
    pathlib.Path(payload["result"]).write_text(
        json.dumps({"refusal": text}), encoding="utf-8")
    print(text, flush=True)
    return 1


def main(argv):
    """Run one step's checks and write the outcome. Never called by a person:
    `hand_in` (a gate's own checks) or `hand_in_trial` (a plan's `proof`
    fields, `[trial-detached]`) spawns this, and it is the only process that
    ever holds a check's exit status. A payload marked `trial` is
    `_trial_main`'s alone -- it refuses nothing and completes no submit,
    the opposite contract from the gate-check loop below."""
    from engine import cli  # imported here: cli spawns this module
    payload = json.loads(pathlib.Path(argv[0]).read_text(encoding="utf-8"))
    if payload.get("trial"):
        return _trial_main(payload)
    wid, step_id, budget = payload["wid"], payload["step"], payload["budget"]
    ran = []
    for fid, cmd in payload["commands"]:
        code, output = _run(cmd, payload["cwd"], budget)
        _attempt(fid, cmd, code, output)
        if code is None:
            journal.append(wid, "check", step=step_id, command=cmd, exit=-1,
                           output=f"no result after {budget}s")
            return _refuse(payload, _overran(wid, step_id, fid, cmd, budget))
        ran.append({"command": cmd, "exit": code, "output": output})
        if code != 0:
            journal.append(wid, "check", step=step_id, **ran[-1])
            return _refuse(payload, _failed(wid, step_id, fid, cmd, code))
    cli.complete_submit(wid, step_id, payload["fields"], ran)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
