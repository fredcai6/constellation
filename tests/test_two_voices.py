"""The two-voices transition: a step carrying both a panel and a form runs
the panel first, and completes on the form's submit -- never the reverse.

run-an-issue's plan-to-execute was the first transition in the repo shaped
this way: the critic panel reads the plan, and the mint form that cuts gates
is what actually releases the round. Before this, four sites in cli.py
guarded on `panel and not form`, so a form-carrying transition took the
plain form path and the critic was never dispatched -- a plan could mint
gates without ever being attacked. Understand's own consolidate is now
shaped the same way top to bottom, not only for its panel half: both of the
panel's words release, so the step holds open for its own form on a revise
as much as on a pass, and the conductor's own `rework` (not the panel's
`revise`) is what sends the round back -- ruling 3 (2026-09-02) gave
plan-to-execute this shape first and its 2026-09-03 follow-up gave
consolidate the same one, so `_work_the_board` below drives both the same
way now, on every fixture in this file. test_verdict_route.py has the
fuller account of that shape, mirrored from run-a-gate's own
review/ROUTE.toml; this file keeps the two-voices mechanism itself (panel
first, form completes it) as its own subject. These tests drive the real
`run-an-issue` assembly (the first, end to end) and the real two-step
mechanism `run.py`/`cli.py` provide (the rest, via direct journal fixtures,
the same way test_verdict_panels.py isolates a revise round).
test_verdict_panels.py is the check that run-a-gate's panel-only review is
unchanged by any of this.
"""

import pathlib

import pytest

from engine import cli, forms, journal, run as runmod
from conftest import REPO
from test_nesting import _write_plan_artifact
from test_explore import _to_rework

CRITIC = "skills/critic/forms/CRITIC.toml"
CONSOLIDATE = REPO / "assemblies/run-an-issue/forms/CONSOLIDATE.toml"


def _fill(path, text):
    pathlib.Path(path).write_text(text)


# -- real end to end: open -> understand -> plan -> plan-to-execute ---------


def _fill_open(wid):
    # the `issue` field names a file in the work location, so write one
    issue = f".agent-work/{wid}/issue.md"
    _fill(issue, "The parser drops the last record of a file with no "
                 "trailing newline.\n")
    _fill(f".agent-work/{wid}/OPEN.toml", f'''
issue = "{issue}"

authority = """
Principal: Tommy, live. I own driving this to a merged fix; gaps go to him."""

[[questions]]
question = "Which inputs drop the last record?"
type = "fact"
''')


def _work_the_board(wid):
    """Resolve the seeded board, then take the spec-writer's own round
    through its cold panel -- both now stand between the board and
    consolidate."""
    b = pathlib.Path(f".agent-work/{wid}/UNDERSTAND.toml")
    b.write_text(b.read_text().replace(
        'status = "open"', 'status = "answered"\nanswer = "settled."'))
    _fill_spec(wid)
    cli.main([wid, "submit"])
    _dispatch_panel(wid, "understand", verdict="pass")


def _fill_spec(wid):
    loc = pathlib.Path(f".agent-work/{wid}")
    (loc / "spec.md").write_text("1. settled.\n")
    _fill(loc / "SPEC.toml", 'spec = "%s/spec.md"\n' % loc)


def _fill_consolidate(wid, settle="waived: none", resolution="pass", calls=""):
    body = 'resolution = "%s"\n' % resolution
    if resolution in ("pass", "revise"):
        body += ('\nspec = ".agent-work/%s/spec.md"\n'
                 'key-terms = "waived: none"\n'
                 'settle = "%s"\n') % (wid, settle)
    if calls:
        body += "\n" + calls
    _fill(f".agent-work/{wid}/CONSOLIDATE.toml", body)


def _fill_plan_form(wid):
    loc = journal.location(wid)
    _write_plan_artifact(loc / "plan.md")
    _fill(loc / "PLAN.toml", '''
plan = "%s/plan.md"
purpose = "fix the parser to handle EOF without a trailing newline"
scope = "src/parser.c only"
proof = "true"
horizon = "waived: none yet"
key-terms = "waived: none"
''' % loc)


