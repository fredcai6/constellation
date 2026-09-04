"""`spine <work-id> wait`: block while the current step has an outstanding
child, then print exactly what `status` would have -- it renders no view of
its own.

Two things this file exists to prove that a shallower suite would miss
(the last round's own critique): the mechanism actually blocks and unblocks
-- not merely that it never blocks on the rooms that were never in scope --
and the boundary this gate deliberately does not cross: `wait` never starts
a child a render would have. `_dispatch_child`/`_spawn_outstanding` are
never called from `cmd_wait`, so every scenario here that mints a
`dispatch-started` record does so directly, by hand, exactly the way
`test_dispatch_wiring.py`'s own "gone without returning" fixtures already
do.

Every process this file spawns is a short-lived `python3 -c ...` of its own
choosing, never `claude`.
"""

import pathlib
import subprocess
import sys
import threading
import time

import pytest

from engine import checks as checkrun
from engine import cli, journal
from engine import run as runmod
from test_brief import _mint_dispatch_step, _mint_panel_step
from test_dispatch_wiring import _throwaway_dispatch, _dispatch_entries, _await
from test_explore import explore, _spine


def _sleeper(seconds):
    """A real, short-lived child process -- genuinely alive until it exits
    on its own, never merely un-reaped."""
    return subprocess.Popen([sys.executable, "-c", f"import time; time.sleep({seconds})"])


def _dead_pid():
    """A pid that is really gone -- run to completion, not merely started
    and abandoned."""
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


def _record(wid, child, pid, tag="g1"):
    log = journal.location(wid) / f"dispatch.{tag}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    journal.append(wid, "dispatch-started", child=child, pid=pid,
                   tree=".", log=str(log))


def _gate(wid="g1"):
    """A real `run-a-gate` open, standing on its own first step ("work-1"),
    a plain form step -- no panel, no dispatches. `test_slow_proofs.py`'s
    own shape, reused here for the in-flight-proof and childless-form
    scenarios."""
    pathlib.Path("constellation.toml").write_text('[models]\nstandard = "x"\n')
    cli.main(["open", "run-a-gate", "--id", wid])
    return wid


@pytest.fixture(autouse=True)
def _fast_poll_would_show(monkeypatch):
    """Every render-immediately scenario below sets `WAIT_POLL` to a value
    long enough that a single accidental sleep would blow the test's own
    elapsed-time assertion -- so "it never polled" is proven, not assumed."""
    monkeypatch.setattr(checkrun, "WAIT_POLL", 5)


# -- refuse, and render immediately: cmd_status's own branch order -----------


def test_an_unknown_work_id_refuses(bare_workdir):
    with pytest.raises(SystemExit) as e:
        cli.main(["nope", "wait"])
    assert "no run named nope" in str(e.value)


def test_a_closed_run_renders_immediately(bare_workdir, capsys):
    journal.append("g1", "run", title="t", assembly="run-a-gate")
    journal.append("g1", "closed")

    began = time.monotonic()
    code = cli.main(["g1", "wait"])
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
    code = cli.main(["g1", "wait"])
    elapsed = time.monotonic() - began

    assert code == 0
    assert elapsed < 1


def test_a_paused_run_renders_immediately(bare_workdir, capsys):
    journal.append("g1", "run", title="t", assembly="run-a-gate", parent="")
    journal.append("g1", "step", id="_pause1", segment="work", paused="work")

    began = time.monotonic()
    code = cli.main(["g1", "wait"])
    elapsed = time.monotonic() - began
    out = capsys.readouterr().out

    assert code == 0
    assert elapsed < 1
    assert "paused" in out


def test_a_proof_in_flight_renders_immediately(bare_workdir, capsys, monkeypatch):
    monkeypatch.setattr(checkrun, "HANDBACK", 1)
    wid = _gate()
    journal.append(wid, "prefill", fields={"proof": "sleep 30"})
    pathlib.Path(f".agent-work/{wid}/IMPLEMENT.toml").write_text(
        'change = "c"\ndeviations = "waived: none"\n')
    cli.main([wid, "submit"])
    capsys.readouterr()
    st = runmod.state(wid)
    assert runmod.in_flight(st, st["current"])

    began = time.monotonic()
    code = cli.main([wid, "wait"])
    elapsed = time.monotonic() - began
    out = capsys.readouterr().out

    assert code == 0
    assert elapsed < 1
    assert "in flight" in out


