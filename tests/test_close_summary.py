"""The close summary carries the implement step's own words.

GATE_CLOSE.toml tells the implementer that the change and deviations return
mechanically, so a parent adjudicating a gate reads what the diff was without
opening the child's journal. `_summary` finds them by shape -- the last
submitted step whose fields carry `change` -- rather than by assembly, form
path or segment id, so a run that fills no such form closes with both keys
empty rather than with no keys at all.
"""

import pathlib

import pytest

from engine import cli, journal, run as runmod
from test_nesting import (
    _dispatch_plan_critic, _dispatch_review, _fill, _fill_close,
    _fill_consolidate, _fill_gate_close, _fill_open, _fill_plan,
    _mint_two_gates, _work_the_board,
)

REPO = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONSTELLATION_SESSION", "test-session")
    (tmp_path / "constellation.toml").write_text((REPO / "constellation.toml").read_text())
    return tmp_path


def _fill_implement(wid, change, deviations):
    _fill(journal.location(wid) / "IMPLEMENT.toml",
          'change = "%s"\ndeviations = "%s"\n' % (change, deviations))


def test_gate_close_summary_carries_the_last_implement_round(workdir):
    """A revise round rewrites the diff, so the round that landed is the one
    the parent should read -- not the round the panel sent back."""
    _mint_two_gates()
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


def test_close_summary_keys_are_empty_where_no_step_carried_a_change(workdir):
    """A run-an-issue closing after its critics escalated fills no implement
    form anywhere. Both keys are present and empty -- a parent reading the
    summary asks for them the same way whatever closed."""
    wid = "issue19"
    cli.main(["open", "run-an-issue", "--issue", "19", "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    _fill_plan(wid)
    cli.main([wid, "submit"])
    _dispatch_plan_critic(wid, verdict="escalate", findings="gap: wrong artifact entirely")
    _fill(journal.location(wid) / "IMPASSE.toml",
          'ruling = "up"\nwhy = "the critics read the plan against the wrong issue"\n')
    cli.main([wid, "submit"])
    _fill_close(wid)
    cli.main([wid, "submit"])
    cli.main([wid, "close"])

    summary = cli._summary(runmod.state(wid))
    assert summary["change"] == ""
    assert summary["deviations"] == ""

    closed = next(e for e in journal.read(wid) if e["kind"] == "closed")
    assert closed["summary"]["change"] == ""
    assert closed["summary"]["deviations"] == ""
