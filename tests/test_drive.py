"""`spine <work-id> drive [--for N]`: walk a run through every step shape the
engine can resolve on its own, pass after pass, with no human retyping the
next command between steps.

Built the same way `tests/test_wait.py` is, over a real, test-configured
`dispatch` entry rather than a hand-written stand-in for one -- `cmd_drive`
calls `cmd_wait`'s own spawn/poll/render mechanism unchanged for the spawn
and the poll, so a test that never actually spawns anything would prove
nothing about the call, only about the three-case check standing after it.

Three things this file exists to prove that a shallower suite would miss:
the corrected three-case rule -- `returns_by_child` tells "resolved" apart
from "spent" where `_outstanding_state`'s own `(count, name_wait)` pair
alone cannot, since both read `(0, False)` -- proven directly against a
resolved step, a spent gate-dispatch step, and a mixed panel step naming the
spent panelist rather than misreading the step as resolved; that `drive`
actually walks past a resolved step to whatever is current next, not merely
that it never crashes; and the segment-order refusal that keeps `drive` from
ever reaching the understand segment's own transition panel -- indistinguishable
in shape from the plan segment's own -- before the run has reached `plan` at all.

Every process this file spawns is a short-lived `python3 -c ...` of its own
choosing, never `claude`.
"""

import pathlib
import threading
import time

import pytest

from engine import checks as checkrun
from engine import cli, journal
from engine import run as runmod
from test_brief import _mint_dispatch_step
from test_wait import (
    _await, _dead_pid, _dispatch_entries, _record, _sleeper, _throwaway_dispatch,
)


# -- refuse, and render immediately: the three before-any-walking guards ----


def test_an_unknown_work_id_refuses(bare_workdir):
    with pytest.raises(SystemExit) as e:
        cli.main(["nope", "drive"])
    assert "no run named nope" in str(e.value)


def test_a_closed_run_renders_immediately(bare_workdir, capsys):
    journal.append("g1", "run", title="t", assembly="run-a-gate")
    journal.append("g1", "closed")

    began = time.monotonic()
    code = cli.main(["g1", "drive"])
    elapsed = time.monotonic() - began

    assert code == 0
    assert elapsed < 1


def test_an_awaiting_close_run_renders_immediately(bare_workdir, capsys):
    journal.append("g1", "run", title="t", assembly="run-a-gate")
    journal.append("g1", "step", id="s1", segment="work", form="x.toml",
                   filler="f", anchor=False, terminal=False, validates="")
    journal.append("g1", "submit", step="s1", fields={})
    assert runmod.state("g1")["awaiting_close"]

    began = time.monotonic()
    code = cli.main(["g1", "drive"])
    elapsed = time.monotonic() - began

    assert code == 0
    assert elapsed < 1


def test_a_palette_with_no_dispatch_entry_refuses_immediately(bare_workdir, capsys):
    """Unlike `wait`, which still renders when the palette carries no
    `dispatch` entry (there is simply nothing outstanding for it to see),
    `drive` refuses outright: without a real spawn mechanism it could only
    ever spin to its own bound doing nothing."""
    _mint_dispatch_step(wid="d1", child="d1.g1")

    began = time.monotonic()
    with pytest.raises(SystemExit) as e:
        cli.main(["d1", "drive"])
    elapsed = time.monotonic() - began

    assert elapsed < 1
    assert "dispatch" in str(e.value)
    assert _dispatch_entries("d1") == []


def test_a_malformed_for_value_refuses(bare_workdir):
    _mint_dispatch_step(wid="d1", child="d1.g1")

    with pytest.raises(SystemExit) as e:
        cli.main(["d1", "drive", "--for", "soon"])
    assert "not a number of seconds" in str(e.value)

    with pytest.raises(SystemExit) as e:
        cli.main(["d1", "drive", "--for", "0"])
    assert "not a number of seconds" in str(e.value)


# -- the fourth guard: refused once the current step is in hand -------------


def test_a_run_before_the_plan_segment_refuses_without_walking(bare_workdir, capsys):
    """A run parked on the understand segment's own transition panel -- a
    `panel_outstanding` step in every way indistinguishable in shape from
    the plan segment's own -- must never reach `cmd_wait`'s mechanism at
    all. The palette carries a real `dispatch` entry here specifically so a
    wrongly-permissive `drive` would have something to spawn against;
    nothing is."""
    marker = bare_workdir / "spawned"
    _throwaway_dispatch(bare_workdir, marker)
    wid = "d1"
    journal.append(wid, "run", title="t", assembly="run-an-issue")
    journal.append(wid, "step", id="u1", segment="understand",
                   panel=[{"worker": "critic", "criteria": "c"}])

    began = time.monotonic()
    with pytest.raises(SystemExit) as e:
        cli.main([wid, "drive"])
    elapsed = time.monotonic() - began

    assert elapsed < 1
    assert "understand" in str(e.value)
    assert "drive starts at the plan segment" in str(e.value)
    assert _dispatch_entries(wid) == []
    assert not marker.exists()


