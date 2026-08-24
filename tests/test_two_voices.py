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
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from engine import cli, journal, run as runmod  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONSTELLATION_SESSION", "test-session")
    (tmp_path / "constellation.toml").write_text((REPO / "constellation.toml").read_text())
    return tmp_path


CRITIC = "skills/reviewer/forms/CRITIC.toml"


def _fill(path, text):
    pathlib.Path(path).write_text(text)


# -- real end to end: open -> understand -> plan -> plan-to-execute ---------


def _fill_open(wid):
    _fill(f".agent-work/{wid}/OPEN.toml", '''
issue = "gh:99"

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


def _fill_consolidate(wid):
    _fill(f".agent-work/{wid}/CONSOLIDATE.toml", '''
learnings = "settled."
key-terms = "waived: none"
settle = "waived: none"
''')


def _fill_plan_form(wid):
    _fill(f".agent-work/{wid}/PLAN.toml", '''
plan = ".agent-work/%s/plan.md"
design-it-twice = "waived: reversible"
key-terms = "waived: none"
findings-addressed = "waived: first pass"
''' % wid)


def _fill_plan_to_execute(wid, n_gates=1):
    gates = "\n".join('''
[[gates]]
purpose = "gate %d"
scope = "src/ only"
done = "true"
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


def _drive_to_plan_to_execute(wid="issue99"):
    """Open a real run-an-issue and drive it to the plan-to-execute
    transition, right after the plan interior is submitted -- the moment
    the critic must fire before anything else."""
    cli.main(["open", "run-an-issue", "--issue", "99", "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
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

    _dispatch_critic(wid, "plan", verdict="pass")
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


# -- 2. revise sends the plan back with findings attributed, panel re-fires -


def test_revise_sends_the_plan_back_with_findings_attributed_and_the_panel_refires(workdir, capsys):
    wid = _drive_to_plan_to_execute()
    capsys.readouterr()

    _dispatch_critic(wid, "plan", verdict="revise", findings="gap: gate 1 is untestable")
    capsys.readouterr()

    st = runmod.state(wid)
    assert "plan" in st["done"]                     # released, like a panel-only step

    fresh_plan = next(s for s in st["steps"]
                      if s["segment"] == "plan" and s.get("source") == "mint")
    assert fresh_plan["form"] == "forms/PLAN.toml"
    assert "gate 1 is untestable" in fresh_plan["prefill"]["findings"]
    assert "[p1]" in fresh_plan["prefill"]["findings"]          # attributed

    fresh_panel = next(s for s in st["steps"]
                       if s.get("panel") and s["id"] != "plan")
    assert fresh_panel["panel"] == st["steps"][3]["panel"]      # same panel config
    assert fresh_panel["form"] == "forms/PLAN_TO_EXECUTE.toml"  # the two-voices shape survives
    assert st["current"]["id"] == fresh_plan["id"]              # plan resumes, not the mint form

    # work the fresh round: revised plan, fresh panel, this time a pass
    _fill_plan_form(wid)
    cli.main([wid, "submit"])
    capsys.readouterr()
    st = runmod.state(wid)
    assert st["current"]["id"] == fresh_panel["id"]

    _dispatch_critic(wid, fresh_panel["id"], verdict="pass")
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
