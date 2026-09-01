"""The plan step is a dispatch, not a local form the conductor fills.

Ruling 6: the conductor stops writing what it will judge. Before this, the
plan segment declared `worker = "conductor"`, so the issue-conductor
authored PLAN.toml and then ruled on the panel attacking it. Now the
segment's first round is minted as a dispatch to `cut-a-gate` -- a fresh
child, opened cold, whose own conductor is the planner -- so the round the
issue-conductor rules on was never its own draft.

Two things, proven separately, the way `test_brief.py` proves a dispatch
brief generally: the skeleton mints the shape (structural, no rendering),
and the shape renders correctly once minted (a real brief, naming the real
assembly). A third: the role the brief announces resolves to a real skill
file, because a brief naming a role with nothing behind it is a promise
nothing can fill.
"""

import pathlib

import pytest

from engine import cli, journal, run as runmod
from conftest import REPO


def test_the_plan_segment_declares_a_dispatch_to_cut_a_gate():
    """The assembly itself, not a fixture: `dispatches` and `worker` sit on
    the plan segment the way they already sit on execute's."""
    asm = runmod.load_assembly("run-an-issue")
    plan = next(s for s in asm["segment"] if s["id"] == "plan")
    assert plan["dispatches"] == "cut-a-gate"
    assert plan["worker"] == "planner"


def test_skeleton_mints_the_plan_segments_first_round_as_a_dispatch():
    """`plan-1` -- the step `open` mints for the plan segment -- carries
    `dispatches`, not `form`: it is opened as a child, not filled in place."""
    steps = runmod.skeleton(runmod.load_assembly("run-an-issue"))
    plan1 = next(s for s in steps if s["id"] == "plan-1")
    assert plan1["dispatches"] == "cut-a-gate"
    assert "form" not in plan1
    assert plan1["filler"] == "planner"


def test_cut_a_gate_is_one_anchored_terminal_step_naming_the_planner():
    """The dispatched assembly's own shape: give-a-verdict's pattern, one
    segment deep, no interior of its own to grow."""
    asm = runmod.load_assembly("cut-a-gate")
    assert asm["conductor"] == "planner"
    assert len(asm["segment"]) == 1
    seg = asm["segment"][0]
    t = seg["transition"]
    assert t["anchor"] and t["terminal"]
    assert t["form"] == "skills/planner/forms/PLAN.toml"
    assert t["filler"] == "planner"


def test_plan_segments_dispatch_step_renders_a_brief_naming_cut_a_gate(workdir, capsys):
    """The shape `open` would mint, minted directly the way `test_brief.py`
    mints an execute-segment dispatch step -- so this proves the render, not
    a second copy of the open flow `test_roundtrip.py` already drives."""
    journal.append("i1", "run", title="t", assembly="run-an-issue")
    journal.append("i1", "step", id="plan-1", segment="plan", dispatches="cut-a-gate",
                   filler="planner", prefill={}, anchor=False, terminal=False,
                   validates="", source="open")
    capsys.readouterr()

    cli.main(["i1"])
    out = capsys.readouterr().out

    assert "i1.plan-1" in out                        # the child id
    assert "role         planner" in out              # cut-a-gate's own conductor
    line = next(l for l in out.splitlines() if "open it:" in l)
    open_cmd = line.split("open it:", 1)[1].strip()
    parts = open_cmd.split()
    assert pathlib.Path(parts[0]).is_file()            # self-located, not bare
    assert parts[1:] == ["open", "cut-a-gate", "--parent", "i1", "--step", "plan-1"]


def test_a_dispatch_step_is_not_submitted_locally(workdir, capsys):
    """The engine refuses a submit on a dispatch step -- the same refusal
    execute's gate steps already get, proven here for plan-1's shape."""
    journal.append("i1", "run", title="t", assembly="run-an-issue")
    journal.append("i1", "step", id="plan-1", segment="plan", dispatches="cut-a-gate",
                   filler="planner", prefill={}, anchor=False, terminal=False,
                   validates="", source="open")
    capsys.readouterr()

    with pytest.raises(SystemExit) as e:
        cli.main(["i1", "submit"])
    assert "cut-a-gate" in str(e.value)


def test_resolve_skill_planner_returns_a_real_file():
    path = runmod.resolve_skill("planner")
    assert path is not None
    assert path == REPO / "skills" / "planner" / "SKILL.md"
    assert path.is_file()