# -- paused: stop immediately, needing no new mechanism ----------------------


def test_a_paused_run_renders_immediately(bare_workdir, capsys):
    marker = bare_workdir / "spawned"
    _throwaway_dispatch(bare_workdir, marker)
    journal.append("g1", "run", title="t", assembly="run-a-gate", parent="")
    journal.append("g1", "step", id="_pause1", segment="work", paused="work")

    began = time.monotonic()
    code = cli.main(["g1", "drive"])
    elapsed = time.monotonic() - began
    out = capsys.readouterr().out

    assert code == 0
    assert elapsed < 1
    assert "paused" in out
    assert not marker.exists()


# -- the corrected three-case rule, exercised directly -----------------------


def test_a_gate_dispatch_step_already_alive_resolves_and_drive_advances_past_it(
        bare_workdir, capsys, monkeypatch):
    """Case 1: a child already dispatched and alive when `drive` starts,
    whose return lands mid-call -- `cmd_wait`'s own poll is what notices it,
    and the post-`wait` re-read must credit it as resolved, not spent (both
    read `(0, False)` from `_outstanding_state` alone). `d1.g1` is this
    run's only step, so a genuine advance lands the run on `awaiting_close`,
    not merely on some other pending step."""
    monkeypatch.setattr(checkrun, "WAIT_POLL", 0.05)
    marker = bare_workdir / "spawned"
    _throwaway_dispatch(bare_workdir, marker)
    _mint_dispatch_step(wid="d1", child="d1.g1")
    proc = _sleeper(5)
    _record("d1", "d1.g1", proc.pid)

    def _land_it():
        time.sleep(0.2)
        journal.append("d1", "return", step="g1", child="d1.g1", fields={"result": "ok"})
    threading.Thread(target=_land_it, daemon=True).start()

    began = time.monotonic()
    code = cli.main(["d1", "drive", "--for", "5"])
    elapsed = time.monotonic() - began
    capsys.readouterr()

    assert code == 0
    assert 0.15 < elapsed < 3, f"elapsed {elapsed}"
    assert "d1.g1" in runmod.state("d1")["returns_by_child"]
    assert runmod.state("d1")["awaiting_close"]
    proc.kill()
    proc.wait()


def test_a_gate_dispatch_step_never_dispatched_gets_spawned_and_resolves(
        bare_workdir, capsys, monkeypatch):
    """Case 3 into case 1: a child never dispatched at all is startable, so
    `drive`'s own call into `cmd_wait` is what starts it -- proven against a
    real, journaled `dispatch-started` record, not merely inferred from the
    run reaching `awaiting_close`."""
    monkeypatch.setattr(checkrun, "WAIT_POLL", 0.05)
    marker = bare_workdir / "spawned"
    _throwaway_dispatch(bare_workdir, marker)
    _mint_dispatch_step(wid="d1", child="d1.g1")
    assert _dispatch_entries("d1") == []

    def _land_it():
        time.sleep(0.2)
        journal.append("d1", "return", step="g1", child="d1.g1", fields={"result": "ok"})
    threading.Thread(target=_land_it, daemon=True).start()

    began = time.monotonic()
    code = cli.main(["d1", "drive", "--for", "5"])
    elapsed = time.monotonic() - began
    capsys.readouterr()

    assert code == 0
    assert 0.15 < elapsed < 3, f"elapsed {elapsed}"
    assert _await(marker, 1)
    started = _dispatch_entries("d1")
    assert len(started) == 1 and started[0]["child"] == "d1.g1"
    assert runmod.state("d1")["awaiting_close"]


