"""Rendering a dispatch or panel room starts nothing at all.
`_dispatch_child` is a pure read: a room reports which of the four states
each outstanding child is in off whatever the journal already holds, and
`wait` -- never a render -- is what starts a child's harness process. The
spawn mechanics (a child spawned once, a failed spawn caught and logged, a
working row reached only by a prior spawn) are held in `tests/test_wait.py`
with the call they depend on; what is here is the render side: the four
words, the briefs beside them, the respawn command -- and the negatives
proving no render reaches a process.

Every process this file starts (through `test_wait.py`'s own test-local
commands mapping) is a short-lived `python3 -c ...` of the test's own
choosing, never `claude`.
"""

import os
import pathlib
import subprocess
import sys
import tomllib

import pytest

import conftest
from engine import checks as checkrun
from engine import cli, journal, render
from test_brief import _mint_dispatch_step, _mint_panel_step
from test_nesting import _response
from test_wait import _throwaway_dispatch, _dispatch_entries, _record, _dead_pid, _gate


# -- rendering starts nothing --------------------------------------------------


def test_rendering_a_dispatch_room_starts_no_child(bare_workdir, capsys):
    """The inverse of the "spawned once" case in `test_wait.py`: the very
    same real, test-configured `dispatch` entry is in place, and rendering
    the room -- twice, since a second render is where a repeat spawn would
    show -- journals nothing, logs nothing, and drops no marker file. The
    row still reports the child's own state, which with nothing ever
    started is "not dispatched"."""
    marker = bare_workdir / "spawned"
    _throwaway_dispatch(bare_workdir, marker)
    _mint_dispatch_step(wid="d1", child="d1.g1")

    cli.main(["d1"])
    cli.main(["d1"])
    out = capsys.readouterr().out

    assert "d1.g1 (not dispatched)" in out
    assert _dispatch_entries("d1") == []
    assert not (journal.location("d1") / "dispatch.g1.log").exists()
    assert not marker.exists()


def test_rendering_a_panel_room_starts_no_panelist(bare_workdir, capsys):
    """The panel-step half: same entry, same two renders, same nothing."""
    marker = bare_workdir / "spawned"
    _throwaway_dispatch(bare_workdir, marker)
    _mint_panel_step(wid="g9", worker="reviewer")

    cli.main(["g9"])
    cli.main(["g9"])
    out = capsys.readouterr().out

    assert "panelist p1 (not dispatched)" in out
    assert _dispatch_entries("g9") == []
    assert not (journal.location("g9") / "dispatch.review.p1.log").exists()
    assert not marker.exists()


# -- no `dispatch` entry, nothing changes ------------------------------------


def test_a_repository_with_no_dispatch_entry_spawns_nothing(bare_workdir, capsys):
    """`bare_workdir` seeds no `constellation.toml` at all. Rendering the
    room must look identical: no journal entry, no log file, no crash."""
    _mint_dispatch_step(wid="d1", child="d1.g1")

    cli.main(["d1"])
    out = capsys.readouterr().out

    assert "d1.g1" in out                       # the room still rendered normally
    assert _dispatch_entries("d1") == []
    assert not (journal.location("d1") / "dispatch.g1.log").exists()


# -- four states, rendered ----------------------------------------------------

# -- one room, whether or not the palette is configured --
# The two fixtures below (`workdir` with a harmless `dispatch` entry,
# `test_a_repository_with_no_dispatch_entry_spawns_nothing`'s own
# `bare_workdir` with none at all) render the same room: a child's row
# never carries a hand-typed command in any state, so these prove the
# room's one shape on fixtures that could otherwise diverge from it.


def test_a_never_touched_child_renders_not_dispatched_with_no_brief(workdir, capsys):
    """An unconfigured repository (`workdir`'s own `constellation.toml` has
    no `dispatch` entry) renders the identical row a configured one does:
    the status word alone, no brief, no `open it:` line -- `spine <work-id>
    wait` is the only move that starts this child, whether or not the
    palette can act on it."""
    _mint_dispatch_step(wid="d1", child="d1.g1")
    capsys.readouterr()

    cli.main(["d1"])
    out = capsys.readouterr().out

    assert "d1.g1 (not dispatched)" in out
    assert "brief -- d1.g1" not in out
    assert "open it:" not in out
    assert not (journal.location("d1") / "dispatch.g1.log").exists()


def test_a_returned_childs_row_still_renders_as_before(workdir, capsys):
    """A returned panelist's row is untouched: the word, and no brief beside
    it. Its still-outstanding sibling reads "not dispatched" with no brief
    of its own either, regardless of the palette."""
    journal.append("g9", "run", title="t", assembly="run-a-gate")
    journal.append("g9", "step", id="review", segment="work",
                   panel=[{"worker": "reviewer", "criteria": "c1"},
                          {"worker": "critic", "criteria": "c2"}])
    journal.append("g9", "return", step="review", child="g9.review.p1",
                   fields={"verdict": "pass"})
    capsys.readouterr()

    cli.main(["g9"])
    out = capsys.readouterr().out

    assert "panelist p1 (returned)" in out
    assert "panelist p2 (not dispatched)" in out
    assert "brief --" not in out


