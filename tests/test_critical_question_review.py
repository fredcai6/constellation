"""Obligation 3 and obligation 5's second bullet: a cut that stops short of
the whole run names its critical questions -- for each, which queued gate
(by its own position in the round) is expected to answer it, and the answer
the cut expects. When that gate's own adjudication rules the actual answer
as differing from the expected one (GATE_TRANSITION.toml's own
`critical-question` field), the open plan gets the same no-panel review a
stale reading already gets, contributing its own reason to the shared list;
an answer ruled as matching reopens nothing, and the queue dispatches on
exactly as it does today when nothing was learned.

`_settle_execution`'s committed branch reads this beside its own existing
staleness check -- either, neither, or both can hold for one `advance`, and
both are read before anything mints so one settle calls the shared
review-mint helper exactly once, carrying every reason that fired.

This drives a real multi-gate cut through one real `PLAN.toml` fill, the
`tests/test_stale_gate_review.py`-style `_mint_a_cut` shape, naming the
cut's own second gate (`g2`) as the critical question's answerer, then
drives `g1` and `g2` for real through `_dispatch_and_close_child` -- `g2`'s
own adjudication is where the ruling lands."""

from engine import journal, run as runmod
from engine import cli
from test_nesting import (
    PURPOSE_HOLDS, _dispatch_and_close_child, _fill, _fill_open, _response,
    _work_the_board, _fill_consolidate, _gate_blocks, _write_plan_artifact,
    _dispatch_and_close_plan, _dispatch_plan_critic, _fill_plan_to_execute,
)
from test_stale_gate_review import _fresh_plan_round


def _fill_plan_with_critical_questions(wid, gates, critical_questions):
    """PLAN.toml's `gates` field, plus a `critical-questions` block naming
    which queued gate (by its own position in this round) is expected to
    answer each question, and the answer this cut expects -- the shape
    obligation 3 asks for, filled once per round alongside `gates`."""
    loc = journal.location(wid)
    _write_plan_artifact(loc / "plan.md")
    cq_blocks = "".join(
        '[[critical-questions]]\nquestion = "%s"\ngate = "%s"\n'
        'expected-answer = "%s"\n\n' % (
            cq["question"], cq["gate"], cq["expected-answer"])
        for cq in critical_questions)
    _fill(_response(wid), '''
plan = "%s/plan.md"
call-tree = "waived: none yet"
key-terms = "waived: none"

%s%s''' % (loc, cq_blocks, _gate_blocks(gates)))


def _mint_a_cut_with_critical_questions(wid, gates, critical_questions):
    """The same real-PLAN.toml, real-critic, real-plan-to-execute shape
    `test_stale_gate_review.py`'s own `_mint_a_cut` drives, through a fill
    that also names `critical_questions`."""
    cli.main(["open", "run-an-issue", "--issue", wid[len("issue"):], "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    _dispatch_and_close_plan(wid, fill_fn=lambda w: _fill_plan_with_critical_questions(
        w, gates, critical_questions))
    _dispatch_plan_critic(wid)
    _fill_plan_to_execute(wid)
    cli.main([wid, "submit"])


def _fill_gate_transition_critical_question(wid, ruling, findings="the gate's own answer"):
    """`g2`'s own adjudication: the conductor's ruling on the critical
    question the cut named it to answer -- `ruling` is `"matches"` or
    `"differs: <reason>"`, GATE_TRANSITION.toml's own enforced vocabulary."""
    _fill(_response(wid), PURPOSE_HOLDS + '''
findings = "%s"
critical-question = "%s"
plan-holds = "advance"
''' % (findings, ruling))


def _transition_entry(new_entries):
    found = [e for e in new_entries if e.get("kind") == "step"
             and e.get("segment") == "plan" and e.get("source") == "panel"]
    assert len(found) == 1
    return found[0]


# `g2` is the one gate every test below actually drives to a real close
# (`_advance_g1_then_dispatch_g2`), so its own proof cannot be a fixed
# `"true"` or `"false"` the way a never-dispatched queued gate's can
# elsewhere, and it cannot be a simple once-fails-then-passes toggle
# either: `_trial_proofs` (engine/cli.py) already runs every gate's own
# `proof` once, as a trial, at the cut's own `PLAN.toml` submit, before
# `g1` even dispatches -- so the identical command actually runs three
# times before g2's own close: that first trial, `_proof_is_stale`'s own
# pre-dispatch read once `g1` commits, and g2's own real implement
# submit. A counter is the one answer that reads right every time: not
# yet 3 is unstale (and harmless at the trial), 3 is the real work done.
_G2_PROOF = ('c=$(cat .g2-proof-count 2>/dev/null || echo 0); c=$((c+1)); '
             'echo $c > .g2-proof-count; [ $c -ge 3 ]')

_CUT = [
    {"purpose": "gate 1 purpose", "scope": "gate 1 scope", "proof": "true"},
    {"purpose": "gate 2 purpose", "scope": "gate 2 scope", "proof": _G2_PROOF},
]

_CRITICAL_QUESTIONS = [{
    "question": "does the parser need a second pass for multi-byte EOF",
    "gate": "g2",
    "expected-answer": "no -- one pass is enough",
}]


def _advance_g1_then_dispatch_g2(wid, gates):
    _mint_a_cut_with_critical_questions(wid, gates, _CRITICAL_QUESTIONS)
    _dispatch_and_close_child(wid, "g1")
    _fill(_response(wid), PURPOSE_HOLDS + '''
findings = "waived: none"
plan-holds = "advance"
''')
    cli.main([wid, "submit"])
    _dispatch_and_close_child(wid, "g2")


