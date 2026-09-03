"""`engine/review_yield.py`: a run's own review yield, derived from the
journal rather than tabulated by hand (#16's first cut).

Drives the real `run-an-issue` and `run-a-gate` assemblies, reusing
`test_nesting.py` and `test_verdict_panels.py`'s own fixtures -- the same
mechanics `test_close_summary.py` and `test_trace.py` already stand on,
not a hand-rolled journal.
"""

import pathlib

from engine import cli, journal, render, review_yield, run as runmod
from gitremote import stub_gh
from test_nesting import (
    _dispatch_and_close_plan, _fill_close, _fill_consolidate,
    _fill_consolidate_route_with_calls, _fill_critic, _fill_open, _fill_plan_rework,
    _fill_plan_route_with_calls, _fill_plan_to_execute, _fill_spec, _work_the_board,
)
from test_verdict_panels import (
    _fill_implement, _fill_review, _fill_route, _open_gate, _open_panelist,
    _review_step, _select,
)
from test_verdict_route import _route_with_calls


def _dispatch_plan_panel(wid, rounds):
    """Open every plan-to-execute panelist, fill each with its own
    (verdict, findings), leave the round standing on its own conductor form
    -- unlike `test_nesting._dispatch_plan_critic`, which auto-submits a
    bare `rework` on any revise and so cannot hand the caller a `calls`
    table to rule the round with."""
    step_id = runmod.state(wid)["current"]["id"]
    for n, (verdict, findings) in enumerate(rounds, start=1):
        cli.main(["open", "give-a-verdict", "--parent", wid, "--step", f"{step_id}.p{n}"])
        panelist = f"{wid}.{step_id}.p{n}"
        _fill_critic(panelist, verdict, findings)
        cli.main([panelist, "submit"])
        cli.main([panelist, "close"])
    return step_id