# -- a "gone without returning" child carries no respawn command either,
# -- configured or not --------------------------------------------------------


def test_gone_without_returning_carries_no_command_when_the_run_was_never_opened(
        bare_workdir, capsys):
    """A dead `dispatch-started` record whose own run was never actually
    opened offers no `open it:` line in the unconfigured world, or any
    other. `spine <work-id> wait` is the only move that restarts it."""
    _mint_dispatch_step(wid="d1", child="d1.g1")
    journal.append("d1", "dispatch-started", child="d1.g1", pid=999999,
                   tree=str(bare_workdir), log=str(bare_workdir / "dispatch.g1.log"))
    assert not journal.exists("d1.g1")

    cli.main(["d1"])
    out = capsys.readouterr().out

    assert "d1.g1 (gone without returning)" in out
    assert "open it:" not in out
    assert "brief --" not in out


def test_gone_without_returning_carries_no_resume_command_once_the_run_exists(
        bare_workdir, capsys):
    """A harness that died mid-step, after its own run already exists, is
    not offered `spine {child_id}` as a hand-typed resume command -- the row
    states its word and nothing else, and `spine <work-id> wait` is what
    restarts it."""
    _mint_dispatch_step(wid="d1", child="d1.g1")
    cli.main(["open", "run-a-gate", "--parent", "d1", "--step", "g1"])
    capsys.readouterr()
    assert journal.exists("d1.g1")

    # the harness died: its own dispatch-started record points at a pid
    # that is gone
    journal.append("d1", "dispatch-started", child="d1.g1", pid=999999,
                   tree=str(bare_workdir), log=str(bare_workdir / "dispatch.g1.log"))

    cli.main(["d1"])
    out = capsys.readouterr().out
    assert "d1.g1 (gone without returning)" in out
    assert "open it:" not in out
    assert "brief --" not in out


# -- `wait` never joins the trailing aside -----------------------------------


def test_legal_moves_never_names_wait():
    """`render.legal_moves`'s trailing "also legal:" aside never names
    `wait`, on purpose. On a room with something outstanding, `wait` is
    *the* move, not one more also-legal option -- it belongs in the line
    above the child rows. The trailing aside is where text-to-read rather
    than an act-to-perform lives, and naming `wait` there would reproduce
    that failure in the one line built to avoid it, so the omission is
    checked rather than a default nobody verified."""
    assert "wait" not in render.legal_moves("d1").lower()


# -- the real constellation.toml names the real harness ----------------------


def test_constellation_toml_names_evals_harnesss_own_real_argv():
    """This repository's own, real `constellation.toml` -- not a test-local
    stand-in -- carries `dispatch` as exactly `evals/harness.py`'s own `cmd`
    (around evals/harness.py:128)."""
    root = pathlib.Path(__file__).resolve().parent.parent
    palette = tomllib.loads((root / "constellation.toml").read_text())

    from evals import harness
    assert palette["commands"]["dispatch"] == [
        "claude", "-p", "{brief}", "--model", "{runner}",
        "--allowedTools", "Bash", "Read", "Write", "Edit",
        "--append-system-prompt", harness.HEADLESS,
    ]


# -- the fast suite spawns no real process -----------------------------------


class _FakeProc:
    """A stand-in for `Popen`'s own return, pid chosen far past any real
    pid_max so `checkrun.alive` reads it as gone immediately -- nothing in
    this test waits on or blocks over a liveness check."""
    pid = 2**30


def test_the_fast_suites_workdir_never_reaches_the_real_dispatch_entry(
        workdir, monkeypatch, capsys):
    """`workdir` carries a present, harmless `dispatch` entry
    (`conftest._HARMLESS_DISPATCH_ENTRY`), so `wait` genuinely reaches
    `subprocess.Popen`. What must hold: the argv `Popen` actually receives,
    for a dispatch step and a panel step alike, is exactly the harmless
    stand-in -- this session's own interpreter -- never the real repo's own
    `claude` invocation."""
    calls = []
    monkeypatch.setattr(subprocess, "Popen", lambda argv, **k: calls.append(argv) or _FakeProc())

    _mint_dispatch_step(wid="d1", child="d1.g1")
    assert cli.main(["d1", "wait"]) == 0
    cli.main(["d1"])
    capsys.readouterr()

    _mint_panel_step(wid="g9", worker="reviewer")
    assert cli.main(["g9", "wait"]) == 0
    cli.main(["g9"])
    capsys.readouterr()

    assert len(calls) == 2
    for argv in calls:
        # the harmless stand-in's own first two words, verbatim -- not a
        # substring scan of the whole argv, which also carries the brief
        # text and legitimately names a runner like "claude-sonnet-5"
        assert argv[:2] == [sys.executable, "-c"]
        assert argv[0] != "claude"
    assert len(_dispatch_entries("d1")) == 1
    assert len(_dispatch_entries("g9")) == 1


# -- [workdir-substitutes-dispatch]: the substitution survives reformatting, and a miss is loud --


