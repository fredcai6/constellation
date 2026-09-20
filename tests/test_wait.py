"""`spine <work-id> wait`: block while the current step has an outstanding
child or an outstanding proof, then print exactly what `status` would have --
it renders no view of its own.

Gate 2 (commitments 13-15) makes `wait` the sole spawner of a child:
`_dispatch_child` is a pure read now, and `cmd_wait`'s own pre-loop makes
one spawn attempt, through `_spawn_outstanding`, per child in `child_ids`
that is neither already returned nor already carrying a `dispatch-started`
record -- before the poll loop ever runs. Rendering starts nothing any
more, in `engine/` or in this file: every mechanics case that used to prove
a render's own spawn (`test_dispatch_wiring.py`'s own "spawned once",
"failed spawn logged", "working row reached only by a prior spawn", the
three-panelist scenario, and the absence-vs-failed-attempt contrast) moved
here with the call they now depend on (commitment 34).

Three things this file exists to prove that a shallower suite would miss:
the mechanism actually blocks and unblocks -- not merely that it never
blocks on the rooms that were never in scope; that `cmd_wait` itself is
what starts a never-dispatched child and journals it, proven against a
real, test-configured `dispatch` entry rather than a hand-written
`_record` standing in for one; and the guard-gap this round's own fix
closes -- a child already returned but carrying no `dispatch-started`
record (standing in for one opened by hand and already finished) must not
be spawned a second time by `cmd_wait`'s own pre-loop.

Scenarios that only need an already-outstanding child to exist -- the
block/unblock mechanics, the bound, commitment 2's equality proof -- still
mint a `dispatch-started` record directly, by hand, since nothing about
those depends on how the record got there.

Every process this file spawns is a short-lived `python3 -c ...` of its own
choosing, never `claude`.
"""

import json
import os
import pathlib
import signal
import subprocess
import sys
import threading
import time

import pytest

from engine import checks as checkrun
from engine import cli, journal
from test_nesting import _response
from engine import run as runmod
from test_brief import _mint_dispatch_step, _mint_panel_step
from test_explore import explore, _spine


# [throwaway-outlives-the-render]
# Rationale: a "working" assertion needs the spawned pid to actually still
#   be running, not merely un-reaped -- `subprocess.Popen` never waits on
#   this test's own children, so a process that has already exited is a
#   zombie `checks.alive` (correctly) still reads as alive right up until
#   something in this same test process creates another `Popen`, which
#   opportunistically reaps every finished one (`subprocess._cleanup`).
#   Under the full suite, some other test's own spawn can land in that exact
#   window and reap this one first, which is exactly what made a "working"
#   assertion flaky here (round 3's own finding). A brief sleep after the
#   marker write keeps the pid genuinely alive -- not merely un-reaped --
#   for comfortably longer than the poll cycles `wait`'s own block loop runs
#   against it and the render that follows them.
# Rejected: asserting on `_dispatch_entries` alone and skipping the "working"
#   word. That would stop proving commitment 12's own liveness read at all,
#   which is the one thing these spawn-mechanics tests were extended to check.
def _throwaway_dispatch(root, marker_dir):
    """A `constellation.toml` naming a `dispatch` entry that runs the real
    python executing this test session -- never `claude` -- drops one file
    per invocation into `marker_dir` so an actual spawn is observable
    directly rather than only inferred from the journal, then sleeps
    briefly so the process reads as genuinely alive rather than as an
    already-exited zombie a later `Popen` elsewhere just hasn't reaped yet."""
    marker_dir = pathlib.Path(marker_dir)
    script = (
        "import pathlib, sys, time\n"
        f"d = pathlib.Path({str(marker_dir)!r})\n"
        "d.mkdir(parents=True, exist_ok=True)\n"
        "(d / f'{time.time_ns()}.brief').write_text(sys.argv[1])\n"
        "time.sleep(2)\n"
    )
    entry = [sys.executable, "-c", script, "{brief}"]
    (pathlib.Path(root) / "constellation.toml").write_text(
        "[commands]\ndispatch = " + json.dumps(entry) + "\n")


