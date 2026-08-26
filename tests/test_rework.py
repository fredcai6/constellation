"""The rework round has its own form, and record-only is real.

A revise on run-an-issue's plan segment mints REWORK.toml -- the segment's
`rework-form` -- in place of the step-form; a replan, and a revise on a
segment without the key, mint the step-form exactly as before. The prefill
guard reads the producing step's form, so a rework round's record-only
ledger (`findings-addressed`, `deleted`) stays out of the next panelist's
prefill. Drives the real assemblies end to end, like test_nesting.py.
"""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from engine import cli, run as runmod  # noqa: E402

from test_nesting import (  # noqa: E402
    _dispatch_and_close_child,
    _dispatch_plan_critic,
    _dispatch_review,
    _fill,
    _fill_consolidate,
    _fill_gate_transition_replan,
    _fill_implement,
    _fill_open,
    _fill_plan,
    _mint_n_gates,
    _work_the_board,
)

REPO = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONSTELLATION_SESSION", "test-session")
    (tmp_path / "constellation.toml").write_text((REPO / "constellation.toml").read_text())
    return tmp_path


def _drive_to_revise(wid="issue17", findings="gap: gate 1 is untestable"):
    """Open a real run-an-issue, drive it to the plan-to-execute panel, and
    have the critic say revise."""
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    _fill_plan(wid)
    cli.main([wid, "submit"])
    _dispatch_plan_critic(wid, verdict="revise", findings=findings)
    return wid


def _fresh_mint(st, segment):
    return next(s for s in st["steps"]
                if s["segment"] == segment and s.get("source") == "mint")


# -- 1. a revise mints the segment's rework form, findings as prefill --------


def test_revise_mints_rework_form_with_findings_as_prefill(workdir, capsys):
    wid = _drive_to_revise()
    capsys.readouterr()

    st = runmod.state(wid)
    fresh = _fresh_mint(st, "plan")
    assert fresh["form"] == "forms/REWORK.toml"
    assert "gate 1 is untestable" in fresh["prefill"]["findings"]
    assert st["current"]["id"] == fresh["id"]

    # the fresh round materializes REWORK.toml, not another PLAN.toml
    cli.main([wid])
    capsys.readouterr()
    assert (pathlib.Path(f".agent-work/{wid}/REWORK.toml")).exists()


# -- 2. a replan mints the step-form ------------------------------------------


def test_replan_mints_the_step_form(workdir, capsys):
    _mint_n_gates(1)
    capsys.readouterr()
    _dispatch_and_close_child("issue17", "g1")
    capsys.readouterr()

    _fill_gate_transition_replan("issue17")
    cli.main(["issue17", "submit"])
    capsys.readouterr()

    fresh = _fresh_mint(runmod.state("issue17"), "plan")
    assert fresh["form"] == "forms/PLAN.toml"  # a replan re-plans from scratch


# -- 3. a revise on a segment without rework-form mints the step-form ---------


def test_revise_without_rework_form_mints_the_step_form(workdir, capsys):
    """run-a-gate's work segment declares no rework-form, so a review revise
    refills with IMPLEMENT.toml exactly as before."""
    cli.main(["open", "run-a-gate", "--id", "g1"])
    _fill_implement("g1", "work-1")
    cli.main(["g1", "submit"])
    capsys.readouterr()
    _dispatch_review("g1", verdict="revise", findings="gap: bound still off by one")
    capsys.readouterr()

    fresh = _fresh_mint(runmod.state("g1"), "work")
    assert fresh["form"] == "skills/implementer/forms/IMPLEMENT.toml"
    assert "bound still off by one" in fresh["prefill"]["findings"]


# -- 4. the rework ledger stays out of the next panelist's prefill ------------


def test_rework_record_only_fields_stay_out_of_the_next_panelists_prefill(workdir, capsys):
    wid = _drive_to_revise()
    capsys.readouterr()

    _fill(pathlib.Path(f".agent-work/{wid}/REWORK.toml"), '''
plan = ".agent-work/%s/plan.md"
findings-addressed = "accepted: rewrote gate 1's done as a runnable command"
deleted = "the restated approach section; the gates already carry it"
key-terms = "waived: none"
''' % wid)
    cli.main([wid, "submit"])
    capsys.readouterr()

    st = runmod.state(wid)
    panel_id = st["current"]["id"]
    assert panel_id != "plan"  # the refired panel, not the first round's
    cli.main(["open", "give-a-verdict", "--parent", wid, "--step", f"{panel_id}.p1"])
    capsys.readouterr()

    prefill = runmod.state(f"{wid}.{panel_id}.p1")["prefill"]
    assert "findings-addressed" not in prefill  # the producer's ledger stays behind
    assert "deleted" not in prefill
    assert prefill["plan"] == f".agent-work/{wid}/plan.md"  # the artifact still rides
    assert prefill["key-terms"] == "waived: none"
    assert prefill["criteria"].startswith("intent-fit")
