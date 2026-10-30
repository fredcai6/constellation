"""Obligation 5's third bullet: a `drop <gate-id>` or a `remint` while later
gates of the same cut are still queued closes the rest of the queue and
sends the open plan back for one review round, no panel -- the same
no-panel route `tests/test_stale_gate_review.py` already pins for a stale
reading -- rather than today's unconditional, full-panel replan. Where
nothing else is left queued, both outcomes carry on exactly as before: a
remint's own fresh replacement simply dispatches (pinning the fix for the
panel's own finding that a fresh read, rather than the pre-verb queue
snapshot, would review on every remint -- including one landing the cut's
own last gate, which obligation 5 does not ask for).

A `replan` with several gates queued still closes every one of them, not
only the gate the conductor named, and still stands alone with its own
fresh panel (obligation 8, re-verified here against a real multi-gate cut).

Every drop or remint below is ruled at `g1`'s own adjudication -- the same
seam `tests/test_nesting.py`'s own `test_drop_closes_a_remint_minted_pair_
too` and `test_multi_gate_cut.py`'s own replan test already rule a
different outcome than `advance` from: naming (`drop <gate-id>`) or
replacing (`remint`) a gate while a later one of the same cut sits still
queued, never dispatched for real. `g2`/`g3`'s own `proof` (`false`) is
never run for real here, only read for staleness or closed outright -- a
`true` would have the committed path's own staleness probe (which does
run for real, as a trial) mistake it for an already-passing gate the
moment `g1` genuinely advanced; nothing here ever advances `g1`, so that
probe never runs regardless, but `false` keeps every gate's own shape
consistent with `test_stale_gate_review.py`'s own fixtures.

This drives a real multi-gate cut through one real `PLAN.toml` fill --
every gate named in its own `gates` field, the `tests/test_stale_gate_review.
py`-style `_mint_a_cut` shape, not `test_multi_gate_cut.py`'s own
seeded-journal one, since the authoring side of naming several gates in one
submit already landed (g1)."""

from engine import journal, run as runmod
from engine import cli
from test_nesting import (
    _dispatch_and_close_child, _fill_gate_transition_drop, _fill_gate_transition_remint,
    _fill_gate_transition_replan,
)
from test_stale_gate_review import _fresh_plan_round, _mint_a_cut


def _transition_entry(new_entries):
    """The plan segment's own fresh transition-round journal entry among
    `new_entries` -- `_mint_segment_round`'s `source = "panel"` label names
    the transition round itself, not that a panel actually dispatched; a
    `"panel"` key on it is what says a panel did. Exactly one such entry
    per fresh plan round, the same read `tests/test_stale_gate_review.py`
    already makes."""
    found = [e for e in new_entries if e.get("kind") == "step"
             and e.get("segment") == "plan" and e.get("source") == "panel"]
    assert len(found) == 1
    return found[0]


