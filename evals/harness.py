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
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPINE = str(ROOT / "spine")
sys.path.insert(0, str(ROOT))

from engine import run as runmod  # noqa: E402


def light_model():
    palette = tomllib.load(open(ROOT / "constellation.toml", "rb"))
    return palette["models"]["light"]


def spine(workdir, *args):
    """Run a spine command in the eval's workdir, as an agent would."""
    return subprocess.run([SPINE, *args], cwd=workdir, capture_output=True,
                          text=True, timeout=60)


def drive(workdir, prompt, timeout=240):
    """Hand a light model the workdir and the prompt, and let it work.

    It gets Bash and file tools and nothing else -- no instructions about the
    engine beyond what it can read from `spine` itself. That is the point: the
    room description is supposed to be sufficient.
    """
    # `spine` on PATH -- not what an install does (install.py only copies,
    # and deliberately adds no PATH entry), but what a human's own installed
    # shell already has by the time they open a root run. All three evals
    # here open root runs, so this pre-seed simulates that install rather
    # than papering over a gap; a dispatched child gets no such shell of its
    # own, and self-location is what covers that case instead.
    env = {**os.environ, "CONSTELLATION_SESSION": "eval",
           "PATH": f"{ROOT}:{os.environ.get('PATH', '')}"}
    r = subprocess.run(
        ["claude", "-p", prompt, "--model", light_model(),
         "--allowedTools", "Bash", "Read", "Write", "Edit"],
        cwd=workdir, capture_output=True, text=True, timeout=timeout, env=env)
    return r


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