def test_workdir_substitutes_dispatch_even_when_the_entry_is_wrapped_across_lines():
    """An ordinary, correct TOML edit -- writing `dispatch` across several
    physical lines instead of one -- must not defeat the substitution. A
    line-oriented regex would only match a `dispatch` key confined to one
    physical line; this drives `conftest._with_a_harmless_dispatch_entry`
    against a wrapped array and checks the result through the same
    postcondition function (`_dispatch_is_harmless`) the `workdir` fixture
    itself calls."""
    wrapped = (
        '[commands]\n'
        'dispatch = [\n'
        '    "claude", "-p", "{brief}",\n'
        '    "--model", "{runner}",\n'
        ']\n'
        'test = "python3 -m pytest -q"\n'
    )

    substituted = conftest._with_a_harmless_dispatch_entry(wrapped)
    conftest._dispatch_is_harmless(substituted)  # does not raise

    palette = tomllib.loads(substituted)
    assert palette["commands"]["dispatch"] == conftest._HARMLESS_DISPATCH_ENTRY
    assert palette["commands"]["test"] == "python3 -m pytest -q"


def test_workdir_would_fail_loudly_if_the_real_dispatch_entry_survived():
    """The failure path of the fixture's postcondition, driven directly
    rather than merely asserted to exist: hand
    `conftest._dispatch_is_harmless` a palette whose `dispatch` command was
    never replaced. It must fail loudly -- naming what actually landed --
    rather than let a real command travel into the fast suite quietly. The
    spawn side cannot tell a working substitution from a silently-dead one
    (see the anchor's rationale, conftest.py); this postcondition is the
    only thing in the system that can, and it is what `workdir` runs at
    fixture setup, before any test body."""
    still_real = '[commands]\ndispatch = ["claude"]\n'

    with pytest.raises(AssertionError, match="dispatch"):
        conftest._dispatch_is_harmless(still_real)


# -- brief suppressed when configured ----------------------------------------


def test_a_never_dispatched_dispatch_childs_row_suppresses_its_brief_when_configured(
        bare_workdir, capsys):
    """`bare_workdir` carries no `constellation.toml` of its own, so a
    real, test-local `dispatch` entry (`_throwaway_dispatch`) is installed
    by hand to put this repository in the configured world. Since `wait` --
    not a render -- is what starts this child, printing the brief's
    `open it:` line here would hand the reader a command they must not run:
    `wait` either already beat them to it, or will the moment it is typed.
    The row must still carry its own status word, proving suppression of
    the brief rather than an empty render."""
    _throwaway_dispatch(bare_workdir, bare_workdir / "spawned")
    _mint_dispatch_step(wid="d1", child="d1.g1")

    cli.main(["d1"])
    out = capsys.readouterr().out

    assert "d1.g1 (not dispatched)" in out
    assert "brief --" not in out
    assert "open it:" not in out


def test_a_never_dispatched_panelists_row_suppresses_its_brief_when_configured(
        bare_workdir, capsys):
    """The panel-step half of the case above: same real, test-local
    `dispatch` entry, same never-dispatched child, same suppressed brief."""
    _throwaway_dispatch(bare_workdir, bare_workdir / "spawned")
    _mint_panel_step(wid="g9", worker="reviewer")

    cli.main(["g9"])
    out = capsys.readouterr().out

    assert "panelist p1 (not dispatched)" in out
    assert "brief --" not in out
    assert "open it:" not in out


# -- an all-gone room names no move, states no lie --------------------------


def test_a_dispatch_room_of_only_gone_not_spent_children_names_wait_to_restart_them(
        bare_workdir, capsys):
    """A dispatch step's lone child carries one dead-pid `dispatch-started`
    record and no return -- gone, not outstanding, but not yet spent
    either: its own count (1) has not reached `checkrun.MAX_STARTS`. `wait`
    will restart it (`_startable` reads true for a dead-and-not-spent record
    with no `is_returned`), so the room must say so even though
    `_wait_outstanding`'s own count -- live-pid records only -- still reads
    0, exactly the way a never-dispatched child's zero count still names
    `wait`. `configured` is what suppresses the row's own brief, so nothing
    beside it prints a stale, hand-typed respawn command that would collide
    with `wait`'s own restart."""
    _throwaway_dispatch(bare_workdir, bare_workdir / "spawned")
    _mint_dispatch_step(wid="d1", child="d1.g1")
    _record("d1", "d1.g1", _dead_pid())

    cli.main(["d1"])
    out = capsys.readouterr().out

    line = next(l for l in out.splitlines() if "outstanding" in l)
    assert "0 outstanding" in line
    assert "d1 wait is the move" in line
    assert "d1.g1 (gone without returning)" in out
    assert "open it:" not in out


