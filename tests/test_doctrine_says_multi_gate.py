"""Pins the doctrine sweep issue223.g3 makes, now that g1 and g2 have
landed the mechanism itself: a plan round may queue one gate or several,
and a queued gate dispatches without a new plan round or panel in
between. Reads the seven files g3's own scope names as plain prose -- a
grep with a name, never a journal-driven run -- and checks both halves of
each: the stale single-gate-per-round phrasing is gone, and the corrected
wording g1/g2's own mechanism earns stands in its place.
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


def _assert_present(text, *phrases):
    collapsed = _collapsed(text)
    for phrase in phrases:
        assert _collapsed(phrase) in collapsed, f"corrected phrase missing: {phrase!r}"


def test_approach_short_loops_reads_as_ooda():
    text = _text("standards/approach.md")
    _assert_absent(
        text,
        "Plan enough to do the next step and to hold a rough idea of what follows.",
    )
    _assert_present(
        text,
        "Plan as far as you can see clearly, and act on it. After each "
        "step, check what you saw against what you expected: if it holds, keep "
        "going; if it doesn't, re-plan.",
    )


def test_glossary_gate_spec_is_one_block_of_one_or_several():
    text = _text("standards/glossary.md")
    _assert_absent(text, "one gate spec per round")
    _assert_present(text, "which holds one gate spec or several")


def test_glossary_call_tree_names_owning_gate_by_position():
    text = _text("standards/glossary.md")
    _assert_present(
        text,
        "names which gate owns it, by that gate's own position in the round, "
        "never a predicted engine-assigned id",
    )


def test_glossary_verdict_panel_drops_gate_landing_as_fresh_occasion():
    text = _text("standards/glossary.md")
    _assert_absent(text, "the re-cut after a gate lands")
    _assert_present(text, "the opening\n  round, a rewrite, a replan")


def test_planner_posture_cuts_one_round_of_one_or_several_gates():
    text = _text("skills/planner/SKILL.md")
    _assert_absent(
        text,
        "This dispatch is one gate's worth of cutting, and it ends",
        "You choose the next implementable chunk toward its done",
        "The engine reopens planning after every gate while an obligation stays open",
    )
    _assert_present(
        text,
        "This dispatch cuts one round -- one gate, or every gate whose path is clear",
        "Cut every chunk toward its done whose path you can see clearly",
    )


def test_issue_conductor_posture_plans_every_clear_gate():
    text = _text("skills/issue-conductor/SKILL.md")
    _assert_absent(
        text,
        "the plan cuts one small gate at a time toward the",
        "the plan chooses the next small chunk toward its done",
    )
    _assert_present(
        text,
        "the plan cuts every gate whose path is clear",
        "the plan cuts every chunk toward its done whose path is",
    )


def test_assembly_toml_comment_drops_gate_landing_as_fresh_occasion():
    text = _text("assemblies/run-an-issue/ASSEMBLY.toml")
    _assert_absent(text, "the re-cut\n# after each gate lands (`settle`)")
    _assert_present(text, "never merely because a gate landed")


def test_plan_to_execute_toml_comment_drops_gate_landing_as_fresh_occasion():
    text = _text("assemblies/run-an-issue/forms/PLAN_TO_EXECUTE.toml")
    _assert_absent(text, "the re-cut after each gate lands, a replan's, a rewrite's")
    _assert_present(text, "never merely because a gate\n# landed")


def test_v2_design_workflow_table_drops_one_gate_at_a_time():
    text = _text("docs/V2_DESIGN.md")
    _assert_absent(text, "one gate at a time")
    _assert_present(text, "a cut's gates queued and dispatched in sequence")


def test_v2_design_ascii_diagram_mints_every_gate_in_the_cut():
    text = _text("docs/V2_DESIGN.md")
    _assert_absent(text, "pass mints one gate dispatch and its")
    _assert_present(text, "pass mints every gate's dispatch and its own")


def test_v2_design_ruling_1_drops_single_gate_claims():
    text = _text("docs/V2_DESIGN.md")
    _assert_absent(
        text,
        "Plan-to-execute mints one gate.",
        "cannot outgrow the work it plans because it is one gate long",
    )
    _assert_present(text, "Plan-to-execute mints every gate the cut named, queued")
