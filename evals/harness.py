"""Drive a real run with a real model, then assert on the journal.

Every other test in this repo proves the engine works when called correctly.
These prove an agent can actually drive it — the claim the whole design rests
on, and the one thing a green suite has never once told us. What makes it
assertable rather than vibes: the journal is the record, so "did review fire"
and "was an anchor amended" are facts a test can read.

The lightest model is deliberate. If a step needs a strong model to be
followed, the form is doing too little work — the difficulty belongs in the
task, never in understanding what was asked.
"""

import os
import pathlib
import subprocess
import tomllib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPINE = str(ROOT / "spine")

from engine import run as runmod


# [tier-model]
# Rationale: an eval names a palette tier, never a provider's model id --
#   the same indirection assemblies and gate specs already use, so a shop
#   that swaps its light model swaps it in one file. The tier is a parameter
#   because it was previously a literal inside this function, which made
#   "run this one eval on a stronger model" a harness edit rather than an
#   argument at the call site.
# Rejected: an eval passing a model id straight through to `claude`. That is
#   the one thing constellation.toml exists to stop leaking into artifacts.
def tier_model(tier="light"):
    """The concrete model behind a palette tier."""
    palette = tomllib.load(open(ROOT / "constellation.toml", "rb"))
    return palette["models"][tier]


def spine(workdir, *args):
    """Run a spine command in the eval's workdir, as an agent would."""
    return subprocess.run([SPINE, *args], cwd=workdir, capture_output=True,
                          text=True, timeout=60)


# [drive-budget]
# Rationale: 240s was the default until a measured run took 289 and was
#   killed mid-step. A killed `claude` leaves the journal standing on the
#   step it was working, which is indistinguishable from an agent that
#   stalled -- so the old default did not slow an eval down, it fabricated a
#   failure and named the agent for it. 420 clears the slowest run seen by a
#   wide margin; a genuinely hung run is still bounded, by the suite runner
#   rather than by clipping the runs that are merely long.
# Rejected: raising it at each call site. What was wrong was the default, so
#   every eval that never passed a timeout stayed wrong.
# Rationale: overrunning the budget is a result, not an infrastructure error,
#   so the timeout is caught here rather than raised. A propagating
#   TimeoutExpired ends the test on this call, the assertion below it never
#   runs, and the journal the eval exists to read is never read -- the
#   failure report becomes a stack trace about subprocess.communicate
#   instead of a statement about what the agent did. What was captured comes
#   back marked, and the eval's own assertion rules on it.
# Rejected: no timeout at all. The bound is what stops one hung model from
#   holding the suite.
def drive(workdir, prompt, timeout=420, tier="light"):
    """Hand a model of `tier` the workdir and the prompt, and let it work.

    It gets Bash and file tools and nothing else -- no instructions about the
    engine beyond what it can read from `spine` itself. That is the point: the
    room description is supposed to be sufficient.

    `tier` defaults to the lightest model on purpose: if a step needs a strong
    model to be followed, the form is at fault. An eval that means to measure
    something else says so here, out loud, in its own call.
    """
    # `spine` on PATH -- not what an install does (install.py only copies,
    # and deliberately adds no PATH entry), but what a human's own installed
    # shell already has by the time they open a root run. All three evals
    # here open root runs, so this pre-seed simulates that install rather
    # than papering over a gap; a dispatched child gets no such shell of its
    # own, and self-location is what covers that case instead.
    env = {**os.environ, "CONSTELLATION_SESSION": "eval",
           "PATH": f"{ROOT}:{os.environ.get('PATH', '')}"}
    cmd = ["claude", "-p", prompt, "--model", tier_model(tier),
           "--allowedTools", "Bash", "Read", "Write", "Edit"]
    try:
        r = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True,
                           timeout=timeout, env=env)
        cut = ""
    except subprocess.TimeoutExpired as e:
        r = subprocess.CompletedProcess(cmd, returncode=None,
                                        stdout=_captured(e.stdout),
                                        stderr=_captured(e.stderr))
        cut = f"\n\n# cut off after {timeout}s -- the model was still working\n"
    # Keep the whole thing. What `r.stdout` holds is the agent's closing
    # summary -- the least reliable artifact in the run, and the only one
    # these evals used to fail with. Debugging from a self-report is the
    # believe-the-record failure the issue-conductor skill exists to warn against.
    d = pathlib.Path(workdir)
    log = d / f"transcript-{len(list(d.glob('transcript-*.md'))) + 1}.md"
    log.write_text(f"# prompt\n\n{prompt}{cut}\n\n# stdout\n\n{r.stdout}"
                   f"\n\n# stderr\n\n{r.stderr}\n")
    r.transcript = log
    r.timed_out = bool(cut)
    r.budget = timeout
    return r


def _captured(stream):
    """Whatever a killed `claude` had written by the time it was killed.
    `TimeoutExpired` carries the partial output as bytes even under
    `text=True`, and carries None when there was nothing."""
    if stream is None:
        return ""
    return stream.decode(errors="replace") if isinstance(stream, bytes) else stream


# [drive-unfinished]
# Rationale: an eval reading the journal after a drive has to know whether it
#   is reading a run that finished or a run that was stopped, and only `drive`
#   knows the budget it was stopped at. One sentence, built here, is what lets
#   an eval's failure say which of the two it is looking at -- the alternative
#   is every assertion below a drive reporting the agent's behaviour for a
#   drive that never got to behave.
# Rejected: each eval reading `r.timed_out` itself. Same rule written per call
#   site, and it drops the budget, which is the number that separates "too
#   slow" from "wrong" for whoever reads the red.
def unfinished(r):
    """Why the drive did not run to completion -- "" when it did."""
    if getattr(r, "timed_out", False):
        return f"the drive was cut off after {getattr(r, 'budget', '?')}s, still working"
    if r.returncode:
        return f"the drive exited {r.returncode} before it was done"
    return ""


def evidence(workdir, work_id, r):
    """What a failing eval should say instead of the agent's last paragraph:
    the engine's own timeline of what actually happened, and where the full
    transcript is. `trace` folds the run and every child it dispatched into
    one ordering, which is the view the seam defects live in."""
    t = subprocess.run([SPINE, work_id, "trace"], cwd=workdir, capture_output=True,
                       text=True, timeout=60)
    stopped = unfinished(r)
    cut = (f"\n-- {stopped}, so the record above is where the agent had got "
           "to --" if stopped else "")
    return (f"\n\n-- what the engine recorded --\n{t.stdout or t.stderr}{cut}"
            f"\n-- the agent's last words --\n{r.stdout[-800:]}"
            f"\n\n-- full transcript: {getattr(r, 'transcript', '(none)')}")


def state(workdir, work_id):
    """The run's state, folded from its journal -- what the eval asserts on."""
    cwd = os.getcwd()
    try:
        os.chdir(workdir)
        return runmod.state(work_id)
    finally:
        os.chdir(cwd)


def journal_text(workdir, work_id):
    p = pathlib.Path(workdir) / ".agent-work" / work_id.replace(".", "/") / "journal.toml"
    return p.read_text() if p.exists() else ""


def prefill(workdir, work_id, **fields):
    """Stamp orders onto a run the way a dispatch would, so an eval can set up
    a gate spec without a parent run."""
    cwd = os.getcwd()
    try:
        os.chdir(workdir)
        from engine import journal
        journal.append(work_id, "prefill", fields=fields)
    finally:
        os.chdir(cwd)


def form_text(workdir, work_id, name):
    p = (pathlib.Path(workdir) / ".agent-work" / work_id.replace(".", "/") / name)
    return p.read_text() if p.exists() else ""
