"""Prior drops surface at the gate's own route room (#127).

A finding has two destinations, never a third (ruling, 2026-09-25,
docs/PURPOSE.md): done, or dropped with its reason recorded where a later
run can find it. The record already exists -- a `rejected` call on the
`calls` table of the submit that ruled it, in that run's own journal,
archived under `<top>/.agent-work/archive/` once the run closes
(`engine/drops.py`). This file proves the two halves: the reader finds one
and extracts its files, and the gate's own ROUTE room shows it only when
this gate's own diff touches one of those files -- recurrence is the
conductor's own call to make, this only puts the prior ones in front of it.
"""

import pathlib

from engine import cli, drops as dropsmod, journal

from test_nesting import (
    _dispatch_and_close_plan, _dispatch_plan_critic, _fill_consolidate,
    _fill_open, _fill_plan_to_execute, _work_the_board,
)
from test_verdict_panels import _fill_implement, _fill_review, _open_panelist, _select


def _archive_a_drop(top, wid, finding, reason):
    """A closed run's own record: one `rejected` call on a `submit` entry,
    moved under `top`'s archive the way `cmd_close` itself leaves it. Not
    driven through a real close -- all `dropsmod.rejected_calls` needs is
    the shape an archived journal actually has."""
    journal.append(wid, "run", title="t", assembly="run-a-gate", root=top)
    journal.append(wid, "submit", step="route",
                   fields={"resolution": "close",
                           "calls": [{"finding": finding, "call": f"rejected: {reason}"}]},
                   root=top)
    archive = pathlib.Path(top) / ".agent-work" / "archive"
    archive.mkdir(parents=True, exist_ok=True)
    (pathlib.Path(top) / ".agent-work" / wid).rename(archive / wid)


# -- (b) the reader finds a rejected call and extracts its files ------------


def test_the_reader_finds_a_rejected_call_and_extracts_its_files(workdir):
    _archive_a_drop(workdir, "oldgate",
                    "the retry loop in engine/cli.py:120 never bounds",
                    "not this gate's to answer")

    drops = dropsmod.rejected_calls(str(workdir))
    assert len(drops) == 1
    d = drops[0]
    assert d["run"] == "oldgate"
    assert d["reason"] == "not this gate's to answer"
    assert "the retry loop" in d["finding"]
    assert d["files"] == {"engine/cli.py"}
    assert d["at"]  # the entry's own timestamp, not blank


# -- (c) the route room shows an intersecting drop, omits one that isn't ----


def _to_the_gates_route_room(wid="issue9"):
    """A run-an-issue driven to its first gate's own ROUTE room, the panel
    having passed -- so the form stands open for the conductor rather than
    disposing of the round on its own."""
    cli.main(["open", "run-an-issue", "--issue", "9", "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    _dispatch_and_close_plan(wid)
    _dispatch_plan_critic(wid, verdict="pass")
    _fill_plan_to_execute(wid, "pass")
    cli.main([wid, "submit"])  # projects the gate

    gate = f"{wid}.g1"
    cli.main(["open", "run-a-gate", "--parent", wid, "--step", "g1"])
    _fill_implement(gate)
    cli.main([gate, "submit"])
    review = _select(gate)
    panelist = _open_panelist(gate, review)
    _fill_review(panelist, "pass")
    cli.main([panelist, "submit"])
    cli.main([panelist, "close"])
    return gate


def test_the_route_room_shows_an_intersecting_drop_and_omits_one_that_does_not(
        workdir, capsys):
    _archive_a_drop(workdir, "oldgate1",
                    "src/parser.c leaks a file handle on the error path",
                    "not this gate's to answer")
    _archive_a_drop(workdir, "oldgate2",
                    "docs/notes.md is stale",
                    "not this gate's to answer")

    gate = _to_the_gates_route_room()
    pathlib.Path("src").mkdir(parents=True, exist_ok=True)
    pathlib.Path("src/parser.c").write_text("int main(void) { return 0; }\n")
    capsys.readouterr()

    cli.main([gate])
    out = capsys.readouterr().out

    assert "dropped before in runs touching these files" in out
    assert "oldgate1" in out and "leaks a file handle" in out
    assert "oldgate2" not in out and "stale" not in out


def test_the_route_room_shows_nothing_where_no_drop_touches_the_diff(workdir, capsys):
    _archive_a_drop(workdir, "oldgate1",
                    "docs/notes.md is stale",
                    "not this gate's to answer")

    gate = _to_the_gates_route_room()
    pathlib.Path("src").mkdir(parents=True, exist_ok=True)
    pathlib.Path("src/parser.c").write_text("int main(void) { return 0; }\n")
    capsys.readouterr()

    cli.main([gate])
    out = capsys.readouterr().out
    assert "dropped before in runs touching these files" not in out
