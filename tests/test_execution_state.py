"""Execution state: the engine, not the conductor, decides the run is done
(#56, g5).

`execute`'s `advance` outcome used to `commit` alone, so a run walked to
CLOSE the moment its worklist of gates ran dry -- whether or not anything the
spec committed to was ever satisfied. Now consolidate seeds a second board,
execution-state, from the spec's own numbered commitments; every gate's
advance reads it (`settle`, alongside `commit`) and either refills the plan
segment for another round, while an obligation is still `open`, or mints
nothing and lets the run walk on, once every row is disposed.

The board mechanism itself (`engine/boards.py`) is largely unchanged -- this
is the same mechanism pointed at a second file, seeded through the existing
`_BOARD_MINT` path (`_mint`, `engine/cli.py`). What's new here is the lookup
that finds the right file now that two boards exist, and the one verb,
`_settle_execution`, that reads dispositions and refuses nothing: any
disposing status -- `satisfied`, `deferred`, `invalidated`,
`rejected` -- counts as settled. (A later gate gave this board a sixth,
non-disposing word, `owed: <reason>`, that counts as open instead --
`boards.unsettled` is the shared read; see `tests/test_disposition.py`.)

Every test here drives the real `run-an-issue` assembly end to end, reusing
`test_nesting`'s fixtures rather than a shortcut -- the behaviour under test
is what the engine does at a real `advance`, not a unit in isolation.
"""

import pathlib

import pytest

from engine import boards, journal, run as runmod
from engine import cli
from gitremote import stub_gh
from test_nesting import (
    _dispatch_and_close_child, _dispatch_and_close_plan, _dispatch_plan_critic,
    _fill, _fill_close, _fill_gate_transition, _fill_gate_transition_drop, _fill_open,
    _fill_plan_to_execute, _response, _work_the_board,
)


