"""Rendering a dispatch or panel room actually starts each outstanding
child's harness process, through the repository's own `dispatch` palette
entry -- once per child, journaled and logged inside the parent's own work
location, a failed attempt reported rather than crashed on. A repository
whose palette carries no `dispatch` entry at all -- and the fast suite's own
`workdir` fixture, whose copied `constellation.toml` now has one stripped
back out -- keeps rendering exactly as before: nothing spawned.

Every process this file starts (through a test-local commands mapping) is a
short-lived `python3 -c ...` of the test's own choosing, never `claude`.
"""

import json
import pathlib
import subprocess
import sys
import time
import tomllib

import pytest

from engine import checks, cli, journal
from test_brief import _mint_dispatch_step, _mint_panel_step


def _throwaway_dispatch(root, marker_dir):
    """A `constellation.toml` naming a `dispatch` entry that runs the real
    python executing this test session -- never `claude` -- and drops one
    file per invocation into `marker_dir`, so an actual spawn is observable
    directly rather than only inferred from the journal."""
    marker_dir = pathlib.Path(marker_dir)
    script = (
        "import pathlib, sys, time\n"
        f"d = pathlib.Path({str(marker_dir)!r})\n"
        "d.mkdir(parents=True, exist_ok=True)\n"
        "(d / f'{time.time_ns()}.brief').write_text(sys.argv[1])\n"
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


# -- mechanics: journaled, logged, once per child -----------------------------


def test_a_dispatch_steps_outstanding_child_is_spawned_once(bare_workdir, capsys):
    marker = bare_workdir / "spawned"
    _throwaway_dispatch(bare_workdir, marker)
    _mint_dispatch_step(wid="d1", child="d1.g1")

    cli.main(["d1"])
    capsys.readouterr()

    assert _await(marker, 1)
    started = _dispatch_entries("d1")
    assert len(started) == 1 and started[0]["child"] == "d1.g1"
    log = journal.location("d1") / "dispatch.g1.log"
    assert log.is_file()

    # rendered again -- already-started, so nothing new is spawned
    cli.main(["d1"])
    capsys.readouterr()
    time.sleep(0.2)
    assert len(_dispatch_entries("d1")) == 1


def test_a_panel_steps_outstanding_child_is_spawned_once(bare_workdir, capsys):
    marker = bare_workdir / "spawned"
    _throwaway_dispatch(bare_workdir, marker)
    _mint_panel_step(wid="g9", worker="reviewer")

    cli.main(["g9"])
    capsys.readouterr()

    assert _await(marker, 1)
    started = _dispatch_entries("g9")
    assert len(started) == 1 and started[0]["child"] == "g9.review.p1"
    log = journal.location("g9") / "dispatch.review.p1.log"
    assert log.is_file()


# -- commitment 3: no `dispatch` entry, nothing changes -----------------------


def test_a_repository_with_no_dispatch_entry_spawns_nothing(bare_workdir, capsys):
    """`bare_workdir` seeds no `constellation.toml` at all -- exactly the
    shape every fast-suite test stood on before this gate. Rendering the
    room must look identical: no journal entry, no log file, no crash."""
    _mint_dispatch_step(wid="d1", child="d1.g1")

    cli.main(["d1"])
    out = capsys.readouterr().out

    assert "d1.g1" in out                       # the room still rendered normally
    assert _dispatch_entries("d1") == []
    assert not (journal.location("d1") / "dispatch.g1.log").exists()


# -- a failed spawn is reported, not crashed ----------------------------------


def test_a_failed_spawn_is_reported_not_crashed_and_its_reason_is_logged(
        bare_workdir, capsys):
    """Today's single-string `[commands]` shape under `dispatch` -- the
    malformed-entry case `checks.DispatchFailure` raises for -- must not
    escape rendering the room: the render completes normally, and the
    reason lands in the child's own log rather than nowhere."""
    (bare_workdir / "constellation.toml").write_text(
        '[commands]\ndispatch = "claude -p {brief}"\n')
    _mint_dispatch_step(wid="d1", child="d1.g1")

    cli.main(["d1"])   # must not raise
    out = capsys.readouterr().out

    assert "d1.g1" in out
    assert _dispatch_entries("d1") == []        # no running process, no journal entry
    log = journal.location("d1") / "dispatch.g1.log"
    assert log.is_file()
    assert checks.DISPATCH_MALFORMED in log.read_text(encoding="utf-8")

    # nothing was journaled, so a later render tries again rather than
    # silently giving up on a child forever
    cli.main(["d1"])
    capsys.readouterr()
    assert _dispatch_entries("d1") == []


# -- scenario: three panelists in three different states, one render ---------


def test_a_panel_of_three_spawns_only_its_one_genuinely_outstanding_child(
        bare_workdir, capsys):
    """Extends `test_brief.py`'s own `_mint_panel_step` shape (and the
    manner of its `test_a_reviewer_panelist_is_unmoved_by_a_neighboring_critic`)
    to three panelists, each in a different state: p1 already returned, p2
    already carries its own `dispatch-started` record, p3 is genuinely
    outstanding. One call to `_panel_status` (via `cli.main`) must spawn
    exactly the one outstanding child -- not the returned one, and not the
    one already started -- leaving exactly one new journal record and one
    new log file, both keyed to p3's own child id."""
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
    journal.append(wid, "dispatch-started", child=f"{wid}.review.p2",
                   pid=999999, tree=str(bare_workdir), log=str(pre_existing_log))

    cli.main([wid])
    out = capsys.readouterr().out

    assert "returned" in out and "outstanding" in out          # both words rendered

    assert _await(marker, 1)
    started = _dispatch_entries(wid)
    # exactly one *new* dispatch-started record: p2's own is the pre-seeded one
    new_started = [e for e in started if e["child"] != f"{wid}.review.p2"]
    assert len(started) == 2
    assert len(new_started) == 1
    assert new_started[0]["child"] == f"{wid}.review.p3"

    new_logs = [p for p in journal.location(wid).glob("dispatch.*.log")
                if p.name != "dispatch.review.p2.log"]
    assert len(new_logs) == 1
    assert new_logs[0].name == "dispatch.review.p3.log"


# -- commitment 1: the real constellation.toml names the real harness --------


def test_constellation_toml_names_evals_harnesss_own_real_argv():
    """Closes commitment 1's own proof: this repository's own, real
    `constellation.toml` -- not a test-local stand-in -- carries `dispatch`
    as exactly `evals/harness.py`'s own `cmd` (around evals/harness.py:128)."""
    root = pathlib.Path(__file__).resolve().parent.parent
    palette = tomllib.loads((root / "constellation.toml").read_text())

    assert palette["commands"]["dispatch"] == [
        "claude", "-p", "{brief}", "--model", "{runner}",
        "--allowedTools", "Bash", "Read", "Write", "Edit",
    ]


# -- commitment 20: the fast suite spawns no real process ---------------------


def test_workdir_rendering_never_touches_a_real_process(workdir, monkeypatch, capsys):
    """Closes commitment 20's own proof: `workdir` copies the host repo's
    real `constellation.toml` verbatim (per its own docstring), which now
    carries a real `dispatch` entry -- so this asserts, directly, that
    rendering a dispatch room and a panel room against that exact fixture
    never reaches `subprocess.Popen` at all, rather than trusting that a
    green suite would have caught a silently-broken guard (it would not:
    `Popen` is fire-and-forget and its own failures are caught and logged,
    never raised)."""
    calls = []
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: calls.append((a, k)))

    _mint_dispatch_step(wid="d1", child="d1.g1")
    cli.main(["d1"])
    capsys.readouterr()

    _mint_panel_step(wid="g9", worker="reviewer")
    cli.main(["g9"])
    capsys.readouterr()

    assert calls == []
    assert _dispatch_entries("d1") == []
    assert _dispatch_entries("g9") == []
