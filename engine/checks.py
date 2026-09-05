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


def _spawn(argv, log, cwd=None):
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
    a non-Python harness never looks at costs it nothing."""
    env = {**os.environ,
           "PYTHONPATH": os.pathsep.join(
               p for p in (str(_ROOT), os.environ.get("PYTHONPATH", "")) if p),
           "CONSTELLATION_SESSION": os.environ.get(
               "CONSTELLATION_SESSION", str(os.getpid()))}
    with open(log, "a", encoding="utf-8") as out:
        return subprocess.Popen(
            argv, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
            start_new_session=True, env=env, cwd=cwd)


# [dispatch-failure]
# Rationale: the primitive's contract has exactly one axis (the gate room's
#   own words): a genuinely absent `dispatch` key is nothing to spawn and no
#   failure (returns `None`, no exception at all -- commitment 3's world),
#   and every other case is a reported, distinguishable failure. Splitting
#   those two by *shape* (return value vs. raised exception) rather than by
#   a value the absent case would also have to carry makes the two
#   mechanically un-collapsible: a caller cannot mistake `None` for a
#   `DispatchFailure`, however either is constructed, which is stronger than
#   asking a caller to compare two sentinel strings correctly forever.
#   `.reason` is one of the module-level DISPATCH_* constants (not free
#   text) so the three failure inputs stay distinguishable from each other
#   too -- a caller branches on `exc.reason`, never on `str(exc)`.
# Rejected: one return-value shape for all outcomes (success, absent, and
#   the three failures) via a small result object. It would make the axis
#   uniform to inspect, but every call site would need an `if` for a case
#   (absent) that commitment 3 says is not an error at all, and Python
#   already has a mechanism for "stop and report why" that isn't "also
#   check a field to see if you should have stopped" -- an unraised `None`
#   already reads, at the call site, as "there was nothing to do here."
class DispatchFailure(Exception):
    """A `spawn_dispatch` attempt that produced no journal entry. `.reason`
    names which of the three failure inputs this was; `.detail` is the free
    text a person reads in a refusal or a log."""
    def __init__(self, reason, detail):
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


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
    time) once the process is actually running. Returns `None` -- no
    exception, no journal entry -- when `commands` carries no `dispatch`
    key at all: a repository that has not configured one (commitment 3).

    Raises `DispatchFailure` for every other way this can fail to produce a
    running, journaled process: the entry is present but not a list
    (today's single-string `[commands]` shape used verbatim would land
    here), a placeholder in it names one of `{brief}`/`{runner}`/`{tree}`
    but the caller passed `None` for that value, or the process itself
    fails to start (a nonexistent executable, most commonly). No journal
    entry is written in any of these cases -- the append happens only after
    `_spawn` hands back a live `Popen`, so there is no window in which a
    partial entry could land.

    `tree` also becomes the spawned process's own working directory
    (commitment 7) regardless of whether the entry's text uses `{tree}` at
    all; `log` is where its stdout and stderr are captured, opened in
    append mode exactly like a check's own log."""
    if "dispatch" not in commands:
        return None
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
        proc = _spawn(argv, log, cwd=tree)
    except OSError as e:
        raise DispatchFailure(DISPATCH_SPAWN_FAILED, str(e)) from e
    return journal.append(wid, "dispatch-started", child=child_id, pid=proc.pid,
                           tree=tree, log=str(pathlib.Path(log).resolve()))


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
    orphan is the worse of the two mistakes."""
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except (OSError, ValueError, TypeError):
        return True
    return True


# -- the detached runner ------------------------------------------------------


def _run(cmd, cwd, budget):
    """(exit, output) for one check; exit `None` when it outran the budget."""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                           timeout=budget, cwd=cwd)
    except subprocess.TimeoutExpired:
        return None, ""
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


def _refuse(payload, text):
    """Leave the refusal where the caller reads it, and print it into the log
    so a check that was already handed back still says why it failed
    somewhere a person can find it."""
    pathlib.Path(payload["result"]).write_text(
        json.dumps({"refusal": text}), encoding="utf-8")
    print(text)
    return 1


def main(argv):
    """Run one step's checks and write the outcome. Never called by a person:
    `hand_in` spawns this, and it is the only process that ever holds a
    check's exit status."""
    from engine import cli  # imported here: cli spawns this module
    payload = json.loads(pathlib.Path(argv[0]).read_text(encoding="utf-8"))
    wid, step_id, budget = payload["wid"], payload["step"], payload["budget"]
    ran = []
    for fid, cmd in payload["commands"]:
        code, output = _run(cmd, payload["cwd"], budget)
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
