"""o6: a queued gate's own proof is checked against the tree as it stands
before it is started. A reading of "already true" or "cannot run as a
command" is never trusted into dispatch -- the whole open queue closes
instead, and the plan segment reopens for one review round, no panel, with
every closed gate's own fields and the conductor's own findings from the
most recently landed gate's adjudication. A reading that ran and genuinely
failed is the healthy one, and dispatch carries on exactly as
`test_multi_gate_cut.py` already pins for an ordinary queue.

This drives a real multi-gate cut through one real `PLAN.toml` fill --
every gate named in its own `gates` field, never seeded directly into the
journal the way `test_multi_gate_cut.py`'s own fixture is (that gate's own
authoring side was still ahead of it; this one is not).
"""

from engine import journal, run as runmod
from engine import cli
from test_nesting import (
    _dispatch_and_close_child, _dispatch_and_close_plan, _dispatch_plan_critic,
    _fill_consolidate, _fill_gate_transition, _fill_open, _fill_plan,
    _fill_plan_to_execute, _fill_review_plan, _work_the_board,
)


def _mint_a_cut(wid, gates):
    """Open a real run-an-issue, and cut `gates` (a list of gate dicts) in
    one real `PLAN.toml` fill, released through a real critic pass and a
    real plan-to-execute submit -- the shape every gate in `gates` ends up
    queued in the execute segment's own worklist, in order."""
    cli.main(["open", "run-an-issue", "--issue", wid[len("issue"):], "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    _dispatch_and_close_plan(wid, fill_fn=lambda w: _fill_plan(w, gates=gates))
    _dispatch_plan_critic(wid)
    _fill_plan_to_execute(wid)
    cli.main([wid, "submit"])


def _advance_g1(wid):
    """Dispatch and close g1, then rule `advance` on its adjudication --
    the one outcome that earns the queue its trust (`advance`'s own
    "commit; settle"), and the submit this whole module's tests check the
    aftermath of."""
    _dispatch_and_close_child(wid, "g1")
    before = len(journal.read(wid))
    _fill_gate_transition(wid)  # plan-holds = "advance"
    cli.main([wid, "submit"])
    return before


def _fresh_plan_round(wid):
    """The plan segment's own fresh interior step, minted by the staleness
    review -- the same lookup `_drive_plan_to_pause` (test_nesting.py)
    already makes for a rework round's own fresh mint."""
    st = runmod.state(wid)
    return next(s for s in st["steps"]
                if s["segment"] == "plan" and s.get("source") == "mint"
                and s["id"] not in st["done"] and s.get("dispatches"))


def test_a_gate_whose_proof_already_passes_closes_the_whole_queue_and_reopens_plan_with_no_panel(
        workdir, capsys):
    """`g2`'s own proof (`true`) already passes against the untouched
    tree -- the stale reading obligation 6 names first. Advancing `g1`
    closes `g2` and `g3` both, not only the one checked, and reopens plan
    on `REVIEW_PLAN.toml` -- the review route, minted with no panel
    (`panel-rounds = "fresh"`, and this round is not a `restarts` one)."""
    wid = "issue61"
    _mint_a_cut(wid, [
        {"purpose": "gate 1 purpose", "scope": "gate 1 scope", "proof": "true"},
        {"purpose": "gate 2 purpose", "scope": "gate 2 scope", "proof": "true"},
        {"purpose": "gate 3 purpose", "scope": "gate 3 scope", "proof": "false",
         "gate_proof": "gate 3 gate-proof", "model": "heavy",
         "direction": "gate 3 direction"},
    ])
    capsys.readouterr()

    before = _advance_g1(wid)
    capsys.readouterr()

    new_entries = journal.read(wid)[before:]
    amends = [e for e in new_entries if e["kind"] == "amend"]
    assert {a["step"] for a in amends} == {"g2", "g2-adjudicate", "g3", "g3-adjudicate"}

    st = runmod.state(wid)
    ids = {s["id"] for s in st["steps"]}
    assert not ({"g2", "g2-adjudicate", "g3", "g3-adjudicate"} & ids), \
        "the whole queue should have closed, not only the gate checked"

    assert st["current"]["segment"] == "plan"
    fresh = _fresh_plan_round(wid)
    assert fresh["dispatches"] == "cut-a-gate"
    assert fresh["form"] == "skills/planner/forms/REVIEW_PLAN.toml"

    transition_entries = [e for e in new_entries if e.get("kind") == "step"
                          and e.get("segment") == "plan" and e.get("source") == "panel"]
    assert len(transition_entries) == 1
    assert "panel" not in transition_entries[0], "a staleness review mints no panel"

    prefill = fresh["prefill"]
    assert "g2" in prefill.get("stale", "") or "g2-adjudicate" not in ids and \
        prefill.get("stale", "").startswith("g2")
    assert "gate 2 purpose" in prefill.get("closed-queue", "")
    assert "gate 3 purpose" in prefill.get("closed-queue", "")
    assert "gate 3 gate-proof" in prefill.get("closed-queue", "")
    assert "gate 3 direction" in prefill.get("closed-queue", "")


def test_a_gate_whose_proof_cannot_run_as_a_command_also_closes_the_whole_queue(
        workdir, capsys):
    """The same stale reading `_resolve_command` already gives a missing
    palette entry -- exit 127 -- closes the queue exactly as an
    already-passing proof does."""
    wid = "issue62"
    _mint_a_cut(wid, [
        {"purpose": "gate 1 purpose", "scope": "gate 1 scope", "proof": "true"},
        {"purpose": "gate 2 purpose", "scope": "gate 2 scope",
         "proof": "palette:no-such-entry-anywhere"},
    ])
    capsys.readouterr()

    before = _advance_g1(wid)
    capsys.readouterr()

    new_entries = journal.read(wid)[before:]
    amends = [e for e in new_entries if e["kind"] == "amend"]
    assert {a["step"] for a in amends} == {"g2", "g2-adjudicate"}

    st = runmod.state(wid)
    assert st["current"]["segment"] == "plan"
    fresh = _fresh_plan_round(wid)
    assert fresh["form"] == "skills/planner/forms/REVIEW_PLAN.toml"


def test_a_gate_whose_proof_still_fails_dispatches_without_a_plan_round(workdir, capsys):
    """The healthy reading: `g2`'s own proof (`false`) ran and genuinely
    failed, so it dispatches exactly as `test_multi_gate_cut.py`'s own
    queue-dispatches test pins for the ordinary case."""
    wid = "issue63"
    _mint_a_cut(wid, [
        {"purpose": "gate 1 purpose", "scope": "gate 1 scope", "proof": "true"},
        {"purpose": "gate 2 purpose", "scope": "gate 2 scope", "proof": "false"},
    ])
    capsys.readouterr()

    before = _advance_g1(wid)
    capsys.readouterr()

    new_entries = journal.read(wid)[before:]
    assert not any(e.get("kind") == "step" and e.get("segment") == "plan"
                   for e in new_entries), "a gate whose proof genuinely fails is not stale"

    st = runmod.state(wid)
    assert st["current"]["id"] == "g2"
    assert "g2" not in st["done"]


def test_the_review_rounds_response_mints_the_whole_fresh_queue_in_one_release(
        workdir, capsys):
    """Naming several gates in one `REVIEW_PLAN.toml` response mints the
    whole fresh queue in one release -- never appended beside whatever the
    stale reading's own close left behind, which is gone."""
    wid = "issue64"
    _mint_a_cut(wid, [
        {"purpose": "gate 1 purpose", "scope": "gate 1 scope", "proof": "true"},
        {"purpose": "gate 2 purpose", "scope": "gate 2 scope", "proof": "true"},
    ])
    capsys.readouterr()
    _advance_g1(wid)
    capsys.readouterr()

    fresh = _fresh_plan_round(wid)
    _dispatch_and_close_plan(wid, fresh["id"], fill_fn=lambda w: _fill_review_plan(w, [
        {"purpose": "g2 replacement purpose", "scope": "fresh scope a", "proof": "false"},
        {"purpose": "g3 replacement purpose", "scope": "fresh scope b", "proof": "false"},
    ]))
    capsys.readouterr()

    # no panel on this round, so the conductor's own release form is
    # already reachable -- `_dispatch_and_close_plan` already stood on it
    _fill_plan_to_execute(wid)
    cli.main([wid, "submit"])
    capsys.readouterr()

    st = runmod.state(wid)
    gates = [s for s in st["steps"] if s.get("dispatches") == "run-a-gate"]
    # a closed id is never reused (#312), so the fresh pair need not be
    # named "g2"/"g3" again -- what matters is there are exactly two of
    # them, fresh, in the planner's own order, and nothing of the closed
    # queue (a `true` proof, long gone) rides along beside them
    assert len(gates) == 3
    assert gates[0]["id"] == "g1"
    fresh_two = gates[1:]
    assert [g["prefill"]["purpose"] for g in fresh_two] == [
        "g2 replacement purpose", "g3 replacement purpose"]
    assert all(g["prefill"]["proof"] == "false" for g in fresh_two)
