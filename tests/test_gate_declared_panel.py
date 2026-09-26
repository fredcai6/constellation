"""run-a-gate's review is `work`'s own declared transition now (ruling,
2026-09-25): a two-voices step the same shape as run-an-issue's plan seam,
with its panel written in `assemblies/run-a-gate/ASSEMBLY.toml` rather than
chosen by a conductor at a separate `select` beat. Five things that
declaration promises, each driven through the real assembly and forms
rather than asserted against a fixture:

(a) a fresh run-a-gate's review step carries exactly the three declared
    lenses and no spec-fit lens;
(b) a route `rework` with one finding called blocking carries that finding
    onto the next round's single `rework:` reader, both on the step's own
    panel and in the panelist's own opened prefill;
(c) an impasse `advance` mints ROUTE.toml alone, with no panel;
(d) the gate seam's yield label is `review`;
(e) a consolidate or plan-to-execute `rewrite` whose `calls` table has a
    `severe` finding mints a fresh round whose prefill holds `orders` and
    `severe`, and not the other findings.

Modeled on test_one_look.py and test_select_mint.py: driven end to end
through `cli.main`, reusing test_nesting.py's and test_verdict_panels.py's
own fixtures rather than hand-rolling a journal.
"""

from engine import cli, review_yield, run as runmod

from test_nesting import (
    _dispatch_and_close_plan, _fill_consolidate, _fill_open, _fill_plan_to_execute,
    _rule_impasse, _work_the_board,
)
from test_select_mint import _drive_gate_through
from test_two_voices import _dispatch_critic
from test_verdict_panels import _fill_review, _open_gate, _open_panelist, _review_step
from test_verdict_route import _route_with_calls


LENSES = ["tests", "simplicity", "claims"]


# -- (a) the opening round carries exactly the three declared lenses -------


def test_a_fresh_reviews_panel_is_exactly_the_three_declared_lenses(workdir, capsys):
    _open_gate()
    review = _review_step("g1")
    st = runmod.state("g1")
    panel = next(s for s in st["steps"] if s["id"] == review)["panel"]

    assert [p["criteria"].split(":")[0] for p in panel] == LENSES
    assert not any(c["criteria"].startswith("spec-fit") for c in panel), (
        "spec-fit is not a lens here -- the gate's own proof is that check, "
        "run at submit and again at close")
    assert all(p["form"] == "skills/reviewer/forms/REVIEW.toml" for p in panel)
    assert all(p["worker"] == "reviewer" for p in panel)


# -- (b) a rework round's single `rework:` reader gets the blocking finding -


def test_a_rework_rounds_single_reader_gets_the_blocking_finding(workdir, capsys):
    _open_gate()
    review = _review_step("g1")
    panel = next(s for s in runmod.state("g1")["steps"] if s["id"] == review)["panel"]
    for n in range(1, len(panel) + 1):
        panelist = _open_panelist("g1", review, n)
        _fill_review(panelist, "revise", findings="gap: the bound is off by one")
        cli.main([panelist, "submit"])
        cli.main([panelist, "close"])

    _route_with_calls("g1", "rework", ("gap: the bound is off by one", "blocking"))
    cli.main(["g1", "submit"])

    st = runmod.state("g1")
    fresh_review = next(s for s in st["steps"] if s["id"] != review and s.get("panel"))
    assert len(fresh_review["panel"]) == 1
    assert fresh_review["panel"][0]["criteria"].startswith("rework:")
    assert fresh_review["prefill"]["findings"] == "gap: the bound is off by one"

    # the panelist actually opened reads the same finding as its own orders,
    # not only the step's own record of it
    panelist = _open_panelist("g1", fresh_review["id"])
    pst = runmod.state(panelist)
    assert "gap: the bound is off by one" in pst["prefill"]["findings"]


# -- (c) an impasse `advance` mints ROUTE.toml alone, with no panel --------


def test_an_impasse_advance_mints_route_alone_with_no_panel(workdir, capsys):
    _drive_gate_through("g1", 3)
    capsys.readouterr()
    st = runmod.state("g1")
    assert st["current"]["form"] == "forms/IMPASSE.toml"

    _rule_impasse("g1", ruling="advance", why="the diff stands as it is over the live revise")
    capsys.readouterr()

    st = runmod.state("g1")
    assert st["current"]["form"] == "forms/ROUTE.toml"
    assert not st["current"].get("panel")


# -- (d) the gate seam's yield label is `review` ---------------------------


def test_the_gate_seams_yield_label_is_review():
    asm = runmod.load_assembly("run-a-gate")
    seg = next(s for s in asm["segment"] if s["id"] == "work")
    assert review_yield.seam_label(seg) == "review"


# -- (e) a rewrite carries `orders` and the `severe` finding, nothing else --


def test_a_plan_to_execute_rewrite_carries_orders_and_only_the_severe_finding(
        workdir, capsys):
    cli.main(["open", "run-an-issue", "--issue", "1", "--title", "t"])
    wid = "issue1"
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    _dispatch_and_close_plan(wid)

    step_id = runmod.state(wid)["current"]["id"]
    panel = next(s for s in runmod.state(wid)["steps"] if s["id"] == step_id)["panel"]
    for n in range(1, len(panel) + 1):
        _dispatch_critic(wid, step_id, verdict="revise",
                         findings=(r"gap: the proof is untestable\n\n"
                                   r"the whole cut wants rewriting"), n=n)
    assert runmod.state(wid)["current"]["id"] == step_id  # held for the conductor's own form

    _fill_plan_to_execute(
        wid, "rewrite",
        calls=('orders = "cut the gate narrower, around the parser only"\n\n'
               '[[calls]]\nfinding = "gap: the proof is untestable"\ncall = "severe"\n\n'
               '[[calls]]\nfinding = "the whole cut wants rewriting"\ncall = "writer"\n'))
    cli.main([wid, "submit"])
    capsys.readouterr()

    st = runmod.state(wid)
    fresh = next(s for s in st["steps"]
                if s["segment"] == "plan" and s.get("source") == "mint"
                and s.get("dispatches") == "cut-a-gate")
    assert fresh["prefill"]["orders"] == "cut the gate narrower, around the parser only"
    assert fresh["prefill"]["severe"] == "gap: the proof is untestable"
    assert "wants rewriting" not in fresh["prefill"].get("severe", "")
    assert set(fresh["prefill"]) == {"orders", "severe"}
