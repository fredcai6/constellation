"""Restore what a dispatched plan round no longer carries.

g1 made every round of the plan segment a dispatch: a fresh child run each
time. That broke two crossings on one boundary. First, `_measure_artifacts`
(engine/cli.py) records an artifact's length into the *submitting* run's own
journal -- the dispatched child's, gone the moment it closes -- so the
parent's own journal, which `render.drift` reads to compare a round against
the ones before it, never gained an entry; the room printed no movement
across rounds. Second, `skills/planner/SKILL.md` promises a round's own
`horizon` arrives as prefill for the next round's dispatched planner, but
the rework round's prefill (`_act_on_verdicts`) carried only the panel's
`findings` -- the horizon never crossed.

Both are closed here: `_fold_measures` (engine/cli.py) re-homes a closing
child's own `measure` entries onto the parent step that dispatched it, at
the return -- under that step's own segment, so `render.drift` (which
filters by the current step's segment) finds them again. `_act_on_verdicts`
threads the judged round's own `horizon` field into the next round's
prefill beside `findings`.

Drives the real assemblies end to end, like test_nesting.py -- no
fixtures standing in for the crossing under test.
"""

from engine import cli, journal, run as runmod

from test_nesting import (
    _dispatch_plan_critic,
    _fill,
    _fill_consolidate,
    _fill_open,
    _fill_plan,
    _work_the_board,
)
from test_rework import _fresh_mint, _plan_measures


def _drive_to_first_round(wid="issue44", title="a plan that grows"):
    """Open a real run-an-issue and drive it to the plan segment's first
    dispatch step, `plan-1` -- the same setup test_rework.py's own drift
    test used before the crossing broke."""
    cli.main(["open", "run-an-issue", "--issue", wid.removeprefix("issue"), "--title", title])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    return wid


# -- 1. the parent holds the measure its dispatched round submitted ---------


def test_a_parent_holds_the_measure_its_dispatched_round_submitted(workdir, capsys):
    wid = _drive_to_first_round()

    cli.main(["open", "cut-a-gate", "--parent", wid, "--step", "plan-1"])
    child = f"{wid}.plan-1"
    art = journal.location(child) / "plan.md"
    art.write_text("one two three four five six seven eight nine ten\n")
    _fill_plan(child)
    cli.main([child, "submit"])
    assert _plan_measures(child) == [10]  # the child's own journal, as before

    cli.main([child, "close"])
    capsys.readouterr()

    # the crossing under test: the parent's own journal now holds it too,
    # attributed to the step that dispatched the round -- not to the
    # child's local "cut" segment, which the parent's assembly does not have
    assert _plan_measures(wid) == [10]


# -- 2. two rounds produce a drift the parent's own room renders ------------


def test_two_rounds_produce_a_drift_the_rooms_renders(workdir, capsys):
    wid = _drive_to_first_round()

    # round one: design-it-twice (ruling 10) -- three siblings, filled
    # identically here since this test is about the drift a rework round
    # produces, not about how the room would reconcile three same-round
    # entries (an open question ruling 10 did not settle).
    for n in (1, 2, 3):
        child = f"{wid}.plan-1.p{n}"
        cli.main(["open", "give-a-verdict", "--parent", wid, "--step", f"plan-1.p{n}"])
        art = journal.location(child) / "plan.md"
        art.write_text("one two three four five six seven eight nine ten\n")
        _fill_plan(child)
        cli.main([child, "submit"])
        cli.main([child, "close"])
    capsys.readouterr()

    _dispatch_plan_critic(wid, verdict="revise", findings="gap: thin")
    capsys.readouterr()

    fresh = _fresh_mint(runmod.state(wid), "plan")
    assert fresh["dispatches"] == "cut-a-gate"
    rework_child = f"{wid}.{fresh['id']}"
    cli.main(["open", "cut-a-gate", "--parent", wid, "--step", fresh["id"]])
    rework_art = journal.location(rework_child) / "plan.md"
    rework_art.write_text("one two three four five six seven eight nine ten eleven twelve\n")
    _fill(journal.location(rework_child) / "REWORK.toml", '''
plan = "%s"
purpose = "fix the parser to handle EOF without a trailing newline"
scope = "src/parser.c only"
proof = "true"
horizon = "waived: none yet"
findings-addressed = "accepted: thickened gate 1"
deleted = "nothing; the growth is all prose"
key-terms = "waived: none"
''' % rework_art)
    cli.main([rework_child, "submit"])
    cli.main([rework_child, "close"])
    capsys.readouterr()

    assert _plan_measures(wid) == [10, 10, 10, 12]

    # a fresh panel is outstanding right after the round closes -- that
    # room shows the panel brief, not drift (`_panel_status`, unrelated to
    # this gate). Drift is visible once the panel passes and releases into
    # the two-voices transition form: the first step in this segment that
    # is neither a dispatch nor an outstanding panel.
    _dispatch_plan_critic(wid, verdict="pass")
    capsys.readouterr()

    cli.main([wid])
    out = capsys.readouterr().out
    assert "12 prose words" in out
    assert "on the first round" in out


# -- 3. a rework round's dispatched planner receives the prior horizon ------


def test_a_rework_rounds_dispatched_planner_receives_the_prior_horizon(workdir, capsys):
    wid = _drive_to_first_round()
    horizon = ("gate 2 likely covers the CLI flag; gate 3 the config loader, "
               "if gate 2 does not absorb it")

    # round one: design-it-twice (ruling 10) -- three siblings. The carry
    # this test proves reads the segment's most recent non-panel step's
    # `done` entry, which is whichever sibling's return landed last
    # (`_act_on_verdicts`, engine/cli.py) -- p3 here, so its own horizon is
    # the one that must cross.
    for n in (1, 2):
        sib = f"{wid}.plan-1.p{n}"
        cli.main(["open", "give-a-verdict", "--parent", wid, "--step", f"plan-1.p{n}"])
        (journal.location(sib) / "plan.md").write_text("one two three\n")
        _fill_plan(sib)
        cli.main([sib, "submit"])
        cli.main([sib, "close"])
    cli.main(["open", "give-a-verdict", "--parent", wid, "--step", "plan-1.p3"])
    child = f"{wid}.plan-1.p3"
    loc = journal.location(child)
    (loc / "plan.md").write_text("one two three\n")
    _fill(loc / "PLAN.toml", '''
plan = "%s/plan.md"
purpose = "fix the parser to handle EOF without a trailing newline"
scope = "src/parser.c only"
proof = "true"
horizon = "%s"
key-terms = "waived: none"
''' % (loc, horizon))
    cli.main([child, "submit"])
    cli.main([child, "close"])
    capsys.readouterr()

    _dispatch_plan_critic(wid, verdict="revise", findings="gap: thin")
    capsys.readouterr()

    # the crossing, at the parent: the freshly minted round already carries
    # the prior round's horizon in its own prefill, beside the findings
    fresh = _fresh_mint(runmod.state(wid), "plan")
    assert horizon in fresh["prefill"].get("horizon", "")
    assert "gap: thin" in fresh["prefill"]["findings"]

    # the crossing, at the child: skills/planner/SKILL.md promises the
    # dispatched planner sees it too, as prefill in its own room
    cli.main(["open", "cut-a-gate", "--parent", wid, "--step", fresh["id"]])
    rework_child = f"{wid}.{fresh['id']}"
    assert horizon in runmod.state(rework_child)["prefill"].get("horizon", "")