def test_a_panel_room_of_only_gone_not_spent_panelists_names_wait_to_restart_them(
        bare_workdir, capsys):
    """The panel-step shape of the case above, with every remaining
    unresolved panelist gone-but-not-spent -- not paired with a live or
    never-dispatched one, since `test_a_panel_of_three_spawns_only_its_one_genuinely_outstanding_child`
    (`test_wait.py`) covers a room with exactly one genuinely outstanding
    child (count 1, not 0). Two panelists, each a single dead-pid record
    with no return: the room's count is 0 but `wait` is named on its line,
    since restarting either is exactly what `wait` will do next, and
    neither panelist's own row carries a brief."""
    _throwaway_dispatch(bare_workdir, bare_workdir / "spawned")
    wid = "g9"
    journal.append(wid, "run", title="t", assembly="run-a-gate")
    journal.append(wid, "step", id="review", segment="work",
                   panel=[{"worker": "reviewer", "criteria": "c1"},
                          {"worker": "critic", "criteria": "c2"}])
    _record(wid, f"{wid}.review.p1", _dead_pid(), tag="review.p1")
    _record(wid, f"{wid}.review.p2", _dead_pid(), tag="review.p2")

    cli.main([wid])
    out = capsys.readouterr().out

    line = next(l for l in out.splitlines() if "outstanding" in l)
    assert "0 outstanding" in line
    assert "g9 wait is the move" in line
    assert "panelist p1 (gone without returning)" in out
    assert "panelist p2 (gone without returning)" in out
    assert "open it:" not in out


def test_a_dispatch_room_of_only_gone_and_spent_children_names_the_drop_it_escape(
        bare_workdir, capsys):
    """A dispatch step's lone child has accumulated `checkrun.MAX_STARTS`
    dead-pid `dispatch-started` records with no return -- gone, and spent,
    so `wait` will not restart it either. Typing `wait` there would do
    nothing at all, so the line names the ruling escape instead of a bare
    count -- dropping the step is the one thing left for a reader to do
    about it -- and the row itself must say plainly that its starts are
    spent rather than offering any command."""
    _throwaway_dispatch(bare_workdir, bare_workdir / "spawned")
    _mint_dispatch_step(wid="d1", child="d1.g1")
    for _ in range(checkrun.MAX_STARTS):
        _record("d1", "d1.g1", _dead_pid())

    cli.main(["d1"])
    out = capsys.readouterr().out

    line = next(l for l in out.splitlines() if "amend close" in l)
    assert "drop it: " in line
    assert "amend close g1 --reason" in line
    assert "wait" not in line
    assert "d1.g1 (gone without returning -- starts spent)" in out
    assert "open it:" not in out


def test_a_panel_room_of_only_gone_and_spent_panelists_names_the_drop_it_escape(
        bare_workdir, capsys):
    """The panel-step shape of the case above: both panelists have each
    already accumulated `checkrun.MAX_STARTS` dead-pid records with no
    return -- gone and spent, on both, so the room's line names the ruling
    escape instead of naming `wait`, and every row states its own starts
    are spent instead of carrying a brief."""
    _throwaway_dispatch(bare_workdir, bare_workdir / "spawned")
    wid = "g9"
    journal.append(wid, "run", title="t", assembly="run-a-gate")
    journal.append(wid, "step", id="review", segment="work",
                   panel=[{"worker": "reviewer", "criteria": "c1"},
                          {"worker": "critic", "criteria": "c2"}])
    for _ in range(checkrun.MAX_STARTS):
        _record(wid, f"{wid}.review.p1", _dead_pid(), tag="review.p1")
        _record(wid, f"{wid}.review.p2", _dead_pid(), tag="review.p2")

    cli.main([wid])
    out = capsys.readouterr().out

    line = next(l for l in out.splitlines() if "amend close" in l)
    assert "drop it: " in line
    assert "amend close review --reason" in line
    assert "wait" not in line
    assert "panelist p1 (gone without returning -- starts spent)" in out
    assert "panelist p2 (gone without returning -- starts spent)" in out
    assert "open it:" not in out


def test_a_two_voices_panel_room_of_only_gone_and_spent_panelists_names_the_waive_it_escape(
        bare_workdir, capsys):
    """The shape run-a-gate's own review step mints -- a panel alongside its
    conductor's own route form (`_review_step`, test_verdict_panels.py) --
    rather than the panel-only shape the test above uses. `amend close`
    here would drop that form along with the panel it is escaping, so once
    every panelist is gone and spent the line names `amend waive` instead,
    never `amend close`."""
    _throwaway_dispatch(bare_workdir, bare_workdir / "spawned")
    wid = "g9"
    journal.append(wid, "run", title="t", assembly="run-a-gate")
    journal.append(wid, "step", id="review", segment="work", form="forms/ROUTE.toml",
                   panel=[{"worker": "reviewer", "criteria": "c1"},
                          {"worker": "critic", "criteria": "c2"}])
    for _ in range(checkrun.MAX_STARTS):
        _record(wid, f"{wid}.review.p1", _dead_pid(), tag="review.p1")
        _record(wid, f"{wid}.review.p2", _dead_pid(), tag="review.p2")

    cli.main([wid])
    out = capsys.readouterr().out

    line = next(l for l in out.splitlines() if "amend waive" in l)
    assert "waive it: " in line
    assert "amend waive review --reason" in line
    assert "wait" not in line
    assert "amend close" not in out
    assert "panelist p1 (gone without returning -- starts spent)" in out
    assert "panelist p2 (gone without returning -- starts spent)" in out


