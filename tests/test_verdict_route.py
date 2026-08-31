"""#56: `_act_on_verdicts` no longer special-cases the raw word. Since g3
dropped `escalate` from the tree, `run-a-gate`'s review and
`explore-an-idea`'s spec were the last transitions whose routing lived in a
hardcoded `if verdict != "revise": return` rather than in a declared
`[[segment.transition.outcome]]` table -- the exact mechanism a two-voices
step (run-an-issue's plan-to-execute) already used. This file proves the
merged verdict now resolves the same way there too, and that nothing in the
engine's routing still compares the word itself.

#57 then made run-a-gate's review a two-voices step of its own: both of the
panel's words perform the declared `release` (a no-op -- nothing mints),
which leaves the step open on its own conductor form, and that form's
`close` or `rework work` is what walks the gate on or refills `work`. So the
table is still what routes; there are simply two voices answering it, and the
one with findings in front of it is the one that decides. The second wave
moved that step into its own `review` segment and made it *minted* rather
than declared -- `select` writes its panel and `route-form` names its form --
so the outcome rows it resolves against sit at segment grain, which is what
`deciding_spec` reaches for a step whose form is not the transition's own.

Drives the real `run-a-gate` assembly, not a fixture -- `test_verdict_panels.py`
already does, and its fixtures are reused here rather than re-declared.
"""

import pathlib

from engine import cli, run as runmod
from test_two_voices import CRITIC
from test_verdict_panels import (  # noqa: F401
    _fill, _fill_implement, _fill_review, _fill_route, _open_gate, _open_panelist,
    _review_step, _select, workdir,
)

REPO = pathlib.Path(__file__).resolve().parent.parent


# -- the wiring: `_decided_here` picks the transition's own `resolution` ---


def test_run_a_gates_review_declares_resolution_disjoint_from_ruling():
    """`_decided_here` on the review step must pick the transition's own
    `resolution` -- answered by both of its voices, the panel's merged word
    and then the conductor form's own -- not `ruling`, the `work` segment's
    own field (IMPASSE.toml's). The two have to stay disjoint for a deciding
    step to resolve to exactly one outcome table. `_outcome` then resolves
    each of `resolution`'s four legal values against the rows the assembly
    actually declares: the panel's two are both inert, and the conductor's
    `rework` is the one that mints."""
    asm = runmod.load_assembly("run-a-gate")
    step = {"segment": "review", "form": "forms/ROUTE.toml",
            "panel": [{"form": "skills/reviewer/forms/REVIEW.toml"}]}

    field = cli._decided_here(asm, step)
    assert field == "resolution"
    assert field != "ruling"  # `work`'s own decides -- IMPASSE.toml's, not this

    # the panel's own two words: neither acts, so the step stays open for the
    # form and the conductor is the one who says where the round goes
    for verdict in ("pass", "revise"):
        seg, does = cli._outcome(asm, step, {"resolution": verdict}, {"steps": []})
        assert seg["id"] == "review" and does == "release"

    # the conductor's two. `rework` names its target now: review is not the
    # segment the fresh round lands in, so a bare verb would refill review.
    seg, does = cli._outcome(asm, step, {"resolution": "rework"}, {"steps": []})
    assert seg["id"] == "review" and does == "rework work"

    seg, does = cli._outcome(asm, step, {"resolution": "close"}, {"steps": []})
    assert seg["id"] == "review" and does == "release"

    # `up` is a real declared value here now, not only on `work`'s own impasse
    # table -- an undeclared one refuses, so this is what makes the word
    # legal at route at all. It targets `work` explicitly, the same as
    # `rework` above: review is not the segment the resumed round lands in.
    seg, does = cli._outcome(asm, step, {"resolution": "up"}, {"steps": []})
    assert seg["id"] == "review" and does == "pause work"


def _route_with_calls(wid, resolution, *calls):
    """The conductor's own half of the review step with a ruling on every
    finding: one `[[calls]]` block per (what was raised, what it was called)
    pair. `_fill_route` is the same submit with no table at all, which is
    what every other caller of the `rework` verb looks like."""
    blocks = "".join('\n[[calls]]\nfinding = "%s"\ncall = "%s"\n' % c for c in calls)
    _fill(runmod.journal.location(wid) / "ROUTE.toml",
          'resolution = "%s"\n' % resolution + blocks)


# -- end to end: both verdicts hold for the form, the form routes ---------


