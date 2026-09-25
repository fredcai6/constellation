"""Ruling 10, shelved (#96): design-it-twice's three-sibling round one is
gone from `assemblies/run-an-issue/ASSEMBLY.toml` -- the plan segment
declares no `panel` any more, so round one is a single planner's dispatch,
exactly the shape `_mint_segment_round` already mints for every round after
the first.

Two groups, both pinning the single-planner shape as DESIRED behaviour (what
this gate's deletion leaves standing):

1. Structural -- what `skeleton()` and the assembly declare, no journal: the
   plan segment carries no `panel`, and round one's own interior step
   (`plan-1`) is a plain dispatch, no different in shape from a rework round.
2. Live -- one planner dispatched and closed on round one, one more on round
   two (a rework), driven through the real assemblies the way
   `test_rework.py` drives everything else.

The interior-step panel-and-form shape (`two_voices`, engine/run.py, holding
for any step carrying both a `panel` and a `form`, round or transition alike)
is pinned directly against `run.state` in `test_verdict_route.py` now --
round one's own step never carried a `form` beside its `panel`, so nothing in
this tree ever exercised that combination through a real assembly, and
nothing here promises three planners any more.
"""

from engine import cli, journal, run as runmod

from test_nesting import (
    _dispatch_and_close_plan,
    _dispatch_plan_critic,
    _fill,
    _fill_consolidate,
    _fill_open,
    _response,
    _work_the_board,
    _write_plan_artifact,
)
from test_rework import _fresh_mint

# -- 1. structural -------------------------------------------------------


def test_the_plan_segment_declares_no_panel():
    asm = runmod.load_assembly("run-an-issue")
    plan = next(s for s in asm["segment"] if s["id"] == "plan")
    assert "panel" not in plan


def test_skeleton_mints_round_ones_interior_step_as_a_plain_dispatch():
    steps = runmod.skeleton(runmod.load_assembly("run-an-issue"))
    plan1 = next(s for s in steps if s["id"] == "plan-1")
    assert plan1["dispatches"] == "cut-a-gate"
    assert "panel" not in plan1  # no different in shape from a rework round
    assert "form" not in plan1


# -- 2. live: one planner on round one, one more on round two ------------


def _drive_to_plan_round_one(wid="issue17"):
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    return wid


def test_round_one_dispatches_a_single_planner_and_completes_on_its_return(workdir, capsys):
    wid = _drive_to_plan_round_one()
    capsys.readouterr()
    assert runmod.state(wid)["current"]["id"] == "plan-1"

    child = _dispatch_and_close_plan(wid, "plan-1")
    capsys.readouterr()
    assert child == f"{wid}.plan-1"  # the plain dispatch address, not `.p1`

    st = runmod.state(wid)
    assert len(st["returns"]["plan-1"]) == 1
    assert st["returns"]["plan-1"][0]["child"] == child
    assert "plan-1" in st["done"]
    assert st["current"]["id"] == "plan"


def test_an_incorporation_round_also_dispatches_a_single_planner(workdir, capsys):
    """A revise on round one, ruled `incorporate` on the route form, mints
    the planner's one pass through `_mint_segment_round` -- one
    planner, addressed the plain dispatch way (`plan-<n>`, never `.pN`), the
    same shape round one now takes too."""
    wid = _drive_to_plan_round_one()
    _dispatch_and_close_plan(wid, "plan-1")
    capsys.readouterr()

    _dispatch_plan_critic(wid, verdict="revise", findings="gap: needs another look")
    capsys.readouterr()

    fresh = _fresh_mint(runmod.state(wid), "plan")
    assert fresh["dispatches"] == "cut-a-gate"
    assert "panel" not in fresh  # round two: still a single planner

    child = f"{wid}.{fresh['id']}"
    cli.main(["open", "cut-a-gate", "--parent", wid, "--step", fresh["id"]])
    _write_plan_artifact(journal.location(child) / "plan.md")
    _fill(_response(child), '''
plan = "%s/plan.md"
purpose = "fix the parser"
scope = "src/parser.c only"
proof = "true"
horizon = "waived: none yet"
findings-addressed = "accepted: addressed the critic's gap"
deleted = "waived: nothing"
key-terms = "waived: none"
''' % journal.location(child))
    cli.main([child, "submit"])
    cli.main([child, "close"])
    capsys.readouterr()

    assert fresh["id"] in runmod.state(wid)["done"]
