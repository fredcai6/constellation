"""One look over a cut, then the proof is in execution (ruling, 2026-09-11).

Two declarations on `assemblies/run-an-issue/ASSEMBLY.toml` carry it. The
plan transition's `panel-rounds = "opening"` mints its critic panel on the
run's opening cut alone: a re-cut after a gate lands, a ruled rework round
and a resumed round each stand the conductor's route form with no panel
beside it. And `impasse-after = 0` at both seams makes the first send-back
of a spec or a cut the ruling itself -- the impasse form, not a free round.

The first outside run is the evidence: the understand seam ran three panel
rounds and four of round 3's five findings were introduced fixing round
2's; the plan seam ran 14 critic panels across 8 gates, the re-cut panels
after the first finding almost nothing a reading could find, while a
reviewer with a diff to run found what nine critic reports on one gate's
three cuts had missed.

`tests/test_rework.py` drives the first send-back to the impasse form at
both seams; this file pins the declarations the engine reads, the shape of
every later plan round, and that `0` is read as a count rather than as an
absence.
"""

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
    call, and `understand` keeps the default, every round."""
    assert _seg("plan")["transition"]["panel-rounds"] == "opening"
    assert len(_seg("plan")["transition"]["panel"]) == 3
    assert "panel-rounds" not in _seg("understand")["transition"]
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


def test_understands_re_minted_transition_still_carries_its_panel(workdir, capsys):
    """The default, `every`, on the seam that keeps it: a fresh understand
    round re-mints CONSOLIDATE with its panel, so the declaration changes
    exactly one seam."""
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
    assert len(understand) == 1 and len(understand[0]["panel"]) == 3
    assert len(plan) == 1 and "panel" not in plan[0]
    assert plan[0]["form"] == "forms/PLAN_TO_EXECUTE.toml"


# -- B. zero is a count, not an absence ---------------------------------------


def test_both_seams_declare_no_free_round():
    assert _seg("understand")["impasse-after"] == 0
    assert _seg("plan")["impasse-after"] == 0
    assert _seg("understand")["round-cap"] == _seg("plan")["round-cap"] == 5


def test_impasse_after_zero_fires_the_outlet_on_the_first_send_back(workdir, capsys):
    """`_panel_judged_rework` reads `impasse-after = 0` as a declaration: the
    opening round was never sent back (`rework_rounds` is 0 there), so the
    first send-back reaches the outlet. A segment that declares no
    `impasse-after` at all never does -- the reading run-a-gate's `review`
    and explore-an-idea's `spec` depend on."""
    journal.append("i1", "run", title="t", assembly=ASM)
    for step in runmod.skeleton(runmod.load_assembly(ASM)):
        journal.append("i1", "step", **step)
    asm = runmod.load_assembly(ASM)
    seg = _seg("plan")
    route = next(s for s in runmod.state("i1")["steps"] if s["id"] == "plan")
    capsys.readouterr()

    _, outlet = cli._panel_judged_rework("i1", asm, seg, route, {"orders": "tighten it"})
    assert outlet == "forms/IMPASSE.toml"

    undeclared = {k: v for k, v in seg.items() if k != "impasse-after"}
    _, outlet = cli._panel_judged_rework("i1", asm, undeclared, route, {"orders": "tighten it"})
    assert outlet == ""


def test_a_panel_less_route_round_sent_back_carries_the_conductors_orders(workdir, capsys):
    """A later plan round stands the route form with no panel, and the
    conductor's `rework` there is still a send-back: it spends the count and
    owes the next round its own `orders`. Keyed on the step standing on the
    segment's own transition form, not on a panel it no longer has."""
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

    prefill, outlet = cli._panel_judged_rework(
        "i1", asm, _seg("plan"), route, {"orders": "one gate, not two"})
    assert prefill["findings"] == "[conductor] one gate, not two"
    assert outlet == "forms/IMPASSE.toml"

    # the impasse ruling itself is still the one step that spends nothing
    ruling = {"id": "plan-a1", "segment": "plan", "form": "forms/IMPASSE.toml",
              "prefill": {"findings": "carried"}}
    prefill, outlet = cli._panel_judged_rework(
        "i1", asm, _seg("plan"), ruling, {"ruling": "rework", "why": "waived: none"})
    assert outlet == "" and prefill is None
