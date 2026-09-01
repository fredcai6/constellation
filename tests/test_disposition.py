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
from test_nesting import _dispatch_and_close_child, _fill, _fill_gate_transition


def _fill_gate_transition_with_disposition(wid, obligation="o1", disposition="satisfied"):
    """Like `test_nesting._fill_gate_transition`, plus the conductor
    disposing one obligation -- root-verified against what the gate that
    just closed actually returned, the one moment in the run this is
    known."""
    _fill(journal.location(wid) / "GATE_TRANSITION.toml", '''
findings = "the fix landed cleanly, root-verified against the child's returns"
plan-holds = "advance"

[[dispositions]]
obligation = "%s"
disposition = "%s"
''' % (obligation, disposition))


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