def _dispatch_and_close_plan(pwid, step_id="plan-1", fill_fn=None):
    """Open cut-a-gate at the plan segment's dispatch step, fill whichever
    form its own step names, submit and close it -- give-a-verdict's own
    shape, one form deep. Every round dispatches, not only the first:
    `fill_fn` (default `_fill_plan_form`) lets a caller pass
    `_fill_rework_form` for a revise round, whose dispatch step carries a
    form override selecting REWORK.toml."""
    panel = next(s for s in runmod.state(pwid)["steps"] if s["id"] == step_id).get("panel")
    if not panel:
        cli.main(["open", "cut-a-gate", "--parent", pwid, "--step", step_id])
        child_wid = f"{pwid}.{step_id}"
        (fill_fn or _fill_plan_form)(child_wid)
        cli.main([child_wid, "submit"])
        cli.main([child_wid, "close"])
        return child_wid
    for n in range(1, len(panel) + 1):
        cli.main(["open", "give-a-verdict", "--parent", pwid, "--step", f"{step_id}.p{n}"])
        child_wid = f"{pwid}.{step_id}.p{n}"
        (fill_fn or _fill_plan_form)(child_wid)
        cli.main([child_wid, "submit"])
        cli.main([child_wid, "close"])
    return child_wid


def _fill_rework_form(wid, findings_addressed="accepted: made gate 1 testable",
                      deleted="the restated background; the gates already carry it"):
    """A revise round's interior step is REWORK.toml, not PLAN.toml. `wid`
    is the dispatched child's own id -- a revise round dispatches too."""
    loc = journal.location(wid)
    _write_plan_artifact(loc / "plan.md")
    _fill(loc / "REWORK.toml", '''
plan = "%s/plan.md"
purpose = "fix the parser to handle EOF without a trailing newline"
scope = "src/parser.c only"
proof = "true"
horizon = "waived: none yet"
findings-addressed = "%s"
deleted = "%s"
key-terms = "waived: none"
''' % (loc, findings_addressed, deleted))


def _fill_plan_to_execute(wid, resolution="pass"):
    """The conductor's own route form at the plan seam (ruling 3): `resolution`
    is the conductor's own typed decision, and `plan` -- the pointer that
    projects the gate -- is filled only where the round releases with
    something to project."""
    body = 'resolution = "%s"\n' % resolution
    if resolution in ("pass", "revise"):
        _write_plan_artifact(f".agent-work/{wid}/plan.md")
        body += '\nplan = ".agent-work/%s/plan.md"\n' % wid
    _fill(f".agent-work/{wid}/PLAN_TO_EXECUTE.toml", body)


def _fill_verdict(wid, verdict, findings="none: waived: clean"):
    """The plan panel declares CRITIC.toml, so that is the form on disk -- a
    critic reads a plan with the critic's form, not the reviewer's."""
    _fill(journal.location(wid) / "CRITIC.toml", '''
findings = "%s"
verdict = "%s"
''' % (findings, verdict))


def _dispatch_critic(pwid, step_id, verdict="pass", findings="none: waived: clean", n=1):
    """Open the plan-to-execute panel's nth panelist, fill and close it."""
    tag = f"{step_id}.p{n}"
    cli.main(["open", "give-a-verdict", "--parent", pwid, "--step", tag])
    panelist = f"{pwid}.{tag}"
    _fill_verdict(panelist, verdict, findings)
    cli.main([panelist, "submit"])
    cli.main([panelist, "close"])
    return panelist


def _dispatch_panel(pwid, step_id, verdict="pass", findings="none: waived: clean",
                    resolution=None):
    """Clear a panel step: every panelist the assembly declares, not just the
    first. The step completes on the last verdict, so closing one of three
    leaves the transition outstanding.

    Both of plan-to-execute's and consolidate's own words release now
    (ruling 3, and its 2026-09-03 follow-up), so a revise leaves the step
    standing open on its own form rather than folding shut. Where that is
    what just happened (the step is still `current`, standing on
    PLAN_TO_EXECUTE.toml or CONSOLIDATE.toml), this also disposes of the
    round on that form, defaulting `resolution` to `"rework"` so a caller
    driving straight through still reaches the fresh round it always did."""
    panel = next(s for s in runmod.state(pwid)["steps"] if s["id"] == step_id)["panel"]
    for n in range(1, len(panel) + 1):
        _dispatch_critic(pwid, step_id, verdict, findings, n=n)
    current = runmod.state(pwid).get("current")
    form = current.get("form") if current else ""
    if (verdict == "revise" and current and current["id"] == step_id
            and form in ("forms/PLAN_TO_EXECUTE.toml", "forms/CONSOLIDATE.toml")):
        if form == "forms/PLAN_TO_EXECUTE.toml":
            _fill_plan_to_execute(pwid, resolution or "rework")
        else:
            _fill_consolidate(pwid, resolution=resolution or "rework")
        cli.main([pwid, "submit"])


