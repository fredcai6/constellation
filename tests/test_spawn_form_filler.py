"""`checks.spawn_form_filler`, exercised directly -- the same way
`tests/test_spawn_dispatch.py` proves `spawn_dispatch` itself, never through
a rendered room (that is `tests/test_drive.py`'s own job, once `cmd_drive`
calls this).

`spawn_form_filler` substitutes `{brief}`/`{runner}`/`{tree}` into the
identical `[commands] dispatch` entry `spawn_dispatch` reads -- there is no
second palette entry for a form filler -- and shares that substitution and
launch logic with it through a private helper (`checks._dispatch_launch`),
proven indirectly here through every case that mirrors one of
`test_spawn_dispatch.py`'s own. What is actually new, and what this file
exists to prove directly, is the journal record itself: kind
`form-filler-started`, keyed by `step` rather than `child`, carrying no
`tree` field at all -- a filler inherits the run's own tree, so there is no
second tree fact to journal about it.

Every process this file starts is a short-lived `python3 -c ...` of its own
choosing, never `claude` or any real harness.
"""

import os
import pathlib
import sys
import time

import pytest

from engine import checks, journal


def _log(wid, name):
    path = journal.location(wid) / f"form-filler.{name}.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


# [await-exit-no-zombie-race]
# Rationale: `checks.alive` cannot tell a zombie (already exited, not yet
#   reaped) from a process genuinely still running -- both read as alive
#   via `os.kill(pid, 0)`. `test_spawn_dispatch.py`'s own `_await_exit`
#   returns that same ambiguous read once its poll ends, so whether the
#   caller ever sees `True` (its own "confirmed exited" reading -- every
#   caller in this file asserts `is True` right after spawning a process
#   that exits almost at once) depends on some *other*, unrelated `Popen`
#   call happening to run `subprocess._cleanup` and reap this pid before
#   its own deadline -- the same gotcha `test_drive_end_to_end.py`'s
#   module docstring names. In this file that other call is not guaranteed
#   to happen in time, which is the 1-in-8 flake the gate spec reports.
#   Reaping the child directly with `os.waitpid(pid, os.WNOHANG)` removes
#   the dependency on some unrelated call ever happening at all: a
#   still-running process reports `(0, 0)` and the loop keeps polling; an
#   already-exited one is reaped -- by us, or (`ChildProcessError`) by
#   someone else who beat us to it -- either way confirming the same
#   thing, that every write it made is already flushed.
# Rejected: leaving this file's copy identical to `test_spawn_dispatch.py`'s
#   and just raising `seconds`. A longer deadline still only ever produces
#   a `True` if something else's `Popen` call happens along -- it does not
#   make that happen, so the race would remain, only rarer.
def _await_exit(pid, seconds=10):
    """Poll until a spawned process is actually gone, reaping it directly
    rather than waiting on some unrelated `Popen` call elsewhere to trigger
    `subprocess._cleanup` first. `True` once exit is confirmed (by us or by
    someone else); `False` only if `seconds` runs out with the process
    still genuinely running."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            reaped_pid, _status = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            return True  # already reaped elsewhere -- also confirms exit
        if reaped_pid == pid:
            return True
        time.sleep(0.05)
    return False


def _form_filler_entries(wid):
    return [e for e in journal.read(wid) if e.get("kind") == "form-filler-started"]


# -- the record itself: kind, key, and what it does not carry ----------------


def test_a_successful_spawn_journals_by_step_never_by_child(bare_workdir):
    wid = "v1"
    tree = pathlib.Path(bare_workdir) / "childtree"
    tree.mkdir()
    commands = {"dispatch": [sys.executable, "-c", "import time; time.sleep(2)", "{brief}"]}

    entry = checks.spawn_form_filler(commands, "brief text", "runner", str(tree),
                                     wid, "g1", _log(wid, "g1"))

    try:
        assert entry is not None
        assert entry["kind"] == "form-filler-started"
        assert entry["step"] == "g1"
        assert "child" not in entry
        assert "tree" not in entry
        assert entry["pid"]
        started = _form_filler_entries(wid)
        assert len(started) == 1 and started[0]["step"] == "g1"
    finally:
        _await_exit(entry["pid"])


def test_the_process_actually_runs_under_tree_with_brief_and_runner_substituted(
        bare_workdir):
    wid = "v1"
    tree = pathlib.Path(bare_workdir) / "childtree"
    tree.mkdir()
    log = _log(wid, "g1")
    script = "import sys, os\nprint(sys.argv[1:]); print(os.getcwd())\n"
    commands = {"dispatch": [sys.executable, "-c", script, "{brief}", "{runner}"]}

    entry = checks.spawn_form_filler(commands, "the brief", "the runner", str(tree),
                                     wid, "g1", log)

    assert _await_exit(entry["pid"]) is True
    content = log.read_text(encoding="utf-8")
    assert "the brief" in content and "the runner" in content
    assert str(tree.resolve()) in content


def test_a_nonzero_exit_is_still_a_successful_spawn(bare_workdir):
    """Mirrors `test_spawn_dispatch.py`'s own case of the same name: nothing
    here reads or waits on the process's own exit code."""
    wid = "v1"
    tree = pathlib.Path(bare_workdir) / "childtree"
    tree.mkdir()
    commands = {"dispatch": [sys.executable, "-c", "import sys; sys.exit(7)"]}

    entry = checks.spawn_form_filler(commands, "brief", "runner", str(tree),
                                     wid, "g1", _log(wid, "nonzero"))

    assert entry is not None and "pid" in entry and "at" in entry
    assert _await_exit(entry["pid"]) is True