def test_an_answer_ruled_differing_reviews_the_open_plan_with_the_next_gate_healthy(
        workdir, capsys):
    """`g2` is named as the critical question's answerer; its own
    adjudication rules the answer `differs`. `g3`'s own proof (`false`) is
    not stale, so only `g2`'s own reason fires -- one review round, no
    panel, carrying that one reason."""
    wid = "issue81"
    gates = _CUT + [{"purpose": "gate 3 purpose", "scope": "gate 3 scope", "proof": "false"}]
    _advance_g1_then_dispatch_g2(wid, gates)
    capsys.readouterr()

    before = len(journal.read(wid))
    _fill_gate_transition_critical_question(
        wid, "differs: a second pass is needed for multi-byte EOF after all")
    cli.main([wid, "submit"])
    capsys.readouterr()

    new_entries = journal.read(wid)[before:]
    amends = [e for e in new_entries if e["kind"] == "amend"]
    assert {a["step"] for a in amends} == {"g3", "g3-adjudicate"}

    st = runmod.state(wid)
    assert st["current"]["segment"] == "plan"
    fresh = _fresh_plan_round(wid)
    assert fresh["dispatches"] == "cut-a-gate"
    assert fresh["form"] == "skills/planner/forms/REVIEW_PLAN.toml"
    assert "panel" not in _transition_entry(new_entries), \
        "a critical-question-differs review mints no panel"

    prefill = fresh["prefill"]
    assert "g2" in prefill.get("stale", "")
    assert "differs" in prefill.get("stale", "")
    assert "multi-byte EOF after all" in prefill.get("stale", "")
    assert "stale against the tree" not in prefill.get("stale", ""), \
        "g3's own proof never read as stale here -- only one reason should fire"
    assert "gate 3 purpose" in prefill.get("closed-queue", "")


def test_an_answer_ruled_matching_dispatches_the_next_gate_as_today(workdir, capsys):
    """`g2`'s own adjudication rules the answer `matches` what the plan
    expected -- nothing was learned, and the queue dispatches `g3` exactly
    as an ordinary `advance` already does."""
    wid = "issue82"
    gates = _CUT + [{"purpose": "gate 3 purpose", "scope": "gate 3 scope", "proof": "false"}]
    _advance_g1_then_dispatch_g2(wid, gates)
    capsys.readouterr()

    before = len(journal.read(wid))
    _fill_gate_transition_critical_question(wid, "matches")
    cli.main([wid, "submit"])
    capsys.readouterr()

    new_entries = journal.read(wid)[before:]
    assert not any(e["kind"] == "amend" for e in new_entries), \
        "a matching answer teaches the queue nothing -- it dispatches, not reviews"

    st = runmod.state(wid)
    assert st["current"]["id"] == "g3"
    assert st["current"]["segment"] == "execute"


def test_a_differing_answer_and_a_stale_next_gate_both_fire_but_mint_one_review(
        workdir, capsys):
    """`g2`'s own adjudication rules the answer `differs`, *and* `g3`'s own
    proof (`true`) already reads as passing against the untouched tree --
    both reasons fire on this one settle, and still only one
    `REVIEW_PLAN.toml` is minted, carrying both."""
    wid = "issue83"
    gates = _CUT + [{"purpose": "gate 3 purpose", "scope": "gate 3 scope", "proof": "true"}]
    _advance_g1_then_dispatch_g2(wid, gates)
    capsys.readouterr()

    before = len(journal.read(wid))
    _fill_gate_transition_critical_question(
        wid, "differs: a second pass is needed for multi-byte EOF after all")
    cli.main([wid, "submit"])
    capsys.readouterr()

    new_entries = journal.read(wid)[before:]
    amends = [e for e in new_entries if e["kind"] == "amend"]
    assert {a["step"] for a in amends} == {"g3", "g3-adjudicate"}

    st = runmod.state(wid)
    assert st["current"]["segment"] == "plan"
    fresh = _fresh_plan_round(wid)
    assert fresh["form"] == "skills/planner/forms/REVIEW_PLAN.toml"

    transition_entries = [e for e in new_entries if e.get("kind") == "step"
                          and e.get("segment") == "plan" and e.get("source") == "panel"]
    assert len(transition_entries) == 1, "both reasons still mint only once"
    assert "panel" not in transition_entries[0]

    prefill = fresh["prefill"]
    assert "g2" in prefill.get("stale", "") and "differs" in prefill.get("stale", "")
    assert "g3" in prefill.get("stale", "") and "stale against the tree" in prefill.get("stale", "")
    assert "gate 3 purpose" in prefill.get("closed-queue", "")


# -- obligation 9: the three planner forms teach the per-gate call-tree
#    naming convention standards/glossary.md's own entry already states --
#    the same grep-with-a-name shape test_doctrine_says_multi_gate.py uses
#    for doctrine prose, read here against the forms themselves.

_CALL_TREE_NOTE_PHRASE = (
    "Once a round cuts more than one gate, a `THIS GATE` node also names "
    "which gate, by its own position in the round, owns it -- never a "
    "predicted engine-assigned id.")


def _collapsed(text):
    import re
    return re.sub(r"\s+", " ", text)


def test_the_three_planner_forms_teach_the_per_gate_call_tree_convention():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    for relpath in ("skills/planner/forms/PLAN.toml", "skills/planner/forms/REWORK.toml",
                    "skills/planner/forms/REVIEW_PLAN.toml"):
        text = (root / relpath).read_text()
        assert _collapsed(_CALL_TREE_NOTE_PHRASE) in _collapsed(text), \
            f"{relpath}: call-tree's own note is missing the per-gate naming convention"
