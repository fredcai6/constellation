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
    proc = _spawn(payload, log)
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


def _spawn(payload, log):
    """The detached runner. `start_new_session` puts it in a session of its
    own, so a harness that kills the caller's whole process group does not
    take the proof with it -- insurance rather than the mechanism, since a
    plain child already outlived a dispatched agent's turn when this was
    measured.

    `PYTHONPATH` carries this tree's root rather than a rewritten path:
    install is a copy, so the runner is found the same way in the repo and in
    an installed copy."""
    env = {**os.environ,
           "PYTHONPATH": os.pathsep.join(
               p for p in (str(_ROOT), os.environ.get("PYTHONPATH", "")) if p),
           "CONSTELLATION_SESSION": os.environ.get(
               "CONSTELLATION_SESSION", str(os.getpid()))}
    with open(log, "a", encoding="utf-8") as out:
        return subprocess.Popen(
            [sys.executable, "-m", "engine.checks", str(payload)],
            stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
            start_new_session=True, env=env)


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
