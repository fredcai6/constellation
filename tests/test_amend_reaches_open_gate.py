"""A proof ruled at the parent reaches a gate child that is already open.

The child's check reads the binding proof off its parent's current gate step,
not from its own prefill: a conductor that amends a proof at the parent after
the child asked up on one that could never pass must see the resumed round's
hand-in run the amended text.

See: #214
"""

import pytest

from engine import cli, journal, run as runmod
from test_nesting import (
    _dispatch_and_close_plan, _dispatch_plan_critic, _fill_implement, _fill_plan,
    _fill_plan_to_execute, _fill_open, _work_the_board, _fill_consolidate,
)


def _to_open_gate(proof):
    from functools import partial
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "parser drops last record"])
    _fill_open("issue17")
    cli.main(["issue17", "submit"])
    _work_the_board("issue17")
    _fill_consolidate("issue17")
    cli.main(["issue17", "submit"])
    _dispatch_and_close_plan("issue17", fill_fn=partial(_fill_plan, proof=proof))
    _dispatch_plan_critic("issue17")
    _fill_plan_to_execute("issue17")
    cli.main(["issue17", "submit"])
    cli.main(["open", "run-a-gate", "--parent", "issue17", "--step", "g1"])
    return "issue17.g1"


def _submitted(child):
    return [e for e in journal.read(child) if e.get("kind") == "submit"
            and e.get("step") == runmod.state(child)["steps"][0]["id"]]


def test_a_proof_amended_at_the_parent_is_the_one_an_open_child_checks(workdir, capsys):
    child = _to_open_gate("test -f ruled.txt")        # the stored bar cannot hold
    (journal.root_for("issue17") / "other.txt").write_text("x\n")
    _fill_implement(child, "implement")
    with pytest.raises(SystemExit):
        cli.main([child, "submit"])
    assert not _submitted(child)                      # blocked on the old proof

    cli.main(["issue17", "amend", "proof", "g1", "--proof", "test -f other.txt",
              "--reason", "n1: the bar named the wrong file"])
    capsys.readouterr()
    cli.main([child, "submit"])

    ran = [c["command"] for e in journal.read(child) if e["kind"] == "submit"
           for c in e.get("checks") or []]
    assert ran == ["test -f other.txt"]


def test_a_child_with_no_amend_still_checks_the_proof_it_was_cut_with(workdir, capsys):
    child = _to_open_gate("test -f cut.txt")
    (journal.root_for("issue17") / "cut.txt").write_text("x\n")
    _fill_implement(child, "implement")
    cli.main([child, "submit"])
    ran = [c["command"] for e in journal.read(child) if e["kind"] == "submit"
           for c in e.get("checks") or []]
    assert ran == ["test -f cut.txt"]


def _to_released_gate(proof, gate_proof):
    from functools import partial
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    _fill_open("issue17")
    cli.main(["issue17", "submit"])
    _work_the_board("issue17")
    _fill_consolidate("issue17")
    cli.main(["issue17", "submit"])
    _dispatch_and_close_plan("issue17", fill_fn=partial(_fill_plan, proof=proof,
                                                         gate_proof=gate_proof))
    _dispatch_plan_critic("issue17")
    _fill_plan_to_execute("issue17")
    cli.main(["issue17", "submit"])


def test_a_gate_proof_amended_before_dispatch_is_the_one_the_child_checks(workdir, capsys):
    """A ruling made at release can widen the gate's boundary before it
    dispatches. The amended gate-proof is what the child checks.

    See: issue223
    """
    _to_released_gate("true", "test -f old-boundary.txt")
    cli.main(["issue17", "amend", "proof", "g1", "--gate-proof", "test -f ruled.txt",
              "--reason", "n1: the ruling widened the boundary"])
    cli.main(["open", "run-a-gate", "--parent", "issue17", "--step", "g1"])
    child = "issue17.g1"
    (journal.root_for("issue17") / "ruled.txt").write_text("x\n")
    _fill_implement(child, "implement")
    capsys.readouterr()
    cli.main([child, "submit"])

    ran = [c["command"] for e in journal.read(child) if e["kind"] == "submit"
           for c in e.get("checks") or []]
    assert "test -f ruled.txt" in ran and "test -f old-boundary.txt" not in ran
    gate = next(s for s in runmod.state("issue17")["steps"] if s["id"] == "g1")
    assert gate["prefill"]["proof"] == "true"          # the other bar stands


def test_a_bound_child_still_reads_the_ruling_made_at_its_parent(workdir, capsys, monkeypatch):
    """The child runs with CONSTELLATION_BOUND set to itself, which puts
    the parent out of scope; the ruled proof must still reach it.

    See: #230
    """
    child = _to_open_gate("test -f ruled.txt")
    (journal.root_for("issue17") / "other.txt").write_text("x\n")
    _fill_implement(child, "implement")
    cli.main(["issue17", "amend", "proof", "g1", "--proof", "test -f other.txt",
              "--reason", "n1: the bar named the wrong file"])
    capsys.readouterr()
    monkeypatch.setenv("CONSTELLATION_BOUND", child)
    assert cli._ruled_proof(runmod.state(child))["proof"] == "test -f other.txt"
