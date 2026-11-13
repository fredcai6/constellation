"""Pins the doctrine sweep issue223.g6 makes, now that g2/g4/g5 have landed
the mechanism itself: a queued gate's own staleness, a critical question's
answer ruled as differing, and a drop or remint while later gates of the
same cut are still queued are three things -- never conflated with each
other, and never conflated with a full replan -- that each send the open
plan back for one no-panel review. Reads the files g6's own scope names as
plain prose -- a grep with a name, never a journal-driven run -- and checks
that the stale, conflated or incomplete phrasing is gone. It does not pin
the wording that replaced it: a pinned sentence cannot be simplified, and
pinning these did not catch PLAN.toml contradicting the planner skill.
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


def test_glossary_verdict_panel_cites_review_of_the_open_plan_not_staleness_alone():
    text = _text("standards/glossary.md")
    _assert_absent(
        text,
        "and so does a queued gate's own staleness sending the open plan back for one look",
    )


def test_planner_posture_review_plan_trigger_names_all_three():
    text = _text("skills/planner/SKILL.md")
    _assert_absent(
        text,
        "REVIEW_PLAN.toml when a queued gate's own staleness sent the plan back "
        "for one look -- never a panel's review",
    )


def test_planner_posture_drops_fresh_cut_conflation():
    text = _text("skills/planner/SKILL.md")
    _assert_absent(
        text,
        "a queued gate's own proof reads stale against the tree, or the run "
        "learns something that calls for a fresh cut",
    )


def test_assembly_toml_review_form_comment_names_all_three_triggers():
    text = _text("assemblies/run-an-issue/ASSEMBLY.toml")
    _assert_absent(
        text,
        "when a\n# queued gate's own proof reads stale against the tree as it "
        "stands\n# (`_settle_execution`, engine/cli.py): the whole open queue "
        "closed before",
    )


def test_assembly_toml_advance_comment_names_all_three_triggers():
    text = _text("assemblies/run-an-issue/ASSEMBLY.toml")
    _assert_absent(
        text,
        "does = \"commit; settle\"     # one commit for the gate that just proved "
        "out; then the\n    # engine's own call -- an obligation still open on "
        "the execution-state",
    )


def test_v2_design_workflow_ascii_block_names_all_three_review_triggers():
    text = _text("docs/V2_DESIGN.md")
    _assert_absent(
        text,
        "and a coarse horizon of what the cut stops short of",
        "Only once the queue is empty\n                  does the adjudication "
        "become the replan beat",
    )


def test_v2_design_ruling_1_horizon_sketch_names_critical_questions():
    text = _text("docs/V2_DESIGN.md")
    _assert_absent(
        text,
        "up to the whole run — and\nsketches the horizon behind whatever it "
        "stops short of",
    )


def test_v2_design_issue_tier_table_produces_names_critical_question():
    text = _text("docs/V2_DESIGN.md")
    _assert_absent(
        text,
        "the **next gate** from the spec and what has landed, plus a coarse "
        "horizon",
    )


def test_v2_design_ruling_1_drops_replan_beat_conflation():
    text = _text("docs/V2_DESIGN.md")
    _assert_absent(
        text,
        "until the queue runs dry, a queued gate's own proof reads stale\n"
        "against the tree, or an obligation stays open with nothing left "
        "queued. Only then is a gate's\nadjudication the replan beat:",
    )


# The glossary entries themselves are terms, not wording: a term that goes
# missing is a real loss, so this one check of presence stays.
def _assert_present(text, *phrases):
    collapsed = _collapsed(text)
    for phrase in phrases:
        assert _collapsed(phrase) in collapsed, f"corrected phrase missing: {phrase!r}"


def test_glossary_has_queued_gate_and_critical_question_entries():
    text = _text("standards/glossary.md")
    _assert_present(
        text,
        "**queued gate** — a gate a released cut minted that has not yet dispatched",
        "**critical question** — a question a cut names when it stops short of the whole run",
        "**review of the open plan** — the planner's one-look pass over a cut's "
        "still-queued gates, no panel",
    )
