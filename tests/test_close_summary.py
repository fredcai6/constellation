"""The close summary carries the implement step's own words.

GATE_CLOSE.toml tells whoever closes the gate that the change and deviations
return mechanically, so a parent adjudicating a gate reads what the diff was without
opening the child's journal. `_summary` finds them by shape -- the last
submitted step whose fields carry `change` -- rather than by assembly, form
path or segment id, so a run that fills no such form closes with both keys
empty rather than with no keys at all.
"""

from engine import cli, journal, run as runmod
from gitremote import read_archived, stub_gh
from test_nesting import (
    _dispatch_and_close_plan, _dispatch_plan_critic, _dispatch_review, _drive_plan_to_pause,
    _fill, _fill_close, _fill_consolidate, _fill_gate_close, _fill_open, _fill_plan,
    _mint_first_gate, _response, _work_the_board,
)


def _fill_implement(wid, change, deviations):
    _fill(_response(wid), 'change = "%s"\ndeviations = "%s"\n' % (change, deviations))


def test_gate_close_summary_carries_the_last_implement_round(workdir):
    """A revise round rewrites the diff, so the round that landed is the one
    the parent should read -- not the round the panel sent back."""
    _mint_first_gate()
    cli.main(["open", "run-a-gate", "--parent", "issue17", "--step", "g1"])
    wid = "issue17.g1"

    _fill_implement(wid, "widened the loop bound in src/parser.c",
                    "waived: none")
    cli.main([wid, "submit"])
    _dispatch_review(wid, verdict="revise", findings="gap: the bound is off by one")
    _fill_implement(wid, "read the record count from the header instead",
                    "took the header route the spec left open")
    cli.main([wid, "submit"])
    _dispatch_review(wid)
    _fill_gate_close(wid)
    cli.main([wid, "submit"])
    cli.main([wid, "close"])

    closed = next(e for e in journal.read(wid) if e["kind"] == "closed")
    assert closed["summary"]["change"] == "read the record count from the header instead"
    assert closed["summary"]["deviations"] == "took the header route the spec left open"

    # the same record reaches the parent, which is who the fields are for
    ret = next(e for e in journal.read("issue17")
               if e["kind"] == "return" and e.get("child") == wid)
    assert ret["summary"]["change"] == closed["summary"]["change"]
    assert ret["summary"]["deviations"] == closed["summary"]["deviations"]


def test_close_summary_keys_are_empty_where_no_step_carried_a_change(workdir, monkeypatch):
    """A run-an-issue closing after its plan seam hits round-cap fills no
    implement form anywhere. Both keys are present and empty -- a parent
    reading the summary asks for them the same way whatever closed.

    An issue-tier close now pushes and opens a PR before it archives, so
    `gh` is stubbed (never a real remote) and the closed entry is read off
    the archive it lands in rather than through `journal.read`, which no
    longer resolves an id once `close` has swept it there."""
    wid = "issue19"
    cli.main(["open", "run-an-issue", "--issue", "19", "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    _dispatch_and_close_plan(wid)
    _drive_plan_to_pause(wid)
    # round-cap pauses this segment rather than releasing it to close
    # (plan declares no impasse of its own any more, ruling 2026-09-25;
    # commitment 3, issue84.g2, is what keeps a pause from releasing) --
    # this test's own subject is the close summary once the run *does*
    # reach `forms/CLOSE.toml`, not the pause itself, so the ask it minted,
    # and the marker behind it, are amend-closed directly rather than
    # routed through a resume this test does not exist to drive.
    paused = runmod.state(wid)["current"]
    assert paused["form"] == "skills/gate-conductor/forms/ASK.toml"
    journal.append(wid, "amend", action="close", segment=paused["segment"],
                   step=paused["id"],
                   reason="the critics read the plan against the wrong issue",
                   anchor=paused.get("anchor", False))
    marker = next(s for s in runmod.state(wid)["steps"]
                 if s["segment"] == paused["segment"] and s.get("paused")
                 and s["id"] not in runmod.state(wid)["done"])
    journal.append(wid, "amend", action="close", segment=marker["segment"],
                   step=marker["id"], reason="not resuming this pause",
                   anchor=marker.get("anchor", False))
    _fill_close(wid)
    cli.main([wid, "submit"])

    summary = cli._summary(runmod.state(wid))
    assert summary["change"] == ""
    assert summary["deviations"] == ""

    stub_gh(monkeypatch)
    cli.main([wid, "close"])

    closed = read_archived(workdir, wid, "closed")
    assert closed["summary"]["change"] == ""
    assert closed["summary"]["deviations"] == ""
