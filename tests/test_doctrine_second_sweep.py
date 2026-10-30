"""Pins the doctrine sweep issue223.g6 makes, now that g2/g4/g5 have landed
the mechanism itself: a queued gate's own staleness, a critical question's
answer ruled as differing, and a drop or remint while later gates of the
same cut are still queued are three things -- never conflated with each
other, and never conflated with a full replan -- that each send the open
plan back for one no-panel review. Reads the files g6's own scope names as
plain prose -- a grep with a name, never a journal-driven run -- and checks
both halves of each: the stale, conflated or incomplete phrasing is gone,
and the corrected wording naming all three triggers stands in its place.
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


def test_glossary_has_queued_gate_and_critical_question_entries():
    text = _text("standards/glossary.md")
    _assert_present(
        text,
        "**queued gate** — a gate a released cut minted that has not yet dispatched",
        "**critical question** — a question a cut names when it stops short of the whole run",
        "**review of the open plan** — the planner's one-look pass over a cut's "
        "still-queued gates, no panel",
    )


def test_glossary_verdict_panel_cites_review_of_the_open_plan_not_staleness_alone():
    text = _text("standards/glossary.md")
    _assert_absent(
        text,
        "and so does a queued gate's own staleness sending the open plan back for one look",
    )
    _assert_present(
        text,
        "and so does a review of the open plan (below) sending it back for one look",
    )


def test_issue_conductor_posture_names_critical_question_ruling():
    text = _text("skills/issue-conductor/SKILL.md")
    _assert_present(
        text,
        "At that adjudication you also rule whether a critical question's actual "
        "answer matches or differs from what the cut expected",
        "a differing ruling joins a queued gate's own staleness and a mid-queue "
        "drop or remint as the three things that send the open plan back for one "
        "no-panel review, never a full replan",
    )


def test_planner_posture_review_plan_trigger_names_all_three():
    text = _text("skills/planner/SKILL.md")
    _assert_absent(
        text,
        "REVIEW_PLAN.toml when a queued gate's own staleness sent the plan back "
        "for one look -- never a panel's review",
    )
    _assert_present(
        text,
        "REVIEW_PLAN.toml when the open plan comes back for one no-panel review "
        "-- a queued gate's own staleness, a critical question's answer ruled as "
        "differing, or a drop or remint while later gates of the same cut are "
        "still queued",
    )


def test_planner_posture_drops_fresh_cut_conflation():
    text = _text("skills/planner/SKILL.md")
    _assert_absent(
        text,
        "a queued gate's own proof reads stale against the tree, or the run "
        "learns something that calls for a fresh cut",
    )
    _assert_present(
        text,
        "a queued gate's own proof reads stale against the tree, a critical "
        "question's answer is ruled as differing from what the cut expected, or "
        "a drop or remint leaves a later gate of the same cut still queued -- "
        "each its own lighter route, a review of the open plan with no panel, "
        "never folded into a fresh cut",
    )


def test_assembly_toml_review_form_comment_names_all_three_triggers():
    text = _text("assemblies/run-an-issue/ASSEMBLY.toml")
    _assert_absent(
        text,
        "when a\n# queued gate's own proof reads stale against the tree as it "
        "stands\n# (`_settle_execution`, engine/cli.py): the whole open queue "
        "closed before",
    )
    _assert_present(
        text,
        "on any\n# of three triggers (`_settle_execution`, engine/cli.py): a "
        "queued gate's\n# own proof reads stale against the tree as it stands, "
        "the gate that just\n# landed ruled its own critical-question answer as "
        "differing from what\n# the plan expected, or a `drop <gate-id>`/`remint` "
        "leaves another gate of\n# this cut still queued",
    )


def test_assembly_toml_advance_comment_names_all_three_triggers():
    text = _text("assemblies/run-an-issue/ASSEMBLY.toml")
    _assert_absent(
        text,
        "does = \"commit; settle\"     # one commit for the gate that just proved "
        "out; then the\n    # engine's own call -- an obligation still open on "
        "the execution-state",
    )
    _assert_present(
        text,
        "settle's own call (`_settle_execution`, engine/cli.py): the next\n    "
        "# queued gate's own proof reading stale against the tree, or this\n    "
        "# gate's own critical-question answer ruled as differing from what\n    "
        "# the plan expected, sends the open plan back for one no-panel review\n"
        "    # instead -- the same review a `drop <gate-id>` or `remint` reaches",
    )


def test_v2_design_workflow_ascii_block_names_all_three_review_triggers():
    text = _text("docs/V2_DESIGN.md")
    _assert_absent(
        text,
        "and a coarse horizon of what the cut stops short of",
        "Only once the queue is empty\n                  does the adjudication "
        "become the replan beat",
    )
    _assert_present(
        text,
        "and, short of the whole run, its critical questions and\n                  "
        "a coarse horizon of what it stops short of",
        "A queued gate's own\n                  staleness, a critical question's "
        "answer ruled as\n                  differing, or a drop/remint while "
        "later gates of this cut\n                  are still queued each send "
        "the open plan back for one\n                  no-panel review instead "
        "-- not a replan. Only once the\n                  queue runs dry with "
        "an obligation still open does the\n                  adjudication "
        "become the replan beat",
    )


def test_v2_design_ruling_1_horizon_sketch_names_critical_questions():
    text = _text("docs/V2_DESIGN.md")
    _assert_absent(
        text,
        "up to the whole run — and\nsketches the horizon behind whatever it "
        "stops short of",
    )
    _assert_present(
        text,
        "up to the whole run — and,\nshort of the whole run, names its critical "
        "questions and sketches the horizon behind whatever\nit stops short of",
    )


def test_v2_design_issue_tier_table_produces_names_critical_question():
    text = _text("docs/V2_DESIGN.md")
    _assert_absent(
        text,
        "the **next gate** from the spec and what has landed, plus a coarse "
        "horizon",
    )
    _assert_present(
        text,
        "the **next gate** from the spec and what has landed, plus its "
        "critical questions and a coarse horizon of what it stops short of",
    )


def test_v2_design_ruling_1_drops_replan_beat_conflation():
    text = _text("docs/V2_DESIGN.md")
    _assert_absent(
        text,
        "until the queue runs dry, a queued gate's own proof reads stale\n"
        "against the tree, or an obligation stays open with nothing left "
        "queued. Only then is a gate's\nadjudication the replan beat:",
    )
    _assert_present(
        text,
        "until\nthe queue runs dry. Three things reopen the plan for one "
        "no-panel review along the way, never a\nfull replan: a queued gate's "
        "own proof reading stale against the tree as it stands, a critical\n"
        "question's answer ruled as differing from what the plan expected, "
        "and a drop or remint while\nlater gates of the same cut are still "
        "queued. Only once the queue runs dry with an obligation\nstill open "
        "is a gate's adjudication the replan beat:",
    )