def _drive_to_plan_to_execute(wid="issue99", settle="waived: none"):
    """Open a real run-an-issue and drive it to the plan-to-execute
    transition, right after the plan interior is submitted -- the moment
    the critic must fire before anything else."""
    cli.main(["open", "run-an-issue", "--issue", "99", "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid, settle)
    cli.main([wid, "submit"])
    _dispatch_and_close_plan(wid)
    return wid


# -- 1. the critic fires before any gate is minted ---------------------------


def test_plan_to_execute_dispatches_its_critic_before_any_gate_is_minted(workdir, capsys):
    wid = _drive_to_plan_to_execute()
    capsys.readouterr()

    st = runmod.state(wid)
    assert st["current"]["id"] == "plan"          # the transition, not past it
    assert not any(s["id"] == "g1" for s in st["steps"])  # nothing minted yet

    cli.main([wid])
    out = capsys.readouterr().out
    assert f"spine open give-a-verdict --parent {wid} --step plan.p1" in out
    assert "intent-fit" in out                     # the critic's own criteria
    assert "outstanding" in out
    assert "PLAN_TO_EXECUTE" not in out             # the form is not offered yet

    # the form cannot be filled around the critic either
    with pytest.raises(SystemExit) as e:
        cli.main([wid, "submit"])
    assert "outstanding" in str(e.value)

    _dispatch_panel(wid, "plan", verdict="pass")
    capsys.readouterr()

    # now, and only now, is the mint form reachable
    st = runmod.state(wid)
    assert st["current"]["id"] == "plan"            # same step id -- resolved, not replaced
    _fill_plan_to_execute(wid)
    cli.main([wid, "submit"])
    capsys.readouterr()

    st = runmod.state(wid)
    assert any(s["id"] == "g1" for s in st["steps"])
    assert "plan" in st["done"]                     # the transition itself completed on submit


def test_the_understanding_reaches_the_critic_across_the_segment_boundary(workdir, capsys):
    """Consolidate `carries`, so its fields join the run's prefill and every
    later dispatch gets them.

    A panelist's prefill is built from prior steps in its *own* segment, so
    without this the critic -- the coldest reader in the run, and the one
    consolidate is written for -- is the only participant who never sees the
    understanding. The critic form promises it arrives; this is what makes
    that true rather than a claim.
    """
    wid = _drive_to_plan_to_execute()
    capsys.readouterr()

    assert runmod.state(wid)["prefill"]["spec"] == f".agent-work/{wid}/spec.md"

    cli.main(["open", "give-a-verdict", "--parent", wid, "--step", "plan.p1"])
    capsys.readouterr()
    prefill = runmod.state(f"{wid}.plan.p1")["prefill"]
    assert prefill["spec"] == f".agent-work/{wid}/spec.md"      # the understanding crossed
    # the artifact still rides -- the segment's own most recent non-panel
    # step is `plan-1` whichever way it was filled, and the fields that
    # land in `done` are whichever design-panel sibling's return closed
    # last (`_act_on_verdicts`, engine/cli.py) -- p3, dispatched third
    assert prefill["plan"] == f".agent-work/{wid}/plan-1/p3/plan.md"
    assert prefill["criteria"].startswith("intent-fit")


# [settle-carries]
# Rationale: no part of the understand board crosses a segment boundary, so
# consolidate's `settle` is the only carrier for what the excursion column
# produced. The test pins both halves -- the note that says report, and the
# prefill hop that delivers it to the fresh-context panelist.
# Rejected: reading the board file from the planner's step to prove the
# answers arrived -- there is no such read, which is the whole reason this
# field carries.
def test_settle_carries_the_boards_answers(workdir, capsys):
    """`settle` reports the board's excursion column; it does not re-ask it.

    The board is a document in the work location and no part of it crosses a
    segment boundary. Consolidate `carries`, so its fields join the run's
    prefill -- which makes this one field the only path by which a per-row
    brief and its return reach the planner, the fresh-context panel, and the journal's
    next reader. The mandate to name an excursion or decline one is already
    on every row, once per row; asking for it a second time here collects one
    fresh answer and drops the answers the column already holds.
    """
    note = next(f for f in forms.load(CONSOLIDATE)["fields"]
                if f["id"] == "settle")["note"]
    assert "excursion" in note        # it names the column it reports
    assert "returns" in note          # what a dispatch produced
    assert "decline" in note          # and what a decline produced

    carried = ("q1 dispatched prior-art on retry budgets; it returned three "
               "attempts as the ecosystem default. q2 declined one: the code "
               "answers it outright.")
    wid = _drive_to_plan_to_execute(settle=carried)
    capsys.readouterr()

    assert runmod.state(wid)["prefill"]["settle"] == carried

    cli.main(["open", "give-a-verdict", "--parent", wid, "--step", "plan.p1"])
    capsys.readouterr()
    assert runmod.state(f"{wid}.plan.p1")["prefill"]["settle"] == carried


# -- 2. revise sends the plan back with findings attributed, panel re-fires -


def test_a_revise_holds_the_form_and_the_conductors_rework_sends_findings_back_attributed(workdir, capsys):
    """Ruling 3 (2026-09-02): both of the panel's own words release now, so a
    revise no longer refires the round on its own -- it holds `plan` open for
    the conductor's own form, the same as run-a-gate's review/ROUTE.toml.
    Only the conductor's own `rework` (not the panel's `revise`) sends the
    round back, and it still carries the panel's findings, attributed."""
    wid = _drive_to_plan_to_execute()
    capsys.readouterr()

    panel = next(s for s in runmod.state(wid)["steps"] if s["id"] == "plan")["panel"]
    for n in range(1, len(panel) + 1):
        _dispatch_critic(wid, "plan", verdict="revise",
                         findings="gap: gate 1 is untestable", n=n)
    capsys.readouterr()

    st = runmod.state(wid)
    assert st["current"]["id"] == "plan"            # held open, not released by the panel alone
    assert st["current"]["form"] == "forms/PLAN_TO_EXECUTE.toml"
    assert not any(s["segment"] == "plan" and s.get("source") == "mint"
                   for s in st["steps"]), "the panel's own revise minted a round"

    _fill_plan_to_execute(wid, "rework")
    cli.main([wid, "submit"])
    capsys.readouterr()

    st = runmod.state(wid)
    fresh_plan = next(s for s in st["steps"]
                      if s["segment"] == "plan" and s.get("source") == "mint")
    # rework, not a second first draft -- and it dispatches, like every round
    assert fresh_plan["dispatches"] == "cut-a-gate"
    assert fresh_plan["form"] == "skills/planner/forms/REWORK.toml"
    assert "gate 1 is untestable" in fresh_plan["prefill"]["findings"]
    assert "[p1]" in fresh_plan["prefill"]["findings"]          # attributed

    fresh_panel = next(s for s in st["steps"]
                       if s.get("source") == "panel" and s["segment"] == "plan")
    original_plan = next(s for s in st["steps"] if s["id"] == "plan")
    assert fresh_panel["panel"] == original_plan["panel"]      # same panel config
    assert fresh_panel["form"] == "forms/PLAN_TO_EXECUTE.toml"  # the two-voices shape survives
    assert st["current"]["id"] == fresh_plan["id"]              # plan resumes, not the mint form

    # work the fresh round: dispatch it, reworked plan, fresh panel, this time a pass
    _dispatch_and_close_plan(wid, fresh_plan["id"], _fill_rework_form)
    capsys.readouterr()
    st = runmod.state(wid)
    assert st["current"]["id"] == fresh_panel["id"]

    _dispatch_panel(wid, fresh_panel["id"], verdict="pass")
    capsys.readouterr()
    st = runmod.state(wid)
    assert st["current"]["id"] == fresh_panel["id"]   # resolved, waiting on its own form now
    _fill_plan_to_execute(wid)
    cli.main([wid, "submit"])
    capsys.readouterr()

    st = runmod.state(wid)
    assert any(s["id"] == "g1" for s in st["steps"])  # the second round minted the gate


# -- 3. a pass opens PLAN_TO_EXECUTE for the conductor -----------------------


def test_pass_opens_plan_to_execute_for_the_conductor(workdir, capsys):
    journal.append("i1", "run", title="t", assembly="run-an-issue")
    journal.append("i1", "step", id="plan", segment="plan", form="forms/PLAN_TO_EXECUTE.toml",
                   filler="conductor", anchor=True,
                   panel=[{"form": CRITIC, "worker": "reviewer", "criteria": "c1"}])
    journal.append("i1", "prefill", fields={})
    capsys.readouterr()

    _dispatch_critic("i1", "plan", verdict="pass")
    capsys.readouterr()

    cli.main(["i1"])
    out = capsys.readouterr().out
    assert "The panel has returned." in out           # PLAN_TO_EXECUTE's own imperative
    assert "spine open give-a-verdict" not in out     # not the panel view anymore


# -- 4. submit refuses while a verdict is outstanding -------------------------


def test_submit_refuses_while_a_verdict_is_outstanding(workdir, capsys):
    journal.append("i2", "run", title="t", assembly="run-an-issue")
    journal.append("i2", "step", id="plan", segment="plan", form="forms/PLAN_TO_EXECUTE.toml",
                   filler="conductor", anchor=True,
                   panel=[{"form": CRITIC, "worker": "reviewer", "criteria": "c1"},
                          {"form": CRITIC, "worker": "reviewer", "criteria": "c2"}])
    journal.append("i2", "prefill", fields={})
    capsys.readouterr()

    with pytest.raises(SystemExit) as e:
        cli.main(["i2", "submit"])
    msg = str(e.value)
    assert "outstanding" in msg
    assert "waived:" not in msg                        # not the generic fill-or-waive escape

    # the escape names is a real command -- type it and confirm it works
    cli.main(["i2"])
    out = capsys.readouterr().out
    assert "spine open give-a-verdict --parent i2 --step plan.p1" in out
    assert "spine open give-a-verdict --parent i2 --step plan.p2" in out

    _dispatch_critic("i2", "plan", verdict="pass", n=1)
    # still outstanding -- p2 has not returned
    with pytest.raises(SystemExit) as e:
        cli.main(["i2", "submit"])
    assert "outstanding" in str(e.value)

    _dispatch_critic("i2", "plan", verdict="pass", n=2)
    capsys.readouterr()
    # now the form is reachable, so submit demands its fields instead
    with pytest.raises(SystemExit) as e:
        cli.main(["i2", "submit"])
    assert "outstanding" not in str(e.value)            # past the panel now


# -- 5. a root objection is a revise finding; the room names a non-pass verdict

# There is no third verdict word. A panel that objects at the root writes it
# as a revise finding, the same as any other -- and, once the panel's own
# vocabulary is `pass | revise`, only two reworks landing on the plan in a
# row reach the segment's outlet (impasse-after = 2). That path -- the third
# revise minting IMPASSE.toml with `arrival = "rework-rounds"` -- is pinned
# in tests/test_rework.py, which drives it for run-an-issue's plan and
# understand and for run-a-gate alike; this file's own job is the
# two-voices shape (panel and form on one step).
#
# Ruling 3 (2026-09-02) moved plan-to-execute's own `revise` row to
# `release` -- the panel's word is always quiet there now, whatever the
# conductor's own route form later decides -- so a plain revise can no
# longer reach the room this test is about at that transition; the room
# still fires (`_returned_verdict` reads the same outcome table everywhere),
# it is only that plan-to-execute's own panel-level row never resolves to
# anything but the quiet class any more. Consolidate did not move, so its
# own impasse is what still exercises this room with a plain revise.


def test_the_room_names_a_returned_panels_non_pass_verdict(workdir, capsys):
    """The findings arrived as orders and the word the panel merged on did
    not, so the reader of an outlet room had to infer whether critics had
    looped or not. A pass is the room arriving normally and is not named.

    Driven through explore-an-idea's spec segment now, not run-an-issue's:
    every panel-bearing transition here (review, plan-to-execute, and
    consolidate since ruling 3's 2026-09-03 follow-up) reads both of the
    panel's own words as quiet (`release`), holding open for a conductor's
    own route form instead of acting on the bare verdict -- so none of them
    can demonstrate a returned verdict that acts any more. explore-an-idea's
    spec segment has no route form and still refills directly off a bare
    revise (`test_explore._to_rework`), so it is the one seam left where the
    panel's own merged verdict, not a conductor's later ruling, is what the
    room names."""
    cli.main(["open", "explore-an-idea", "--title", "t"])
    out = capsys.readouterr().out
    ewid = out.split()[1]
    _fill(f".agent-work/{ewid}/OPEN.toml",
         'idea = "x"\nauthority = "Tommy"\n[[seeds]]\nidea = "the itch"\n')
    cli.main([ewid, "submit"])
    capsys.readouterr()
    _to_rework(ewid)
    capsys.readouterr()

    cli.main([ewid])
    out = " ".join(capsys.readouterr().out.split())
    assert "The panel that last ruled here returned revise." in out

    # a pass says nothing: the run simply reached the conductor's own form
    journal.append("i3", "run", title="t", assembly="run-an-issue")
    journal.append("i3", "step", id="plan", segment="plan", form="forms/PLAN_TO_EXECUTE.toml",
                   filler="conductor", anchor=True,
                   panel=[{"form": CRITIC, "worker": "reviewer", "criteria": "c1"}])
    journal.append("i3", "prefill", fields={})
    _dispatch_critic("i3", "plan", verdict="pass")
    capsys.readouterr()

    cli.main(["i3"])
    out = " ".join(capsys.readouterr().out.split())
    assert "The panel that last ruled here" not in out
