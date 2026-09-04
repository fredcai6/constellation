"""Rendering a dispatch or panel room starts nothing at all. After gate 2
(commitments 13-15) `_dispatch_child` is a pure read: a room reports which of
the four states each outstanding child is in off whatever the journal already
holds, and `wait` -- never a render -- is what starts a child's harness
process. The spawn-mechanic cases that used to live here (a child spawned
once, a failed spawn caught and logged, a working row reached only by a prior
spawn) moved to `tests/test_wait.py` with the call they now depend on
(commitment 34); what is left here is the render side: the four words, the
briefs beside them, the respawn command -- and the negatives proving no
render reaches a process.

Every process this file starts (through `test_wait.py`'s own test-local
commands mapping) is a short-lived `python3 -c ...` of the test's own
choosing, never `claude`.
"""

import pathlib
import subprocess
import tomllib

import pytest

from engine import cli, journal, render
from test_brief import _mint_dispatch_step, _mint_panel_step
from test_wait import _throwaway_dispatch, _dispatch_entries


# -- gate 2's own negative: rendering starts nothing ---------------------------


def test_rendering_a_dispatch_room_starts_no_child(bare_workdir, capsys):
    """The inverse of the "spawned once" case that moved to
    `test_wait.py`: the very same real, test-configured `dispatch` entry is
    in place, and rendering the room -- twice, since a second render is
    where a repeat spawn would have shown -- journals nothing, logs
    nothing, and drops no marker file. The row still reports the child's
    own state, which with nothing ever started is "not dispatched"."""
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


# -- commitment 12: four states, rendered -------------------------------------


def test_a_never_touched_child_renders_not_dispatched_with_its_brief(workdir, capsys):
    """`workdir`'s own `constellation.toml` has no `dispatch` entry (see
    `_without_dispatch_entry` in conftest.py), so a spawn attempt here is
    always the quiet `None` commitment 3 describes -- no journal entry, no
    log, no exception. That child's row still carries its own brief, with
    the plain `open it:` command, exactly as a never-dispatched child's
    ought to -- and a resolved tier and runner ride along with it
    (commitment 23)."""
    _mint_dispatch_step(wid="d1", child="d1.g1")
    capsys.readouterr()

    cli.main(["d1"])
    out = capsys.readouterr().out

    assert "d1.g1 (not dispatched)" in out
    assert "brief -- d1.g1" in out
    assert "tier         standard" in out
    assert "runner       claude-sonnet-5" in out
    line = next(l for l in out.splitlines() if "open it:" in l)
    assert pathlib.Path(line.split("open it:", 1)[1].strip().split()[0]).is_file()
    assert not (journal.location("d1") / "dispatch.g1.log").exists()


def test_a_returned_childs_row_still_renders_as_before(workdir, capsys):
    """Commitment 16, non-regression: a returned panelist's row is
    untouched by this gate -- the word, and no brief beside it, exactly as
    it always rendered. Its still-outstanding sibling (`workdir` drops the
    `dispatch` entry, so it reads as "not dispatched") keeps the step open
    long enough for both rows to land on the same render."""
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
    lines = out.splitlines()
    p1_line = next(i for i, l in enumerate(lines) if "panelist p1" in l)
    p2_line = next(i for i, l in enumerate(lines) if "panelist p2" in l)
    assert not any("brief --" in l for l in lines[p1_line:p2_line])


# -- commitment 15: the respawn command, both directions ----------------------


def test_gone_without_returning_offers_open_it_when_the_run_was_never_opened(
        bare_workdir, capsys):
    """A dead `dispatch-started` record whose own run was never actually
    opened still offers the brief's plain `open it:` line:
    `journal.exists(child_id)` is false, so there is nothing for
    `_open_child`'s own refusal to collide with."""
    _mint_dispatch_step(wid="d1", child="d1.g1")
    journal.append("d1", "dispatch-started", child="d1.g1", pid=999999,
                   tree=str(bare_workdir), log=str(bare_workdir / "dispatch.g1.log"))
    assert not journal.exists("d1.g1")

    cli.main(["d1"])
    out = capsys.readouterr().out

    assert "d1.g1 (gone without returning)" in out
    # bare_workdir carries no constellation.toml at all, so tier still
    # resolves from the assembly's own default while runner has nothing to
    # resolve against -- both literals below are what this fixture actually
    # produces, not the palette-backed `workdir` fixture's resolved runner.
    assert "tier         standard" in out
    assert "runner       (unresolved -- check constellation.toml [models])" in out
    line = next(l for l in out.splitlines() if "open it:" in l)
    parts = line.split("open it:", 1)[1].strip().split()
    assert parts[1:] == ["open", "run-a-gate", "--parent", "d1", "--step", "g1"]