def test_a_childless_form_step_renders_immediately(bare_workdir, capsys):
    wid = _gate()
    capsys.readouterr()

    began = time.monotonic()
    code = cli.main([wid, "wait"])
    elapsed = time.monotonic() - began
    out = capsys.readouterr().out

    assert code == 0
    assert elapsed < 1
    assert "run-a-gate \u00b7 work (1 of 3)" in out
    assert "Make the change the gate spec above describes" in out
    assert "your response form: .agent-work/g1/IMPLEMENT.toml" in out


def test_a_palette_with_no_dispatch_entry_renders_immediately(bare_workdir, capsys):
    """`bare_workdir` seeds no `constellation.toml` at all -- the room
    still renders, and nothing is ever outstanding for `wait` to see."""
    _mint_dispatch_step(wid="d1", child="d1.g1")

    began = time.monotonic()
    code = cli.main(["d1", "wait"])
    elapsed = time.monotonic() - began

    assert code == 0
    assert elapsed < 1
    assert _dispatch_entries("d1") == []


# -- commitment 5: an excursion never reaches wait's predicate ---------------


def test_wait_never_polls_an_excursions_board_row(explore):
    """The board's own `i1` row now carries a live, un-returned excursion --
    `wait`'s branch order never looks at a board at all, so this renders
    exactly as the childless-form case above does."""
    _spine("open", "find-prior-art", "--parent", explore, "--row", "i1")

    began = time.monotonic()
    out, code = _spine(explore, "wait")
    elapsed = time.monotonic() - began

    assert code == 0
    assert elapsed < 1


# -- gate 1's own boundary: a never-dispatched child is not outstanding -----


def test_wait_starts_nothing_of_its_own_for_a_never_dispatched_dispatch_child(
        bare_workdir, capsys):
    """`wait`'s own block loop starts nothing and blocks on nothing when no
    `dispatch-started` record exists: zero records reads as nothing
    outstanding on the very first pass, so `wait` returns without a single
    poll cycle (`WAIT_POLL` is 5s here, so one accidental sleep would show).

    What the trailing render then starts is `status`'s doing, not `wait`'s,
    and that is deliberate. Commitment 2 makes `wait` `status` with a block
    in front of it -- it renders no view of its own -- so `cmd_wait` ends on
    `cmd_status([wid])`, and this gate's scope says verbatim that
    "rendering still spawns exactly as it does today (`_dispatch_child`
    still calls `_spawn_outstanding`)". Suppressing that spawn would mean
    editing `cmd_status`/`_dispatch_child`, which this gate's scope forbids,
    and would make `wait`'s output differ from `status`'s for the identical
    state -- breaking commitment 2 outright. Gate 2's commitments 13-15 are
    where the spawn moves. So what is asserted here is what is both true and
    in scope: `wait` starts exactly what `status` starts and no more.
    """
    marker = bare_workdir / "spawned"
    _throwaway_dispatch(bare_workdir, marker)
    _mint_dispatch_step(wid="d1", child="d1.g1")

    began = time.monotonic()
    code = cli.main(["d1", "wait"])
    elapsed = time.monotonic() - began
    capsys.readouterr()

    assert code == 0
    assert elapsed < 1                      # `wait`'s own loop never ran a cycle
    started = _dispatch_entries("d1")
    assert len(started) == 1 and started[0]["child"] == "d1.g1"
    assert _await(marker, 1)

    cli.main(["d1"])                        # plain `status`, same state: nothing more
    capsys.readouterr()
    assert len(_dispatch_entries("d1")) == 1
    assert len(list(marker.iterdir())) == 1


