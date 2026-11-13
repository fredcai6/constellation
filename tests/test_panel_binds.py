"""On a gate the agent that built the diff rules on its review. A reader's
`revise` binds it: the round goes back, or the disagreement goes up."""
import pytest

from engine import cli
from engine import run as runmod
from test_verdict_panels import (_fill_implement, _fill_review, _open_gate,
                                 _open_panelist, _review_step)
from test_verdict_route import _route_with_calls


def _reviewed(revising=0, findings="gap: the bound is off by one"):
    """A real gate with its first-round panel returned: the first `revising`
    readers answered `revise`, the rest `pass`."""
    _open_gate()
    wid = "g1"
    review = _review_step(wid)
    panel = next(s for s in runmod.state(wid)["steps"] if s["id"] == review)["panel"]
    for n in range(1, len(panel) + 1):
        child = _open_panelist(wid, review, n)
        if n <= revising:
            _fill_review(child, "revise", findings=findings)
        else:
            _fill_review(child, "pass", findings="waived: clean")
        cli.main([child, "submit"])
        cli.main([child, "close"])
    return wid


def test_close_over_a_readers_revise_is_refused_and_names_both_ways_out(workdir, capsys):
    wid = _reviewed(1)
    _route_with_calls(wid, "close", ("gap: the bound is off by one", "accepted"))
    with pytest.raises(SystemExit) as e:
        cli.main([wid, "submit"])
    text = str(e.value)
    assert "a reader answered `revise` (p1)" in text
    assert 'resolution = "rework"' in text and 'resolution = "up"' in text


def test_close_after_every_reader_passed_still_releases(workdir, capsys):
    wid = _reviewed(0)
    _route_with_calls(wid, "close")
    cli.main([wid, "submit"])
    assert runmod.state(wid)["current"]["form"].endswith("GATE_CLOSE.toml")


def test_a_rework_hands_its_reader_what_the_builder_set_aside(workdir, capsys):
    wid = _reviewed(1, findings=r"gap: the bound is off by one\n\nthe parser is slow")
    _route_with_calls(wid, "rework",
                      ("gap: the bound is off by one", "blocking"),
                      ("the parser is slow", "rejected: not this gate's to answer"))
    cli.main([wid, "submit"])
    prefill = runmod.state(wid)["current"]["prefill"]
    assert prefill["findings"] == "gap: the bound is off by one"
    assert prefill["set-aside"] == "[rejected: not this gate's to answer] the parser is slow"
    asm = runmod.load_assembly("run-a-gate")
    [reader] = asm["segment"][0]["transition"]["rework-panel"]
    assert "`set-aside`" in reader["criteria"]
