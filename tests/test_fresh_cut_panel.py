"""Each fresh artifact gets one cold read, and a pass over its findings gets
none (one look, 2026-09-25; every fresh cut, 2026-09-26).

One declaration on `assemblies/run-an-issue/ASSEMBLY.toml` carries it on
both seams: `panel-rounds = "fresh"` mints a transition's critic panel on
each fresh artifact -- the run's opening spec or cut, a `rewrite`'s, a
replan's, the re-cut after each gate lands -- while an `incorporate`'s round
and a resumed round stand the conductor's route form alone. It replaced
`opening`, which panelled the run's first cut alone: every later gate's cut
went unread, and planners wrote them as amendments to the first. There
is no free round to police any more either: `_check_one_look` refuses a
second `incorporate` of the same artifact outright, in place of the old
`impasse-after = 0` ruling-on-the-first-send-back mechanism, which was
removed along with the impasse outlet itself on these two seams.

The first outside run is the evidence for one look: the understand seam
ran three panel rounds and four of round 3's five findings were introduced
fixing round 2's. The 2026-09-26 re-measure is the evidence for panelling
each gate's cut: across 12 runs, 30 later cuts went to the conductor alone,
and issue191's fifth planner read the third gate's plan and wrote "earlier
plans' facts still hold and are not repeated".

This file pins the declarations the engine reads and the shape of every
later plan or understand round.
"""

import pytest

from engine import cli, journal, run as runmod

from test_nesting import (
    _dispatch_and_close_child,
    _fill_gate_transition_replan,
    _mint_first_gate,
)

ASM = "run-an-issue"


def _seg(seg_id):
    return next(s for s in runmod.load_assembly(ASM)["segment"] if s["id"] == seg_id)


# -- A. the panel reads every fresh artifact ---------------------------------


def test_both_seams_declare_their_panel_for_fresh_rounds():
    """The declaration the engine reads, on the assembly rather than in a
    mint-time rule: which rounds a seam's panel reads is that seam's own
    call, and both seams read each fresh artifact."""
    assert _seg("plan")["transition"]["panel-rounds"] == "fresh"
    assert len(_seg("plan")["transition"]["panel"]) == 3
    assert _seg("understand")["transition"]["panel-rounds"] == "fresh"
    assert _seg("understand")["transition"]["panel"]


def test_skeleton_mints_the_opening_plan_round_with_its_panel():
    """`skeleton()` reads the panel unconditionally -- the opening round is
    the one the declaration names."""
    steps = runmod.skeleton(runmod.load_assembly(ASM))
    opening = next(s for s in steps if s["id"] == "plan")
    assert opening["form"] == "forms/PLAN_TO_EXECUTE.toml"
    assert len(opening["panel"]) == 3


def test_a_re_cut_after_a_gate_lands_gets_the_full_panel(workdir, capsys):
    """The refill `replan` and `settle` both mint (`_mint_segment_round`,
    `restarts=True`): a fresh planner dispatch and the conductor's route
    form with the seam's whole panel beside it -- each gate's cut is read
    cold against the code and spec as they stand."""
    _mint_first_gate()
    _dispatch_and_close_child("issue17", "g1")
    _fill_gate_transition_replan("issue17")
    cli.main(["issue17", "submit"])
    capsys.readouterr()

    st = runmod.state("issue17")
    fresh = [s for s in st["steps"]
             if s["segment"] == "plan" and s["id"] not in st["done"]]
    assert [s.get("dispatches") for s in fresh] == ["cut-a-gate", None]
    route = fresh[1]
    assert route["form"] == "forms/PLAN_TO_EXECUTE.toml"
    assert route["panel"] == _seg("plan")["transition"]["panel"]
    # the opening round's own transition still carries the panel it had
    assert len(next(s for s in st["steps"] if s["id"] == "plan")["panel"]) == 3


