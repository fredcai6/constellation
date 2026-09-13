"""A waived optional field is not an order.

`waived: <reason>` and `unknown: <reason>` are how a form says a field has no
value. They were stored as the value, so every later reader had to know the
vocabulary to avoid acting on a non-answer -- and three did not. A real
`run-an-issue` drive cut a gate whose spec carried `model = "waived: none"`;
`_tier` read that as the tier, `_runner` found no such entry in `[models]`
and returned `""`, and the engine dispatched `claude --model ""` three times
until the start cap spent. The light model then did the gate's work by hand.
Nothing in the eval that drive ran under noticed.

The fix is that the null never travels: `forms.without_nulls` drops it where
a spec becomes a step's prefill, and every reader's existing
absent-field default -- `_tier`'s own `or seg.get("model", "")` -- is already
the behaviour a waived field asks for.
"""

from engine import checks as checkrun, cli, forms, run as runmod

SEG = {"id": "execute", "dispatches": "run-a-gate", "model": "standard",
       "adjudication-form": "forms/GATE_TRANSITION.toml"}


def _gate_prefill(wid, spec):
    cli._mint_gates(wid, SEG, [spec])
    step = next(s for s in runmod.state(wid)["steps"] if s["id"] == "g1")
    return step


def test_a_waived_model_falls_through_to_the_segments_own_tier(workdir):
    step = _gate_prefill("solo", {"purpose": "p", "scope": "s", "proof": "true",
                                  "model": "waived: none"})
    assert "model" not in (step.get("prefill") or {})
    assert cli._tier(step, {"segment": [SEG]}) == "standard"
    # the dispatch this used to break: a real model id, never the empty
    # string that made `claude --model ""` a 400
    assert cli._runner(cli._tier(step, {"segment": [SEG]}))


def test_a_waived_budget_leaves_the_proof_on_the_default(workdir):
    step = _gate_prefill("solo", {"purpose": "p", "scope": "s", "proof": "true",
                                  "budget": "waived: none"})
    assert checkrun.budget_for(step.get("prefill") or {}) == checkrun.BUDGET


def test_a_declared_model_still_overrides_the_segment(workdir):
    """The knob still works -- `heavy` appears in six real gate specs."""
    step = _gate_prefill("solo", {"purpose": "p", "scope": "s", "proof": "true",
                                  "model": "heavy"})
    assert cli._tier(step, {"segment": [SEG]}) == "heavy"


def test_unknown_is_a_null_the_same_way_waived_is(workdir):
    step = _gate_prefill("solo", {"purpose": "p", "scope": "s", "proof": "true",
                                  "model": "unknown: the plan never said"})
    assert cli._tier(step, {"segment": [SEG]}) == "standard"


def test_without_nulls_keeps_a_reason_bearing_real_answer():
    """`waived`/`unknown` lead a null; a real answer that merely mentions one
    later in its own sentence is an answer."""
    kept = forms.without_nulls({"purpose": "waiving input validation is out of scope",
                                "model": "waived: none"})
    assert kept == {"purpose": "waiving input validation is out of scope"}