def test_a_pass_resolves_through_the_outcome_table_and_holds_for_the_form(workdir, capsys):
    """Pass's declared verb is `release`, which `_perform` matches nothing
    for -- a deliberate no-op, not an absence of routing. Because it is
    inert, the review step stays open on its own form rather than folding
    shut: the conductor's `close` is what walks the gate on, and it still
    walks it on by the step order minted at open, never by a mint either
    submit makes."""
    _open_gate()
    review = _review_step("g1")
    panelist = _open_panelist("g1", review)
    _fill_review(panelist, "pass")
    cli.main([panelist, "submit"])
    capsys.readouterr()
    cli.main([panelist, "close"])
    capsys.readouterr()

    st = runmod.state("g1")
    assert st["current"]["id"] == review          # held for the second voice
    assert st["current"]["form"] == "forms/ROUTE.toml"

    _fill_route("g1", "close")
    cli.main(["g1", "submit"])
    capsys.readouterr()

    st = runmod.state("g1")
    assert st["current"]["id"] == "close"
    assert [s["id"] for s in st["steps"]] == ["work-1", "select", review, "close"]


def test_a_revise_holds_for_the_form_and_the_forms_rework_mints_the_round(workdir, capsys):
    """Revise's declared verb is `release` now, exactly as pass's is: the
    round with findings in it is the one somebody has to rule on, so it
    holds the step open instead of refilling behind the conductor's back.
    `rework` -- the form's own word, not the panel's -- is what mints the
    fresh implement round, and it still carries the panel's own findings as
    prefill, the shape the mechanical refill produced."""
    _open_gate()
    review = _review_step("g1")
    panelist = _open_panelist("g1", review)
    _fill_review(panelist, "revise", findings="gap: the bound is still off")
    cli.main([panelist, "submit"])
    capsys.readouterr()
    cli.main([panelist, "close"])
    capsys.readouterr()

    st = runmod.state("g1")
    assert st["current"]["id"] == review          # nothing minted off the word
    # the review step itself is a mint (select's); no *round* was minted off
    # the word, which is what this pins
    assert not any(s["segment"] == "work" and s.get("source") == "mint"
                   for s in st["steps"])

    _fill_route("g1", "rework")
    cli.main(["g1", "submit"])
    capsys.readouterr()

    st = runmod.state("g1")
    fresh = next(s for s in st["steps"] if s["segment"] == "work" and s.get("source") == "mint")
    assert fresh["form"] == "skills/implementer/forms/IMPLEMENT.toml"
    # No `calls` table on that submit, so the round carries every finding the
    # panel returned -- the behaviour every other caller of the same verb
    # still gets, pinned here beside the filtered round below.
    assert "gap: the bound is still off" in fresh["prefill"]["findings"]
    assert st["current"]["id"] == fresh["id"]

    # -- and now a mixed round, ruled on finding by finding ------------------
    #
    # One round is not enough to tell carry-everything from carry-blocking:
    # with a single finding, both answers are the same string. So the second
    # round returns three things to rule on -- a gap, a `beyond`, and the
    # implementer's own declared deviation -- and exactly one is called
    # blocking.
    _fill_implement("g1")
    cli.main(["g1", "submit"])
    second_review = _select("g1")
    panelist = _open_panelist("g1", second_review)
    _fill_review(panelist, "revise",
                 findings=(r"gap: the bound is off by one still\n\n"
                           r"beyond: the whole parser wants rewriting"))
    cli.main([panelist, "submit"])
    cli.main([panelist, "close"])
    capsys.readouterr()

    _route_with_calls(
        "g1", "rework",
        ("gap: the bound is off by one still", "blocking"),
        ("beyond: the whole parser wants rewriting", "beyond"),
        ("renamed two locals in the file the gate already touches", "accepted"))
    cli.main(["g1", "submit"])
    capsys.readouterr()

    carried = runmod.state("g1")["current"]["prefill"]["findings"]
    assert carried == "gap: the bound is off by one still"
    assert "parser wants rewriting" not in carried      # called beyond, not work here
    assert "renamed two locals" not in carried          # a deviation, accepted


# -- the generalization is a strict superset: nobody else's fold moved -----


# Every two-voices step shape in the tree -- one step standing a `panel` and a
# `form` together -- and which merged verdicts leave it open for that form.
# Pinned as a table rather than swept blindly, because the claim under test is
# a *comparison*: before #56 the answer was `pass` at all three, by a literal
# in `state()`; now it is whatever each assembly's own outcome rows say is
# inert, and only run-a-gate's changed. A new row here means an assembly
# gained a two-voices step and someone has to say what its fold does; a
# changed row means an existing consumer's behavior moved.
TWO_VOICES = {
    ("run-a-gate", "review"): ["pass", "revise"],    # minted by select, not declared
    ("run-an-issue", "understand"): ["pass"],        # consolidate -- untouched
    ("run-an-issue", "plan"): ["pass"],              # plan-to-execute -- untouched
}