def test_an_incorporated_round_stands_with_no_panel_on_either_seam(workdir, capsys):
    """A round that is another pass at the artifact standing (`restarts`
    left False, what `incorporate` mints) stands CONSOLIDATE or
    PLAN_TO_EXECUTE with no panel: the writer has already ruled on every
    finding it carried (one look)."""
    journal.append("i1", "run", title="t", assembly=ASM)
    for step in runmod.skeleton(runmod.load_assembly(ASM)):
        journal.append("i1", "step", **step)
    asm = runmod.load_assembly(ASM)
    cli._mint_segment_round("i1", asm, "understand")
    cli._mint_segment_round("i1", asm, "plan")
    capsys.readouterr()

    st = runmod.state("i1")
    understand = [s for s in st["steps"]
                  if s["segment"] == "understand" and s.get("source") == "panel"]
    plan = [s for s in st["steps"] if s["segment"] == "plan" and s.get("source") == "panel"]
    assert len(understand) == 1 and "panel" not in understand[0]
    assert understand[0]["form"] == "forms/CONSOLIDATE.toml"
    assert len(plan) == 1 and "panel" not in plan[0]
    assert plan[0]["form"] == "forms/PLAN_TO_EXECUTE.toml"


# -- B. no free round, by refusal rather than by ruling ------------------------


def test_both_seams_declare_no_free_round():
    """One look (2026-09-25) replaces the old `impasse-after = 0` ruling --
    the first send-back was the ruling itself, on a form dedicated to it.
    Both segments dropped `impasse-after` (and the impasse outlet)
    entirely: `_check_one_look` now refuses a second `incorporate` of the
    same artifact outright, in code rather than in a conductor's ruling.
    The ceiling here is `rewrite-cap = 1`: one major rewrite, then an ask
    -- `round-cap` stays on run-a-gate's review alone."""
    assert "impasse-after" not in _seg("understand")
    assert "impasse-after" not in _seg("plan")
    assert "impasse-form" not in _seg("understand")
    assert "impasse-form" not in _seg("plan")
    assert _seg("understand")["rewrite-cap"] == _seg("plan")["rewrite-cap"] == 1
    assert "round-cap" not in _seg("understand")
    assert "round-cap" not in _seg("plan")


def test_a_second_incorporate_of_the_same_artifact_is_refused(workdir, capsys):
    """`_check_one_look` is what replaced `impasse-after = 0`'s ruling-on-
    the-first-send-back: an `incorporate` is legal once per artifact, and a
    second one on the same round is refused before the submit lands, rather
    than reaching an outlet a conductor rules on."""
    journal.append("i1", "run", title="t", assembly=ASM)
    for step in runmod.skeleton(runmod.load_assembly(ASM)):
        journal.append("i1", "step", **step)
    asm = runmod.load_assembly(ASM)
    seg = _seg("plan")
    route = next(s for s in runmod.state("i1")["steps"] if s["id"] == "plan")
    capsys.readouterr()

    outcome = (seg, "incorporate")
    # the opening round was never sent back, so the first incorporate is legal
    cli._check_one_look(asm, runmod.state("i1"), outcome, {"orders": "tighten it"})

    # a second incorporate on top of one already minted is refused
    cli._mint_segment_round("i1", asm, "plan")
    with pytest.raises(SystemExit):
        cli._check_one_look(asm, runmod.state("i1"), outcome, {"orders": "tighten it again"})


def test_a_panel_less_route_round_incorporated_carries_the_conductors_orders(workdir, capsys):
    """An incorporated plan round stands the route form with no panel, and an
    `incorporate` there still carries the conductor's `orders` ahead of
    whatever findings the round holds, into the dispatched writer's
    prefill. Keyed on the step standing on the segment's own transition
    form, not on a panel it no longer has."""
    journal.append("i1", "run", title="t", assembly=ASM)
    for step in runmod.skeleton(runmod.load_assembly(ASM)):
        journal.append("i1", "step", **step)
    asm = runmod.load_assembly(ASM)
    cli._mint_segment_round("i1", asm, "plan")
    st = runmod.state("i1")
    route = next(s for s in st["steps"]
                 if s["segment"] == "plan" and s.get("source") == "panel")
    assert "panel" not in route
    capsys.readouterr()

    prefill = cli._incorporated("i1", _seg("plan"), route, {"orders": "one gate, not two"})
    assert prefill["findings"] == "[conductor] one gate, not two"
