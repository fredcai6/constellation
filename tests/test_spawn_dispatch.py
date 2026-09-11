"""`checks.spawn_dispatch`, exercised directly -- never through a rendered
dispatch or panel room, which stays out of scope for this gate.

Every process this file starts is a short-lived `python3 -c ...`
invocation of the test's own choosing, never `claude` or any real harness --
the wiring that would make a real harness's name matter is next gate's job.
"""

import json
import os
import pathlib
import subprocess
import sys
import time

import pytest

from engine import checks, journal


def _log(wid, name):
    path = journal.location(wid) / f"dispatch.{name}.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _await_exit(pid, seconds=10):
    """Poll `checks.alive` until a spawned process is actually gone."""
    deadline = time.time() + seconds
    while checks.alive(pid) and time.time() < deadline:
        time.sleep(0.05)
    return checks.alive(pid)


# -- substitution, cwd, and log routing ---------------------------------------


def test_placeholders_land_whole_and_untouched_words_pass_through(
        bare_workdir, capsys):
    """{brief}/{runner}/{tree} each land as one whole argv element regardless
    of spaces, newlines, colons or dashes inside them; a word that is not
    exactly one of the three is left exactly as written; the process's cwd
    is the given tree; and its stdout/stderr reach the log, not the test's
    own."""
    wid = "g1"
    tree = pathlib.Path(bare_workdir) / "childtree"
    tree.mkdir()
    log = _log(wid, "sub")
    script = (
        "import sys, os, json\n"
        "print(json.dumps({'argv': sys.argv[1:], 'cwd': os.getcwd()}))\n"
        "print('stderr-marker', file=sys.stderr)\n"
    )
    brief = "line one\nline two: with a - dash and spaces"
    runner = "runner:model-name with spaces"
    commands = {"dispatch": [
        sys.executable, "-c", script,
        "{brief}", "--runner", "{runner}", "--tree", "{tree}",
        "literal-{brief}", "{unrecognized}",
    ]}

    entry = checks.spawn_dispatch(commands, brief, runner, str(tree), wid, "c1", log)

    assert entry is not None
    assert capsys.readouterr() == ("", "")   # nothing leaked to the test's own streams

    assert _await_exit(entry["pid"]) is False   # wait past the process's own exit ...
    content = log.read_text(encoding="utf-8")  # ... so every write it made is flushed
    assert "stderr-marker" in content
    json_line = next(l for l in content.splitlines() if l.startswith("{"))
    payload = json.loads(json_line)
    assert payload["argv"] == [
        brief, "--runner", runner, "--tree", str(tree),
        "literal-{brief}", "{unrecognized}",
    ]
    assert os.path.realpath(payload["cwd"]) == os.path.realpath(str(tree))


def test_cwd_is_set_to_tree_even_when_the_entry_never_mentions_tree(bare_workdir):
    """Commitment 7 holds "regardless of whether the entry's text uses
    {tree}" -- an argv that contains no `{tree}` token at all must still
    spawn its child with `tree` as the working directory. An implementation
    that only threaded `cwd` through inside the branch handling that token
    would pass every other test in this file (all of them reference
    `{tree}` in their argv) while failing this one."""
    wid = "g1"
    tree = pathlib.Path(bare_workdir) / "childtree"
    tree.mkdir()
    log = _log(wid, "notree")
    script = "import os, json\nprint(json.dumps({'cwd': os.getcwd()}))\n"
    commands = {"dispatch": [sys.executable, "-c", script, "{brief}"]}  # no {tree} anywhere

    entry = checks.spawn_dispatch(commands, "brief", "runner", str(tree), wid, "c1", log)

    assert _await_exit(entry["pid"]) is False
    content = log.read_text(encoding="utf-8")
    json_line = next(l for l in content.splitlines() if l.startswith("{"))
    payload = json.loads(json_line)
    assert os.path.realpath(payload["cwd"]) == os.path.realpath(str(tree))


# -- detachment ----------------------------------------------------------------


def test_the_spawned_process_is_detached_in_its_own_session(bare_workdir):
    """The concrete fact `start_new_session=True` produces: a session id of
    its own, distinct from the test process's -- not merely a `Popen`
    handle the test drops outliving the same still-running test process,
    which would be true of any subprocess started any way at all."""
    wid = "g1"
    tree = pathlib.Path(bare_workdir) / "childtree"
    tree.mkdir()
    log = _log(wid, "session")
    commands = {"dispatch": [sys.executable, "-c", "import time; time.sleep(2)"]}

    entry = checks.spawn_dispatch(commands, "brief", "runner", str(tree), wid, "c1", log)

    try:
        assert os.getsid(entry["pid"]) != os.getsid(os.getpid())
    finally:
        _await_exit(entry["pid"])   # let it finish rather than leaving it be reaped later


# -- exit code decides nothing about the spawn (commitment 8) ------------------


def test_a_nonzero_exit_is_still_a_successful_spawn(bare_workdir):
    """A process that starts fine and exits quickly with a nonzero code is
    journaled as a spawn, not reported as a failure -- nothing here waits on
    or reads its exit code. `checks.alive` still reads its liveness
    correctly once it is actually gone."""
    wid = "g1"
    tree = pathlib.Path(bare_workdir) / "childtree"
    tree.mkdir()
    log = _log(wid, "nonzero")
    commands = {"dispatch": [sys.executable, "-c", "import sys; sys.exit(7)"]}

    entry = checks.spawn_dispatch(commands, "brief", "runner", str(tree), wid, "c1", log)

    assert entry is not None and "pid" in entry and "at" in entry
    assert entry["child"] == "c1"
    landed = journal.read(wid)
    started = [e for e in landed if e.get("kind") == "dispatch-started"]
    assert len(started) == 1
    assert started[0]["child"] == "c1" and started[0]["pid"] == entry["pid"]
    assert started[0]["at"]                                   # a start time was stamped

    assert _await_exit(entry["pid"]) is False                  # alive() now reads it as gone


