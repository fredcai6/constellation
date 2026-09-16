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
# [headless]
# Rationale: the one fact about this harness a brief cannot carry. A headless
#   `claude -p` is never woken: twelve children across three runs died by
#   starting a check in the background and ending their turn to wait for a
#   notification (docs/process-notes/issue99.md note 28). Stated once here and
#   copied verbatim into constellation.toml's `dispatch` entry, which
#   tests/test_dispatch_wiring.py holds equal to this argv.
HEADLESS = 'You are a headless process started by an engine. Nothing will ever notify you: no background task, no timer, no other agent. Run every command in the foreground and read its output before going on; never start a check in the background and never end your turn to wait for anything. Your turn ends only when the room you were handed says your step is done.'


def tier_model(tier="light"):
    """The concrete model behind a palette tier."""
    palette = tomllib.load(open(ROOT / "constellation.toml", "rb"))
    return palette["models"][tier]


def init_checkout(workdir):
    """Make `workdir` a git checkout with a commit and a local bare remote
    named `origin` -- `spine open`'s root-run path (ruling 8) refuses one
    with neither, and every eval that opens a root run needs somewhere real
    to point at without ever reaching a live remote. Call after `workdir`
    already carries whatever else the eval seeds it with (a `retry.py`, a
    `constellation.toml`) -- everything on disk at that point is what the
    commit, and so every worktree opened from here, carries."""
    workdir = pathlib.Path(workdir)
    remote = workdir.parent / f"{workdir.name}-remote.git"
    git = lambda *a: subprocess.run(["git", *a], cwd=workdir, check=True,
                                    capture_output=True, text=True)
    subprocess.run(["git", "init", "--quiet", "--bare", str(remote)],
                   cwd=workdir.parent, check=True, capture_output=True)
    git("init", "--quiet")
    git("config", "user.email", "eval@example.com")
    git("config", "user.name", "eval")
    git("remote", "add", "origin", str(remote))
    (workdir / ".gitignore").write_text(".agent-work/\n.worktrees/\n")
    git("add", "-A")
    git("commit", "--quiet", "-m", "initial")
    return remote


# [eval-run-root]
# Rationale: `spine open` on a root run now makes a worktree beside
#   `workdir` and works inside it (ruling 8), so `workdir` itself is only
#   ever right for the *first* `open` -- every call after that has to land
#   in whatever worktree that run's own id already lives in. Each eval here
#   drives exactly one run per workdir, so "the one worktree there is" is
#   unambiguous; picking the right one among several is the two-root
#   resolution a later gate owns, not a distinction these evals need yet.
# Rejected: threading a work id through every helper here instead. `drive`
#   has none to thread -- the model is handed a directory and a prompt, not
#   a work id -- so the resolution has to work from `workdir` alone.
def run_root(workdir):
    """The directory a run opened from `workdir` actually works in: the sole
    worktree under `.worktrees/` once one exists, else `workdir` itself."""
    trees = pathlib.Path(workdir) / ".worktrees"
    found = sorted(p for p in trees.glob("*") if p.is_dir()) if trees.is_dir() else []
    return found[0] if len(found) == 1 else pathlib.Path(workdir)


def spine(workdir, *args):
    """Run a spine command in the eval's workdir, as an agent would."""
    cwd = workdir if (not args or args[0] == "open") else run_root(workdir)
    return subprocess.run([SPINE, *args], cwd=cwd, capture_output=True,
                          text=True, timeout=60)


# [harness-response-path-via-engine]
# Rationale: `_response_path` (engine/cli.py) now names a step's response
#   form for the step as well as the form, so a fixture spelling `OPEN.toml`
#   is exactly the #118 defect these evals would otherwise carry into a real
#   drive -- silently, since a stale path just never gets read rather than
#   raising. Resolving it is a pure read with no side effect on the run, so
#   it takes the same `os.chdir` shape `state()` already uses to call the
#   engine in-process, rather than shelling out to `spine` and parsing the
#   room it prints back -- one fewer subprocess, and nothing to keep in sync
#   with `render.status`'s own wording.
def response_path(workdir, work_id):
    """Where `work_id`'s current step takes its answer -- asked of the
    engine (`_response_path`, engine/cli.py) rather than spelled, the same
    move `tests/test_nesting.py`'s own `_response` makes for the fast
    suite."""
    from engine import cli as clim
    cwd = os.getcwd()
    try:
        os.chdir(run_root(workdir))
        st = runmod.state(work_id)
        return clim._response_path(st, st["current"]).resolve()
    finally:
        os.chdir(cwd)


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
           "--allowedTools", "Bash", "Read", "Write", "Edit",
           "--append-system-prompt", HEADLESS]
    # the model works wherever a real agent would land after `spine open`
    # ran -- inside the run's own worktree once one exists, `workdir` before
    d = run_root(workdir)
    try:
        r = subprocess.run(cmd, cwd=d, capture_output=True, text=True,
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
    # [transcript-survives-its-own-close]
    # Rationale: `d`, captured before the drive, is the run's worktree while
    #   one exists -- but a drive that reaches a real `close` on a root run
    #   removes that worktree as part of closing (`_sweep_to_archive`,
    #   engine/cli.py), so the directory `d` named is gone by the time this
    #   line runs. Re-resolving here falls back to `workdir` itself exactly
    #   the way `run_root` already does when no worktree exists -- the first
    #   directory this file ever offers, and always present. Found by
    #   `test_rolling_horizon.py`'s own drive actually reaching `closed`;
    #   no eval before it ever drove a run through its own close, so this
    #   path was never exercised.
    # Rejected: writing the transcript into the (now-gone) worktree path
    #   regardless, catching the error. A silently dropped transcript is the
    #   one artifact a failing eval's `evidence()` depends on to say what the
    #   agent actually did -- losing it turns every future failure here back
    #   into a self-report.
    d = run_root(workdir) if not d.exists() else d
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
    t = subprocess.run([SPINE, work_id, "trace"], cwd=run_root(workdir),
                       capture_output=True, text=True, timeout=60)
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
        os.chdir(run_root(workdir))
        return runmod.state(work_id)
    finally:
        os.chdir(cwd)


def journal_text(workdir, work_id):
    p = run_root(workdir) / ".agent-work" / work_id.replace(".", "/") / "journal.toml"
    return p.read_text() if p.exists() else ""


def prefill(workdir, work_id, **fields):
    """Stamp orders onto a run the way a dispatch would, so an eval can set up
    a gate spec without a parent run."""
    cwd = os.getcwd()
    try:
        os.chdir(run_root(workdir))
        from engine import journal
        journal.append(work_id, "prefill", fields=fields)
    finally:
        os.chdir(cwd)


def form_text(workdir, work_id):
    """The text of `work_id`'s own current response form -- named for the
    step now (#118), so read through `response_path` rather than a filename
    a caller supplies."""
    p = response_path(workdir, work_id)
    return p.read_text() if p.exists() else ""