def test_a_gate_dispatch_step_dead_past_max_starts_stops_and_names_it(
        bare_workdir, capsys):
    """Case 2: a child dead past `checkrun.MAX_STARTS` reads the identical
    `(0, False)` an already-resolved child would -- only `returns_by_child`
    (empty here) tells them apart. `drive` must stop, not misread this as
    resolved and spin looking for a step that will never advance."""
    marker = bare_workdir / "spawned"
    _throwaway_dispatch(bare_workdir, marker)
    _mint_dispatch_step(wid="d1", child="d1.g1")
    for _ in range(checkrun.MAX_STARTS):
        _record("d1", "d1.g1", _dead_pid())
    assert len(_dispatch_entries("d1")) == checkrun.MAX_STARTS

    began = time.monotonic()
    code = cli.main(["d1", "drive"])
    elapsed = time.monotonic() - began
    out = capsys.readouterr().out

    assert code == 0
    assert elapsed < 1
    assert len(_dispatch_entries("d1")) == checkrun.MAX_STARTS
    assert not marker.exists()
    assert "d1.g1 (gone without returning -- starts spent)" in out


def test_a_panel_step_with_one_returned_and_one_spent_stops_and_names_the_spent_one(
        bare_workdir, capsys):
    """The panel-shaped version of the same case-2 guard, minus
    `test_wait.py`'s own third, genuinely-outstanding panelist: with p1
    returned and p2 dead-and-spent, no panelist is left outstanding, and
    `_outstanding_state` alone cannot tell this apart from "every panelist
    resolved" -- `all(cid in returns_by_child ...)` reading false for p2 is
    what does. `drive` must stop and name p2, not misread the step as
    fully resolved."""
    marker = bare_workdir / "spawned"
    _throwaway_dispatch(bare_workdir, marker)
    wid = "g9"
    journal.append(wid, "run", title="t", assembly="run-a-gate")
    journal.append(wid, "step", id="review", segment="work",
                   panel=[{"worker": "reviewer", "criteria": "c"},
                          {"worker": "critic", "criteria": "c"}])
    journal.append(wid, "return", step="review", child=f"{wid}.review.p1",
                   fields={"verdict": "pass"})
    pre_existing_log = journal.location(wid) / "dispatch.review.p2.log"
    pre_existing_log.parent.mkdir(parents=True, exist_ok=True)
    pre_existing_log.write_text("already running\n")
    for _ in range(checkrun.MAX_STARTS):
        journal.append(wid, "dispatch-started", child=f"{wid}.review.p2",
                       pid=999999, tree=str(bare_workdir), log=str(pre_existing_log))

    began = time.monotonic()
    code = cli.main([wid, "drive"])
    elapsed = time.monotonic() - began
    out = capsys.readouterr().out

    assert code == 0
    assert elapsed < 1
    assert "panelist p1 (returned)" in out
    assert "panelist p2 (gone without returning -- starts spent)" in out
    assert not marker.exists()


# -- drive's own bound --------------------------------------------------------


def test_for_overrides_the_default_bound(bare_workdir, monkeypatch):
    monkeypatch.setattr(checkrun, "WAIT_POLL", 0.05)
    monkeypatch.setattr(checkrun, "WAIT_BOUND", 0.2)   # keep the nested `wait` call short
    monkeypatch.setattr(checkrun, "DRIVE_BOUND", 90)   # confirm --for wins over this
    marker = bare_workdir / "spawned"
    _throwaway_dispatch(bare_workdir, marker)
    _mint_dispatch_step(wid="d1", child="d1.g1")
    proc = _sleeper(5)
    _record("d1", "d1.g1", proc.pid)

    began = time.monotonic()
    code = cli.main(["d1", "drive", "--for", "1"])
    elapsed = time.monotonic() - began

    assert code == 0
    assert 0.9 < elapsed < 4, f"elapsed {elapsed}"
    assert checkrun.alive(proc.pid)          # the bound expired, the child did not
    proc.kill()
    proc.wait()


def test_the_bounds_own_expiry_exits_0_with_a_child_still_outstanding(
        bare_workdir, monkeypatch):
    monkeypatch.setattr(checkrun, "WAIT_POLL", 0.05)
    monkeypatch.setattr(checkrun, "WAIT_BOUND", 0.1)
    monkeypatch.setattr(checkrun, "DRIVE_BOUND", 0.3)
    marker = bare_workdir / "spawned"
    _throwaway_dispatch(bare_workdir, marker)
    _mint_dispatch_step(wid="d1", child="d1.g1")
    proc = _sleeper(5)
    _record("d1", "d1.g1", proc.pid)

    began = time.monotonic()
    code = cli.main(["d1", "drive"])
    elapsed = time.monotonic() - began

    assert code == 0
    assert elapsed < 2, f"elapsed {elapsed}"
    assert checkrun.alive(proc.pid)
    proc.kill()
    proc.wait()