def _dispatch_entries(wid):
    return [e for e in journal.read(wid) if e.get("kind") == "dispatch-started"]


def _await(marker_dir, count, seconds=10):
    """Poll until `marker_dir` holds `count` files or the deadline passes."""
    deadline = time.time() + seconds
    marker_dir = pathlib.Path(marker_dir)
    while time.time() < deadline:
        if marker_dir.is_dir() and len(list(marker_dir.iterdir())) >= count:
            return True
        time.sleep(0.05)
    return marker_dir.is_dir() and len(list(marker_dir.iterdir())) >= count


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


# -- the proof case: `wait` holds for it, rather than refusing to --------


def _submitted_proof(wid, proof, **spec):
    """A real gate standing on its proof, already submitted -- `cmd_wait`'s
    own final branch is what every test below is against, never a
    hand-written `check-started` record standing in for one: the proof
    really runs in `checks.hand_in`'s own detached process, the same one
    production spawns."""
    _gate(wid)
    journal.append(wid, "prefill", fields={"proof": proof, **spec})
    _response(wid).write_text(
        'change = "c"\ndeviations = "waived: none"\n')
    cli.main([wid, "submit"])
    st = runmod.state(wid)
    started = runmod.in_flight(st, st["current"])
    assert started, "the proof did not outrun HANDBACK -- nothing in flight"
    return started


def test_a_proof_in_flight_holds_until_it_lands_then_renders_the_next_step(
        bare_workdir, capsys, monkeypatch):
    """The contract `wait` used to refuse for a proof: it now blocks while
    the detached runner is still going, and unblocks the moment that runner
    journals its own `submit` -- releasing well before the 90s round-trip a
    caller used to have to re-render for by hand, and landing the run on
    its own next step, not the in-flight room it started in."""
    monkeypatch.setattr(checkrun, "HANDBACK", 0.1)
    monkeypatch.setattr(checkrun, "WAIT_POLL", 0.05)
    wid = "g1"
    _submitted_proof(wid, "sleep 0.3; true")
    capsys.readouterr()
    before = runmod.state(wid)["current"]["id"]

    began = time.monotonic()
    code = cli.main([wid, "wait", "--for", "5"])
    elapsed = time.monotonic() - began
    out = capsys.readouterr().out

    assert code == 0
    assert 0.15 < elapsed < 3, f"elapsed {elapsed}"   # it blocked, then released
    assert "in flight" not in out
    fresh = runmod.state(wid)
    assert fresh["current"]["id"] != before           # the room moved on


def test_a_proof_still_running_at_the_bound_renders_the_in_flight_room_again(
        bare_workdir, capsys, monkeypatch):
    """The bound's own expiry, proven by shrinking it rather than by waiting
    out the real 90s default: the proof outlives `--for`, so `wait` gives up
    and renders the same in-flight room, still naming `wait` as the move --
    unlike the orphan case below, there is genuinely something to keep
    waiting for."""
    monkeypatch.setattr(checkrun, "HANDBACK", 0.1)
    monkeypatch.setattr(checkrun, "WAIT_POLL", 0.05)
    wid = "g1"
    started = _submitted_proof(wid, "sleep 5")
    capsys.readouterr()

    began = time.monotonic()
    code = cli.main([wid, "wait", "--for", "1"])
    elapsed = time.monotonic() - began
    out = capsys.readouterr().out

    assert code == 0
    assert 0.9 < elapsed < 3, f"elapsed {elapsed}"
    assert checkrun.alive(started["pid"])              # the bound expired, not the proof
    assert "in flight" in out
    assert "1 outstanding" in out and "wait is the move" in out
    os.kill(started["pid"], signal.SIGKILL)
    os.waitpid(started["pid"], 0)


