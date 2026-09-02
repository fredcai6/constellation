"""Ruling 10: design-it-twice is two more planners, not a field.

On the first plan round the conductor dispatches the planner and two more,
each under a constraint chosen to open a different path, and picks or merges
before the critics read one; a later round re-argues nothing, so it stays a
single planner. `skeleton()` attaches the plan segment's own `panel` (three
entries, `standards/glossary.md`'s design-it-twice) to round one's interior
step; `_mint_segment_round` mints every round after and does not read
`segment.panel`, so a rework round is unaffected.

Three groups, all pinning DESIRED behaviour (this gate's own change, or a
shape this gate now relies on):

1. Structural -- what `skeleton()` and the assembly declare, no journal.
2. Live -- three children dispatched and closed on round one, one on round
   two (a rework), driven through the real assemblies the way
   `test_rework.py` drives everything else. This is also the assertion that
   failed before this gate: without the fix in `_act_on_verdicts`
   (engine/cli.py), closing the third planner child raises `SystemExit` --
   the merged (default) verdict "pass" is not a legal `ruling` for the plan
   segment's own outcome table, which `_decided_here`'s segment-level
   fallback reached by mistake for an interior step that is not the
   segment's transition.
3. The interior-step panel-and-form shape `two_voices` (engine/run.py) has
   held by accident since `two_voices` was written per-step rather than
   per-transition: an interior step carrying both a `panel` and a `form`
   stays open for the conductor once every panelist returns with no
   `verdict` field, the same as a two-voices transition passing. No shipped
   assembly combines panel+form on an interior step (round one's own
   dispatch step carries a panel but no form), so this is exercised
   directly against `run.state` rather than through a real assembly --
   pinning it as DESIRED behaviour, not merely current, per standing
   instruction.
"""

from engine import cli, journal, run as runmod

from test_nesting import (
    _fill,
    _fill_consolidate,
    _fill_open,
    _fill_plan,
    _work_the_board,
    _write_plan_artifact,
)
from test_rework import _fresh_mint

# -- 1. structural -------------------------------------------------------


def test_the_plan_segment_declares_a_three_entry_design_panel():
    asm = runmod.load_assembly("run-an-issue")
    plan = next(s for s in asm["segment"] if s["id"] == "plan")
    assert len(plan["panel"]) == 3
    for entry in plan["panel"]:
        assert entry["worker"] == "planner"
        assert entry["form"] == "skills/planner/forms/PLAN.toml"
        assert entry["criteria"]  # each sibling authors under its own constraint
    # every entry's constraint opens a different path -- no two the same
    assert len({e["criteria"] for e in plan["panel"]}) == 3


def test_skeleton_attaches_the_design_panel_to_round_ones_interior_step():
    steps = runmod.skeleton(runmod.load_assembly("run-an-issue"))
    plan1 = next(s for s in steps if s["id"] == "plan-1")
    assert plan1["dispatches"] == "cut-a-gate"
    assert len(plan1["panel"]) == 3
    assert "form" not in plan1  # two_voices does not apply to round one's own step


# -- 2. live: three on round one, one on round two ------------------------


def _open_planner(parent_wid, step_id, tag):
    cli.main(["open", "give-a-verdict", "--parent", parent_wid, "--step", f"{step_id}.{tag}"])
    return f"{parent_wid}.{step_id}.{tag}"


def _dispatch_and_close_design_panel(wid, step_id="plan-1"):
    """Open, fill and close all three of round one's planner siblings --
    the panel `skeleton()` attached, addressed the same way a verdict
    panel's panelists are (`<step-id>.pN`)."""
    st = runmod.state(wid)
    panel = next(s for s in st["steps"] if s["id"] == step_id)["panel"]
    children = []
    for n in range(1, len(panel) + 1):
        child = _open_planner(wid, step_id, f"p{n}")
        _fill_plan(child, purpose=f"cut {n}", scope=f"scope {n}")
        cli.main([child, "submit"])
        cli.main([child, "close"])
        children.append(child)
    return children


def _drive_to_plan_round_one(wid="issue17"):
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    return wid