# -- the shared substitution/launch logic, mirrored from spawn_dispatch ------


def test_no_dispatch_key_fails_distinguishably_and_journals_nothing(bare_workdir):
    """`o-absent-dispatch-raises`: an absent `dispatch` key raises here too,
    the identical discipline the other three failure inputs already hold --
    no journal entry, whatever the reason."""
    wid = "v1"
    with pytest.raises(checks.DispatchFailure) as exc:
        checks.spawn_form_filler({}, "brief", "runner", "/tmp", wid, "g1",
                                 _log(wid, "absent"))

    assert exc.value.reason == checks.DISPATCH_ABSENT
    assert _form_filler_entries(wid) == []


def test_a_malformed_entry_fails_distinguishably_and_journals_nothing(bare_workdir):
    wid = "v1"
    commands = {"dispatch": "claude -p {brief}"}  # today's single-string shape, by mistake

    with pytest.raises(checks.DispatchFailure) as exc:
        checks.spawn_form_filler(commands, "brief", "runner", "/tmp", wid, "g1",
                                 _log(wid, "malformed"))

    assert exc.value.reason == checks.DISPATCH_MALFORMED
    assert _form_filler_entries(wid) == []


def test_an_unfilled_placeholder_fails_distinguishably_and_journals_nothing(bare_workdir):
    wid = "v1"
    commands = {"dispatch": [sys.executable, "-c", "pass", "{tree}"]}

    with pytest.raises(checks.DispatchFailure) as exc:
        checks.spawn_form_filler(commands, "brief", "runner", None, wid, "g1",
                                 _log(wid, "unfilled"))

    assert exc.value.reason == checks.DISPATCH_UNFILLED
    assert _form_filler_entries(wid) == []


def test_a_process_that_fails_to_start_fails_distinguishably_and_journals_nothing(
        bare_workdir):
    wid = "v1"
    commands = {"dispatch": ["/no/such/executable-constellation-issue100", "{brief}"]}

    with pytest.raises(checks.DispatchFailure) as exc:
        checks.spawn_form_filler(commands, "brief", "runner", ".", wid, "g1",
                                 _log(wid, "nostart"))

    assert exc.value.reason == checks.DISPATCH_SPAWN_FAILED
    assert _form_filler_entries(wid) == []


# -- the new cap, apart from MAX_STARTS ---------------------------------------


def test_form_filler_max_starts_is_its_own_positive_constant(bare_workdir):
    """Named apart from `checks.MAX_STARTS` on purpose (a form filler is not
    a dispatched child) -- this only proves it exists and is a sane bound;
    `tests/test_drive.py`'s own spent-filler case is what proves `cmd_drive`
    actually reads this one, not `MAX_STARTS`, when it caps a filler's own
    restarts."""
    assert isinstance(checks.FORM_FILLER_MAX_STARTS, int)
    assert checks.FORM_FILLER_MAX_STARTS > 0