def test_a_two_voices_panel_room_with_a_startable_panelist_still_names_wait(
        bare_workdir, capsys):
    """A two-voices panel room is not always the spent case: a live-pid
    panelist is exactly what `wait`'s own poll loop is blocking on, so the
    line still names `wait`, never `amend waive` or `amend close` -- the
    escape only replaces the count once nothing remains live or
    startable."""
    _throwaway_dispatch(bare_workdir, bare_workdir / "spawned")
    wid = "g9"
    journal.append(wid, "run", title="t", assembly="run-a-gate")
    journal.append(wid, "step", id="review", segment="work", form="forms/ROUTE.toml",
                   panel=[{"worker": "reviewer", "criteria": "c1"}])
    _record(wid, f"{wid}.review.p1", os.getpid(), tag="review.p1")

    cli.main([wid])
    out = capsys.readouterr().out

    line = next(l for l in out.splitlines() if "outstanding" in l)
    assert "1 outstanding" in line
    assert "g9 wait is the move" in line
    assert "amend waive" not in out
    assert "amend close" not in out


def test_a_returned_panelist_never_makes_a_gone_and_spent_sibling_name_wait(
        bare_workdir, capsys):
    """A panel where p1 already returned -- a `return` entry, no
    `dispatch-started` record for it at all -- and p2 is gone-and-spent
    (`checkrun.MAX_STARTS` pre-seeded dead-pid records). `_startable` reads
    false for p1 on `is_returned` alone, before its (nonexistent) record or
    count are even inspected, and false for p2 on its own spent count -- so
    nothing in this room can make `name_wait` true. The line names the
    drop-it escape rather than `wait`.

    See: plan-aaefb/p3
    """
    _throwaway_dispatch(bare_workdir, bare_workdir / "spawned")
    wid = "g9"
    journal.append(wid, "run", title="t", assembly="run-a-gate")
    journal.append(wid, "step", id="review", segment="work",
                   panel=[{"worker": "reviewer", "criteria": "c1"},
                          {"worker": "critic", "criteria": "c2"}])
    journal.append(wid, "return", step="review", child=f"{wid}.review.p1",
                   fields={"verdict": "pass"})
    for _ in range(checkrun.MAX_STARTS):
        _record(wid, f"{wid}.review.p2", _dead_pid(), tag="review.p2")

    cli.main([wid])
    out = capsys.readouterr().out

    line = next(l for l in out.splitlines() if "amend close" in l)
    assert "drop it: " in line
    assert "wait" not in line


# -- a genuinely outstanding room names the count and wait ------------------


def test_a_dispatch_room_with_a_genuinely_outstanding_child_names_the_count_and_wait(
        bare_workdir, capsys):
    """The positive case the line exists for in the first place: a live-pid
    `dispatch-started` record with no return is exactly `_wait_outstanding`'s
    own definition of outstanding, so the count is 1 and naming `wait` is
    true -- typing it is what `wait`'s own poll loop is already blocking on
    for this child. `os.getpid()` stands in for a live pid: this test
    process is genuinely alive for as long as the assertion below runs,
    which is all `checkrun.alive`'s `os.kill(pid, 0)` needs to read it as
    outstanding rather than gone."""
    _throwaway_dispatch(bare_workdir, bare_workdir / "spawned")
    _mint_dispatch_step(wid="d1", child="d1.g1")
    _record("d1", "d1.g1", os.getpid())

    cli.main(["d1"])
    out = capsys.readouterr().out

    line = next(l for l in out.splitlines() if "outstanding" in l)
    assert "1 outstanding" in line
    assert "d1 wait is the move" in line
    assert "d1.g1 (working)" in out


def test_a_panel_room_with_a_genuinely_outstanding_panelist_names_the_count_and_wait(
        bare_workdir, capsys):
    """The panel-step half of the case above: one panelist carries a
    live-pid record and no return, so the room's count is 1 and its line
    names `wait` -- the same population `wait`'s own poll loop blocks on,
    read here through `_outstanding_state` rather than a second definition
    that could drift from it."""
    _throwaway_dispatch(bare_workdir, bare_workdir / "spawned")
    _mint_panel_step(wid="g9", worker="reviewer")
    _record("g9", "g9.review.p1", os.getpid(), tag="review.p1")

    cli.main(["g9"])
    out = capsys.readouterr().out

    line = next(l for l in out.splitlines() if "outstanding" in l)
    assert "1 outstanding" in line
    assert "g9 wait is the move" in line
    assert "panelist p1 (working)" in out


# -- a never-dispatched child still names wait at zero count -----------------


def test_a_never_dispatched_dispatch_childs_room_still_names_wait_at_zero_count(
        bare_workdir, capsys):
    """The zero count that is not the all-gone case: this room's only child
    carries no `dispatch-started` record at all, so `_wait_outstanding`'s own
    count reads 0 -- the same number
    `test_a_dispatch_room_of_only_gone_children_reports_zero_outstanding_and_names_no_wait`
    above reads for a room where every unresolved child is gone. The two
    must not read the same on the line itself: `wait`'s own pre-loop spawn
    (`_wait_spawn`) is exactly what starts a never-dispatched child, so this
    line has to name `wait` even at count 0, while that other room's line,
    at the identical count, must not. Both halves (this test's positive and
    that test's negative) are asserted so a reader can see the count alone
    never decides this -- `name_wait` is a second, independent read."""
    _throwaway_dispatch(bare_workdir, bare_workdir / "spawned")
    _mint_dispatch_step(wid="d1", child="d1.g1")

    cli.main(["d1"])
    out = capsys.readouterr().out

    line = next(l for l in out.splitlines() if "outstanding" in l)
    assert "0 outstanding" in line
    assert "d1 wait is the move" in line