def test_round_one_dispatches_three_planners_and_completes_on_the_third(workdir, capsys):
    wid = _drive_to_plan_round_one()
    capsys.readouterr()
    assert runmod.state(wid)["current"]["id"] == "plan-1"

    children = _dispatch_and_close_design_panel(wid)
    capsys.readouterr()
    assert len(children) == 3

    st = runmod.state(wid)
    # all three returns landed under plan-1, attributed to their own child
    assert len(st["returns"]["plan-1"]) == 3
    assert {r["child"] for r in st["returns"]["plan-1"]} == set(children)
    # plan-1 is done and the run walked on to the transition -- no crash in
    # `_act_on_verdicts` closing the third child (the assertion that failed
    # before this gate's fix)
    assert "plan-1" in st["done"]
    assert st["current"]["id"] == "plan"


def test_a_rework_round_dispatches_a_single_planner(workdir, capsys):
    """A revise on the design-panel round mints through `_mint_segment_round`
    -- ruling 10 says a second round re-arguing a settled alternative is
    accretion, so it carries no panel: one planner, addressed the plain
    dispatch way (`plan-1`, not `plan-1.p1`), the same as before this gate."""
    wid = _drive_to_plan_round_one()
    _dispatch_and_close_design_panel(wid)
    capsys.readouterr()

    # the merge is the conductor's: pick one of the three as the live plan,
    # then the transition's own critic panel judges it and sends it back
    st = runmod.state(wid)
    step_id = st["current"]["id"]
    panel = next(s for s in st["steps"] if s["id"] == step_id)["panel"]
    for n in range(1, len(panel) + 1):
        cli.main(["open", "give-a-verdict", "--parent", wid, "--step", f"{step_id}.p{n}"])
        critic = f"{wid}.{step_id}.p{n}"
        _fill(journal.location(critic) / "CRITIC.toml",
              'findings = "gap: needs another look"\n'
              'verdict = "revise"\n')
        cli.main([critic, "submit"])
        cli.main([critic, "close"])
    capsys.readouterr()

    fresh = _fresh_mint(runmod.state(wid), "plan")
    assert fresh["dispatches"] == "cut-a-gate"
    assert "panel" not in fresh  # round two: single planner, not three

    child = f"{wid}.{fresh['id']}"
    cli.main(["open", "cut-a-gate", "--parent", wid, "--step", fresh["id"]])
    _write_plan_artifact(journal.location(child) / "plan.md")
    _fill(journal.location(child) / "REWORK.toml", '''
plan = "%s/plan.md"
purpose = "fix the parser"
scope = "src/parser.c only"
proof = "true"
horizon = "waived: none yet"
findings-addressed = "accepted: picked cut 2, addressed the critic's gap"
deleted = "waived: nothing"
key-terms = "waived: none"
''' % journal.location(child))
    cli.main([child, "submit"])
    cli.main([child, "close"])
    capsys.readouterr()

    assert fresh["id"] in runmod.state(wid)["done"]


# -- 3. the interior-step panel-and-form shape, pinned directly -----------


def test_an_interior_step_with_panel_and_form_stays_open_for_the_conductor(workdir):
    """Not this gate's own change -- `two_voices` (engine/run.py) is computed
    per-step, not per-transition, so this already holds for any step, round
    or transition alike. Pinned here as DESIRED behaviour rather than relied
    on silently: round one's own interior step (this gate's real design
    panel) carries no `form`, so nothing exercises this combination through
    a real assembly today."""
    wid = "synthetic"
    journal.append(wid, "run", title="t", assembly="run-an-issue")
    journal.append(wid, "step", id="s1", segment="plan", panel=[{"criteria": "a"},
                   {"criteria": "b"}], form="skills/planner/forms/PLAN.toml",
                   filler="conductor", anchor=False, terminal=False, validates="",
                   source="open")

    journal.append(wid, "return", step="s1", child=f"{wid}.s1.p1", fields={})
    st = runmod.state(wid)
    assert "s1" not in st["done"]  # one of two panelists in -- unsurprising yet

    journal.append(wid, "return", step="s1", child=f"{wid}.s1.p2", fields={})
    st = runmod.state(wid)
    # both panelists in, neither carried a `verdict` field -- the merged
    # verdict defaults to "pass", and two_voices holds the step open for the
    # conductor's own form submission rather than completing it here
    assert "s1" not in st["done"]
    assert st["current"]["id"] == "s1"
