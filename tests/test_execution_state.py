"""Execution state: the engine, not the conductor, decides the run is done
(#56, g5).

`execute`'s `advance` outcome used to `commit` alone, so a run walked to
CLOSE the moment its worklist of gates ran dry -- whether or not anything the
spec committed to was ever satisfied. Now consolidate seeds a second board,
execution-state, from the spec's own numbered commitments; every gate's
advance reads it (`settle`, alongside `commit`) and either refills the plan
segment for another round, while an obligation is still `open`, or mints
nothing and lets the run walk on, once every row is disposed.

The board mechanism itself is unchanged (`engine/boards.py`) -- this is the
same mechanism pointed at a second file, seeded through the existing
`_BOARD_MINT` path (`_mint`, `engine/cli.py`). What's new is the lookup that
finds the right file now that two boards exist, and the one verb,
`_settle_execution`, that reads dispositions and refuses nothing: any status
but `open` counts as settled.

Every test here drives the real `run-an-issue` assembly end to end, reusing
`test_nesting`'s fixtures rather than a shortcut -- the behaviour under test
is what the engine does at a real `advance`, not a unit in isolation.
"""

import pathlib

from engine import boards, journal, run as runmod
from engine import cli
from test_nesting import (
    _dispatch_and_close_child, _dispatch_and_close_plan, _dispatch_plan_critic,
    _fill, _fill_gate_transition, _fill_open, _fill_plan_to_execute, _work_the_board,
)


def _fill_consolidate_with_obligation(wid, obligation="Fix the parser to handle EOF "
                                       "without a trailing newline."):
    """Like `test_nesting._fill_consolidate`, plus one obligation block --
    the spec's own numbered commitment, seeded as a row on the
    execution-state board."""
    _fill(pathlib.Path(f".agent-work/{wid}/CONSOLIDATE.toml"), '''
resolution = "pass"

spec = ".agent-work/%s/spec.md"
key-terms = "waived: none"
settle = "waived: none"

[[obligations]]
obligation = "%s"
''' % (wid, obligation))


def _mint_first_gate_with_obligation(wid="issue17", obligation=None):
    """`test_nesting._mint_first_gate`, but consolidate seeds the
    execution-state board with one obligation rather than leaving the
    (optional) field blank -- the shape every assertion below needs on
    record before a gate ever advances."""
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "parser drops last record"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    if obligation:
        _fill_consolidate_with_obligation(wid, obligation)
    else:
        _fill_consolidate_with_obligation(wid)
    cli.main([wid, "submit"])
    _dispatch_and_close_plan(wid)
    _dispatch_plan_critic(wid)
    _fill_plan_to_execute(wid)
    cli.main([wid, "submit"])


def _execution_state_path(wid):
    return runmod.state(wid)["boards"]["execution-state"]


def _dispose(wid, status):
    """Edit the execution-state board in place, the way the conductor would
    at a real gate's adjudication -- `status = "open"` becomes whatever the
    caller names, engine-side validation never in the loop."""
    path = pathlib.Path(_execution_state_path(wid))
    path.write_text(path.read_text().replace('status = "open"', f'status = "{status}"'))


# -- an open obligation refills plan rather than closing ---------------------


def test_an_undisposed_obligation_refills_plan_rather_than_closing(workdir, capsys):
    """DESIRED behaviour, the whole point of this gate: a spec's obligation
    left `open` on the execution-state board means the run is not done, so
    `advance` -- after committing the gate that just proved out -- refills
    the plan segment for another round instead of letting the worklist
    running dry walk the run to CLOSE.toml."""
    _mint_first_gate_with_obligation()
    capsys.readouterr()

    rows = boards.rows(_execution_state_path("issue17"))
    assert len(rows) == 1 and rows[0]["status"] == "open"  # seeded, undisposed

    _dispatch_and_close_child("issue17", "g1")
    capsys.readouterr()

    _fill_gate_transition("issue17")  # plan-holds = "advance"; row still open
    cli.main(["issue17", "submit"])
    capsys.readouterr()

    st = runmod.state("issue17")
    # a fresh plan round was minted -- not the terminal close step
    assert st["current"]["segment"] == "plan"
    assert st["current"]["form"] != "forms/CLOSE.toml"
    fresh_plan = next(s for s in st["steps"]
                      if s["segment"] == "plan" and s.get("source") == "mint")
    assert fresh_plan["dispatches"] == "cut-a-gate"  # a real round, ruling 6 intact


# -- every obligation disposed walks the run on to close ---------------------


def test_every_obligation_disposed_walks_to_close(workdir, capsys):
    """DESIRED behaviour: once the execution-state board carries no `open`
    row, `settle` mints nothing and the run reaches its terminal step --
    the same shape `test_advance_performs_no_amends`
    (tests/test_nesting.py) already pins for a run that seeds no
    execution-state board at all."""
    _mint_first_gate_with_obligation()
    capsys.readouterr()

    _dispose("issue17", "satisfied")  # the conductor's own edit, in place

    _dispatch_and_close_child("issue17", "g1")
    capsys.readouterr()

    _fill_gate_transition("issue17")
    cli.main(["issue17", "submit"])
    capsys.readouterr()

    assert runmod.state("issue17")["current"]["form"] == "forms/CLOSE.toml"


def test_a_disposition_carrying_a_reason_still_counts_as_settled(workdir, capsys):
    """The engine reads dispositions and refuses nothing: `deferred:
    <reason>` is exactly as settled as `satisfied` -- neither the word nor
    the reason after it is checked against anything. DESIRED behaviour,
    the same predicate as the test above, exercised on the disposition
    words #56's spec names explicitly rather than only the shortest one."""
    _mint_first_gate_with_obligation()
    capsys.readouterr()

    _dispose("issue17", "deferred: out of scope for this issue")

    _dispatch_and_close_child("issue17", "g1")
    capsys.readouterr()
    _fill_gate_transition("issue17")
    cli.main(["issue17", "submit"])
    capsys.readouterr()

    assert runmod.state("issue17")["current"]["form"] == "forms/CLOSE.toml"


# -- two boards on one run: the lookup finds the right file, not the first --


def test_board_lookup_finds_the_right_file_with_two_board_segments_present(workdir, capsys):
    """`_mint`'s board seeding used to grab the first `interior == "board"`
    segment positionally -- correct while run-an-issue held one, silently
    wrong the moment it holds two. `open`'s `questions` field and
    consolidate's `obligations` field now each name their own target
    (`board = "understand"` / `"execution-state"`); this pins that neither
    field's rows land in the other's file, with both board segments live on
    the same run at once."""
    _mint_first_gate_with_obligation(obligation="Obligation, not a question.")
    capsys.readouterr()

    st = runmod.state("issue17")
    understand_path = pathlib.Path(st["boards"]["understand"])
    execution_path = pathlib.Path(st["boards"]["execution-state"])
    assert understand_path.name == "UNDERSTAND.toml"
    assert execution_path.name == "EXECUTION_STATE.toml"
    assert understand_path != execution_path

    understand_rows = boards.rows(understand_path)
    execution_rows = boards.rows(execution_path)

    # the seed question landed on the understand board, not execution-state
    assert any("drop the last record" in r.get("question", "") for r in understand_rows)
    assert all("question" not in r for r in execution_rows)

    # the obligation landed on execution-state, not understand
    assert any(r.get("obligation") == "Obligation, not a question." for r in execution_rows)
    assert all("obligation" not in r for r in understand_rows)