def _two_voices_steps():
    """Every step shape in the tree that carries a panel and a form at once.

    Two ways to be one now. A transition declaring both statically is the
    original; run-a-gate's review is the second -- `select` writes the panel
    at its own submit and `route-form` names the form, so no static table
    holds the pair and a sweep that reads only `[segment.transition]` sees
    nothing where the tree's most-exercised two-voices step actually is.
    """
    for name in runmod.assemblies():
        asm = runmod.load_assembly(name)
        for seg in asm["segment"]:
            t = seg.get("transition", {})
            if t.get("panel") and t.get("form"):
                panel, form = t["panel"], t["form"]
            elif seg.get("route-form"):
                panel, form = [{"worker": "reviewer", "criteria": "c"}], seg["route-form"]
            else:
                continue
            yield name, seg["id"], {"segment": seg["id"], "form": form, "panel": panel}


def test_only_run_a_gates_own_fold_moved_and_the_other_consumers_are_untouched():
    """`state()` holds a two-voices step open on the verdicts its own deciding
    spec declares inert, so consolidate and plan-to-execute still reach their
    forms on `pass` and still refill behind the conductor on `revise` -- their
    `revise` rows read `rework`, which acts, and neither gate edited them.
    Asserting the whole table, not just run-a-gate's row, is what makes
    "strict superset" a checked claim instead of a hope."""
    found = {}
    for name, seg_id, step in _two_voices_steps():
        st = {"assembly": name, "steps": [step]}
        found[(name, seg_id)] = [
            v for v in ("pass", "revise")
            if runmod._holds_for_its_form(st, step, [{"fields": {"verdict": v}}])]
    assert found == TWO_VOICES


def test_an_interior_design_panel_still_completes_on_its_own_form():
    """The other half of the same promise, and the one a table walk could
    quietly break: ruling 10's design panel sits on an *interior* step, whose
    segment declares an impasse `ruling` and no verdict word at all. No row
    resolves, so nothing acts, so the step holds for its form -- pass and
    revise alike, exactly as the literal `pass` check left it."""
    step = {"segment": "plan", "form": "skills/planner/forms/PLAN.toml",
            "panel": [{"form": CRITIC}]}
    st = {"assembly": "run-an-issue", "steps": [step]}
    for verdict in ("pass", "revise"):
        assert runmod._holds_for_its_form(st, step, [{"fields": {"verdict": verdict}}])


# -- the vocabulary comparison itself is gone from the routing branches -----


def test_no_line_in_cli_compares_the_word_verdict():
    """#46's own completion condition, checked literally: `_returned_verdict`
    was the one surviving site that still wrote `verdict == "pass"` -- the
    room's own suppression, not a routing branch, but still the engine
    holding the reviewer's word. It now reads the same outcome table
    `_holds_for_its_form` and `_act_on_verdicts` already read (`declared_does`
    resolving to `release`, or an undeclared word, is the quiet class), so
    the grep this issue names returns nothing rather than one deliberate
    survivor."""
    src = (REPO / "engine" / "cli.py").read_text()
    hits = [(n, line) for n, line in enumerate(src.splitlines(), start=1)
           if "verdict ==" in line or "verdict !=" in line]
    assert hits == [], f"expected no surviving comparison, found: {hits}"


def test_renaming_the_passing_value_in_the_outcome_table_needs_no_engine_edit(monkeypatch):
    """The check #46 itself asks for: change the reviewer's declared
    vocabulary and the room's suppression follows it, with no edit to
    `engine/cli.py`. `_returned_verdict` no longer compares the merged word
    against the literal `pass` -- it asks the same outcome table
    `_holds_for_its_form` and `_act_on_verdicts` already read, so a renamed
    `value` row is exactly as quiet as the original one was.

    `merged_verdict` (engine/run.py) still folds a panel's returns to the
    fixed pair `pass`/`revise` regardless of what a critic's own form calls
    them -- CRITIC.toml's `verdict` field note is where that pair is named,
    a second site outside this issue's one-line, cli.py-scoped completion
    check, found here but not fixed: #46 asks only that `engine/cli.py` hold
    no verdict word, and that function does not. Monkeypatching
    `merged_verdict` to answer the renamed word is the honest stand-in for
    the rest of a full vocabulary rename this issue does not reach; what
    this test actually exercises is the half `_returned_verdict` touches --
    the outcome table's own declared value, read fresh rather than compared
    against a word this function remembers."""
    step = {"id": "plan", "segment": "plan", "form": "forms/PLAN_TO_EXECUTE.toml",
            "panel": [{"form": CRITIC}]}
    st = {"assembly": "run-an-issue", "steps": [step],
          "returns": {"plan": [{"fields": {"verdict": "clear"}}]}}

    asm = runmod.load_assembly("run-an-issue")
    seg = next(s for s in asm["segment"] if s["id"] == "plan")
    row = next(o for o in seg["transition"]["outcome"] if o["value"] == "pass")
    row["value"] = "clear"  # the reviewer's passing value, renamed in the assembly alone

    monkeypatch.setattr(runmod, "merged_verdict", lambda returns: "clear")
    assert cli._returned_verdict(st, asm) == "", (
        "renaming the outcome table's passing value should still leave the "
        "room quiet, with no edit to engine/cli.py")