def test_a_proof_that_fails_mid_wait_stops_waiting_and_reflects_the_failure(
        bare_workdir, capsys, monkeypatch):
    """The runner is the only writer of a failing outcome too (a `check`
    entry, never a `submit`) -- `wait`'s own predicate is `runmod.in_flight`,
    which a `check` entry clears exactly as a `submit` does, so a failing
    proof releases `wait` the same way a passing one does, onto a room that
    now shows the failure rather than the step having advanced."""
    monkeypatch.setattr(checkrun, "HANDBACK", 0.1)
    monkeypatch.setattr(checkrun, "WAIT_POLL", 0.05)
    wid = "g1"
    _submitted_proof(wid, "sleep 0.3; exit 4")
    capsys.readouterr()

    began = time.monotonic()
    code = cli.main([wid, "wait", "--for", "5"])
    elapsed = time.monotonic() - began
    out = capsys.readouterr().out

    assert code == 0
    assert 0.15 < elapsed < 3, f"elapsed {elapsed}"
    st = runmod.state(wid)
    assert not st["in_flight"]                         # the check entry cleared it
    assert st["current"]["id"] == "work-1"              # still standing on the failed step
    checked = [e for e in journal.read(wid) if e.get("kind") == "check"]
    assert checked[-1]["exit"] == 4
    assert "in flight" not in out


def test_a_proof_killed_mid_wait_renders_the_orphan_room_immediately(
        bare_workdir, capsys, monkeypatch):
    """The fourth release: nothing to poll survives a killed pid, so `wait`
    must not hold it to the bound. `runmod.in_flight` alone cannot tell this
    apart from a live proof -- only a `submit` or `check` entry clears it,
    and a killed process writes neither -- so `checkrun.alive` is what has
    to catch it, both at entry and every cycle after."""
    monkeypatch.setattr(checkrun, "HANDBACK", 0.1)
    monkeypatch.setattr(checkrun, "WAIT_POLL", 0.05)
    wid = "g1"
    started = _submitted_proof(wid, "sleep 30")
    capsys.readouterr()
    pid = started["pid"]

    def _kill_it():
        time.sleep(0.2)
        os.kill(pid, signal.SIGKILL)
        os.waitpid(pid, 0)   # reap it -- this test process is its real parent
    threading.Thread(target=_kill_it, daemon=True).start()

    began = time.monotonic()
    code = cli.main([wid, "wait", "--for", "5"])
    elapsed = time.monotonic() - began
    out = capsys.readouterr().out

    assert code == 0
    assert 0.15 < elapsed < 3, f"elapsed {elapsed}"     # noticed the death, not the bound
    assert not checkrun.alive(pid)
    assert "process is gone" in out
    assert "0 outstanding" in out
    assert "wait is the move" not in out                  # no verb named -- nothing to poll


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
    assert f"your response form: {_response(wid)}" in out


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
    # an unconfigured repository never mints through this path at all --
    # `_dispatch_entries` above only reads the parent's own
    # `dispatch-started` records, never whether the child's own run got
    # minted, so this checks the other half directly.
    assert not journal.exists("d1.g1")


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


# -- gate 2's own move: `wait` is the one thing that starts a child --------


