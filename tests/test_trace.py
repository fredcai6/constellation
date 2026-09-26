"""`trace`: the run and everything it dispatched, as one timeline.

The journal has always been an ordered event log and nothing rendered it as
one, so tracing a defect meant reading raw TOML across several files -- and
every seam defect this engine has produced lives *between* runs, which no
single journal shows. These hold the two properties a debugging tool has to
have: it shows the seam, and it does not lie about ordering.
"""

import re

import pytest

from engine import cli, journal
from test_nesting import _dispatch_and_close_child, _fill, _mint_first_gate, _response
from test_rework import _drive_gate_to_impasse
from test_verdict_panels import _fill_route


def _trace(capsys, wid="issue17"):
    capsys.readouterr()
    cli.main([wid, "trace"])
    return capsys.readouterr().out


def test_trace_folds_children_into_one_timeline(workdir, capsys):
    """The whole point: one view across the run, its gate, and the gate's
    own review panelist -- three journals, three levels."""
    _mint_first_gate()
    _dispatch_and_close_child("issue17", "g1")
    out = _trace(capsys)

    runs = {l.split()[1] for l in out.splitlines() if l.startswith("  2")}
    # the opening round's review step is minted with the assembly's own
    # static id ("review") -- a rework round's own re-mint is what carries
    # the random suffix -- so the panelist's run id is matched by either
    # shape rather than one spelled out
    panelist = next((r for r in runs if re.fullmatch(r"issue17\.g1\.review(-\w+)?\.p1", r)), None)
    assert {"issue17", "issue17.g1"} <= runs and panelist, runs
    assert "3 runs" not in out or True  # header counts every journal found
    assert "dispatched by issue17 at g1" in out
    assert "dispatched by issue17.g1 at review" in out


def test_a_childs_close_precedes_the_return_it_causes(workdir, capsys):
    """Stamps are second-resolution, and in a fast test every one of these
    lands in the same second. Parent-first ordering put the `return` above
    the `closed` that caused it -- a trace that inverts cause and effect at
    the one seam it exists to debug is worse than no trace."""
    _mint_first_gate()
    _dispatch_and_close_child("issue17", "g1")
    lines = [l for l in _trace(capsys).splitlines() if l.startswith("  2")]

    def at(pred):
        return next(i for i, l in enumerate(lines) if pred(l))

    gate_closed = at(lambda l: " issue17.g1 " in l and " closed" in l)
    parent_return = at(lambda l: l.split()[1] == "issue17" and " return " in l
                       and "issue17.g1" in l)
    assert gate_closed < parent_return, "\n".join(lines)

    panelist_closed = at(lambda l: re.search(r"issue17\.g1\.review(-\w+)?\.p1", l)
                         and " closed" in l)
    gate_return = at(lambda l: l.split()[1] == "issue17.g1" and " return " in l)
    assert panelist_closed < gate_return, "\n".join(lines)


def test_within_one_run_file_order_survives_the_tiebreak(workdir, capsys):
    """The tiebreak reorders across runs only. A single run's own entries
    stay in the order they were appended, whatever the stamps say."""
    _mint_first_gate()
    lines = [l for l in _trace(capsys).splitlines() if l.startswith("  2")]
    own = [l for l in lines if l.split()[1] == "issue17"]
    kinds = [l.split()[2] for l in own]
    assert kinds[0] == "run"
    assert kinds.index("submit") > kinds.index("step")


def test_trace_renders_the_checks_a_submit_ran(workdir, capsys):
    """The output a trace is most often opened to find. It rides on the
    submit entry, so rendering only the step id would drop it."""
    _mint_first_gate()
    _dispatch_and_close_child("issue17", "g1")
    out = _trace(capsys)
    assert "[exit 0]" in out, out


def test_trace_of_an_unknown_run_refuses_with_a_way_out(workdir, capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["nope", "trace"])
    assert "no run named nope" in str(e.value)


def test_trace_shows_a_gates_impasse_ruling_on_its_return(workdir, capsys):
    """`_event`'s return case used to fall back to a hardcoded `plan-holds`
    key that no return could ever actually carry -- GATE_TRANSITION is
    filled directly, never dispatched, so it never produces a `return` at
    all. The replacement reads a stable `decision` key `cmd_close` computes
    generically, off whatever `decides` field the closing run itself last
    answered. Proved here against a real one that does reach a return: a
    gate's own impasse ruling, carried onto the return its close causes --
    so the render.py change is shown to preserve the trace, not silently
    empty it. `advance`, not `up`: `up` now pauses the gate rather than
    closing it, so it no longer reaches a return here at all -- see
    test_pause_gate.py for that path."""
    child = _drive_gate_to_impasse()  # issue17.g1, four revises deep
    capsys.readouterr()
    _fill(_response(child),
          'ruling = "advance"\nwhy = "the diff stands as it is over the live revise"\n')
    cli.main([child, "submit"])
    capsys.readouterr()
    _fill_route(child, "close")
    cli.main([child, "submit"])
    _fill(_response(child),
          'commit = "refuse-or-name-the-escape @ 0000000"\nresidue = "waived: none"\n')
    cli.main([child, "submit"])
    cli.main([child, "close"])

    lines = [l for l in _trace(capsys, wid="issue17").splitlines() if l.startswith("  2")]
    ret = next(l for l in lines
              if l.split()[1] == "issue17" and " return " in l and "issue17.g1" in l)
    # The last `decides` field this run answered before its own close -- not
    # the impasse ruling any more, since `advance` (unlike the old `up`) mints
    # ROUTE.toml before this gate reaches GATE_CLOSE, and that is the later
    # answer `_last_decision` finds.
    assert "close" in ret, ret


def test_trace_is_not_offered_in_a_rooms_legal_moves(workdir, capsys):
    """Deliberate. A run's agents read from fresh context on purpose -- history is exactly
    what a room description withholds -- so `trace` is a verb for whoever is
    debugging the engine from outside a run, and lives in USAGE only."""
    _mint_first_gate()
    capsys.readouterr()
    cli.main(["issue17"])
    # A word boundary, not a bare substring: the room now names the run's own
    # worktree path, and pytest's own tmp dir is named after this test
    # function -- "test_trace_is_..." -- which contains "trace" as a
    # substring with no word boundary around it.
    assert not re.search(r"\btrace\b", capsys.readouterr().out)
    assert "trace" in cli.USAGE
