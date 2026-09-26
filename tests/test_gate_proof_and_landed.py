"""Each gate's cut answers to the code and spec as they stand (2026-09-26).

Two changes carry it, beside `panel-rounds = "fresh"` (tests/
test_fresh_cut_panel.py):

- A gate carries two proofs. `proof` is what must be true when the issue
  ends: run at the cut, when the gate lands, and again at close.
  `gate-proof` is what must be true when the gate lands -- what it left
  alone -- run at the cut and when the gate lands, never at close. The
  prose rule that kept such clauses out of `proof` (#201) did not take: 12
  of 36 gate proofs across the next 12 runs still pinned `git diff --quiet
  <cut> -- <paths>`, and issue191's close could not survive one.
- Every dispatched child is handed what has landed (`_landed`): the
  commits past the run's cut point and the rows already settled, so a
  planner cuts from the state rather than reading the last plan.
"""

import pathlib

from engine import cli, forms, journal, run as runmod
from gitremote import stub_gh
from test_execution_state import _to_close_with_g1_satisfied


ROOT = pathlib.Path(__file__).resolve().parent.parent


def _fields(path):
    return {f["id"]: f for f in forms.load(ROOT / path)["fields"]}


def _gate_checks(wid):
    """Every command the gate's own implement submits ran."""
    return [c["command"] for e in journal.read(wid)
            if e["kind"] == "submit" for c in e.get("checks") or []]


# -- the two proofs ----------------------------------------------------------


def test_every_form_that_carries_a_gate_spec_carries_both_proofs():
    """The planner writes both, the projection carries both, and the gate's
    implement step runs both."""
    for path in ("skills/planner/forms/PLAN.toml", "skills/planner/forms/REWORK.toml"):
        fields = _fields(path)
        assert fields["proof"]["kind"] == "proof"
        assert fields["gate-proof"]["kind"] == "proof"
        assert fields["gate-proof"].get("optional")
    implement = _fields("skills/implementer/forms/IMPLEMENT.toml")
    assert implement["proof"]["kind"] == implement["gate-proof"]["kind"] == "check"
    assert "gate-proof" in cli._GATE_FIELDS


def test_a_gate_proof_runs_when_the_gate_lands_and_never_at_close(
        workdir, capsys, monkeypatch):
    """issue191 g6: a clause about what the gate left alone went false once a
    later change touched those paths, and close could not finish. As a
    `gate-proof` it runs when the gate lands and is never replayed."""
    stub_gh(monkeypatch)
    _to_close_with_g1_satisfied("test -f landed.txt", gate_proof="test ! -f later.txt")
    assert _gate_checks("issue17.g1") == ["test -f landed.txt", "test ! -f later.txt"]
    (journal.root_for("issue17") / "later.txt").write_text("a later gate's work\n")
    capsys.readouterr()

    cli.main(["issue17", "close"])

    out = capsys.readouterr().out
    assert "test ! -f later.txt" not in out
    assert runmod.state("issue17") is None or runmod.state("issue17")["closed"]


def test_a_waived_gate_proof_runs_nothing_at_the_gate(workdir, capsys, monkeypatch):
    stub_gh(monkeypatch)
    _to_close_with_g1_satisfied("test -f landed.txt", gate_proof="waived: none")
    assert _gate_checks("issue17.g1") == ["test -f landed.txt"]


# -- what has landed ---------------------------------------------------------


def test_a_child_is_handed_the_commits_past_the_cut_and_the_settled_rows(
        workdir, capsys, monkeypatch):
    """A planner re-cutting after a gate reads what landed off its prefill,
    not off the last plan: each gate's commit subject, and each row a gate
    settled, with its word."""
    stub_gh(monkeypatch)
    _to_close_with_g1_satisfied("test -f landed.txt")
    landed = cli._landed(runmod.state("issue17"), journal.root_for("issue17"))["landed"]
    assert "g1: fix the parser to handle EOF without a trailing newline" in landed
    assert landed.index("g1:") < landed.index("o1 -- satisfied")


def test_nothing_has_landed_on_the_opening_cut(workdir, capsys):
    from test_nesting import _fill_open
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    _fill_open("issue17")
    cli.main(["issue17", "submit"])
    capsys.readouterr()
    assert cli._landed(runmod.state("issue17"), journal.root_for("issue17")) == {}