def test_wait_starts_nothing_of_its_own_for_a_never_dispatched_panelist(
        bare_workdir, capsys):
    """The panel-step half of the case above, on the branch
    `runmod.panel_outstanding` selects: with no `dispatch-started` record
    for `g9.review.p1`, `wait`'s block loop has nothing to poll and returns
    immediately, and the spawn that follows is the trailing `cmd_status`
    render's -- exactly what `status` alone does today (commitment 2, and
    this gate's scope; the move is gate 2's, commitments 13-15).
    """
    marker = bare_workdir / "spawned"
    _throwaway_dispatch(bare_workdir, marker)
    _mint_panel_step(wid="g9", worker="reviewer")

    began = time.monotonic()
    code = cli.main(["g9", "wait"])
    elapsed = time.monotonic() - began
    capsys.readouterr()

    assert code == 0
    assert elapsed < 1                      # `wait`'s own loop never ran a cycle
    started = _dispatch_entries("g9")
    assert len(started) == 1 and started[0]["child"] == "g9.review.p1"
    assert _await(marker, 1)

    cli.main(["g9"])                        # plain `status`, same state: nothing more
    capsys.readouterr()
    assert len(_dispatch_entries("g9")) == 1
    assert len(list(marker.iterdir())) == 1


# -- the mechanism itself: blocks, and unblocks three ways -------------------


def test_wait_blocks_on_a_live_dispatch_child_and_unblocks_on_its_return(
        bare_workdir, monkeypatch):
    monkeypatch.setattr(checkrun, "WAIT_POLL", 0.05)
    _mint_dispatch_step(wid="d1", child="d1.g1")
    proc = _sleeper(5)
    _record("d1", "d1.g1", proc.pid)

    def _land_it():
        time.sleep(0.2)
        journal.append("d1", "return", step="g1", child="d1.g1", fields={"result": "ok"})
    threading.Thread(target=_land_it, daemon=True).start()

    began = time.monotonic()
    code = cli.main(["d1", "wait", "--for", "5"])
    elapsed = time.monotonic() - began

    assert code == 0
    assert 0.15 < elapsed < 2, f"elapsed {elapsed}"
    proc.kill()
    proc.wait()


def test_wait_blocks_on_a_live_panelist_and_unblocks_on_its_return(
        bare_workdir, monkeypatch):
    monkeypatch.setattr(checkrun, "WAIT_POLL", 0.05)
    _mint_panel_step(wid="g9", worker="reviewer")
    proc = _sleeper(5)
    _record("g9", "g9.review.p1", proc.pid, tag="review.p1")

    def _land_it():
        time.sleep(0.2)
        journal.append("g9", "return", step="review", child="g9.review.p1",
                       fields={"verdict": "pass"})
    threading.Thread(target=_land_it, daemon=True).start()

    began = time.monotonic()
    code = cli.main(["g9", "wait", "--for", "5"])
    elapsed = time.monotonic() - began

    assert code == 0
    assert 0.15 < elapsed < 2, f"elapsed {elapsed}"
    proc.kill()
    proc.wait()


def test_wait_unblocks_when_the_childs_pid_dies_mid_block(bare_workdir, monkeypatch):
    """Commitment 3's third way to stop blocking: the child's pid dies with
    no return landed, so it is gone rather than outstanding and `wait` stops
    well inside `--for`.

    The reaper thread is what makes the pid genuinely dead rather than
    merely exited. A `_sleeper` is a child of the pytest process, so when it
    exits nothing reaps it: it lingers as a zombie, `os.kill(pid, 0)` keeps
    succeeding, and `checks.alive` correctly reads it as alive forever.
    `test_dispatch_wiring.py::_throwaway_dispatch`'s own docstring names
    this same hazard. In production `wait` is never the child's parent -- a
    dead child is reaped elsewhere and its pid really goes -- so reaping on
    a thread here reproduces production rather than testing the zombie.
    """
    monkeypatch.setattr(checkrun, "WAIT_POLL", 0.05)
    _mint_dispatch_step(wid="d1", child="d1.g1")
    proc = _sleeper(0.3)
    reaper = threading.Thread(target=proc.wait, daemon=True)
    reaper.start()
    _record("d1", "d1.g1", proc.pid)

    began = time.monotonic()
    code = cli.main(["d1", "wait", "--for", "5"])
    elapsed = time.monotonic() - began

    assert code == 0
    assert 0.2 < elapsed < 2, f"elapsed {elapsed}"   # it blocked, then stopped
    assert not checkrun.alive(proc.pid)
    assert "d1.g1" not in runmod.state("d1")["returns_by_child"]  # gone, not returned
    reaper.join(5)