def test_wait_spawns_a_never_dispatched_dispatch_child_then_blocks_on_it(
        bare_workdir, capsys, monkeypatch):
    """Commitments 13-15, the dispatch-step half: nothing in this test
    renders the room before `wait` runs, and no `dispatch-started` record
    exists when it starts -- so the record found afterwards is one
    `cmd_wait`'s own pre-loop wrote, through a real, test-configured
    `dispatch` entry whose process leaves a marker file behind. `wait` then
    polls that same record: the run stops only once a `return` for that
    child lands 0.2s in, which is several `WAIT_POLL` cycles past the
    spawn, so elapsed is bounded on both sides -- above the poll interval
    (it really cycled) and well below the `--for` bound (the return, not
    the deadline, is what released it).

    Gate 1 (`o-child-never-opens-its-own-run`) also proves itself here: the
    child's own run already exists (`_spawn_outstanding` minted it, not the
    spawned process itself), the brief that process was actually handed
    carries no "open it:" line, and `wait`'s own stdout carries no trace of
    the minted child's status room either -- neither the "opened ..." line
    nor its rendered brief's own "brief -- ..." header, the two markers that
    would appear only if this path had called `_open_child`'s wrapper
    instead of the silent minting core."""
    monkeypatch.setattr(checkrun, "WAIT_POLL", 0.05)
    marker = bare_workdir / "spawned"
    _throwaway_dispatch(bare_workdir, marker)
    _mint_dispatch_step(wid="d1", child="d1.g1")
    assert _dispatch_entries("d1") == []

    def _land_it():
        time.sleep(0.2)
        journal.append("d1", "return", step="g1", child="d1.g1",
                       fields={"result": "ok"})
    threading.Thread(target=_land_it, daemon=True).start()

    began = time.monotonic()
    code = cli.main(["d1", "wait", "--for", "5"])
    elapsed = time.monotonic() - began
    out = capsys.readouterr().out

    assert code == 0
    assert 0.15 < elapsed < 3, f"elapsed {elapsed}"   # cycled, and not to the bound
    assert _await(marker, 1)                          # a real process, really started
    started = _dispatch_entries("d1")
    assert len(started) == 1 and started[0]["child"] == "d1.g1"
    assert started[0]["pid"]
    assert (journal.location("d1") / "dispatch.g1.log").is_file()
    assert "d1.g1" in runmod.state("d1")["returns_by_child"]   # what released it
    assert journal.exists("d1.g1")                    # minted before the process ever started

    briefs = list(marker.iterdir())
    assert len(briefs) == 1
    brief_text = briefs[0].read_text(encoding="utf-8")
    assert not any("open it:" in l for l in brief_text.splitlines())
    assert "opened d1.g1" not in out
    assert "brief -- d1.g1" not in out

    # a second `wait` over the same state starts nothing further
    cli.main(["d1", "wait"])
    capsys.readouterr()
    assert len(_dispatch_entries("d1")) == 1
    assert len(list(marker.iterdir())) == 1


def test_wait_spawns_a_never_dispatched_panelist_then_blocks_on_it(
        bare_workdir, capsys, monkeypatch):
    """The panel-step half of the case above, on the branch
    `runmod.panel_outstanding` selects -- same two-sided bound, same proof
    that `cmd_wait` itself wrote the record it then polled."""
    monkeypatch.setattr(checkrun, "WAIT_POLL", 0.05)
    marker = bare_workdir / "spawned"
    _throwaway_dispatch(bare_workdir, marker)
    _mint_panel_step(wid="g9", worker="reviewer")
    assert _dispatch_entries("g9") == []

    def _land_it():
        time.sleep(0.2)
        journal.append("g9", "return", step="review", child="g9.review.p1",
                       fields={"verdict": "pass"})
    threading.Thread(target=_land_it, daemon=True).start()

    began = time.monotonic()
    code = cli.main(["g9", "wait", "--for", "5"])
    elapsed = time.monotonic() - began
    capsys.readouterr()

    assert code == 0
    assert 0.15 < elapsed < 3, f"elapsed {elapsed}"
    assert _await(marker, 1)
    started = _dispatch_entries("g9")
    assert len(started) == 1 and started[0]["child"] == "g9.review.p1"
    assert started[0]["pid"]
    assert (journal.location("g9") / "dispatch.review.p1.log").is_file()
    assert "g9.review.p1" in runmod.state("g9")["returns_by_child"]

    cli.main(["g9", "wait"])
    capsys.readouterr()
    assert len(_dispatch_entries("g9")) == 1
    assert len(list(marker.iterdir())) == 1


