"""The two-voices transition: a step carrying both a panel and a form runs
the panel first, and completes on the form's submit -- never the reverse.

run-an-issue's plan-to-execute is the one transition in the repo shaped this
way: the critic panel reads the plan, and only a `pass` reaches the mint form
that cuts gates. Before this, four sites in cli.py guarded on `panel and not
form`, so a form-carrying transition took the plain form path and the critic
was never dispatched -- a plan could mint gates without ever being attacked.
These tests drive the real `run-an-issue` assembly (the first, end to end) and
the real two-step mechanism `run.py`/`cli.py` provide (the rest, via direct
journal fixtures, the same way test_verdict_panels.py isolates a revise
round). test_verdict_panels.py is the check that run-a-gate's panel-only
review is unchanged by any of this.
"""

import pathlib

import pytest

from engine import cli, forms, journal, run as runmod

REPO = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONSTELLATION_SESSION", "test-session")
    (tmp_path / "constellation.toml").write_text((REPO / "constellation.toml").read_text())
    return tmp_path


CRITIC = "skills/reviewer/forms/CRITIC.toml"
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
    b = pathlib.Path(f".agent-work/{wid}/UNDERSTAND.toml")
    b.write_text(b.read_text().replace(
        'status = "open"', 'status = "answered"\nanswer = "settled."'))


def _fill_consolidate(wid, settle="waived: none"):
    _fill(f".agent-work/{wid}/CONSOLIDATE.toml", '''
learnings = "settled."
key-terms = "waived: none"
settle = "%s"
''' % settle)


def _fill_plan_form(wid):
    _fill(f".agent-work/{wid}/PLAN.toml", '''
plan = ".agent-work/%s/plan.md"
design-it-twice = "waived: reversible"
key-terms = "waived: none"
''' % wid)


def _fill_rework_form(wid, findings_addressed="accepted: made gate 1 testable",
                      deleted="the restated background; the gates already carry it"):
    """A revise round's interior step is REWORK.toml, not PLAN.toml."""
    _fill(f".agent-work/{wid}/REWORK.toml", '''
plan = ".agent-work/%s/plan.md"
findings-addressed = "%s"
deleted = "%s"
key-terms = "waived: none"
''' % (wid, findings_addressed, deleted))


def _fill_plan_to_execute(wid, n_gates=1):
    gates = "\n".join('''
[[gates]]
purpose = "gate %d"
scope = "src/ only"
proof = "true"
''' % i for i in range(1, n_gates + 1))
    _fill(f".agent-work/{wid}/PLAN_TO_EXECUTE.toml",
         'plan = ".agent-work/%s/plan.md"\n%s' % (wid, gates))


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
    _fill_plan_form(wid)
    cli.main([wid, "submit"])
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

    assert runmod.state(wid)["prefill"]["learnings"] == "settled."

    cli.main(["open", "give-a-verdict", "--parent", wid, "--step", "plan.p1"])
    capsys.readouterr()
    prefill = runmod.state(f"{wid}.plan.p1")["prefill"]
    assert prefill["learnings"] == "settled."      # the understanding crossed
    assert prefill["plan"] == f".agent-work/{wid}/plan.md"   # the artifact still rides
    assert prefill["criteria"].startswith("intent-fit")


# [settle-carries]
# Rationale: no part of the understand board crosses a segment boundary, so
# consolidate's `settle` is the only carrier for what the excursion column
# produced. The test pins both halves -- the note that says report, and the
# prefill hop that delivers it to the cold panelist.
# Rejected: reading the board file from the planner's step to prove the
# answers arrived -- there is no such read, which is the whole reason this
# field carries.
def test_settle_carries_the_boards_answers(workdir, capsys):
    """`settle` reports the board's excursion column; it does not re-ask it.

    The board is a document in the work location and no part of it crosses a
    segment boundary. Consolidate `carries`, so its fields join the run's
    prefill -- which makes this one field the only path by which a per-row
    brief and its return reach the planner, the cold panel, and the journal's
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
    assert fresh_plan["form"] == "forms/REWORK.toml"            # rework, not a second first draft
    assert "gate 1 is untestable" in fresh_plan["prefill"]["findings"]
    assert "[p1]" in fresh_plan["prefill"]["findings"]          # attributed

    fresh_panel = next(s for s in st["steps"]
                       if s.get("panel") and s["id"] != "plan")
    assert fresh_panel["panel"] == st["steps"][3]["panel"]      # same panel config
    assert fresh_panel["form"] == "forms/PLAN_TO_EXECUTE.toml"  # the two-voices shape survives
    assert st["current"]["id"] == fresh_plan["id"]              # plan resumes, not the mint form

    # work the fresh round: reworked plan, fresh panel, this time a pass
    _fill_rework_form(wid)
    cli.main([wid, "submit"])
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
    assert "Cut it into gates" in out                # PLAN_TO_EXECUTE's own imperative
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


# -- 5. an escalate mints the segment's outlet, and the room says so ---------


def test_an_escalated_plan_mints_the_outlet_instead_of_finishing(workdir, capsys):
    """A panel objecting at the root leaves a two-voices step with nowhere to
    go: `state()` marks it done without its form -- correct, an escalated
    plan should not fill the mint form -- and before this the transition
    acted only on `revise`, so nothing was minted and the run walked to its
    terminal close with no gates and no ruling. The outlet is where it goes
    now; the same three rulings a looped revise gets."""
    wid = _drive_to_plan_to_execute()
    capsys.readouterr()

    _dispatch_panel(wid, "plan", verdict="escalate",
                    findings="gap: the parser is not where the record is dropped")
    capsys.readouterr()

    st = runmod.state(wid)
    assert "plan" in st["done"]                       # released, like any non-pass
    assert not any(s.get("dispatches") for s in st["steps"]), "an escalate minted gates"

    outlet = st["current"]
    assert outlet["form"] == "forms/IMPASSE.toml", (
        f"the escalate left the run on {outlet.get('form')!r} -- an escalated "
        "plan walked to its close instead of reaching a ruling")
    assert outlet["prefill"]["arrival"] == "escalate"  # which way in, not just the findings
    assert "not where the record is dropped" in outlet["prefill"]["findings"]
    assert "[p1]" in outlet["prefill"]["findings"]     # attributed, like a revise's
    # no fourth cold reader: the outlet carries no panel of its own
    assert not any(s.get("panel") and s["id"] not in st["done"] for s in st["steps"])

    # and the ruling is live from this arrival too -- advance overrules the
    # panel and takes the plan to its transition
    _fill(journal.location(wid) / "IMPASSE.toml",
          'ruling = "advance"\nwhy = "the panel read the plan against the wrong issue"\n')
    cli.main([wid, "submit"])
    capsys.readouterr()
    assert runmod.state(wid)["current"]["form"] == "forms/PLAN_TO_EXECUTE.toml"


def test_the_room_names_a_returned_panels_non_pass_verdict(workdir, capsys):
    """The findings arrived as orders and the word the panel merged on did
    not, so the reader of an outlet room had to infer whether three critics
    had looped or objected at the root. A pass is the room arriving normally
    and is not named."""
    wid = _drive_to_plan_to_execute()
    _dispatch_panel(wid, "plan", verdict="escalate", findings="gap: wrong artifact entirely")
    capsys.readouterr()

    cli.main([wid])
    out = " ".join(capsys.readouterr().out.split())
    assert "The panel that last ruled here returned escalate." in out

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