def _fill_consolidate_with_obligation(wid, obligation="Fix the parser to handle EOF "
                                       "without a trailing newline."):
    """Like `test_nesting._fill_consolidate`, plus one obligation block --
    the spec's own numbered commitment, seeded as a row on the
    execution-state board."""
    _fill(_response(wid), '''
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


# -- dropping the last pending gate settles the board too --------------------


def test_dropping_the_last_pending_gate_still_refills_plan_over_an_open_obligation(
        workdir, capsys):
    """THE FIX (#95): `drop <gate-id>`'s outcome used to `close` alone, so
    dropping the run's last pending gate emptied execute's worklist without
    ever touching `advance` -- the one outcome that used to read the
    execution-state board. The run walked to CLOSE.toml reporting itself
    done while the seeded obligation sat `open`, undisposed. `does = "close;
    settle"` reads the board on the drop route too: closing the last
    pending gate still finds the obligation open and refills plan for
    another round, the same shape
    `test_an_undisposed_obligation_refills_plan_rather_than_closing` pins for
    the advance route."""
    _mint_first_gate_with_obligation()
    capsys.readouterr()

    # a second pending gate, minted the way `test_nesting._mint_n_gates`
    # seeds gates beyond the first -- direct journal entries in the exact
    # shape the plan segment's own mint produces, since a second *real* gate
    # would take a second plan round this fixture never drives.
    journal.append("issue17", "step", id="g2", segment="execute", dispatches="run-a-gate",
                   prefill={"purpose": "gate 2 purpose", "scope": "gate 2 scope",
                            "proof": "true"},
                   child="issue17.g2", anchor=False, terminal=False, source="mint")
    journal.append("issue17", "step", id="g2-adjudicate", segment="execute",
                   form="forms/GATE_TRANSITION.toml", filler="conductor",
                   child="issue17.g2", anchor=False, terminal=False, validates="",
                   source="mint")

    rows = boards.rows(_execution_state_path("issue17"))
    assert len(rows) == 1 and rows[0]["status"] == "open"  # seeded, undisposed

    _dispatch_and_close_child("issue17", "g1")
    capsys.readouterr()
    assert runmod.state("issue17")["current"]["id"] == "g1-adjudicate"

    # g1 can't name itself (test_nesting.py::
    # test_drop_on_a_gate_not_pending_refuses_and_names_pending) -- g2 is the
    # only other pending gate, so dropping it empties execute's worklist
    _fill_gate_transition_drop("issue17", "g2")
    cli.main(["issue17", "submit"])
    capsys.readouterr()

    amends = [e for e in journal.read("issue17") if e["kind"] == "amend"]
    assert {a["step"] for a in amends} == {"g2", "g2-adjudicate"}  # the drop still lands

    st = runmod.state("issue17")
    # a fresh plan round was minted -- not the terminal close step
    assert st["current"]["segment"] == "plan"
    assert st["current"]["form"] != "forms/CLOSE.toml"
    fresh_plan = next(s for s in st["steps"]
                      if s["segment"] == "plan" and s.get("source") == "mint")
    assert fresh_plan["dispatches"] == "cut-a-gate"  # a real round, ruling 6 intact


# -- a worklist emptied outside every outcome verb still settles at close ----


def test_a_worklist_emptied_outside_every_outcome_verb_still_settles_at_close(
        workdir, capsys, monkeypatch):
    """THE FIX (#143): `_settle_execution` only ever fires from inside the
    execute segment's own outcome table -- `advance`'s `commit; settle` and
    `drop <gate-id>`'s `close; settle` (#95) above. Both routes need a gate
    that actually reaches its own adjudication. `spine <wid> amend close
    <step-id> --reason ...` -- `cmd_close`'s own escape for a step stuck on
    a pending gate -- closes a step directly, with no outcome table and no
    `_settle_execution` call anywhere in the loop: the same shape any
    future defect between a journal write and its own follow-on mint
    reproduces (#141 was one cause of that; #143 is the gap independent of
    cause). Amend-closing execute's only pending pair empties its worklist
    that way, so `issue17` reaches CLOSE.toml with its one obligation still
    `open` and nothing left in execute able to close it -- run `issue139`'s
    own shape, reproduced here by a different, general-purpose route rather
    than the one crash #141 already closed off. `cmd_close` is where every
    route to the terminal step converges; this pins that it reads the board
    there too, refilling plan instead of finalizing (and archiving) a run
    that reports itself done over an open obligation. `gh` is stubbed
    (`gitremote.stub_gh`) so a run that this check fails to catch would
    actually reach `_publish` and archive clean -- the real shape
    of the bug, not a run saved by a `gh` call failing for an unrelated
    reason."""
    stub_gh(monkeypatch)
    _mint_first_gate_with_obligation()
    capsys.readouterr()

    rows = boards.rows(_execution_state_path("issue17"))
    assert len(rows) == 1 and rows[0]["status"] == "open"  # seeded, undisposed

    cli.main(["issue17", "amend", "close", "g1", "--reason",
             "simulating a defect that empties the worklist with no outcome verb involved"])
    cli.main(["issue17", "amend", "close", "g1-adjudicate", "--reason",
             "simulating a defect that empties the worklist with no outcome verb involved"])
    capsys.readouterr()

    st = runmod.state("issue17")
    # the reproduction: execute's worklist is empty and nothing stands
    # between the run and its own terminal step
    assert st["current"]["form"] == "forms/CLOSE.toml"

    _fill_close("issue17")
    cli.main(["issue17", "submit"])
    capsys.readouterr()

    with pytest.raises(SystemExit) as e:
        cli.main(["issue17", "close"])
    assert "not complete" in str(e.value)
    capsys.readouterr()

    st = runmod.state("issue17")
    assert not st["closed"]  # refused -- never archived over an open obligation
    # a fresh plan round was minted instead, the same shape `advance` and
    # `drop` already refill through mid-run
    assert st["current"]["segment"] == "plan"
    assert st["current"]["form"] != "forms/CLOSE.toml"
    fresh_plan = next(s for s in st["steps"]
                      if s["segment"] == "plan" and s.get("source") == "mint")
    assert fresh_plan["dispatches"] == "cut-a-gate"  # a real round, ruling 6 intact


# -- #74: a satisfied row is rechecked at close ------------------------------


def _to_close_with_g1_satisfied(proof, gate_proof=""):
    """One obligation, one gate whose proof is `proof` (and `gate-proof`,
    where given), the row disposed `satisfied` by that gate, and the run
    standing on its close form."""
    from functools import partial
    from test_nesting import _fill_plan
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "parser drops last record"])
    _fill_open("issue17")
    cli.main(["issue17", "submit"])
    _work_the_board("issue17")
    _fill_consolidate_with_obligation("issue17")
    cli.main(["issue17", "submit"])
    _dispatch_and_close_plan("issue17", fill_fn=partial(_fill_plan, proof=proof,
                                                         gate_proof=gate_proof))
    _dispatch_plan_critic("issue17")
    _fill_plan_to_execute("issue17")
    cli.main(["issue17", "submit"])
    path = pathlib.Path(_execution_state_path("issue17"))
    path.write_text(path.read_text().replace('status = "open"',
                                             'status = "satisfied"\ngate = "g1"'))
    (journal.root_for("issue17") / "landed.txt").write_text("the fix\n")
    _dispatch_and_close_child("issue17", "g1")
    _fill_gate_transition("issue17")
    cli.main(["issue17", "submit"])
    _fill_close("issue17")
    cli.main(["issue17", "submit"])


def test_a_satisfied_obligation_a_later_change_broke_is_owed_again_at_close(
        workdir, capsys, monkeypatch):
    """#74: the gate proved its obligation, and something after it undid the
    proof. Close runs that proof again, and the row it no longer holds up is
    owed -- the run recuts its plan rather than closing on a false word."""
    stub_gh(monkeypatch)
    _to_close_with_g1_satisfied("test -f landed.txt")
    assert runmod.state("issue17")["awaiting_close"]
    (journal.root_for("issue17") / "landed.txt").unlink()   # a later change undid it
    capsys.readouterr()

    with pytest.raises(SystemExit) as e:
        cli.main(["issue17", "close"])
    assert "not complete" in str(e.value)

    [row] = boards.rows(_execution_state_path("issue17"))
    assert row["status"].startswith("owed: g1's proof no longer passes at close")
    assert "test -f landed.txt" in row["status"]
    assert runmod.state("issue17")["current"]["segment"] == "plan"
    assert not runmod.state("issue17")["closed"]


def test_a_reopened_obligation_names_the_moves_and_they_work(workdir, capsys, monkeypatch):
    """issue87: close reopened a row whose substance still held, and the
    conductor's way past it was a hand edit to the board. Close names the
    moves -- a note and `up` -- and both are open from where it leaves the
    run."""
    stub_gh(monkeypatch)
    _to_close_with_g1_satisfied("test -f landed.txt")
    (journal.root_for("issue17") / "landed.txt").unlink()
    capsys.readouterr()
    with pytest.raises(SystemExit):
        cli.main(["issue17", "close"])
    out = capsys.readouterr().out
    assert "reopened at close" in out
    assert "spine issue17 note observation" in out
    assert 'spine issue17 up "<reason>"' in out

    cli.main(["issue17", "note", "observation", "re-ran the substance; it holds"])
    capsys.readouterr()
    cli.main(["issue17", "up", "g1's proof failed only on what it left alone"])
    cli.main(["issue17"])
    assert "ASK." in capsys.readouterr().out     # the question is standing


def test_a_satisfied_obligation_whose_proof_still_passes_closes(workdir, capsys, monkeypatch):
    stub_gh(monkeypatch)
    _to_close_with_g1_satisfied("test -f landed.txt")
    capsys.readouterr()

    cli.main(["issue17", "close"])

    assert "re-running g1's proof" in capsys.readouterr().out
    assert runmod.state("issue17") is None or runmod.state("issue17")["closed"]


def test_an_amended_proof_is_the_one_close_re_runs(workdir, capsys, monkeypatch):
    """issue165: a ruling corrected a released gate's proof bar. The amend
    carries the ruling, and close re-runs the corrected text rather than
    reopening the obligation on the stale one."""
    stub_gh(monkeypatch)
    _to_close_with_g1_satisfied("test -f landed.txt")
    root = journal.root_for("issue17")
    (root / "landed.txt").unlink()                  # the stored bar no longer holds
    (root / "ruled.txt").write_text("the bar the ruling set\n")
    capsys.readouterr()

    cli.main(["issue17", "amend", "proof", "g1", "--proof", "test -f ruled.txt",
              "--reason", "n5065: the bar counts win/loss rows only"])
    [amend] = [e for e in journal.read("issue17")
               if e.get("kind") == "amend" and e.get("action") == "proof"]
    assert (amend["proof"], amend["was"]) == ("test -f ruled.txt", "test -f landed.txt")
    assert amend["reason"].startswith("n5065")

    cli.main(["issue17", "close"])

    out = capsys.readouterr().out
    assert "re-running g1's proof: test -f ruled.txt" in out
    assert runmod.state("issue17") is None or runmod.state("issue17")["closed"]


def test_a_gate_amended_before_dispatch_carries_the_new_proof_into_its_child(
        workdir, capsys):
    _mint_first_gate_with_obligation()
    (journal.root_for("issue17") / "ruled.txt").write_text("x\n")
    cli.main(["issue17", "amend", "proof", "g1", "--proof", "test -f ruled.txt",
              "--reason", "n1: the cut named the wrong file"])

    _dispatch_and_close_child("issue17", "g1")

    [prefill] = [e for e in journal.read("issue17.g1") if e.get("kind") == "prefill"][:1]
    assert prefill["fields"]["proof"] == "test -f ruled.txt"


def test_amend_proof_on_a_step_that_is_not_a_gate_names_the_gates(workdir, capsys):
    _mint_first_gate_with_obligation()
    with pytest.raises(SystemExit) as e:
        cli.main(["issue17", "amend", "proof", "nope", "--proof", "true",
                  "--reason", "n1: x"])
    assert "gates: g1" in str(e.value)