def test_wait_never_respawns_a_dispatch_child_that_already_returned(
        bare_workdir, capsys):
    """The guard half `_spawn_outstanding`'s own check cannot make on its
    own: it reads only `dispatch-started` records and has no notion of a
    `return` at all, so the `returns_by_child` half now lives inside
    `_startable`, read from `_spawn_outstanding`'s own call to it -- not
    beside `_wait_spawn`'s own call, which carries no guard of its own at
    all. A child opened by hand (`spine open ... --parent ...`, still legal
    until gate 4's room-text rewrite) and already returned carries no
    record -- without that half it would read as never-started and `wait`
    would start a second, redundant process for work already done.

    Two dispatch steps naming the same child hold the shape open: `g0` has
    the return, so `g1` -- still current, still naming `d1.g1` -- reaches
    `cmd_wait`'s pre-loop with that child in `returns_by_child` and no
    record on the journal. Nothing may be spawned: no journal record, no
    log file, and no marker from the real `dispatch` entry configured here
    (a repository without one would prove nothing, since `spawn_dispatch`
    declines before the guard is ever the reason)."""
    marker = bare_workdir / "spawned"
    _throwaway_dispatch(bare_workdir, marker)
    journal.append("d1", "run", title="fix the parser", assembly="run-an-issue")
    for sid in ("g0", "g1"):
        journal.append("d1", "step", id=sid, segment="execute",
                       dispatches="run-a-gate", child="d1.g1",
                       prefill={"purpose": "p", "scope": "s", "proof": "true"},
                       anchor=False, terminal=False, source="mint")
    journal.append("d1", "return", step="g0", child="d1.g1", fields={"result": "ok"})
    st = runmod.state("d1")
    assert st["current"]["id"] == "g1" and "d1.g1" in st["returns_by_child"]

    began = time.monotonic()
    code = cli.main(["d1", "wait"])
    elapsed = time.monotonic() - began
    capsys.readouterr()

    assert code == 0
    assert elapsed < 1
    assert _dispatch_entries("d1") == []
    assert not (journal.location("d1") / "dispatch.g1.log").exists()
    assert not marker.exists()


def test_wait_never_respawns_a_panelist_that_already_returned(
        bare_workdir, capsys, monkeypatch):
    """The panel-step shape of the same guard, where it bites without any
    contrivance: p1 returned without ever carrying a `dispatch-started`
    record (opened by hand), p2 is genuinely outstanding, and the step stays
    current because its panel has not finished voting. `cmd_wait`'s pre-loop
    sees both ids and must start exactly one -- p2's. Drop the
    `returns_by_child` half of the guard and p1 is started a second time:
    two records, two markers, and a `dispatch.review.p1.log` that should not
    exist."""
    monkeypatch.setattr(checkrun, "WAIT_POLL", 0.05)
    marker = bare_workdir / "spawned"
    _throwaway_dispatch(bare_workdir, marker)
    journal.append("g9", "run", title="t", assembly="run-a-gate")
    journal.append("g9", "step", id="review", segment="work",
                   panel=[{"worker": "reviewer", "criteria": "c"},
                          {"worker": "critic", "criteria": "c"}])
    journal.append("g9", "return", step="review", child="g9.review.p1",
                   fields={"verdict": "pass"})

    code = cli.main(["g9", "wait", "--for", "1"])
    capsys.readouterr()

    assert code == 0
    assert _await(marker, 1)
    started = _dispatch_entries("g9")
    assert len(started) == 1 and started[0]["child"] == "g9.review.p2"
    assert len(list(marker.iterdir())) == 1
    assert (journal.location("g9") / "dispatch.review.p2.log").is_file()
    assert not (journal.location("g9") / "dispatch.review.p1.log").exists()


def test_a_failed_spawn_is_reported_not_crashed_and_its_reason_is_logged(
        bare_workdir, capsys):
    """Today's single-string `[commands]` shape under `dispatch` -- the
    malformed-entry case `checks.DispatchFailure` raises for -- must not
    escape `wait`: the call completes normally, nothing is journaled, and
    the reason lands in the child's own log rather than nowhere. With no
    record written there is nothing outstanding either, so `wait` renders
    immediately, the same room `status` shows there (`WAIT_POLL` is 5s
    here, so a single accidental cycle would show)."""
    (bare_workdir / "constellation.toml").write_text(
        '[commands]\ndispatch = "claude -p {brief}"\n')
    _mint_dispatch_step(wid="d1", child="d1.g1")

    began = time.monotonic()
    code = cli.main(["d1", "wait"])   # must not raise
    elapsed = time.monotonic() - began
    out = capsys.readouterr().out

    assert code == 0
    assert elapsed < 1
    assert "d1.g1" in out
    assert _dispatch_entries("d1") == []        # no running process, no journal entry
    log = journal.location("d1") / "dispatch.g1.log"
    assert log.is_file()
    assert checkrun.DISPATCH_MALFORMED in log.read_text(encoding="utf-8")

    # nothing was journaled, so a later `wait` tries again rather than
    # silently giving up on a child forever
    cli.main(["d1", "wait"])
    capsys.readouterr()
    assert _dispatch_entries("d1") == []
    assert log.read_text(encoding="utf-8").count(checkrun.DISPATCH_MALFORMED) == 2


