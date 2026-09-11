"""Disposition: the conductor's own hand for the mechanism g5 built (#56, g1).

g5 seeded the execution-state board from the spec's own obligations and
taught `settle` to end the run once every row carries something other than
`open` -- but no form ever asked anyone to *record* a disposition, so
`settle` found every row open forever and a run with a real spec could
never close on its own. The mechanism was complete except for the hand that
moves it.

GATE_TRANSITION.toml gains one field, `dispositions`: a `plan` field like
`obligations` on CONSOLIDATE.toml, minted through the same board-writing
path (`_seed_board`, `engine/cli.py`) rather than a second row-writer --
only the merge that finds each named row and folds the conductor's word
onto it (`_mint`'s new `_DISPOSE_MINT` branch) is new. `_settle_execution`
itself, and the board template, are g5's and untouched.

Every test here drives the real `run-an-issue` and `run-a-gate` assemblies
end to end, reusing `test_nesting`'s and `test_execution_state`'s own
fixtures rather than a shortcut -- the behaviour under test is what the
engine does at a real adjudication, not a unit in isolation.
"""

from engine import boards, journal, run as runmod
from engine import cli
from test_execution_state import _execution_state_path, _mint_first_gate_with_obligation
from test_nesting import (
    PURPOSE_HOLDS, _dispatch_and_close_child, _dispatch_review, _fill, _fill_gate_transition,
    _fill_implement, _response,
)


def _fill_gate_transition_with_disposition(wid, obligation="o1", disposition="satisfied"):
    """Like `test_nesting._fill_gate_transition`, plus the conductor
    disposing one obligation by hand -- the shape a conductor types where
    the gate claimed nothing and the row is still its to settle."""
    _fill(_response(wid), PURPOSE_HOLDS + '''
findings = "the fix landed cleanly, root-verified against the child's returns"
plan-holds = "advance"

[[dispositions]]
obligation = "%s"
disposition = "%s"
''' % (obligation, disposition))


def _close_child_with_claims(parent_wid, step_id, claims):
    """`test_nesting._dispatch_and_close_child`, with the gate-conductor
    claiming obligations at close -- GATE_CLOSE.toml's `claims`, one block
    per (obligation, disposition, root)."""
    cli.main(["open", "run-a-gate", "--parent", parent_wid, "--step", step_id])
    child_wid = f"{parent_wid}.{step_id}"
    _fill_implement(child_wid, step_id)
    cli.main([child_wid, "submit"])
    _dispatch_review(child_wid)
    blocks = "".join('\n[[claims]]\nobligation = "%s"\ndisposition = "%s"\nroot = "%s"\n' % c
                     for c in claims)
    _fill(_response(child_wid), 'residue = "nothing surprising"\n' + blocks)
    cli.main([child_wid, "submit"])
    cli.main([child_wid, "close"])
    return child_wid


def _answer_drafted_adjudication(wid, **answers):
    """Fill the prose slots of the adjudication form the engine already
    wrote, leaving its drafted `[[dispositions]]` blocks as they stand --
    what a conductor accepting every claim does. `purpose_holds=...` names
    the `purpose-holds` slot."""
    path = _response(wid)
    text = path.read_text()
    for key, value in answers.items():
        field = key.replace("_", "-")
        text = text.replace(f'{field} = """\n"""', f'{field} = "{value}"')
        text = text.replace(f'{field} = ""', f'{field} = "{value}"')
    path.write_text(text)


# -- a disposition lands on the matching board row ----------------------


def test_a_disposition_recorded_at_adjudication_lands_on_the_matching_board_row(
        workdir, capsys):
    """DESIRED behaviour, and it fails before this gate: GATE_TRANSITION.toml
    declared no `dispositions` field, so nothing an agent typed under that
    name ever reached `_mint` -- the board stayed `open` no matter what the
    filled response said. With the field declared, submitting one lands the
    conductor's word, and this gate's own id, on the obligation it named."""
    _mint_first_gate_with_obligation()
    capsys.readouterr()

    _dispatch_and_close_child("issue17", "g1")
    capsys.readouterr()

    _fill_gate_transition_with_disposition("issue17", "o1", "satisfied")
    cli.main(["issue17", "submit"])
    capsys.readouterr()

    rows = boards.rows(_execution_state_path("issue17"))
    assert len(rows) == 1
    assert rows[0]["status"] == "satisfied"
    assert rows[0]["gate"] == "g1"  # the gate that settled it, not the child wid


# -- the final obligation disposed walks the run to close ---------------


def test_a_gate_that_disposes_the_last_open_obligation_walks_the_run_to_close(
        workdir, capsys):
    """DESIRED behaviour, and it fails before this gate: with no way to
    record a disposition, `settle` found the one obligation still `open`
    forever, so the run could refill `plan` but never reach CLOSE.toml. The
    same gate, adjudicated with a disposition this time, lets `settle` see
    the board clear and the run walk on."""
    _mint_first_gate_with_obligation()
    capsys.readouterr()

    _dispatch_and_close_child("issue17", "g1")
    capsys.readouterr()

    _fill_gate_transition_with_disposition("issue17", "o1", "deferred: out of scope")
    cli.main(["issue17", "submit"])
    capsys.readouterr()

    assert runmod.state("issue17")["current"]["form"] == "forms/CLOSE.toml"


# -- an obligation left unnamed stays open, and plans another gate ------


