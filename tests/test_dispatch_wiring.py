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

from engine import checks, cli, journal, render
from test_brief import _mint_dispatch_step, _mint_panel_step


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
#   for comfortably longer than the handful of milliseconds between the
#   marker landing and this file's own very next render.
# Rejected: asserting on `_dispatch_entries` alone and skipping the "working"
#   word. That would stop proving commitment 12's own liveness read at all,
#   which is the one thing these two mechanics tests were extended to check.
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

    # rendered again -- already-started, so nothing new is spawned, and the
    # row says "working" instead of printing a brief beside a live pid
    cli.main(["d1"])
    out = capsys.readouterr().out
    time.sleep(0.2)
    assert len(_dispatch_entries("d1")) == 1
    assert "working" in out
    assert "brief --" not in out


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

    # rendered again -- same "working, no brief" story as the dispatch step
    cli.main(["g9"])
    out = capsys.readouterr().out
    time.sleep(0.2)
    assert len(_dispatch_entries("g9")) == 1
    assert "working" in out
    assert "brief --" not in out


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
    already carries its own `dispatch-started` record whose pid (999999)
    reads as dead, p3 is genuinely outstanding. One call to `_panel_status`
    (via `cli.main`) must spawn exactly the one outstanding child -- not the
    returned one, and not the one already started -- leaving exactly one
    new journal record and one new log file, both keyed to p3's own child
    id, and must report all three siblings' own state on that one render
    (commitment 11)."""
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

    assert "panelist p1 (returned)" in out
    assert "panelist p2 (gone without returning)" in out
    assert "panelist p3 (working)" in out

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


def test_not_dispatched_from_absence_and_from_a_failed_attempt_differ_only_by_log(
        bare_workdir, capsys):
    """Commitment 13: a spawn attempt that failed renders the same word a
    wholly absent entry gets -- "not dispatched" both times -- distinguished
    only by whether that child's own log holds a reason. `d1` here sees no
    `constellation.toml` at all (a wholly absent entry, no log possible);
    `d2` sees a malformed `[commands]` `dispatch` (today's single-string
    shape, not a list) -- a real entry whose attempt fails and is logged."""
    _mint_dispatch_step(wid="d1", child="d1.g1")
    cli.main(["d1"])
    out_absent = capsys.readouterr().out

    assert "d1.g1 (not dispatched)" in out_absent
    assert not (journal.location("d1") / "dispatch.g1.log").exists()

    (bare_workdir / "constellation.toml").write_text(
        '[commands]\ndispatch = "claude -p {brief}"\n')
    _mint_dispatch_step(wid="d2", child="d2.g1")
    cli.main(["d2"])
    out_failed = capsys.readouterr().out

    assert "d2.g1 (not dispatched)" in out_failed
    log = journal.location("d2") / "dispatch.g1.log"
    assert log.is_file()
    assert checks.DISPATCH_MALFORMED in log.read_text(encoding="utf-8")


def test_a_working_childs_row_omits_the_brief_and_every_command(bare_workdir, capsys):
    """Commitment 14: printing a manual dispatch command beside a live pid
    is the exact double-dispatch commitment 19 exists to prevent, so a
    working child's row carries none of a brief's own ingredients -- no
    role, no tier, no runner, no `open it:` line (commitment 23's other
    half: a working row deliberately carries none of this)."""
    marker = bare_workdir / "spawned"
    _throwaway_dispatch(bare_workdir, marker)
    _mint_panel_step(wid="g9", worker="reviewer")

    cli.main(["g9"])
    capsys.readouterr()
    assert _await(marker, 1)

    cli.main(["g9"])
    out = capsys.readouterr().out

    assert "panelist p1 (working)" in out
    assert "brief --" not in out
    assert "open it:" not in out
    assert "runner" not in out


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