def test_not_dispatched_from_absence_and_from_a_failed_attempt_differ_only_by_log(
        bare_workdir, capsys):
    """Commitment 13: a spawn attempt that failed renders the same word a
    wholly absent entry gets -- "not dispatched" both times -- distinguished
    only by whether that child's own log holds a reason. `d1` here sees no
    `constellation.toml` at all (a wholly absent entry, no log possible);
    `d2` sees a malformed `[commands]` `dispatch` (today's single-string
    shape, not a list) -- a real entry whose attempt fails and is logged.
    Both are driven through `wait`, since after this gate that is the only
    caller that attempts a spawn at all."""
    _mint_dispatch_step(wid="d1", child="d1.g1")
    cli.main(["d1", "wait"])
    out_absent = capsys.readouterr().out

    assert "d1.g1 (not dispatched)" in out_absent
    assert not (journal.location("d1") / "dispatch.g1.log").exists()

    (bare_workdir / "constellation.toml").write_text(
        '[commands]\ndispatch = "claude -p {brief}"\n')
    _mint_dispatch_step(wid="d2", child="d2.g1")
    cli.main(["d2", "wait"])
    out_failed = capsys.readouterr().out

    assert "d2.g1 (not dispatched)" in out_failed
    log = journal.location("d2") / "dispatch.g1.log"
    assert log.is_file()
    assert checkrun.DISPATCH_MALFORMED in log.read_text(encoding="utf-8")


def test_a_panel_of_three_spawns_only_its_one_genuinely_outstanding_child(
        bare_workdir, capsys, monkeypatch):
    """Extends `test_brief.py`'s own `_mint_panel_step` shape to three
    panelists, each in a different state: p1 already returned, p2 already
    carries `checkrun.MAX_STARTS` `dispatch-started` records whose pid
    (999999) reads as dead -- gone and spent, so this gate's own restart
    guard must not touch it either -- p3 is genuinely outstanding. One
    `wait` must spawn exactly the one startable child -- not the returned
    one, and not the spent one -- leaving exactly one new journal record
    and one new log file, both keyed to p3's own child id, and the room it
    renders afterwards must report all three siblings' own state
    (commitment 11)."""
    monkeypatch.setattr(checkrun, "WAIT_POLL", 0.05)
    marker = bare_workdir / "spawned"
    _throwaway_dispatch(bare_workdir, marker)
    wid = "g9"
    journal.append(wid, "run", title="t", assembly="run-a-gate")
    journal.append(wid, "step", id="review", segment="work",
                   panel=[{"worker": "reviewer", "criteria": "c"},
                          {"worker": "critic", "criteria": "c"},
                          {"worker": "reviewer", "criteria": "c"}])
    journal.append(wid, "return", step="review", child=f"{wid}.review.p1",
                   fields={"verdict": "pass"})
    pre_existing_log = journal.location(wid) / "dispatch.review.p2.log"
    pre_existing_log.parent.mkdir(parents=True, exist_ok=True)
    pre_existing_log.write_text("already running\n")
    for _ in range(checkrun.MAX_STARTS):
        journal.append(wid, "dispatch-started", child=f"{wid}.review.p2",
                       pid=999999, tree=str(bare_workdir), log=str(pre_existing_log))

    code = cli.main([wid, "wait", "--for", "1"])
    out = capsys.readouterr().out

    assert code == 0
    assert "panelist p1 (returned)" in out
    assert "panelist p2 (gone without returning -- starts spent)" in out
    assert "panelist p3 (working)" in out

    assert _await(marker, 1)
    started = _dispatch_entries(wid)
    # exactly one *new* dispatch-started record: p2's own are the pre-seeded ones
    new_started = [e for e in started if e["child"] != f"{wid}.review.p2"]
    assert len(started) == 4
    assert len(new_started) == 1
    assert new_started[0]["child"] == f"{wid}.review.p3"
    assert len(list(marker.iterdir())) == 1

    new_logs = [p for p in journal.location(wid).glob("dispatch.*.log")
                if p.name != "dispatch.review.p2.log"]
    assert len(new_logs) == 1
    assert new_logs[0].name == "dispatch.review.p3.log"