def test_drop_with_a_later_gate_still_queued_reviews_the_open_plan(workdir, capsys):
    """A `drop <gate-id>` ruled at `g1`'s own adjudication, naming `g2` as
    the now-pointless one to close, while `g3` (a later gate of the same
    cut) is still queued: this reopens plan for one review round, no
    panel, closing `g3` along with the named `g2` -- the whole rest of the
    queue, not only the gate the ruling named."""
    wid = "issue65"
    _mint_a_cut(wid, [
        {"purpose": "gate 1 purpose", "scope": "gate 1 scope", "proof": "true"},
        {"purpose": "gate 2 purpose", "scope": "gate 2 scope", "proof": "false"},
        {"purpose": "gate 3 purpose", "scope": "gate 3 scope", "proof": "false"},
    ])
    capsys.readouterr()

    _dispatch_and_close_child(wid, "g1")
    capsys.readouterr()

    before = len(journal.read(wid))
    _fill_gate_transition_drop(wid, "g2")   # drops the early one; g3 is still queued
    cli.main([wid, "submit"])
    capsys.readouterr()

    new_entries = journal.read(wid)[before:]
    amends = [e for e in new_entries if e["kind"] == "amend"]
    assert {a["step"] for a in amends} == {"g2", "g2-adjudicate", "g3", "g3-adjudicate"}

    st = runmod.state(wid)
    ids = {s["id"] for s in st["steps"]}
    assert not ({"g2", "g2-adjudicate", "g3", "g3-adjudicate"} & ids), \
        "the whole rest of the queue should have closed, not only the gate named"

    assert st["current"]["segment"] == "plan"
    fresh = _fresh_plan_round(wid)
    assert fresh["dispatches"] == "cut-a-gate"
    assert fresh["form"] == "skills/planner/forms/REVIEW_PLAN.toml"
    assert "panel" not in _transition_entry(new_entries), \
        "a mid-queue drop review mints no panel"

    prefill = fresh["prefill"]
    assert "g2" in prefill.get("stale", "") and "dropped" in prefill.get("stale", "")
    assert "still queued" in prefill.get("stale", "")
    assert "gate 3 purpose" in prefill.get("closed-queue", "")
    assert prefill.get("findings") == "no longer needed"


def test_remint_with_a_later_gate_still_queued_reviews_the_open_plan(workdir, capsys):
    """A `remint` ruled at `g1`'s own adjudication -- replacing `g1` itself
    with a fresh gate-spec rather than advancing it -- while `g2` and `g3`
    are still queued behind it: this mints the fresh replacement first and
    then reopens plan for one review round, no panel, closing `g2` and `g3`
    *and* the fresh replacement itself, since all three are "still queued"
    the moment the review runs. The naming -- which gate was re-minted --
    reads off the deciding step's own id (`g1`), the pre-verb snapshot's
    own ground."""
    wid = "issue66"
    _mint_a_cut(wid, [
        {"purpose": "gate 1 purpose", "scope": "gate 1 scope", "proof": "true"},
        {"purpose": "gate 2 purpose", "scope": "gate 2 scope", "proof": "false"},
        {"purpose": "gate 3 purpose", "scope": "gate 3 scope", "proof": "false"},
    ])
    capsys.readouterr()

    _dispatch_and_close_child(wid, "g1")
    capsys.readouterr()

    before = len(journal.read(wid))
    _fill_gate_transition_remint(wid, purpose="g1 redone", scope="src/ only", proof="true")
    cli.main([wid, "submit"])
    capsys.readouterr()

    new_entries = journal.read(wid)[before:]
    mints = [e for e in new_entries if e.get("kind") == "step"
             and e.get("dispatches") == "run-a-gate"]
    assert len(mints) == 1, "the remint's own fresh replacement, minted before settle ran"
    new_id = mints[0]["id"]

    amends = [e for e in new_entries if e["kind"] == "amend"]
    assert {a["step"] for a in amends} == {
        new_id, f"{new_id}-adjudicate", "g2", "g2-adjudicate", "g3", "g3-adjudicate"}

    st = runmod.state(wid)
    ids = {s["id"] for s in st["steps"]}
    assert not ({new_id, f"{new_id}-adjudicate", "g2", "g2-adjudicate",
                 "g3", "g3-adjudicate"} & ids), \
        "the fresh replacement and the rest of the queue should both have closed"

    assert st["current"]["segment"] == "plan"
    fresh = _fresh_plan_round(wid)
    assert fresh["dispatches"] == "cut-a-gate"
    assert fresh["form"] == "skills/planner/forms/REVIEW_PLAN.toml"
    assert "panel" not in _transition_entry(new_entries), \
        "a mid-queue remint review mints no panel"

    prefill = fresh["prefill"]
    assert "g1" in prefill.get("stale", "") and "re-minted" in prefill.get("stale", "")
    assert "still queued" in prefill.get("stale", "")
    assert "g1 redone" in prefill.get("closed-queue", "")
    assert "gate 2 purpose" in prefill.get("closed-queue", "")
    assert "gate 3 purpose" in prefill.get("closed-queue", "")
    assert prefill.get("findings") == "the spec was wrong, needs a redo"


