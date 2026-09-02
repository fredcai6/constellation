"""The return is announced.

`close` is the only move in this engine whose effect lands in a run other
than the one you are standing in. Every other move's result is visible in
the room you are already in; this one's is not, so the engine has to say it.
Until it did, a conductor drove a child to close, watched the return land,
and had nowhere to go -- the returns-up half of the dispatch seam, missing.

Four sites say it now, and the strongest test here is behavioural: the
command `close` prints is run, and it must land the conductor on the step
the return unblocked.
"""

import pathlib
import subprocess

from engine import cli, journal, render, run as runmod
from test_nesting import (
    _dispatch_and_close_child, _fill, _fill_gate_close, _fill_implement,
    _mint_first_gate,
)


def _gate_ready_to_close(parent="issue17", step="g1"):
    """A child dispatched from a real gates mint, worked and reviewed, one
    move short of close -- the moment before the return is stamped."""
    _mint_first_gate(parent)
    cli.main(["open", "run-a-gate", "--parent", parent, "--step", step])
    child = f"{parent}.{step}"
    _fill_implement(child, step)
    cli.main([child, "submit"])
    from test_nesting import _dispatch_review
    _dispatch_review(child)
    _fill_gate_close(child)
    cli.main([child, "submit"])
    return child


# -- 1. close says where the return went -------------------------------------


def test_closing_a_child_names_the_parent_and_the_step(workdir, capsys):
    child = _gate_ready_to_close()
    capsys.readouterr()

    cli.main([child, "close"])
    out = capsys.readouterr().out

    assert "returned to issue17, at its step g1." in out
    assert "continue there:" in out


def test_the_continue_command_actually_lands_on_the_unblocked_step(workdir, capsys):
    """The behavioural one. Not that a plausible string was printed -- that
    typing it puts the conductor on the adjudication the return unblocked,
    from a shell with nothing on PATH, which is the situation a dispatched
    child is actually in."""
    child = _gate_ready_to_close()
    capsys.readouterr()

    cli.main([child, "close"])
    line = next(l for l in capsys.readouterr().out.splitlines() if "continue there:" in l)
    cmd = line.split("continue there:", 1)[1].strip().split()

    # not `workdir`: the run this continues into now works inside the
    # worktree `open` made for it (ruling 8), which is where the process
    # already stands -- exactly where a dispatched child's own shell would be.
    r = subprocess.run(cmd, capture_output=True, text=True, env={},
                       cwd=pathlib.Path.cwd(), timeout=20)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "GATE_TRANSITION.toml" in r.stdout, r.stdout
    assert "returns from issue17.g1" in r.stdout, r.stdout


def test_a_closed_child_still_says_where_it_returned(workdir, capsys):
    """Not a one-off line at close time: the closed room description carries
    it, so a conductor that lost the output can ask again."""
    child = _gate_ready_to_close()
    cli.main([child, "close"])
    capsys.readouterr()

    cli.main([child])
    out = capsys.readouterr().out
    assert "returned to issue17, at its step g1." in out
    assert render.spine_cmd() in out


def test_a_panelist_returns_to_the_gate_not_the_run(workdir, capsys):
    """The nested case: a verdict's parent is the gate that dispatched it,
    two levels down, and the step it names is the panel step."""
    from test_nesting import _select_panel
    _mint_first_gate()
    cli.main(["open", "run-a-gate", "--parent", "issue17", "--step", "g1"])
    _fill_implement("issue17.g1", "g1")
    cli.main(["issue17.g1", "submit"])
    _select_panel("issue17.g1")            # mints the review step and its panel
    review = runmod.state("issue17.g1")["current"]["id"]
    cli.main(["open", "give-a-verdict", "--parent", "issue17.g1", "--step", f"{review}.p1"])
    panelist = f"issue17.g1.{review}.p1"
    _fill(journal.location(panelist) / "REVIEW.toml",
          'verify = "ran it"\nfindings = "none: waived: clean"\n'
          'verdict = "pass"\n')
    cli.main([panelist, "submit"])
    capsys.readouterr()

    cli.main([panelist, "close"])
    out = capsys.readouterr().out
    assert f"returned to issue17.g1, at its step {review}." in out


# -- 2. awaiting close says what closing will do -----------------------------


def test_awaiting_close_names_who_the_returns_go_to(workdir, capsys):
    child = _gate_ready_to_close()
    capsys.readouterr()

    cli.main([child])
    out = capsys.readouterr().out
    assert "stamps your returns to issue17, at its step g1" in out


def test_a_root_run_awaiting_close_claims_no_dispatcher(workdir, capsys):
    """A root run has nobody upstream. The old text said returns go "to
    whoever dispatched this run" on every run alike, which was untrue for
    exactly the runs a human opens by hand."""
    _mint_first_gate()
    _dispatch_and_close_child("issue17", "g1")
    from test_nesting import _replan_to_next_gate
    _replan_to_next_gate("issue17", "g1-adjudicate")  # sequential: cuts "g2"
    _dispatch_and_close_child("issue17", "g2")
    _fill(journal.location("issue17") / "GATE_TRANSITION.toml",
          'findings = "waived: nothing"\nplan-holds = "advance"\n')
    cli.main(["issue17", "submit"])
    from test_nesting import _fill_close
    _fill_close("issue17")
    cli.main(["issue17", "submit"])
    capsys.readouterr()

    cli.main(["issue17"])
    out = capsys.readouterr().out
    assert "closing is what writes the record" in out
    assert "returns to" not in out


# -- 3. a return with nowhere to go offers no command ------------------------


def test_a_missing_parent_offers_no_command_to_run(workdir, capsys):
    """`close` already says the return was not delivered. Printing a move
    that fails on top of that is worse than printing none."""
    child = _gate_ready_to_close()
    (pathlib.Path(".agent-work/issue17/journal.toml")).unlink()
    capsys.readouterr()

    cli.main([child, "close"])
    out = capsys.readouterr().out
    assert "not found -- return not delivered" in out
    assert "continue there:" not in out
    assert "returned to" not in out


# -- 4. the parent names which child came back -------------------------------


def test_the_parents_returns_block_names_the_child(workdir, capsys):
    """With several gates in flight, which one came back is the first thing
    the conductor needs, and the engine has held it all along."""
    _mint_first_gate()
    _dispatch_and_close_child("issue17", "g1")
    capsys.readouterr()

    cli.main(["issue17"])
    out = capsys.readouterr().out
    assert "returns from issue17.g1" in out