# -- the outstanding line is never withheld --------------------------------


def test_an_unconfigured_dispatch_rooms_line_is_present_too(workdir, capsys):
    """`workdir`'s own `constellation.toml` carries a harmless `dispatch`
    entry (`_with_a_harmless_dispatch_entry`, conftest.py), and the
    outstanding line is never withheld: `spine <work-id> wait` starts this
    child whether or not the palette can actually act on it, and the line
    says so."""
    _mint_dispatch_step(wid="d1", child="d1.g1")

    cli.main(["d1"])
    out = capsys.readouterr().out

    assert "d1.g1 (not dispatched)" in out
    line = next(l for l in out.splitlines() if "outstanding" in l)
    assert "0 outstanding" in line
    assert "d1 wait is the move" in line


def test_an_unconfigured_panel_rooms_line_is_present_too(workdir, capsys):
    """The panel-step half of the case above."""
    _mint_panel_step(wid="g9", worker="reviewer")

    cli.main(["g9"])
    out = capsys.readouterr().out

    assert "panelist p1 (not dispatched)" in out
    line = next(l for l in out.splitlines() if "outstanding" in l)
    assert "0 outstanding" in line
    assert "g9 wait is the move" in line


# -- a childless form step has nothing to be outstanding ---------------------


def test_a_childless_form_steps_room_has_no_outstanding_line(bare_workdir, capsys):
    """`_gate()` opens a real run-a-gate standing on its own first step
    ("work-1"), a plain form step -- no panel, no dispatches. Nothing
    can be called outstanding there by the process-only definition, so the
    line must not appear at all: one that is always present carries no
    information."""
    wid = _gate()
    capsys.readouterr()

    cli.main([wid])
    out = capsys.readouterr().out

    assert "outstanding" not in out


# -- the in-flight line is unconditional, in both worlds ----------------------


@pytest.mark.parametrize("fixture_name", ["workdir", "bare_workdir"])
def test_a_live_in_flight_proof_reports_one_outstanding_in_both_worlds(
        fixture_name, request, capsys, monkeypatch):
    """A step's proof is spawned through the check-runner/`HANDBACK`
    mechanism, a path with nothing to do with whether `commands.dispatch` is
    configured, so this line renders with no `_dispatch_configured` gate at
    all. `_gate()` itself always leaves `constellation.toml` unconfigured --
    `[models]` only, no `dispatch` entry -- so parametrizing the fixture
    alone would exercise the same unconfigured world twice and never catch a
    change that wrongly gated this line. The `bare_workdir` run installs a
    real, test-local `dispatch` entry (`_throwaway_dispatch`, same helper
    `test_wait.py`'s own configured-world tests use) after `_gate()`
    returns, so the two parametrized runs are genuinely different
    repositories -- one configured, one not -- and the assertion below on
    `_dispatch_configured` itself proves that difference rather than
    assuming it.

    `wait` blocks on a live proof exactly as it does on a live child
    (`[in-flight-room]` above `_in_flight_status`, `engine/cli.py`), so the
    running half of this line names it as the move the same way a
    dispatch or panel room's own outstanding line does -- unconditionally,
    in both worlds, since a proof's pid has nothing to do with whether
    `commands.dispatch` is configured either."""
    root = request.getfixturevalue(fixture_name)
    monkeypatch.setattr(checkrun, "HANDBACK", 1)
    wid = _gate()
    if fixture_name == "bare_workdir":
        _throwaway_dispatch(root, root / "spawned")
    assert cli._dispatch_configured(root) == (fixture_name == "bare_workdir")
    journal.append(wid, "prefill", fields={"proof": "sleep 30"})
    _response(wid).write_text(
        'change = "c"\ndeviations = "waived: none"\n')
    cli.main([wid, "submit"])
    capsys.readouterr()

    cli.main([wid])
    out = capsys.readouterr().out

    line = next(l for l in out.splitlines() if "outstanding" in l)
    assert "1 outstanding" in line
    assert "wait is the move" in line


@pytest.mark.parametrize("fixture_name", ["workdir", "bare_workdir"])
def test_a_dead_in_flight_proof_reports_zero_outstanding_in_both_worlds(
        fixture_name, request, capsys):
    """The dead-pid half of the case above: `checkrun.alive` reads a really-
    gone pid (`_dead_pid`, run to completion rather than merely abandoned) as
    dead, so the count drops to zero -- still with no `wait` named, because
    a dead process has nothing left to poll and naming `wait` here would
    promise a block that never happens. Unlike the live case above, `wait`
    renders this half of the room immediately rather than blocking on
    it -- `[in-flight-room]` above `_in_flight_status` says why. Made
    genuinely configured under `bare_workdir` and genuinely
    unconfigured under `workdir`, the same way the live case above is, and
    for the same reason: this line's presence must not be an accident of one
    particular `constellation.toml`, and the pair must actually prove that
    rather than reading the identical unconfigured file twice."""
    root = request.getfixturevalue(fixture_name)
    wid = _gate()
    if fixture_name == "bare_workdir":
        _throwaway_dispatch(root, root / "spawned")
    assert cli._dispatch_configured(root) == (fixture_name == "bare_workdir")
    journal.append(wid, "check-started", step="work-1", pid=_dead_pid(),
                   cwd=".", budget=600, log="check.work-1.log",
                   commands=[{"field": "proof", "command": "true"}])

    cli.main([wid])
    out = capsys.readouterr().out

    line = next(l for l in out.splitlines() if "outstanding" in l)
    assert "0 outstanding" in line
    assert "wait" not in line