def test_review_yield_renders_two_plan_rounds_then_a_pass(workdir, capsys, monkeypatch):
    """A rework round ruled finding by finding, then a clean pass: the
    printed and archived yield names the seam `plan-to-execute` (the
    disposing form's own name), shows round one's call tally, and shows
    round two as a bare `pass`."""
    wid = "issue19"
    cli.main(["open", "run-an-issue", "--issue", "19", "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    _dispatch_and_close_plan(wid)

    # round one: two critics find something, one passes clean; the
    # conductor calls one finding blocking and rejects the other.
    _dispatch_plan_panel(wid, [
        ("revise", "gap: the loop bound is untested"),
        ("revise", "gap: the risk section is thin"),
        ("pass", "none: waived: clean"),
    ])
    _fill_plan_route_with_calls(
        wid, "rework",
        ("gap: the loop bound is untested", "blocking"),
        ("gap: the risk section is thin", "rejected: below the bar a plan is held to"))
    cli.main([wid, "submit"])

    fresh = next(s for s in runmod.state(wid)["steps"]
                if s["segment"] == "plan" and s.get("source") == "mint" and s.get("dispatches"))
    _dispatch_and_close_plan(wid, fresh["id"], _fill_plan_rework)

    # round two: clean, so the round releases with nothing to call
    _dispatch_plan_panel(wid, [
        ("pass", "none: waived: clean"),
        ("pass", "none: waived: clean"),
        ("pass", "none: waived: clean"),
    ])
    _fill_plan_to_execute(wid, "pass")
    cli.main([wid, "submit"])

    entries = review_yield.run_yield(wid)
    plan = next(e for e in entries if e["label"] == "plan-to-execute")
    assert len(plan["rounds"]) == 2
    r1, r2 = plan["rounds"]
    assert r1 == {"verdict": "revise", "revising": 2, "findings": 2, "called": True,
                  "calls": {"blocking": 1, "rejected": 1}}
    assert r2 == {"verdict": "pass", "revising": 0, "findings": 0, "called": False, "calls": {}}

    table = render.review_yield(entries)
    assert "plan-to-execute" in table
    assert "r1  2 revise   2 findings   1 blocking 1 rejected" in table
    assert "r2  pass" in table

    # skip the projected gate -- this test's subject is the plan seam's own
    # yield, not a gate's -- and reach CLOSE.toml (execute's own terminal
    # transition, not a step of its own) the same way test_close_summary.py's
    # impasse test skips past an impasse ruling.
    st = runmod.state(wid)
    for s in st["steps"]:
        if s["segment"] == "execute" and not s.get("terminal") and s["id"] not in st["done"]:
            journal.append(wid, "amend", action="close", segment="execute", step=s["id"],
                           reason="this test's subject is the plan seam, not a gate",
                           anchor=s.get("anchor", False))
    _fill_close(wid)
    cli.main([wid, "submit"])
    capsys.readouterr()

    stub_gh(monkeypatch)
    cli.main([wid, "close"])
    out = capsys.readouterr().out
    assert "plan-to-execute" in out and "1 blocking 1 rejected" in out

    archived = pathlib.Path(workdir) / ".agent-work" / "archive" / wid / "YIELD.md"
    assert archived.exists()
    assert "1 blocking 1 rejected" in archived.read_text()


def test_review_yield_at_the_gate_tier_through_route_toml(workdir, capsys):
    """`run-a-gate`'s review, minted at `select` rather than declared, is
    found and named the same way -- `review`, the segment's own id, since
    its transition declares neither form nor panel."""
    _open_gate()
    review = _review_step("g1")
    panelist = _open_panelist("g1", review)
    _fill_review(panelist, "revise", findings="gap: the bound is off by one")
    cli.main([panelist, "submit"])
    cli.main([panelist, "close"])
    _route_with_calls("g1", "rework", ("gap: the bound is off by one", "blocking"))
    cli.main(["g1", "submit"])

    _fill_implement("g1")
    cli.main(["g1", "submit"])
    second_review = _select("g1")
    panelist = _open_panelist("g1", second_review)
    _fill_review(panelist, "pass")
    cli.main([panelist, "submit"])
    cli.main([panelist, "close"])
    _fill_route("g1", "close")
    cli.main(["g1", "submit"])

    entries = review_yield.run_yield("g1")
    review_entry = next(e for e in entries if e["label"] == "review")
    assert len(review_entry["rounds"]) == 2
    r1, r2 = review_entry["rounds"]
    assert r1 == {"verdict": "revise", "revising": 1, "findings": 1, "called": True,
                  "calls": {"blocking": 1}}
    assert r2 == {"verdict": "pass", "revising": 0, "findings": 0, "called": False, "calls": {}}

    table = render.review_yield(entries)
    assert "review" in table
    assert "r1  1 revise   1 finding   1 blocking" in table
    assert "r2  pass" in table


def test_review_yield_renders_consolidates_findings_with_calls(workdir, capsys):
    """Follow-up to ruling 3, 2026-09-03: consolidate is a route-form seam
    now, CONSOLIDATE.toml, the same shape plan-to-execute's own
    PLAN_TO_EXECUTE.toml already has -- so a round with findings renders its
    call tally the same way plan-to-execute's own round does, not
    `uncalled`. `explore-an-idea`'s own spec segment is the one seam left
    without a route form; `uncalled` is what its own findings still render
    as, unexercised by this file."""
    wid = "issue19"
    cli.main(["open", "run-an-issue", "--issue", "19", "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    board = pathlib.Path(f".agent-work/{wid}/UNDERSTAND.toml")
    board.write_text(board.read_text().replace(
        'status = "open"', 'status = "answered"\nanswer = "no trailing newline"'))
    _fill_spec(wid)
    cli.main([wid, "submit"])

    step_id = runmod.state(wid)["current"]["id"]
    assert step_id == "understand"

    # round one: two critics find something, one passes clean; the
    # conductor calls one finding blocking and rejects the other.
    _dispatch_plan_panel(wid, [
        ("revise", "gap: the glossary check ran on the wrong word"),
        ("revise", "gap: the settle field is thin"),
        ("pass", "none: waived: clean"),
    ])
    _fill_consolidate_route_with_calls(
        wid, "rework",
        ("gap: the glossary check ran on the wrong word", "blocking"),
        ("gap: the settle field is thin", "rejected: below the bar a spec is held to"))
    cli.main([wid, "submit"])

    # round two: a fresh spec-writer pass, filled in place (no dispatch --
    # understand declares no `dispatches`), then a clean panel: the round
    # releases with nothing to call.
    _fill_spec(wid)
    cli.main([wid, "submit"])
    _dispatch_plan_panel(wid, [
        ("pass", "none: waived: clean"),
        ("pass", "none: waived: clean"),
        ("pass", "none: waived: clean"),
    ])
    _fill_consolidate(wid, "pass")
    cli.main([wid, "submit"])

    entries = review_yield.run_yield(wid)
    consolidate = next(e for e in entries if e["label"] == "consolidate")
    assert len(consolidate["rounds"]) == 2
    r1, r2 = consolidate["rounds"]
    assert r1 == {"verdict": "revise", "revising": 2, "findings": 2, "called": True,
                  "calls": {"blocking": 1, "rejected": 1}}
    assert r2 == {"verdict": "pass", "revising": 0, "findings": 0, "called": False, "calls": {}}

    table = render.review_yield(entries)
    assert "consolidate" in table
    assert "1 blocking 1 rejected" in table
    assert "uncalled" not in table
