"""A ruling on how chunks are cut outlives the round it was made in.

sports-market-manager issue299/issue312: the conductor ruled the proof
standard at one plan seam, as `orders`, and every later cut -- a fresh
planner -- never saw it. PLAN_TO_EXECUTE's `approach` joins the run's
prefill on any submit, so the next planner child opens holding it.
"""

from engine import cli, run as runmod

from test_call_vocabulary import _at_the_plan_route
from test_nesting import (_dispatch_and_close_plan, _fill_plan_route_with_calls,
                          _fill_plan_to_execute, _response)
from test_rework import _fill_rework

RULING = "every proof is the full suite plus lint and types on shipped code"


def _submit_route(wid, approach, capsys):
    _fill_plan_route_with_calls(wid, "incorporate",
                                ("the retry budget is unbounded", "writer"))
    resp = _response(wid)
    resp.write_text(f'approach = "{approach}"\n' + resp.read_text())
    cli.main([wid, "submit"])
    capsys.readouterr()


def test_an_approach_ruled_on_a_send_back_reaches_the_next_planner(workdir, capsys):
    wid = _at_the_plan_route()
    _submit_route(wid, RULING, capsys)

    assert runmod.state(wid)["prefill"]["approach"] == RULING
    step = runmod.state(wid)["current"]["id"]
    child = _dispatch_and_close_plan(wid, step, _fill_rework)
    assert runmod.state(child)["prefill"]["approach"] == RULING


def test_a_waived_approach_leaves_the_standing_one(workdir, capsys):
    wid = _at_the_plan_route()
    _submit_route(wid, RULING, capsys)
    _dispatch_and_close_plan(wid, runmod.state(wid)["current"]["id"], _fill_rework)
    _fill_plan_to_execute(wid, "pass")
    resp = _response(wid)
    resp.write_text('approach = "waived: none"\n' + resp.read_text())
    cli.main([wid, "submit"])
    capsys.readouterr()

    assert runmod.state(wid)["prefill"]["approach"] == RULING