def test_a_working_childs_row_omits_the_brief_and_every_command(
        bare_workdir, capsys, monkeypatch):
    """Commitment 14: printing a manual dispatch command beside a live pid
    is the exact double-dispatch commitment 19 exists to prevent, so a
    working child's row carries none of a brief's own ingredients -- no
    role, no tier, no runner, no `open it:` line (commitment 23's other
    half). The row is reached only by a prior spawn, which after this gate
    is `wait`'s own: the room asserted on here is the one `wait` renders
    when its bound expires with the child it started still alive."""
    monkeypatch.setattr(checkrun, "WAIT_POLL", 0.05)
    marker = bare_workdir / "spawned"
    _throwaway_dispatch(bare_workdir, marker)
    _mint_panel_step(wid="g9", worker="reviewer")

    code = cli.main(["g9", "wait", "--for", "1"])
    out = capsys.readouterr().out

    assert code == 0
    assert _await(marker, 1)
    assert len(_dispatch_entries("g9")) == 1
    assert "panelist p1 (working)" in out
    assert "brief --" not in out
    assert "open it:" not in out
    assert "runner" not in out


# -- gate 4: `wait` restarts a gone-but-not-spent child itself, capped -------


def test_wait_restarts_a_dead_pid_dispatch_child_then_blocks_on_its_new_pid(
        bare_workdir, capsys, monkeypatch):
    """Commitments 23-27: a single dead-pid `dispatch-started` record with
    no return is gone but not spent (`checkrun.MAX_STARTS` is 3, and this
    child carries only one), so `_startable` reads true and `cmd_wait`'s
    own pre-loop restarts it -- a real, second process, through the same
    test-configured `dispatch` entry, dropping its own marker file beside
    (not instead of) the dead record's silence. `wait` then blocks on that
    new pid exactly as `test_wait_blocks_on_a_live_dispatch_child_and_unblocks_on_its_return`
    already proves for a first start, and releases on the child's `return`,
    not the bound -- and since `WAIT_POLL` cycles several times before that
    return lands, a second, wrongly-repeated restart attempt within this
    same call would have dropped a second marker file (commitment 25)."""
    monkeypatch.setattr(checkrun, "WAIT_POLL", 0.05)
    marker = bare_workdir / "spawned"
    _throwaway_dispatch(bare_workdir, marker)
    _mint_dispatch_step(wid="d1", child="d1.g1")
    _record("d1", "d1.g1", _dead_pid())
    assert len(_dispatch_entries("d1")) == 1

    def _land_it():
        time.sleep(0.2)
        journal.append("d1", "return", step="g1", child="d1.g1",
                       fields={"result": "ok"})
    threading.Thread(target=_land_it, daemon=True).start()

    began = time.monotonic()
    code = cli.main(["d1", "wait", "--for", "5"])
    elapsed = time.monotonic() - began
    capsys.readouterr()

    assert code == 0
    assert 0.15 < elapsed < 3, f"elapsed {elapsed}"
    assert _await(marker, 1)                          # the restart's own marker
    assert len(list(marker.iterdir())) == 1            # never a second restart attempt
    assert cli._dispatch_start_counts("d1")["d1.g1"] == 2
    assert "d1.g1" in runmod.state("d1")["returns_by_child"]