def test_gone_without_returning_offers_the_resume_command_once_the_run_exists(
        bare_workdir, capsys):
    """Round 2's own headline scenario: a harness dies mid-step after
    already running the brief's `open it:` line once, so that child's own
    run already exists by the time this room offers it again. The brief's
    own original line now raises `SystemExit` with "already exists" in it,
    proven directly; the respawn command this gate prints instead (`spine
    {child_id}`) succeeds, landing on that run's own current room."""
    _mint_dispatch_step(wid="d1", child="d1.g1")
    open_cmd = [render.spine_cmd(), "open", "run-a-gate", "--parent", "d1", "--step", "g1"]

    cli.main(["open", "run-a-gate", "--parent", "d1", "--step", "g1"])
    capsys.readouterr()
    assert journal.exists("d1.g1")

    # the brief's own original command, run again, is exactly what raises
    with pytest.raises(SystemExit) as e:
        cli.main(open_cmd[1:])
    assert "already exists" in str(e.value)

    # the harness died: its own dispatch-started record now points at a pid
    # that is gone
    journal.append("d1", "dispatch-started", child="d1.g1", pid=999999,
                   tree=str(bare_workdir), log=str(bare_workdir / "dispatch.g1.log"))

    cli.main(["d1"])
    out = capsys.readouterr().out
    assert "d1.g1 (gone without returning)" in out
    # bare_workdir carries no constellation.toml at all, so tier still
    # resolves from the assembly's own default while runner has nothing to
    # resolve against -- both literals below are what this fixture actually
    # produces, not the palette-backed `workdir` fixture's resolved runner.
    assert "tier         standard" in out
    assert "runner       (unresolved -- check constellation.toml [models])" in out
    line = next(l for l in out.splitlines() if "open it:" in l)
    resume_cmd = line.split("open it:", 1)[1].strip().split()
    assert resume_cmd == [render.spine_cmd(), "d1.g1"]

    # and it actually succeeds, self-located and runnable exactly as printed
    r = subprocess.run(resume_cmd, capture_output=True, text=True, env={},
                       cwd=bare_workdir, timeout=20)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "d1.g1" in r.stdout

    # while the brief's own original line, run the same way, still refuses
    r2 = subprocess.run([str(p) for p in open_cmd], capture_output=True, text=True,
                        env={}, cwd=bare_workdir, timeout=20)
    assert r2.returncode != 0
    assert "already exists" in (r2.stdout + r2.stderr)


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


def test_the_fast_suites_workdir_never_touches_a_real_process(
        workdir, monkeypatch, capsys):
    """Closes commitment 20's own proof where the hazard actually lives now
    (commitment 35). `workdir` copies the host repo's real
    `constellation.toml` and strips its `dispatch` entry back out
    (`_without_dispatch_entry`, conftest.py) precisely so nothing in the
    fast suite can start a real harness -- and after gate 2 the caller that
    would have tried is `wait`, not `status`. So this asserts directly that
    `cmd_wait` against a dispatch step and against a panel step, on that
    exact fixture, never reaches `subprocess.Popen` at all, rather than
    trusting that a green suite would have caught a silently-broken guard
    (it would not: `Popen` is fire-and-forget and its own failures are
    caught and logged, never raised). Rendering is asserted alongside it,
    since after this gate a render must reach `Popen` even less."""
    calls = []
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: calls.append((a, k)))

    _mint_dispatch_step(wid="d1", child="d1.g1")
    assert cli.main(["d1", "wait"]) == 0
    cli.main(["d1"])
    capsys.readouterr()

    _mint_panel_step(wid="g9", worker="reviewer")
    assert cli.main(["g9", "wait"]) == 0
    cli.main(["g9"])
    capsys.readouterr()

    assert calls == []
    assert _dispatch_entries("d1") == []
    assert _dispatch_entries("g9") == []
