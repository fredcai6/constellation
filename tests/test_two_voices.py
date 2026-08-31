"""The two-voices transition: a step carrying both a panel and a form runs
the panel first, and completes on the form's submit -- never the reverse.

run-an-issue's plan-to-execute was the first transition in the repo shaped
this way: the critic panel reads the plan, and only a `pass` reaches the mint
form that cuts gates. Before this, four sites in cli.py guarded on `panel and
not form`, so a form-carrying transition took the plain form path and the
critic was never dispatched -- a plan could mint gates without ever being
attacked. Understand's own consolidate is now shaped the same way -- the
cold panel reads the spec-writer's round, and only a `pass` reaches
consolidate's own bookkeeping -- so `_work_the_board` below drives that one
too, on every fixture in this file. These tests drive the real `run-an-issue`
assembly (the first, end to end) and the real two-step mechanism
`run.py`/`cli.py` provide (the rest, via direct journal fixtures, the same
way test_verdict_panels.py isolates a revise round). test_verdict_panels.py
is the check that run-a-gate's panel-only review is unchanged by any of this.
"""

import pathlib

import pytest

from engine import cli, forms, journal, run as runmod
from gitremote import init_checkout
from test_nesting import _write_plan_artifact

REPO = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONSTELLATION_SESSION", "test-session")
    (tmp_path / "constellation.toml").write_text((REPO / "constellation.toml").read_text())
    init_checkout(tmp_path)
    return tmp_path


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


def _fill_consolidate(wid, settle="waived: none"):
    _fill(f".agent-work/{wid}/CONSOLIDATE.toml", '''
spec = ".agent-work/%s/spec.md"
key-terms = "waived: none"
settle = "%s"
''' % (wid, settle))


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


def _fill_plan_to_execute(wid):
    """Nothing to author here now (#27): the round the panel just passed
    already cut the gate, and submitting this projects it."""
    _write_plan_artifact(f".agent-work/{wid}/plan.md")
    _fill(f".agent-work/{wid}/PLAN_TO_EXECUTE.toml",
         'plan = ".agent-work/%s/plan.md"\n' % wid)


def _fill_verdict(wid, verdict, findings="none: waived: clean"):
    """The plan panel declares CRITIC.toml, so that is the form on disk -- a
    critic reads a plan with the critic's form, not the reviewer's."""
    _fill(journal.location(wid) / "CRITIC.toml", '''
findings = "%s"
vocabulary = "waived: consistent"
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


def _dispatch_panel(pwid, step_id, verdict="pass", findings="none: waived: clean"):
    """Clear a panel step: every panelist the assembly declares, not just the
    first. The step completes on the last verdict, so closing one of three
    leaves the transition outstanding."""
    panel = next(s for s in runmod.state(pwid)["steps"] if s["id"] == step_id)["panel"]
    for n in range(1, len(panel) + 1):
        _dispatch_critic(pwid, step_id, verdict, findings, n=n)


def _drive_plan_to_impasse(wid, panel_id="plan", findings="gap: wrong artifact entirely"):
    """Four revises landing on the same objection -- the only way a root
    objection reaches the plan segment's impasse form now that the panel's
    vocabulary is `pass | revise`, not a third word that jumps there in one."""
    _dispatch_panel(wid, panel_id, verdict="revise", findings=findings)
    for _ in range(3):
        st = runmod.state(wid)
        fresh_interior = next(s for s in st["steps"]
                              if s["segment"] == "plan" and s.get("dispatches")
                              and s["id"] not in st["done"])
        _dispatch_and_close_plan(wid, fresh_interior["id"], _fill_rework_form)
        panel_id = next(s["id"] for s in runmod.state(wid)["steps"]
                        if s.get("panel") and s["id"] not in runmod.state(wid)["done"])
        _dispatch_panel(wid, panel_id, verdict="revise", findings=findings)


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


def test_revise_sends_the_plan_back_with_findings_attributed_and_the_panel_refires(workdir, capsys):
    wid = _drive_to_plan_to_execute()
    capsys.readouterr()

    _dispatch_panel(wid, "plan", verdict="revise", findings="gap: gate 1 is untestable")
    capsys.readouterr()

    st = runmod.state(wid)
    assert "plan" in st["done"]                     # released, like a panel-only step

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
    assert "nothing to author here" in out            # PLAN_TO_EXECUTE's own imperative
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
# vocabulary is `pass | revise`, only three of them landing on the plan in a
# row reaches the segment's outlet. That path -- four revises, the fourth
# minting IMPASSE.toml with `arrival = "rework-rounds"` -- is pinned in
# tests/test_rework.py, which drives it for both run-an-issue and run-a-gate;
# this file's own job is the two-voices shape (panel and form on one step),
# which the room-naming test below still exercises with a plain revise.


def test_the_room_names_a_returned_panels_non_pass_verdict(workdir, capsys):
    """The findings arrived as orders and the word the panel merged on did
    not, so the reader of an outlet room had to infer whether three critics
    had looped or not. A pass is the room arriving normally and is not
    named.

    A single revise no longer proves this: every round now dispatches (#27),
    so the very next room after one revise is the dispatch view, which never
    reaches `_returned_verdict` at all. Only the outlet -- a looped revise's
    non-dispatch IMPASSE.toml -- lands the reader on the room this test is
    about, the same room an escalate used to reach in one."""
    wid = _drive_to_plan_to_execute()
    _drive_plan_to_impasse(wid)
    capsys.readouterr()

    cli.main([wid])
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