def test_a_dead_pid_record_with_no_return_is_gone_not_outstanding(bare_workdir, capsys):
    """Commitment 3's own distinction, on the path that never has to poll at
    all: a dead-pid record with no return is gone, not outstanding, so
    `wait` renders immediately rather than blocking for even one cycle."""
    _mint_dispatch_step(wid="d1", child="d1.g1")
    _record("d1", "d1.g1", _dead_pid())

    began = time.monotonic()
    code = cli.main(["d1", "wait"])
    elapsed = time.monotonic() - began

    assert code == 0
    assert elapsed < 1


def test_for_overrides_the_default_bound(bare_workdir, monkeypatch):
    monkeypatch.setattr(checkrun, "WAIT_POLL", 0.05)
    monkeypatch.setattr(checkrun, "WAIT_BOUND", 90)  # confirm --for wins over this
    _mint_dispatch_step(wid="d1", child="d1.g1")
    proc = _sleeper(5)
    _record("d1", "d1.g1", proc.pid)

    began = time.monotonic()
    code = cli.main(["d1", "wait", "--for", "1"])
    elapsed = time.monotonic() - began

    assert code == 0
    assert 0.9 < elapsed < 3, f"elapsed {elapsed}"
    assert checkrun.alive(proc.pid)          # the bound expired, the child did not
    proc.kill()
    proc.wait()


def test_a_malformed_for_value_refuses(bare_workdir):
    _mint_dispatch_step(wid="d1", child="d1.g1")

    with pytest.raises(SystemExit) as e:
        cli.main(["d1", "wait", "--for", "soon"])
    assert "not a number of seconds" in str(e.value)

    with pytest.raises(SystemExit) as e:
        cli.main(["d1", "wait", "--for", "0"])
    assert "not a number of seconds" in str(e.value)


def test_the_bounds_own_expiry_exits_0_with_a_child_still_outstanding(
        bare_workdir, monkeypatch):
    monkeypatch.setattr(checkrun, "WAIT_POLL", 0.05)
    monkeypatch.setattr(checkrun, "WAIT_BOUND", 0.3)
    _mint_dispatch_step(wid="d1", child="d1.g1")
    proc = _sleeper(5)
    _record("d1", "d1.g1", proc.pid)

    began = time.monotonic()
    code = cli.main(["d1", "wait"])
    elapsed = time.monotonic() - began

    assert code == 0
    assert elapsed < 2, f"elapsed {elapsed}"
    assert checkrun.alive(proc.pid)
    proc.kill()
    proc.wait()


# -- commitment 2: the room is status's own, not a view of wait's -----------


def test_waits_output_is_exactly_what_status_prints_for_the_same_state(
        bare_workdir, capsys, monkeypatch):
    """Commitment 2 whole: `wait` is `status` with a block in front of it,
    renders no view of its own, and adds no state to the room. The state is
    held identical across the two reads -- one dispatch step, one already
    journaled `dispatch-started` record whose pid is still live at both
    reads, and no return ever landing -- so the two rooms can differ only if
    `wait` prints something `status` does not."""
    monkeypatch.setattr(checkrun, "WAIT_POLL", 0.05)
    _mint_dispatch_step(wid="d1", child="d1.g1")
    proc = _sleeper(30)
    _record("d1", "d1.g1", proc.pid)
    capsys.readouterr()

    code = cli.main(["d1", "wait", "--for", "1"])  # holds to the bound, child still out
    waited = capsys.readouterr().out
    assert checkrun.alive(proc.pid)                # the state the second read sees
    assert cli.main(["d1"]) == 0
    statused = capsys.readouterr().out

    assert code == 0
    assert "d1.g1" in waited and "working" in waited   # a real room, not two blanks
    assert waited == statused
    proc.kill()
    proc.wait()
