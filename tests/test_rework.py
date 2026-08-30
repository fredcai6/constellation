"""The rework round has its own form, and record-only is real.

A revise on run-an-issue's plan segment mints REWORK.toml -- the segment's
`rework-form` -- in place of the step-form; a replan, and a revise on a
segment without the key, mint the step-form exactly as before. The prefill
guard reads the producing step's form, so a rework round's record-only
ledger (`findings-addressed`, `deleted`) stays out of the next panelist's
prefill. Drives the real assemblies end to end, like test_nesting.py.
"""

import pathlib

import pytest

from engine import cli, run as runmod
from gitremote import init_checkout

from test_nesting import (
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
    init_checkout(tmp_path)
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


def test_a_replan_restarts_the_rework_count(workdir, capsys):
    """The count is of rounds on one artifact, so a replan -- which is a new
    artifact -- starts it over. The principal ruled this against the
    alternative of counting every send-back."""
    wid = _drive_to_revise()
    _round(wid, "gap 1")
    asm = runmod.load_assembly("run-an-issue")
    assert runmod.rework_rounds(runmod.state(wid), asm, "plan") == 2

    # carry that plan through to a gate, then replan from the gate transition
    _fill_rework(wid)
    cli.main([wid, "submit"])
    _dispatch_plan_critic(wid, verdict="pass")
    capsys.readouterr()
    _fill(runmod.journal.location(wid) / "PLAN_TO_EXECUTE.toml", '''
plan = "the plan doc"

[[gates]]
purpose = "p"
scope = "s"
proof = "true"
''')
    cli.main([wid, "submit"])
    capsys.readouterr()
    _dispatch_and_close_child(wid, "g1")
    capsys.readouterr()
    _fill_gate_transition_replan(wid)
    cli.main([wid, "submit"])
    capsys.readouterr()

    assert runmod.rework_rounds(runmod.state(wid), asm, "plan") == 0


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


def _plan_measures(wid):
    """Prose lengths of the plan artifact, round by round. The `issue` field
    is an artifact too and is measured on the open step; the room reports
    drift per segment, so scoping here says what this test is about."""
    return [m["words"] for m in runmod.state(wid)["measures"] if m["field"] == "plan"]


def test_the_room_reports_how_the_plan_moved_across_its_rounds(workdir, capsys):
    """A rework round is told what the artifact did, and nothing more.

    The engine measures prose only -- fenced blocks, tables and indented code
    do not count -- because a plan that grew by gaining proofs has not
    accreted, and a count that cannot tell those apart makes an agent delete
    meaning to hit a number. It reports; it never refuses.
    """
    wid = "issue44"
    cli.main(["open", "run-an-issue", "--issue", "44", "--title", "a plan that grows"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])

    art = pathlib.Path(f".agent-work/{wid}/plan.md")
    art.write_text("one two three four five six seven eight nine ten\n")
    _fill_plan(wid)
    cli.main([wid, "submit"])
    capsys.readouterr()

    # round one measured, and says nothing -- there is nothing yet to compare
    assert _plan_measures(wid) == [10]
    cli.main([wid])
    assert "prose words" not in capsys.readouterr().out

    _dispatch_plan_critic(wid, verdict="revise", findings="gap: thin")
    capsys.readouterr()

    # a longer plan, whose growth is all table and fenced block
    art.write_text("one two three four five six seven eight nine ten\n"
                   "| a | b | c | d | e | f |\n"
                   "```\nnot prose at all, not counted, not once\n```\n"
                   "    indented code is not prose either\n"
                   "eleven twelve\n")
    _fill(runmod.journal.location(wid) / "REWORK.toml", '''
plan = ".agent-work/%s/plan.md"
findings-addressed = "accepted: thickened gate 1"
deleted = "nothing; the growth is all table and fence"
key-terms = "waived: none"
''' % wid)
    cli.main([wid, "submit"])
    capsys.readouterr()

    assert _plan_measures(wid) == [10, 12]

    # the room reports it at the NEXT round, where the conductor is writing:
    # the artifact on disk is the one just submitted, and now it has a history
    _dispatch_plan_critic(wid, verdict="revise", findings="gap: still thin")
    capsys.readouterr()
    cli.main([wid])
    out = capsys.readouterr().out
    assert "12 prose words" in out          # the table, fence and indent are absent
    assert "+20% on the first round" in out
    assert "growth is not a defect" in out
    assert "too long" not in out            # a notice, never a verdict


# -- 5. the outlet: a fourth revise mints a ruling, not a fourth round --------


def _fill_rework(wid):
    _fill(runmod.journal.location(wid) / "REWORK.toml", '''
plan = "the plan doc"
findings-addressed = "waived: first pass"
deleted = "waived: nothing"
key-terms = "none"
''')


def _round(wid, findings):
    """One rework round: fill the fresh REWORK.toml, submit, and have the
    fresh panel say revise again."""
    _fill_rework(wid)
    cli.main([wid, "submit"])
    _dispatch_plan_critic(wid, verdict="revise", findings=findings)


def _drive_to_impasse(wid="issue17"):
    """Three rework rounds, then the fourth revise -- which is the one the
    segment's `impasse-after` turns into a ruling."""
    _drive_to_revise(wid)
    for n in (1, 2, 3):
        _round(wid, f"gap: the proof still passes on an empty diff ({n})")
    return wid


def test_a_fourth_revise_mints_the_impasse_form_not_another_round(workdir, capsys):
    wid = _drive_to_impasse()
    capsys.readouterr()

    st = runmod.state(wid)
    assert st["current"]["form"] == "forms/IMPASSE.toml", (
        f"the fourth revise minted {st['current']['form']!r} -- the segment "
        "declares impasse-after = 3, so this round is the ruling")
    assert "empty diff (3)" in st["current"]["prefill"]["findings"]
    # no fourth panel: another fresh-context reader is the loop, not the way out
    assert not any(s.get("source") == "panel" and s["id"] not in st["done"]
                   for s in st["steps"]), "the impasse minted a panel"


def test_the_count_reaches_the_outlet_on_the_round_after_the_third(workdir, capsys):
    """The boundary, both sides. The first revise mints round one, so the
    count is already 1 before any loop runs."""
    wid = _drive_to_revise()
    asm = runmod.load_assembly("run-an-issue")
    counts = [runmod.rework_rounds(runmod.state(wid), asm, "plan")]
    for n in (1, 2):
        _round(wid, f"gap {n}")
        counts.append(runmod.rework_rounds(runmod.state(wid), asm, "plan"))
    capsys.readouterr()
    assert counts == [1, 2, 3]
    # three rounds is still a round -- the revise that follows is the ruling
    assert runmod.state(wid)["current"]["form"] == "forms/REWORK.toml"
    _round(wid, "gap 3")
    capsys.readouterr()
    assert runmod.state(wid)["current"]["form"] == "forms/IMPASSE.toml"


def test_an_unhandled_ruling_refuses_rather_than_releasing_the_step(workdir, capsys):
    """The ruling has no check of its own any more: it is refused by the same
    generic mechanism that refuses CYCLE.toml's `decision` -- the segment's
    own declared `[[outcome]]` rows, not a hand-rolled reader."""
    wid = _drive_to_impasse()
    capsys.readouterr()
    before = len(runmod.journal.read(wid))
    _fill(runmod.journal.location(wid) / "IMPASSE.toml",
          'ruling = "keep going"\nwhy = "it is nearly there"\n')
    with pytest.raises(SystemExit) as e:
        cli.main([wid, "submit"])
    msg = str(e.value)
    assert "ruling" in msg and "is not an outcome this step declares" in msg
    assert "advance | rework | up" in msg        # the assembly's own outcome rows
    assert len(runmod.journal.read(wid)) == before  # not even the submit landed
    assert runmod.state(wid)["current"]["form"] == "forms/IMPASSE.toml"


def test_advance_takes_the_plan_to_its_transition_over_a_live_revise(workdir, capsys):
    wid = _drive_to_impasse()
    capsys.readouterr()
    _fill(runmod.journal.location(wid) / "IMPASSE.toml",
          'ruling = "advance"\nwhy = "three rounds all landed on the proof"\n')
    cli.main([wid, "submit"])
    capsys.readouterr()

    st = runmod.state(wid)
    assert st["current"]["form"] == "forms/PLAN_TO_EXECUTE.toml"
    assert st["current"].get("source") == "mint"
    assert not st["current"].get("panel"), "advance minted a fresh panel to argue with"


def test_rework_runs_the_round_the_outlet_displaced(workdir, capsys):
    wid = _drive_to_impasse()
    capsys.readouterr()
    _fill(runmod.journal.location(wid) / "IMPASSE.toml",
          'ruling = "rework"\nwhy = "round four changes the proof, not the prose"\n')
    cli.main([wid, "submit"])
    capsys.readouterr()

    st = runmod.state(wid)
    assert st["current"]["form"] == "forms/REWORK.toml"
    assert "empty diff (3)" in st["current"]["prefill"]["findings"]


def test_up_mints_nothing_and_the_run_walks_to_its_close(workdir, capsys):
    """One way up, not two. Refilling nothing is what an escalate verdict
    already does, so the run reaches its terminal form and the ruling becomes
    the record whoever dispatched it reads."""
    wid = _drive_to_impasse()
    before = len(runmod.state(wid)["steps"])
    capsys.readouterr()
    _fill(runmod.journal.location(wid) / "IMPASSE.toml",
          'ruling = "up"\nwhy = "the plan may be solving the wrong problem"\n')
    cli.main([wid, "submit"])
    capsys.readouterr()

    st = runmod.state(wid)
    assert len(st["steps"]) == before, "up minted a step"
    assert st["current"]["form"] == "forms/CLOSE.toml"
    ruling = st["done"][[s["id"] for s in st["steps"]
                         if s.get("form") == "forms/IMPASSE.toml"][0]]["fields"]
    assert ruling["ruling"] == "up" and "wrong problem" in ruling["why"]


# -- 6. the same outlet on run-a-gate, which has no rework form ---------------


def _drive_gate_to_impasse(child="issue17.g1"):
    """Four review revises on one diff: the first three refill the interior,
    and the fourth is the one the outlet takes. run-a-gate's work segment
    declares no rework-form, so every refill mints the step-form again -- the
    count is of those, and the opening step is not one."""
    _mint_n_gates(1)
    cli.main(["open", "run-a-gate", "--parent", "issue17", "--step", "g1"])
    for n in (1, 2, 3, 4):
        _fill_implement(child, runmod.state(child)["current"]["id"])
        cli.main([child, "submit"])
        _dispatch_review(child, verdict="revise",
                         findings=f"gap: the spec asks for something untestable ({n})")
    return child


def test_a_gates_fourth_revise_mints_the_impasse_form(workdir, capsys):
    child = _drive_gate_to_impasse()
    capsys.readouterr()

    st = runmod.state(child)
    assert st["current"]["form"] == "forms/IMPASSE.toml"
    assert "untestable (4)" in st["current"]["prefill"]["findings"]
    asm = runmod.load_assembly("run-a-gate")
    assert runmod.rework_rounds(st, asm, "work") == 3


def test_a_gates_advance_walks_to_close_since_its_transition_has_no_form(workdir, capsys):
    """run-a-gate's review transition declares no conductor form -- releasing
    is the whole of it -- so advancing mints nothing and the run walks on."""
    child = _drive_gate_to_impasse()
    capsys.readouterr()
    before = len(runmod.state(child)["steps"])
    _fill(runmod.journal.location(child) / "IMPASSE.toml",
          'ruling = "advance"\nwhy = "three reviews all landed on the spec"\n')
    cli.main([child, "submit"])
    capsys.readouterr()

    st = runmod.state(child)
    assert len(st["steps"]) == before, "advance minted a step for a formless transition"
    assert st["current"]["form"] == "forms/GATE_CLOSE.toml"


def test_a_gates_rework_mints_the_step_form_again(workdir, capsys):
    child = _drive_gate_to_impasse()
    capsys.readouterr()
    _fill(runmod.journal.location(child) / "IMPASSE.toml",
          'ruling = "rework"\nwhy = "round four rewrites the check, not the diff"\n')
    cli.main([child, "submit"])
    capsys.readouterr()

    assert runmod.state(child)["current"]["form"] == "skills/implementer/forms/IMPLEMENT.toml"


def test_the_opening_step_is_not_a_send_back(workdir, capsys):
    """A gate that has never been reviewed is at zero, not one."""
    _mint_n_gates(1)
    cli.main(["open", "run-a-gate", "--parent", "issue17", "--step", "g1"])
    capsys.readouterr()
    asm = runmod.load_assembly("run-a-gate")
    assert runmod.rework_rounds(runmod.state("issue17.g1"), asm, "work") == 0
