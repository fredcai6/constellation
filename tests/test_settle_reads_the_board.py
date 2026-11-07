"""#237, from story_time issue57, 62 and 64: what settle does once a gate's
adjudication lands, read from the execution-state board first.

- every row settled: the queue closes, whatever was still in it;
- a remint of the cut's last gate: its fresh gate answers the open rows,
  so no plan round is minted beside it, and the gate that ran is committed;
- a remint whose gate-spec is the form's own example left blank is a remint
  with no spec, and refuses.
"""

import pathlib
import subprocess

import pytest

from engine import cli, journal, run as runmod
from test_disposition import _fill_gate_transition_with_disposition
from test_execution_state import _mint_first_gate_with_obligation
from test_multi_gate_cut import _mint_n_gates_with_obligation
from test_nesting import (
    PURPOSE_HOLDS, _dispatch_and_close_child, _fill, _fill_gate_transition_remint, _response,
)


def _plan_steps_after(wid, before):
    return [e for e in journal.read(wid)[before:]
            if e.get("kind") == "step" and e.get("segment") == "plan"]


def test_an_advance_that_settles_every_row_closes_the_queue(workdir, capsys):
    """issue62: g2 landed what g3 was cut for, and g3 still dispatched."""
    _mint_n_gates_with_obligation(3)
    _dispatch_and_close_child("issue17", "g1")
    capsys.readouterr()

    before = len(journal.read("issue17"))
    _fill_gate_transition_with_disposition("issue17", "o1", "satisfied")
    cli.main(["issue17", "submit"])
    capsys.readouterr()

    st = runmod.state("issue17")
    pending = {s["id"] for s in st["steps"] if s["id"] not in st["done"]}
    assert not pending & {"g2", "g2-adjudicate", "g3", "g3-adjudicate"}
    assert not _plan_steps_after("issue17", before)
    assert st["current"]["id"] == "execute"      # the run walks on to close


def test_a_remint_of_the_last_gate_mints_no_plan_round_and_commits_the_gate(
        workdir, capsys):
    """issue57: the remint recut the plan beside its own fresh gate, and the
    cut that came back was a duplicate the board later dropped by hand. The
    gate that ran stayed uncommitted until the conductor committed it."""
    _mint_first_gate_with_obligation()
    _dispatch_and_close_child("issue17", "g1")
    capsys.readouterr()
    worktree = pathlib.Path(runmod.state("issue17")["worktree"])
    (worktree / "first-try.txt").write_text("the gate's work\n")
    subprocess.run(["git", "add", "first-try.txt"], cwd=worktree, check=True)

    before = len(journal.read("issue17"))
    _fill_gate_transition_remint("issue17", purpose="redo the fix", scope="src/parser.c",
                                 proof="false")
    cli.main(["issue17", "submit"])
    capsys.readouterr()

    assert not _plan_steps_after("issue17", before)
    st = runmod.state("issue17")
    assert st["current"]["id"].startswith("g1-a")  # the fresh gate, next to run
    log = subprocess.run(["git", "log", "-1", "--format=%B"], cwd=worktree,
                         capture_output=True, text=True).stdout
    assert "Work-Id: issue17.g1" in log
    status = subprocess.run(["git", "status", "--porcelain", "first-try.txt"], cwd=worktree,
                            capture_output=True, text=True).stdout
    assert status == ""


def test_a_remint_from_the_blank_example_block_refuses(workdir, capsys):
    """issue57: an edit to the form never landed, the example `[[gate-spec]]`
    block went in with every field blank, and the remint went through."""
    _mint_first_gate_with_obligation()
    _dispatch_and_close_child("issue17", "g1")
    capsys.readouterr()

    before = len(journal.read("issue17"))
    _fill(_response("issue17"), PURPOSE_HOLDS + '''
findings = "the spec was wrong"
plan-holds = "remint"

[[gate-spec]]
# the example's own comment, left standing
purpose = ""
scope = ""
proof = \'\'\'
\'\'\'
''')
    with pytest.raises(SystemExit) as e:
        cli.main(["issue17", "submit"])
    assert "remint needs a new gate spec" in str(e.value)
    assert len(journal.read("issue17")) == before
