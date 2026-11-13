"""A merged verdict resolves through the transition's own declared outcomes,
the same way a submitted decision field does -- and the word `escalate`
appears nowhere in the corpus, engine included.

Two independent claims, standing apart on purpose: the first is about the
mechanism (`_act_on_verdicts` hands a synthetic `{decides_field: verdict}` to
`_outcome`/`_perform` wherever a transition declares one, `resolution` for
run-an-issue's plan-to-execute); the second is about the corpus (nothing
left behind still spells the removed word). A change could satisfy either
without the other: the mechanism could be wired correctly while stale prose
still taught the dropped word, or every authored artifact could read clean
while a dead-but-present branch still compared against it in engine code
that prose review never reads. Scoping the second check to prose alone would
miss exactly that branch -- `engine/` is checked like any other root.
"""

from engine import cli, journal, run as runmod
from conftest import REPO
from test_nesting import _response, _write_plan_artifact
from test_two_voices import CRITIC, _dispatch_and_close_plan, _dispatch_panel, _drive_to_plan_to_execute


# -- 1. the merged verdict resolves through the declared outcome table ------


def test_run_an_issues_plan_transition_declares_resolution_not_a_stale_word():
    """The wiring itself. `_decided_here` on the plan-to-execute step must
    pick the transition's own `resolution` field. The plan segment declares
    no `ruling`, `impasse-after` or `impasse-form` (one look), so there is
    no second outcome table on `plan` to stay disjoint from; the assertion
    that `_decided_here` never answers the `ruling` name is a cheap guard.
    The table walk below is this test's live content: `_outcome` resolves
    each of `resolution`'s five legal values against the row the assembly
    actually declares -- the panel's two are both inert, and the
    conductor's own `incorporate` and `rewrite` are what mint, `rework`
    not being one of this table's words -- the same shape run-a-gate's review/ROUTE.toml has
    (test_verdict_route.py's own version of this test)."""
    asm = runmod.load_assembly("run-an-issue")
    step = {"segment": "plan", "form": "forms/PLAN_TO_EXECUTE.toml"}

    field = cli._decided_here(asm, step)
    assert field == "resolution"
    assert field != "ruling"  # not a name any segment on this seam declares

    # the panel's own two words: neither acts, so the step stays open for the
    # form and the conductor is the one who says where the round goes
    for verdict in ("pass", "revise"):
        seg, does = cli._outcome(asm, step, {"resolution": verdict}, {"steps": []})
        assert seg["id"] == "plan" and does == "release"

    # the conductor's own three
    seg, does = cli._outcome(asm, step, {"resolution": "incorporate"}, {"steps": []})
    assert seg["id"] == "plan" and does == "incorporate"

    seg, does = cli._outcome(asm, step, {"resolution": "rewrite"}, {"steps": []})
    assert seg["id"] == "plan" and does == "rewrite"

    seg, does = cli._outcome(asm, step, {"resolution": "up"}, {"steps": []})
    assert seg["id"] == "plan" and does == "pause"


def test_the_conductors_incorporate_resolves_through_the_outcome_table_and_reworks(workdir, capsys):
    """End to end: the panel's own merged verdict is inert --
    it releases and holds `plan` open for the conductor's own form, exactly
    like run-a-gate's review/ROUTE.toml -- so what reaches `_perform`'s
    `incorporate` verb is the conductor's own typed `incorporate`, through
    the same outcome table a submitted decision field would use at any other
    step. `_dispatch_panel` (test_two_voices.py) submits that route form
    itself, defaulting to `incorporate` (one look), the same way
    a conductor following a revise would. The fresh round dispatches
    the same as any other round, carrying the panel's findings --
    proof that `_perform` ran against this step's own prefill (what caused
    the round) rather than the real plan-to-execute step's own prefill (the
    consolidated spec, the run's own understanding), which is not what an
    incorporate round should carry forward. An `incorporate` mints the
    fresh round directly, with no impasse ruling in between.

    See: #27
    """
    wid = _drive_to_plan_to_execute()
    real_prefill = runmod.state(wid)["prefill"]
    assert real_prefill  # the real step's prefill is non-empty to begin with
    capsys.readouterr()

    _dispatch_panel(wid, "plan", verdict="revise",
                    findings="gap: the loop bound is off by one")
    capsys.readouterr()

    st = runmod.state(wid)
    fresh = next(s for s in st["steps"]
                if s["segment"] == "plan" and s.get("source") == "mint" and s.get("dispatches"))
    assert fresh["dispatches"] == "cut-a-gate"
    assert fresh["form"] == "skills/planner/forms/REWORK.toml"
    # the fresh round carries what caused it -- the panel's findings -- and
    # nothing from the real plan-to-execute step's own prefill.
    assert not set(real_prefill) & set(fresh["prefill"])
    assert "off by one" in fresh["prefill"]["findings"]
    assert "[p1]" in fresh["prefill"]["findings"]


def test_a_conductor_typing_resolution_pass_still_projects_the_gate(workdir, capsys):
    """`resolution` is optional -- most conductors never touch it, and every
    other test in this file's own suite proves that path -- but one who
    types the honest `pass` must not disturb the ordinary projection.
    `_perform` runs after `_mint_projected_gate`, so a real submit exercises
    the row's `release` verb against a gate already projected, not in place
    of it."""
    wid = _drive_to_plan_to_execute()
    capsys.readouterr()
    _dispatch_panel(wid, "plan", verdict="pass")
    capsys.readouterr()

    _write_plan_artifact(f".agent-work/{wid}/plan.md")
    _response(wid).write_text('''
plan = ".agent-work/%s/plan.md"
resolution = "pass"
''' % wid)
    cli.main([wid, "submit"])
    capsys.readouterr()

    st = runmod.state(wid)
    assert any(s["id"] == "g1" for s in st["steps"])
    assert not any(s["segment"] == "plan" and s.get("source") == "mint"
                  for s in st["steps"]), "typing pass minted a redundant rework round"


# -- 2. the word itself is gone, engine included -----------------------------


CHECKED_ROOTS = ["engine", "skills", "standards", "assemblies", "docs"]


def test_escalate_appears_nowhere_under_engine_or_the_corpus():
    """`engine/` is on this list on purpose, not as an afterthought: a
    vocabulary comparison or a mint-time string literal that spelled
    `escalate` would be invisible to a check scoped to prose alone, and that
    is exactly the shape a dead branch takes -- reachable
    by nothing, since the word had already been refused out of every form
    that could submit it, but sitting in `engine/run.py` comparing
    against a value nothing could ever hand it."""
    hits = []
    for root in CHECKED_ROOTS:
        for path in (REPO / root).rglob("*"):
            if path.is_dir() or "__pycache__" in path.parts:
                continue
            try:
                text = path.read_text()
            except (UnicodeDecodeError, OSError):
                continue
            if "escalat" in text.lower():
                hits.append(str(path.relative_to(REPO)))
    assert not hits, f"'escalate' still appears in: {hits}"