# -- the in-flight room says plainly that nothing notifies you ---------------


def test_a_proof_in_flight_no_longer_carries_the_cadence_paragraph(
        bare_workdir, capsys, monkeypatch):
    """The room does not say "see where it landed: spine <wid>": headless
    gate-conductors read that as a destination rather than an act,
    concluded a notification was coming, and stopped acting; nothing was
    going to arrive. A hand-spelled cadence paragraph ("nothing notifies
    you... run this room's own command again... every minute or two") is
    not the answer either: `wait` blocks on exactly this case
    (`tests/test_wait.py`'s own
    `test_a_proof_in_flight_holds_until_it_lands_then_renders_the_next_step`
    proves the loop itself), so the cadence lives in the engine's own poll
    loop, and the outstanding line names `wait` as the move rather than
    staying silent about it (`[in-flight-room]` above `_in_flight_status`
    carries the full account)."""
    monkeypatch.setattr(checkrun, "HANDBACK", 1)
    wid = _gate()
    journal.append(wid, "prefill", fields={"proof": "sleep 30"})
    _response(wid).write_text(
        'change = "c"\ndeviations = "waived: none"\n')
    cli.main([wid, "submit"])
    capsys.readouterr()

    cli.main([wid])
    out = capsys.readouterr().out

    assert "in flight" in out
    lowered = out.lower()
    assert "nothing notifies you" not in lowered
    assert "no message arrives" not in lowered
    assert "does not change on its own" not in lowered
    assert "every minute or two" not in lowered
    assert "see where it landed" not in lowered
    line = next(l for l in out.splitlines() if "outstanding" in l)
    assert "wait is the move" in line


# -- cmd_submit's and cmd_close's refusals reuse the read ----------------------


def test_cmd_submits_dispatch_refusal_names_wait_when_the_child_is_startable(
        bare_workdir, capsys):
    """A configured repository whose dispatch step's child has never been
    started: `wait` would start it, so `cmd_submit`'s refusal names `wait`
    instead of a hand-typed `open its child: spine open ...` command a
    conductor must not type."""
    _throwaway_dispatch(bare_workdir, bare_workdir / "spawned")
    _mint_dispatch_step(wid="d1", child="d1.g1")

    with pytest.raises(SystemExit) as e:
        cli.main(["d1", "submit"])
    msg = str(e.value)

    assert "d1 wait" in msg
    assert "open its child" not in msg


def test_cmd_submits_dispatch_refusal_names_the_drop_it_escape_when_spent(
        bare_workdir, capsys):
    """The same step, but its child is gone and spent: `wait` would restart
    nothing, so the refusal names the ruling escape -- dropping the step --
    rather than a command that would do nothing."""
    _throwaway_dispatch(bare_workdir, bare_workdir / "spawned")
    _mint_dispatch_step(wid="d1", child="d1.g1")
    for _ in range(checkrun.MAX_STARTS):
        _record("d1", "d1.g1", _dead_pid())

    with pytest.raises(SystemExit) as e:
        cli.main(["d1", "submit"])
    msg = str(e.value)

    assert "drop it: " in msg
    assert "amend close g1 --reason" in msg
    assert "wait" not in msg
    assert "open its child" not in msg


def test_cmd_submits_dispatch_refusal_names_wait_even_when_unconfigured(
        workdir, capsys):
    """`workdir`'s own `constellation.toml` carries a harmless `dispatch`
    entry (`_with_a_harmless_dispatch_entry`, conftest.py); the refusal names
    `wait`, the same as a configured repository's does, not a hand-typed
    `open its child: ...` command."""
    _mint_dispatch_step(wid="d1", child="d1.g1")

    with pytest.raises(SystemExit) as e:
        cli.main(["d1", "submit"])
    msg = str(e.value)

    assert "d1 wait" in msg
    assert "open its child" not in msg


def test_cmd_submits_panel_refusal_names_wait_when_a_panelist_is_startable(
        bare_workdir, capsys):
    """The panel-step half: `wait` genuinely answers "who is outstanding"
    when a panelist has never been started, so the refusal names it."""
    _throwaway_dispatch(bare_workdir, bare_workdir / "spawned")
    _mint_panel_step(wid="g9", worker="reviewer")

    with pytest.raises(SystemExit) as e:
        cli.main(["g9", "submit"])
    msg = str(e.value)

    assert "g9 wait" in msg