def test_an_obligation_left_unnamed_still_plans_another_gate(workdir, capsys):
    """DESIRED behaviour, restated with the new field in play rather than
    absent: this already held under g5 alone (`test_execution_state.py`'s
    own first test, with no `dispositions` field to omit), and the scope for
    this gate is explicit that naming every obligation is not required --
    the engine still refuses nothing. This pins that the addition does not
    change what an un-named row does: it is exactly as open, and the run
    plans exactly the same fresh round, as before this field existed."""
    _mint_first_gate_with_obligation()
    capsys.readouterr()

    _dispatch_and_close_child("issue17", "g1")
    capsys.readouterr()

    _fill_gate_transition("issue17")  # no dispositions block at all
    cli.main(["issue17", "submit"])
    capsys.readouterr()

    rows = boards.rows(_execution_state_path("issue17"))
    assert rows[0]["status"] == "open"
    assert rows[0].get("gate", "") == ""  # never disposed -- the column is unwritten, not blank

    st = runmod.state("issue17")
    assert st["current"]["segment"] == "plan"
    assert st["current"]["form"] != "forms/CLOSE.toml"
    fresh_plan = next(s for s in st["steps"]
                      if s["segment"] == "plan" and s.get("source") == "mint")
    assert fresh_plan["dispatches"] == "cut-a-gate"


# -- the gate claims; the issue-conductor accepts or contests ------------
#
# The first run of this engine elsewhere adjudicated obligations at the issue
# tier -- the gate's own question, answered a second time with a bigger
# model -- and never asked whether the gate's purpose held. Now the gate
# claims each obligation at close (GATE_CLOSE.toml's `claims`), the claims
# open GATE_TRANSITION.toml's `dispositions` already written, and the board
# path `_mint`'s `_DISPOSE_MINT` branch walks is untouched: what changed is
# who writes the first draft, not how the row is written.


def test_a_gates_orders_carry_the_open_obligations_by_row_id(workdir, capsys):
    """A claim is keyed by the board's own row id, and the only place that
    id reached a gate before was the planner's prose. Now a child of a run
    holding an execution-state board opens with the open rows in its
    orders, id beside text, under `obligations`."""
    _mint_first_gate_with_obligation()
    capsys.readouterr()

    cli.main(["open", "run-a-gate", "--parent", "issue17", "--step", "g1"])
    prefill = runmod.state("issue17.g1")["prefill"]
    assert prefill["obligations"].startswith("o1 -- Fix the parser to handle EOF")
    assert prefill["purpose"]  # the gate spec still rides beside it


def test_a_gates_claims_open_the_adjudication_form_already_written(workdir, capsys):
    """The gate's `claims` return up on the same `return` entry every field
    of its close does, and the adjudication form materializes holding them
    as `[[dispositions]]` blocks -- word and root as the gate made them.
    The room shows the claim as words, never as a Python repr."""
    _mint_first_gate_with_obligation()
    capsys.readouterr()
    _close_child_with_claims("issue17", "g1",
                             [("o1", "satisfied", "tests/test_parser.py::test_eof passes")])
    capsys.readouterr()

    cli.main(["issue17"])
    out = capsys.readouterr().out
    drafted = _response("issue17").read_text()
    assert "[[dispositions]]" in drafted
    assert 'obligation = "o1"' in drafted
    assert 'disposition = "satisfied"' in drafted
    assert 'root = "tests/test_parser.py::test_eof passes"' in drafted
    assert drafted.count("Repeat this block per item") == 1  # gate-spec's example alone
    assert "tests/test_parser.py::test_eof passes" in out
    assert "{'obligation'" not in out


def test_an_accepted_claim_writes_the_board_row_as_the_gate_claimed(workdir, capsys):
    """Accepting is leaving the drafted block as it stands. Submitting it
    walks the same dispose path a hand-typed block always did: the gate's
    word lands on the row with the gate's own id, and the settled board
    walks the run to close."""
    _mint_first_gate_with_obligation()
    capsys.readouterr()
    _close_child_with_claims("issue17", "g1",
                             [("o1", "satisfied", "tests/test_parser.py::test_eof passes")])
    cli.main(["issue17"])
    capsys.readouterr()

    _answer_drafted_adjudication(
        "issue17", purpose_holds="the parser reads EOF cleanly; re-ran the gate's check",
        findings="waived: none", plan_holds="advance")
    cli.main(["issue17", "submit"])
    capsys.readouterr()

    rows = boards.rows(_execution_state_path("issue17"))
    assert rows[0]["status"] == "satisfied"
    assert rows[0]["gate"] == "g1"
    assert runmod.state("issue17")["current"]["form"] == "forms/CLOSE.toml"


def test_a_contested_claim_writes_the_conductors_word_not_the_gates(workdir, capsys):
    """Contesting is changing the block's word. The board carries what the
    issue-conductor settled on, not what the gate claimed, and nothing about
    the disagreement is checked -- the engine reads dispositions and refuses
    nothing, exactly as before."""
    _mint_first_gate_with_obligation()
    capsys.readouterr()
    _close_child_with_claims("issue17", "g1",
                             [("o1", "satisfied", "tests/test_parser.py::test_eof passes")])
    cli.main(["issue17"])
    capsys.readouterr()

    _answer_drafted_adjudication(
        "issue17", purpose_holds="the root names a test the diff never touched",
        findings="waived: none", plan_holds="advance")
    path = _response("issue17")
    path.write_text(path.read_text().replace(
        'disposition = "satisfied"',
        'disposition = "rejected: the root names a test the diff never touched"'))
    cli.main(["issue17", "submit"])
    capsys.readouterr()

    rows = boards.rows(_execution_state_path("issue17"))
    assert rows[0]["status"] == "rejected: the root names a test the diff never touched"
    assert rows[0]["gate"] == "g1"
