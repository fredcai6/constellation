"""One look over a cut, then the proof is in execution (ruling, 2026-09-11,
extended to both review seams 2026-09-25).

One declaration on `assemblies/run-an-issue/ASSEMBLY.toml` now carries it on
both seams: `panel-rounds = "opening"` mints a transition's critic panel on
the run's opening artifact (spec or cut) alone, plus a `rewrite`'s fresh one
-- an `incorporate`'s round, a re-cut after a gate lands, and a resumed
round each stand the conductor's route form with no panel beside it. There
is no free round to police any more either: `_check_one_look` refuses a
second `incorporate` of the same artifact outright, in place of the old
`impasse-after = 0` ruling-on-the-first-send-back mechanism, which was
removed along with the impasse outlet itself on these two seams.

The first outside run is the evidence: the understand seam ran three panel
rounds and four of round 3's five findings were introduced fixing round
2's; the plan seam ran 14 critic panels across 8 gates, the re-cut panels
after the first finding almost nothing a reading could find, while a
reviewer with a diff to run found what nine critic reports on one gate's
three cuts had missed.

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


# -- A. the panel reads the opening cut only ---------------------------------


def test_the_plan_transition_declares_its_panel_for_the_opening_round_only():
    """The declaration the engine reads, on the assembly rather than in a
    mint-time rule: which rounds a seam's panel reads is that seam's own
    call. One look (2026-09-25) put the same declaration on `understand`
    too -- both seams read their opening artifact's panel alone now, not
    just `plan`."""
    assert _seg("plan")["transition"]["panel-rounds"] == "opening"
    assert len(_seg("plan")["transition"]["panel"]) == 3
    assert _seg("understand")["transition"]["panel-rounds"] == "opening"
    assert _seg("understand")["transition"]["panel"]


def test_skeleton_mints_the_opening_plan_round_with_its_panel():
    """`skeleton()` reads the panel unconditionally -- the opening round is
    the one the declaration names."""
    steps = runmod.skeleton(runmod.load_assembly(ASM))
    opening = next(s for s in steps if s["id"] == "plan")
    assert opening["form"] == "forms/PLAN_TO_EXECUTE.toml"
    assert len(opening["panel"]) == 3


def test_a_re_cut_after_a_gate_lands_carries_the_route_form_and_no_panel(workdir, capsys):
    """The refill `replan` and `settle` both mint (`_mint_segment_round`,
    `restarts=True`): a fresh planner dispatch and the conductor's route
    form alone -- no critic re-reads a cut the run's own gates are already
    testing."""
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
    assert "panel" not in route
    # the opening round's own transition still carries the panel it had
    assert len(next(s for s in st["steps"] if s["id"] == "plan")["panel"]) == 3


def test_understands_re_minted_transition_no_longer_carries_its_panel(workdir, capsys):
    """One look (2026-09-25) put `panel-rounds = "opening"` on `understand`
    too, so a fresh CONSOLIDATE round now stands with no panel, the same
    shape a re-minted PLAN_TO_EXECUTE round already had -- the declaration
    that used to distinguish the two seams no longer does."""
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
    `round-cap` is the ceiling still declared here, unchanged."""
    assert "impasse-after" not in _seg("understand")
    assert "impasse-after" not in _seg("plan")
    assert "impasse-form" not in _seg("understand")
    assert "impasse-form" not in _seg("plan")
    assert _seg("understand")["round-cap"] == _seg("plan")["round-cap"] == 5


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
    """A later plan round stands the route form with no panel, and an
    `incorporate` there still carries the conductor's `orders` ahead of
    whatever findings the round holds, into the dispatched writer's
    prefill. Keyed on the step standing on the segment's own transition
    form, not on a panel it no longer has."""
    journal.append("i1", "run", title="t", assembly=ASM)
    for step in runmod.skeleton(runmod.load_assembly(ASM)):
        journal.append("i1", "step", **step)
    asm = runmod.load_assembly(ASM)
    cli._mint_segment_round("i1", asm, "plan", restarts=True)
    st = runmod.state("i1")
    route = next(s for s in st["steps"]
                 if s["segment"] == "plan" and s.get("source") == "panel")
    assert "panel" not in route
    capsys.readouterr()

    prefill = cli._incorporated("i1", _seg("plan"), route, {"orders": "one gate, not two"})
    assert prefill["findings"] == "[conductor] one gate, not two"
