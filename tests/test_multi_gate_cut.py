"""A plan round may queue more than one gate at a time (obligation 1,
ahead of this gate): a cut naming several gates mints every one of them,
and once the first is accepted (`advance`) the next queued gate dispatches
on its own -- no new plan round, no panel -- until the queue runs dry
(obligation 4). That trust belongs to the one outcome that actually
committed a gate, and to no other: a `drop <gate-id>` while later gates of
the same cut are still queued still reopens plan exactly as it does today
(obligation 5), because nothing yet exists to give it anything lighter.

No form here cuts more than one gate yet (obligation 1's authoring side is
ahead of this gate too), so the several-gates-pending shape is seeded
directly as journal entries, in the exact shape `_mint_gates` itself
produces -- the same move `test_nesting._mint_n_gates` already makes for
its own drop/remint/replan tests, extended with a real, undisposed
obligation on the execution-state board so a `_settle_execution` call that
skipped the queue-pending guard would reopen plan here too, same as
`tests/test_execution_state.py::test_an_undisposed_obligation_refills_plan_
rather_than_closing` pins for a single gate. Both tests below drive the
engine's cli through its normal submit path, same as
tests/test_gate_projection.py.
"""

from engine import journal, run as runmod
from engine import cli
from test_execution_state import _fill_consolidate_with_obligation
from test_nesting import (
    _dispatch_and_close_child, _dispatch_and_close_plan, _dispatch_plan_critic,
    _fill_gate_transition, _fill_gate_transition_drop, _fill_open, _fill_plan_to_execute,
    _work_the_board,
)


def _mint_n_gates_with_obligation(n, wid="issue17",
                                   obligation="Fix the parser to handle EOF "
                                   "without a trailing newline."):
    """`g1` from a real plan round and a real critic pass, with the
    execution-state board seeded with one open obligation
    (`_fill_consolidate_with_obligation`), exactly like
    `test_execution_state._mint_first_gate_with_obligation` -- plus
    `g2..gN`, seeded directly as journal entries in the shape `_mint_gates`
    itself produces, `test_nesting._mint_n_gates`'s own move. One plan
    round still cuts one gate (obligation 1's authoring side is ahead of
    this gate), so getting several pending at once for a queue test is not
    something one submit can do yet."""
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate_with_obligation(wid, obligation)
    cli.main([wid, "submit"])
    _dispatch_and_close_plan(wid)
    _dispatch_plan_critic(wid)
    _fill_plan_to_execute(wid)
    cli.main([wid, "submit"])
    for i in range(2, n + 1):
        gid, child = f"g{i}", f"{wid}.g{i}"
        journal.append(wid, "step", id=gid, segment="execute", dispatches="run-a-gate",
                       prefill={"purpose": "gate %d purpose" % i, "scope": "gate %d scope" % i,
                                "proof": "true"},
                       child=child, anchor=False, terminal=False, source="mint")
        journal.append(wid, "step", id=f"{gid}-adjudicate", segment="execute",
                       form="forms/GATE_TRANSITION.toml", filler="conductor", child=child,
                       anchor=False, terminal=False, validates="", source="mint")


def test_queue_dispatches_without_a_plan_round_between_gates(workdir, capsys):
    """Advancing the first gate of a three-gate cut, with its own spec
    obligation still open on the execution-state board, still walks
    straight on to the next queued gate -- no fresh plan round, no panel --
    because `advance`'s own "commit; settle" is the one outcome the queue
    has earned trust from (obligation 4). Without the queue-pending guard
    this would recut the plan instead, the same way a single-gate cut's
    own `advance` does in
    `test_execution_state.test_an_undisposed_obligation_refills_plan_
    rather_than_closing` -- the only difference here is that two more gates
    are already minted and waiting."""
    _mint_n_gates_with_obligation(3)
    capsys.readouterr()

    _dispatch_and_close_child("issue17", "g1")
    capsys.readouterr()

    before = len(journal.read("issue17"))
    _fill_gate_transition("issue17")  # plan-holds = "advance"
    cli.main(["issue17", "submit"])
    capsys.readouterr()

    new_entries = journal.read("issue17")[before:]
    assert not any(e.get("kind") == "step" and e.get("segment") == "plan"
                   for e in new_entries), "advance recut the plan with gates still queued"

    st = runmod.state("issue17")
    assert st["current"]["id"] == "g2"           # the next queued gate, reached on its own
    assert st["current"]["segment"] == "execute"
    assert "g3" in {s["id"] for s in st["steps"]} and "g3" not in st["done"]


def test_drop_of_an_early_gate_still_reopens_plan_while_later_gates_are_queued(
        workdir, capsys):
    """Obligation 5: a `drop <gate-id>` while later gates of the same cut
    are still queued still reopens plan exactly as it does today -- the
    queue-pending guard trusts only the outcome that just committed a gate
    (`advance`), never a `drop`, since nothing yet exists (obligations 5, 7,
    ahead) to give a mid-cut drop anything lighter than the unconditional
    replan. The case the round the panel read did not exercise."""
    _mint_n_gates_with_obligation(3)
    capsys.readouterr()

    _dispatch_and_close_child("issue17", "g1")
    capsys.readouterr()

    _fill_gate_transition_drop("issue17", "g2")   # drops the early one; g3 is still queued
    cli.main(["issue17", "submit"])
    capsys.readouterr()

    amends = [e for e in journal.read("issue17") if e["kind"] == "amend"]
    assert {a["step"] for a in amends} == {"g2", "g2-adjudicate"}

    st = runmod.state("issue17")
    assert st["current"]["segment"] == "plan"     # reopened, not g3
    assert st["current"]["form"] != "forms/CLOSE.toml"
    fresh_plan = next(s for s in st["steps"]
                      if s["segment"] == "plan" and s.get("source") == "mint")
    assert fresh_plan["dispatches"] == "cut-a-gate"   # a real round, ruling 6 intact

    ids = {s["id"] for s in st["steps"]}
    assert not ({"g2", "g2-adjudicate"} & ids)        # the dropped gate is gone
    assert "g3" in ids and "g3" not in st["done"]      # the other queued gate: untouched
