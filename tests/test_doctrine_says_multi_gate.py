"""Pins the doctrine sweep issue223.g3 makes, now that g1 and g2 have
landed the mechanism itself: a plan round may queue one gate or several,
and a queued gate dispatches without a new plan round or panel in
between. Reads the seven files g3's own scope names as plain prose -- a
grep with a name, never a journal-driven run -- and checks that the stale
single-gate-per-round phrasing is gone. It does not pin the wording that
replaced it: a pinned sentence cannot be simplified, and pinning these did
not catch PLAN.toml contradicting the planner skill.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _text(relpath):
    return (ROOT / relpath).read_text()


def _collapsed(text):
    """These files wrap prose at ~90 columns, so a phrase spanning a line
    break still reads as one run of spaces here."""
    return re.sub(r"\s+", " ", text)


def _assert_absent(text, *phrases):
    collapsed = _collapsed(text)
    for phrase in phrases:
        assert _collapsed(phrase) not in collapsed, f"stale phrase still present: {phrase!r}"


def test_approach_short_loops_reads_as_ooda():
    text = _text("standards/approach.md")
    _assert_absent(
        text,
        "Plan enough to do the next step and to hold a rough idea of what follows.",
    )


def test_glossary_gate_spec_is_one_block_of_one_or_several():
    text = _text("standards/glossary.md")
    _assert_absent(text, "one gate spec per round")


def test_glossary_verdict_panel_drops_gate_landing_as_fresh_occasion():
    text = _text("standards/glossary.md")
    _assert_absent(text, "the re-cut after a gate lands")


def test_planner_posture_cuts_one_round_of_one_or_several_gates():
    text = _text("skills/planner/SKILL.md")
    _assert_absent(
        text,
        "This dispatch is one gate's worth of cutting, and it ends",
        "You choose the next implementable chunk toward its done",
        "The engine reopens planning after every gate while an obligation stays open",
    )


def test_issue_conductor_posture_plans_every_clear_gate():
    text = _text("skills/issue-conductor/SKILL.md")
    _assert_absent(
        text,
        "the plan cuts one small gate at a time toward the",
        "the plan chooses the next small chunk toward its done",
    )


def test_assembly_toml_comment_drops_gate_landing_as_fresh_occasion():
    text = _text("assemblies/run-an-issue/ASSEMBLY.toml")
    _assert_absent(text, "the re-cut\n# after each gate lands (`settle`)")


def test_plan_to_execute_toml_comment_drops_gate_landing_as_fresh_occasion():
    text = _text("assemblies/run-an-issue/forms/PLAN_TO_EXECUTE.toml")
    _assert_absent(text, "the re-cut after each gate lands, a replan's, a rewrite's")


def test_v2_design_workflow_table_drops_one_gate_at_a_time():
    text = _text("docs/V2_DESIGN.md")
    _assert_absent(text, "one gate at a time")


def test_v2_design_ascii_diagram_mints_every_gate_in_the_cut():
    text = _text("docs/V2_DESIGN.md")
    _assert_absent(text, "pass mints one gate dispatch and its")


def test_v2_design_ruling_1_drops_single_gate_claims():
    text = _text("docs/V2_DESIGN.md")
    _assert_absent(
        text,
        "Plan-to-execute mints one gate.",
        "cannot outgrow the work it plans because it is one gate long",
    )