def test_remint_of_the_cuts_own_last_gate_with_nothing_else_queued_dispatches_without_review(
        workdir, capsys):
    """`g1` is the cut's own only (and so last) gate -- nothing is queued
    behind it, before or after the remint runs. A fresh read taken after
    the remint's own replacement already minted would find that
    replacement pending and review on every remint, including this one
    landing the cut's own last gate; obligation 5 does not ask for that.
    Grounded in the pre-verb snapshot instead -- empty here, since nothing
    but `g1` itself was ever queued -- no review fires: the replacement
    simply dispatches."""
    wid = "issue67"
    _mint_a_cut(wid, [
        {"purpose": "gate 1 purpose", "scope": "gate 1 scope", "proof": "true"},
    ])
    capsys.readouterr()

    _dispatch_and_close_child(wid, "g1")
    capsys.readouterr()

    before = len(journal.read(wid))
    _fill_gate_transition_remint(wid, purpose="g1 redone", scope="src/ only", proof="true")
    cli.main([wid, "submit"])
    capsys.readouterr()

    new_entries = journal.read(wid)[before:]
    assert not any(e["kind"] == "amend" for e in new_entries), \
        "nothing else was queued -- the replacement should simply dispatch"

    mints = [e for e in new_entries if e.get("kind") == "step"
             and e.get("dispatches") == "run-a-gate"]
    assert len(mints) == 1
    new_id = mints[0]["id"]

    st = runmod.state(wid)
    assert st["current"]["id"] == new_id
    assert st["current"]["segment"] == "execute"


def test_replan_with_several_gates_queued_closes_every_one_and_stands_alone_with_a_fresh_panel(
        workdir, capsys):
    """Obligation 8, re-verified against a real multi-gate cut: a `replan`
    ruled at `g1`'s own adjudication, with `g2` and `g3` still queued
    behind it, closes both of them -- not only the gate the conductor
    named -- and re-enters plan with its own fresh round, a fresh panel,
    read cold (`PLAN.toml`, not `REVIEW_PLAN.toml`)."""
    wid = "issue68"
    _mint_a_cut(wid, [
        {"purpose": "gate 1 purpose", "scope": "gate 1 scope", "proof": "true"},
        {"purpose": "gate 2 purpose", "scope": "gate 2 scope", "proof": "false"},
        {"purpose": "gate 3 purpose", "scope": "gate 3 scope", "proof": "false"},
    ])
    capsys.readouterr()

    _dispatch_and_close_child(wid, "g1")
    capsys.readouterr()

    before = len(journal.read(wid))
    _fill_gate_transition_replan(wid, findings="the cut was wrong from the start")
    cli.main([wid, "submit"])
    capsys.readouterr()

    new_entries = journal.read(wid)[before:]
    amends = [e for e in new_entries if e["kind"] == "amend"]
    assert {a["step"] for a in amends} == {"g2", "g2-adjudicate", "g3", "g3-adjudicate"}
    assert all(a["action"] == "close" and a["reason"] == "replan" for a in amends)

    st = runmod.state(wid)
    ids = {s["id"] for s in st["steps"]}
    assert not ({"g2", "g2-adjudicate", "g3", "g3-adjudicate"} & ids)
    assert "g1" in st["done"] and "g1-adjudicate" in st["done"]   # the decider: untouched

    assert st["current"]["segment"] == "plan"
    fresh = _fresh_plan_round(wid)
    assert fresh["dispatches"] == "cut-a-gate"
    assert fresh["form"] == "skills/planner/forms/PLAN.toml"      # a full replan, cold
    assert fresh["prefill"]["findings"] == "the cut was wrong from the start"
    assert _transition_entry(new_entries).get("panel"), \
        "a replan stands alone with its own fresh panel"