def test_a_zombie_reads_as_not_alive(bare_workdir):
    """Exited but never waited on: `os.kill(pid, 0)` still succeeds on it,
    and `alive` must not."""
    proc = subprocess.Popen(
        [sys.executable, "-c", "raise SystemExit(3)"],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(0.1)  # long enough to have exited; nothing has reaped it
    try:
        assert checks.alive(proc.pid) is False
    finally:
        proc.wait()

# -- the three failure inputs ---------------------------------------------------


def test_no_dispatch_key_is_not_dispatched_and_not_a_failure(bare_workdir):
    """Commitment 3's world: nothing to spawn, no failure -- a plain `None`,
    no exception, and no journal entry."""
    wid = "g1"
    result = checks.spawn_dispatch({}, "brief", "runner", "/tmp", wid, "c1",
                                    _log(wid, "absent"))
    assert result is None
    assert journal.read(wid) == []


def test_a_malformed_entry_fails_distinguishably_from_the_missing_key(bare_workdir):
    """Today's single-string `[commands]` shape, written under `dispatch` by
    mistake, must fail loudly -- and its reason must not collapse into the
    missing-key case's own reason, or a standing misconfiguration would
    render as nothing configured."""
    wid = "g1"
    commands = {"dispatch": "claude -p {brief}"}   # every other entry's own shape

    with pytest.raises(checks.DispatchFailure) as exc:
        checks.spawn_dispatch(commands, "brief", "runner", "/tmp", wid, "c1",
                               _log(wid, "malformed"))

    assert exc.value.reason == checks.DISPATCH_MALFORMED
    assert exc.value.reason is not None
    assert journal.read(wid) == []


def test_an_unfilled_placeholder_fails_distinguishably_from_the_other_two(bare_workdir):
    """A recognized placeholder the caller supplied no value for -- here,
    `{tree}` with `tree=None` -- fails with its own reason, distinct from
    both the missing-key case and the malformed-entry case."""
    wid = "g1"
    commands = {"dispatch": [sys.executable, "-c", "pass", "{tree}"]}

    with pytest.raises(checks.DispatchFailure) as exc:
        checks.spawn_dispatch(commands, "brief", "runner", None, wid, "c1",
                               _log(wid, "unfilled"))

    assert exc.value.reason == checks.DISPATCH_UNFILLED
    assert exc.value.reason != checks.DISPATCH_MALFORMED
    assert journal.read(wid) == []


def test_an_unfilled_brief_or_runner_fails_the_same_way_as_an_unfilled_tree(bare_workdir):
    """The spec's own change section frames uniform treatment of all three
    placeholders as the deliberately-chosen, non-obvious correct behavior --
    `{tree}` is elsewhere described as "optional to use", which makes it the
    tempting special case. This exercises the other two: a missing `brief`
    against an entry using `{brief}`, and a missing `runner` against an
    entry using `{runner}`, each must raise DISPATCH_UNFILLED and journal
    nothing -- not fall through and land `str(None)` as a literal argv word."""
    wid = "g1"
    tree = pathlib.Path(bare_workdir) / "childtree"
    tree.mkdir()

    cases = [
        ("{brief}", dict(brief=None, runner="runner")),
        ("{runner}", dict(brief="brief", runner=None)),
    ]
    for word, values in cases:
        commands = {"dispatch": [sys.executable, "-c", "pass", word]}

        with pytest.raises(checks.DispatchFailure) as exc:
            checks.spawn_dispatch(commands, tree=str(tree), wid=wid, child_id="c1",
                                   log=_log(wid, "unfilled-" + word.strip("{}")),
                                   **values)

        assert exc.value.reason == checks.DISPATCH_UNFILLED
        assert exc.value.reason != checks.DISPATCH_MALFORMED

    assert journal.read(wid) == []   # neither case journaled anything, even partially


def test_a_process_that_fails_to_start_fails_distinguishably_too(bare_workdir):
    """A `dispatch` entry naming a nonexistent executable: the spawn itself
    raises, and that is reported as a failure with its own reason -- never
    an unhandled exception escaping the primitive, and no journal entry."""
    wid = "g1"
    tree = pathlib.Path(bare_workdir) / "childtree"
    tree.mkdir()
    commands = {"dispatch": ["/no/such/executable-constellation-issue88", "{brief}"]}

    with pytest.raises(checks.DispatchFailure) as exc:
        checks.spawn_dispatch(commands, "brief", "runner", str(tree), wid, "c1",
                               _log(wid, "nostart"))

    assert exc.value.reason == checks.DISPATCH_SPAWN_FAILED
    assert exc.value.reason not in (checks.DISPATCH_MALFORMED, checks.DISPATCH_UNFILLED)
    assert journal.read(wid) == []


def test_the_three_failure_reasons_and_the_absent_case_are_all_distinguishable(
        bare_workdir):
    """The reasons a caller branches on, gathered in one place: three
    distinct sentinels for the three failure inputs, and the absent-key case
    is a different shape entirely (`None`, never raised), so none of the
    four can be mistaken for another by the time they leave the primitive."""
    reasons = {checks.DISPATCH_MALFORMED, checks.DISPATCH_UNFILLED,
               checks.DISPATCH_SPAWN_FAILED}
    assert len(reasons) == 3
    assert all(isinstance(r, str) and r for r in reasons)