def test_cmd_submits_panel_refusal_stays_who_is_outstanding_when_all_spent(
        bare_workdir, capsys):
    """No per-panelist drop mechanism exists, so a panel step's refusal
    keeps naming "who is outstanding" even once every remaining panelist is
    spent -- that is still true advice, and this branch does not invent a
    drop-it escape it has no story for."""
    _throwaway_dispatch(bare_workdir, bare_workdir / "spawned")
    wid = "g9"
    journal.append(wid, "run", title="t", assembly="run-a-gate")
    journal.append(wid, "step", id="review", segment="work",
                   panel=[{"worker": "reviewer", "criteria": "c1"}])
    for _ in range(checkrun.MAX_STARTS):
        _record(wid, f"{wid}.review.p1", _dead_pid(), tag="review.p1")

    with pytest.raises(SystemExit) as e:
        cli.main(["g9", "submit"])
    msg = str(e.value)

    assert "who is outstanding" in msg
    assert "wait" not in msg


def test_cmd_submits_panel_refusal_names_wait_even_when_unconfigured(
        workdir, capsys):
    """The panel-step half: an unconfigured repository's never-dispatched
    panelist is still startable by `wait`, so the refusal names it, the
    same as a configured repository's does."""
    _mint_panel_step(wid="g9", worker="reviewer")

    with pytest.raises(SystemExit) as e:
        cli.main(["g9", "submit"])
    msg = str(e.value)

    assert "g9 wait" in msg


def test_cmd_closes_dispatch_refusal_names_wait_when_the_child_is_startable(
        bare_workdir, capsys):
    """`cmd_close`'s "not complete" refusal gets the identical treatment as
    `cmd_submit`'s dispatch site above."""
    _throwaway_dispatch(bare_workdir, bare_workdir / "spawned")
    _mint_dispatch_step(wid="d1", child="d1.g1")

    with pytest.raises(SystemExit) as e:
        cli.main(["d1", "close"])
    msg = str(e.value)

    assert "d1 wait" in msg
    assert "open its child" not in msg


def test_cmd_closes_refusal_names_the_drop_it_escape_exactly_once_when_spent(
        bare_workdir, capsys):
    """The dispatch branch's own `how` is the identical drop-it string
    the function's generic suffix appends -- asserted to appear exactly
    once, not twice, since an unguarded concatenation would print the same
    command twice in one refusal."""
    _throwaway_dispatch(bare_workdir, bare_workdir / "spawned")
    _mint_dispatch_step(wid="d1", child="d1.g1")
    for _ in range(checkrun.MAX_STARTS):
        _record("d1", "d1.g1", _dead_pid())

    with pytest.raises(SystemExit) as e:
        cli.main(["d1", "close"])
    msg = str(e.value)

    assert msg.count("amend close g1 --reason") == 1
    assert "wait" not in msg


def test_cmd_closes_dispatch_refusal_names_wait_even_when_unconfigured(
        workdir, capsys):
    """The dispatch-branch half: `wait` is named even where the palette
    cannot yet act on it, not a hand-typed `open its child: ...` escape."""
    _mint_dispatch_step(wid="d1", child="d1.g1")

    with pytest.raises(SystemExit) as e:
        cli.main(["d1", "close"])
    msg = str(e.value)

    assert "d1 wait" in msg
    assert "open its child" not in msg


def test_cmd_closes_panel_refusal_names_wait_when_a_panelist_is_startable(
        bare_workdir, capsys):
    """The panel-branch half of `cmd_close`'s treatment."""
    _throwaway_dispatch(bare_workdir, bare_workdir / "spawned")
    _mint_panel_step(wid="g9", worker="reviewer")

    with pytest.raises(SystemExit) as e:
        cli.main(["g9", "close"])
    msg = str(e.value)

    assert "g9 wait" in msg


def test_cmd_closes_panel_refusal_stays_its_panelists_complete_it_when_all_spent(
        bare_workdir, capsys):
    """Like `cmd_submit`'s panel site, no per-panelist drop mechanism
    exists, so this branch keeps its text once every panelist is spent,
    naming no `wait` that would do nothing."""
    _throwaway_dispatch(bare_workdir, bare_workdir / "spawned")
    wid = "g9"
    journal.append(wid, "run", title="t", assembly="run-a-gate")
    journal.append(wid, "step", id="review", segment="work",
                   panel=[{"worker": "reviewer", "criteria": "c1"}])
    for _ in range(checkrun.MAX_STARTS):
        _record(wid, f"{wid}.review.p1", _dead_pid(), tag="review.p1")

    with pytest.raises(SystemExit) as e:
        cli.main(["g9", "close"])
    msg = str(e.value)

    assert "its panelists complete it" in msg
    assert "wait" not in msg


def test_cmd_closes_panel_refusal_names_wait_even_when_unconfigured(
        workdir, capsys):
    """The panel-branch half: an unconfigured repository's never-dispatched
    panelist is still startable, so `wait` is named here too."""
    _mint_panel_step(wid="g9", worker="reviewer")

    with pytest.raises(SystemExit) as e:
        cli.main(["g9", "close"])
    msg = str(e.value)

    assert "g9 wait" in msg