def test_wait_restarts_again_at_the_boundary_nearest_the_cap(
        bare_workdir, capsys, monkeypatch):
    """The same guard, chased one step further: this child already carries
    `checkrun.MAX_STARTS - 1` (2) dead-pid records with no return -- gone,
    and one restart short of spent. `_startable`'s own comparison must read
    `count < checkrun.MAX_STARTS` (2 < 3, true) rather than a guard written
    as `count >= checkrun.MAX_STARTS - 1` (2 >= 2, wrongly false) -- the
    boundary value nearest the cap on the still-restarts side. One `wait`
    call restarts it a third time, reaching count 3 exactly."""
    monkeypatch.setattr(checkrun, "WAIT_POLL", 0.05)
    marker = bare_workdir / "spawned"
    _throwaway_dispatch(bare_workdir, marker)
    _mint_dispatch_step(wid="d1", child="d1.g1")
    for _ in range(checkrun.MAX_STARTS - 1):
        _record("d1", "d1.g1", _dead_pid())
    assert len(_dispatch_entries("d1")) == checkrun.MAX_STARTS - 1

    code = cli.main(["d1", "wait", "--for", "1"])
    out = capsys.readouterr().out

    assert code == 0
    assert _await(marker, 1)
    assert len(list(marker.iterdir())) == 1
    assert cli._dispatch_start_counts("d1")["d1.g1"] == checkrun.MAX_STARTS
    assert "d1.g1 (working)" in out


def test_wait_does_not_restart_a_dispatch_child_already_at_max_starts(
        bare_workdir, capsys):
    """The cap's own far side: this child already carries
    `checkrun.MAX_STARTS` dead-pid records with no return -- gone, and
    spent. `wait` must not attempt a fourth start at all: no new marker
    file, no new journal entry, and the render it falls through to
    (nothing outstanding, nothing startable) happens immediately rather
    than after any poll cycle, naming this child's starts as spent."""
    marker = bare_workdir / "spawned"
    _throwaway_dispatch(bare_workdir, marker)
    _mint_dispatch_step(wid="d1", child="d1.g1")
    for _ in range(checkrun.MAX_STARTS):
        _record("d1", "d1.g1", _dead_pid())
    assert len(_dispatch_entries("d1")) == checkrun.MAX_STARTS

    began = time.monotonic()
    code = cli.main(["d1", "wait"])
    elapsed = time.monotonic() - began
    out = capsys.readouterr().out

    assert code == 0
    assert elapsed < 1
    assert len(_dispatch_entries("d1")) == checkrun.MAX_STARTS
    assert not marker.exists()
    assert "d1.g1 (gone without returning -- starts spent)" in out


def test_wait_restarts_with_the_resume_command_once_the_runs_already_exists(
        bare_workdir, capsys, monkeypatch):
    """The restart-brief mirror of
    `test_gone_without_returning_offers_the_resume_command_once_the_run_exists`
    (`tests/test_dispatch_wiring.py`), but proven against the process
    `wait` actually spawns rather than only the rendered text: this
    child's run was already opened by hand once before its harness died.
    `_wait_spawn` no longer calls `_respawn_cmd` at all -- per
    `o-child-never-opens-its-own-run`, "no separate case for either" a
    fresh dispatch or a restart, so the restarted process's own brief
    carries no "open it:" line at all, matching the fresh-dispatch case
    rather than being handed `spine {child_id}` to run again."""
    monkeypatch.setattr(checkrun, "WAIT_POLL", 0.05)
    marker = bare_workdir / "spawned"
    _throwaway_dispatch(bare_workdir, marker)
    _mint_dispatch_step(wid="d1", child="d1.g1")
    cli.main(["open", "run-a-gate", "--parent", "d1", "--step", "g1"])
    capsys.readouterr()
    assert journal.exists("d1.g1")
    _record("d1", "d1.g1", _dead_pid())

    code = cli.main(["d1", "wait", "--for", "1"])
    capsys.readouterr()

    assert code == 0
    assert _await(marker, 1)
    briefs = list(pathlib.Path(marker).iterdir())
    assert len(briefs) == 1
    text = briefs[0].read_text(encoding="utf-8")
    assert not any("open it:" in l for l in text.splitlines())


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
    This file's own `_throwaway_dispatch` docstring names this same
    hazard. In production `wait` is never the child's parent -- a
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
