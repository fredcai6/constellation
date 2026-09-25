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

import ast

from engine import cli, journal, run as runmod
from conftest import REPO
from test_two_voices import CRITIC, _dispatch_critic, _drive_to_plan_to_execute
from test_nesting import (
    _fill_plan_route_with_calls, _fill_plan_to_execute, _response,
)
from test_verdict_panels import (
    _fill, _fill_implement, _fill_review, _fill_route, _open_gate, _open_panelist,
    _review_step, _select,
)


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
    _fill(_response(wid),
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
    # round returns three things to rule on -- a gap, a finding real but
    # outside this gate, and the implementer's own declared deviation -- and
    # exactly one is called blocking.
    _fill_implement("g1")
    cli.main(["g1", "submit"])
    second_review = _select("g1")
    panelist = _open_panelist("g1", second_review)
    _fill_review(panelist, "revise",
                 findings=(r"gap: the bound is off by one still\n\n"
                           r"the whole parser wants rewriting"))
    cli.main([panelist, "submit"])
    cli.main([panelist, "close"])
    capsys.readouterr()

    _route_with_calls(
        "g1", "rework",
        ("gap: the bound is off by one still", "blocking"),
        ("the whole parser wants rewriting", "rejected: outside this gate's own scope"),
        ("renamed two locals in the file the gate already touches", "accepted"))
    cli.main(["g1", "submit"])
    capsys.readouterr()

    carried = runmod.state("g1")["current"]["prefill"]["findings"]
    assert carried == "gap: the bound is off by one still"
    assert "parser wants rewriting" not in carried      # rejected, not work here
    assert "renamed two locals" not in carried          # a deviation, accepted


# -- the generalization is a strict superset: nobody else's fold moved -----


# Every two-voices step shape in the tree -- one step standing a `panel` and a
# `form` together -- and which merged verdicts leave it open for that form.
# Pinned as a table rather than swept blindly, because the claim under test is
# a *comparison*: before #56 the answer was `pass` at all three, by a literal
# in `state()`; now it is whatever each assembly's own outcome rows say is
# inert, and #56, ruling 3 (2026-09-02) and its 2026-09-03 follow-up at
# consolidate are the only ones that moved it. A new row here means an
# assembly gained a two-voices step and someone has to say what its fold
# does; a changed row means an existing consumer's behavior moved.
TWO_VOICES = {
    ("run-a-gate", "review"): ["pass", "revise"],    # minted by select, not declared
    ("run-an-issue", "understand"): ["pass", "revise"],  # consolidate -- ruling 3 follow-up
    ("run-an-issue", "plan"): ["pass", "revise"],    # plan-to-execute -- ruling 3
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


def test_run_a_gates_review_plan_to_executes_and_consolidates_own_folds_all_moved():
    """`state()` holds a two-voices step open on the verdicts its own deciding
    spec declares inert. All three of run-a-gate's review, plan-to-execute
    and (2026-09-03) consolidate now read both `pass` and `revise` as
    `release`, so all three hold open for their conductor's own route form
    rather than any of them refilling behind the conductor directly.
    Asserting the whole table, not just one row, is what makes the
    comparison a checked claim instead of a hope.

    Each return carries a `child` tag positional with `step["panel"]`, which
    is what makes this a real read of the seam's own table. `verdict_fold`
    pairs a return to its panelist by that tag; a return with no `child` key
    resolves to no panelist form at all and folds to quiet, which holds
    regardless of the word -- so a childless fixture would keep this whole
    table green while proving nothing it claims."""
    found = {}
    for name, seg_id, step in _two_voices_steps():
        st = {"assembly": name, "steps": [step]}
        found[(name, seg_id)] = [
            v for v in ("pass", "revise")
            if runmod._holds_for_its_form(
                st, step, [{"child": f"w.{seg_id}.p1", "fields": {"verdict": v}}])]
    assert found == TWO_VOICES


def test_an_interior_design_panel_still_completes_on_its_own_form():
    """The other half of the same promise, and the one a table walk could
    quietly break: a panel can sit on an *interior* step whose own segment
    declares an impasse `ruling` and no verdict word at all -- design-it-twice's
    round-one panel (ruling 10, shelved #96) was the tree's one live example,
    read here as a hand-built step since nothing mints one any more. No row
    resolves, so nothing acts, so the step holds for its form -- pass and
    revise alike, exactly as the literal `pass` check left it.

    The return carries its own `child` tag for the same reason the table
    walk above does: without one the fold pairs it to no panelist form and
    answers quiet, which holds for a reason that has nothing to do with this
    segment's table."""
    step = {"segment": "plan", "form": "skills/planner/forms/PLAN.toml",
            "panel": [{"form": CRITIC}]}
    st = {"assembly": "run-an-issue", "steps": [step]}
    for verdict in ("pass", "revise"):
        assert runmod._holds_for_its_form(
            st, step, [{"child": "w.plan.p1", "fields": {"verdict": verdict}}])


def test_an_interior_step_with_panel_and_form_stays_open_for_the_conductor(workdir):
    """Relocated from the old test_three_planners.py (#96): not this gate's
    own change -- `two_voices` (engine/run.py) is computed per-step, not
    per-transition, so this already holds for any step, round or transition
    alike. Pinned here as DESIRED behaviour rather than relied on silently:
    no interior step in the shipped tree carries both a `panel` and a `form`
    -- design-it-twice's own round-one step (ruling 10, shelved #96) carried
    a `panel` with no `form` beside it -- so nothing exercises this
    combination through a real assembly, and this stays a synthetic journal
    rather than a driven one."""
    wid = "synthetic"
    journal.append(wid, "run", title="t", assembly="run-an-issue")
    journal.append(wid, "step", id="s1", segment="plan", panel=[{"criteria": "a"},
                   {"criteria": "b"}], form="skills/planner/forms/PLAN.toml",
                   filler="conductor", anchor=False, terminal=False, validates="",
                   source="open")

    journal.append(wid, "return", step="s1", child=f"{wid}.s1.p1", fields={})
    st = runmod.state(wid)
    assert "s1" not in st["done"]  # one of two panelists in -- unsurprising yet

    journal.append(wid, "return", step="s1", child=f"{wid}.s1.p2", fields={})
    st = runmod.state(wid)
    # both panelists in, neither carried a `verdict` field -- the merged
    # verdict defaults to "pass", and two_voices holds the step open for the
    # conductor's own form submission rather than completing it here
    assert "s1" not in st["done"]
    assert st["current"]["id"] == "s1"


# -- the vocabulary comparison itself is gone from the routing branches -----


# The four `engine/` modules that read a returned verdict: the three the
# wiring gate touched plus `run.py` itself, which is where `verdict_fold`,
# `_voice_outcome` and `declared_does` live now. Obligation 1's own words are
# "anywhere in `engine/`", and this is the one check that carries them, so it
# has to reach the module the fold lives in as well as the modules that call
# it -- otherwise a future hardcoded comparison inside the fold's own home
# passes through clean.
VERDICT_READING_MODULES = ("cli.py", "render.py", "review_yield.py", "run.py")


def _reads_a_verdict(node):
    """Does this expression reach a returned verdict's own word anywhere
    inside it -- a `["verdict"]` subscript or a `.get("verdict", ...)` call,
    at any depth, so a comparison that wraps the read in
    `forms.leading_word(...)` is seen the same as a bare one."""
    for sub in ast.walk(node):
        if (isinstance(sub, ast.Subscript) and isinstance(sub.slice, ast.Constant)
                and sub.slice.value == "verdict"):
            return True
        if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)
                and sub.func.attr == "get" and sub.args
                and isinstance(sub.args[0], ast.Constant)
                and sub.args[0].value == "verdict"):
            return True
    return False


def _verdict_comparisons(src):
    """Every `==`/`!=` node in `src` either side of which reads a returned
    verdict -- the shape obligation 1 forbids, whatever word it is compared
    against."""
    hits = []
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.Compare):
            continue
        if not any(isinstance(op, (ast.Eq, ast.NotEq)) for op in node.ops):
            continue
        if any(_reads_a_verdict(o) for o in [node.left] + list(node.comparators)):
            hits.append(node.lineno)
    return hits


def test_no_node_in_the_engine_compares_a_returned_verdict_to_a_word():
    """Obligation 1's own completion condition -- no literal reviewer verdict
    word compared against a returned verdict anywhere in `engine/` -- read as
    a syntax tree rather than as text, and swept across every module that
    reads one.

    The text form this replaces (`"verdict ==" in line`, over `cli.py`
    alone) missed both of the real comparisons this gate removed.
    `engine/render.py:612`'s `rnd["verdict"] == "revise"` breaks the
    contiguous substring on the `"]`; `engine/review_yield.py:93-94`'s
    `forms.leading_word((r.get("fields") or {}).get("verdict", "")) ==
    "revise"` puts the word and the operator on two physical lines and wraps
    the read in a call besides. Verified by hand against both files as they
    stood before this gate touched them: the predicate below flags
    `render.py:612` and `review_yield.py:93` and nothing else.

    It costs no false positive on `run.py`'s two legitimate reads either:
    `_voice_outcome`'s own `.get("verdict", "")` feeds an `in vocab`
    membership test, which is not an `Eq`/`NotEq` node, and `declared_does`
    compares the outcome table's own `"value"` key, which is not a verdict
    read.

    What this cannot see, by its own shape, is a bare string-literal verdict
    *value* that nothing compares against -- the `"pass"` fallback
    `render._yield_round` used to carry. `tests/test_verdict_wiring.py`
    drives that layer instead, at the one function this check cannot reach
    into."""
    found = {}
    for name in VERDICT_READING_MODULES:
        hits = _verdict_comparisons((REPO / "engine" / name).read_text())
        if hits:
            found[name] = hits
    assert found == {}, f"expected no surviving comparison, found: {found}"


# A critic's own form, renamed: CRITIC.toml's shape exactly -- a `decision`
# field whose note opens with its alternatives -- with the passing value
# called `clear` instead of `pass`. Written to disk rather than built as a
# dict because `run.panel_forms` reads the path the step's own panel entry
# names, which is the whole point of driving the real reader here.
RENAMED_CRITIC = """
[[field]]
id = "findings"
kind = "evidence"
note = "One per finding. None found: waived: clean."

[[field]]
id = "verdict"
kind = "decision"
note = "clear | revise. The passing word, renamed."
"""


def test_renaming_the_passing_value_in_the_outcome_table_needs_no_engine_edit(tmp_path):
    """The check #46 itself asks for, and now the whole of it: rename the
    reviewer's passing value in the outcome table *and* in the panelist
    form's own note, and the room's suppression follows both with no edit to
    `engine/cli.py`.

    Nothing is stubbed. `_returned_verdict` resolves the panel's own forms
    through `run.panel_forms` and folds the returns through `verdict_fold`,
    so the renamed word has to survive two readings to reach the room: the
    panelist's own declared vocabulary (`forms.enforced_vocabulary` on the
    form the step's panel entry names) and the deciding table's own row.
    Neither is a literal in `engine/`, so renaming the pair together leaves
    the round exactly as quiet as `pass` was.

    This is what the earlier version of this test could only stand in for.
    It monkeypatched `merged_verdict` to answer the renamed word, because
    `merged_verdict` folded every panel to the fixed pair `pass`/`revise`
    whatever a critic's form called them -- so the half of the rename below
    the room's own line was not reachable at all. `merged_verdict` is gone
    and the fold reads the form, so the stand-in has a real thing to be."""
    form_ref = "RENAMED_CRITIC.toml"
    (tmp_path / form_ref).write_text(RENAMED_CRITIC)

    asm = runmod.load_assembly("run-an-issue")
    # The panel entry names an assembly-owned ref, so `resolve_form` reads it
    # relative to the assembly's own directory -- pointed at this test's own
    # tmp dir, which is what puts the renamed form in the panelist's slot
    # without touching `skills/`.
    asm["dir"] = tmp_path
    seg = next(s for s in asm["segment"] if s["id"] == "plan")
    row = next(o for o in seg["transition"]["outcome"] if o["value"] == "pass")
    row["value"] = "clear"  # the reviewer's passing value, renamed in the assembly

    step = {"id": "plan", "segment": "plan", "form": "forms/PLAN_TO_EXECUTE.toml",
            "panel": [{"form": form_ref}]}
    st = {"assembly": "run-an-issue", "steps": [step],
          "returns": {"plan": [{"child": "w.plan.p1", "fields": {"verdict": "clear"}}]}}

    assert cli._returned_verdict(st, asm) == "", (
        "renaming the outcome table's passing value, and the panelist form's "
        "own note with it, should still leave the room quiet, with no edit "
        "to engine/cli.py")

    # And the converse, so the assertion above is not passing on silence:
    # rename only the table's row and leave the form's note naming `clear`
    # too, but have the voice answer the word neither of them declares. The
    # room names the refusal rather than reporting a word it could not read.
    st["returns"]["plan"] = [{"child": "w.plan.p1", "fields": {"verdict": "pass"}}]
    assert cli._returned_verdict(st, asm) == "unreadable p1", (
        "the old passing word is no longer in this panelist's own vocabulary, "
        "so the room should name the refusal, not fall back to the word")


# -- the plan seam gets the same shape (ruling 3, 2026-09-02) ---------------


def test_a_plan_revise_holds_the_form_and_the_conductors_incorporate_mints_the_round_narrowed_by_calls(
        workdir, capsys):
    """PLAN_TO_EXECUTE.toml is this same shape now: a revise holds `plan`
    open rather than refiring the round automatically, and the conductor's
    own `incorporate` -- ruled finding by finding on the `calls` table, the
    same shape ROUTE.toml's own `_route_with_calls` exercises above -- is
    what actually sends the round back, narrowed to the `writer`-called
    findings alone; one look (2026-09-25) means this lands directly on the
    fresh round, with no impasse form in between any more. Also pins the
    other half of the projection gate: an `incorporate` names no `plan`, so
    nothing is projected into `execute`."""
    wid = _drive_to_plan_to_execute()
    capsys.readouterr()

    panel = next(s for s in runmod.state(wid)["steps"] if s["id"] == "plan")["panel"]
    for n in range(1, len(panel) + 1):
        _dispatch_critic(wid, "plan", verdict="revise",
                         findings=(r"gap: the proof is untestable\n\n"
                                   r"the whole parser wants rewriting"), n=n)
    capsys.readouterr()

    st = runmod.state(wid)
    assert st["current"]["id"] == "plan"          # held for the conductor's own form
    assert not any(s["segment"] == "plan" and s.get("source") == "mint"
                   for s in st["steps"]), "the panel's own revise minted a round"

    _fill_plan_route_with_calls(
        wid, "incorporate",
        ("gap: the proof is untestable", "writer"),
        ("the whole parser wants rewriting", "rejected: outside this plan's own scope"))
    cli.main([wid, "submit"])
    capsys.readouterr()

    st = runmod.state(wid)
    fresh = next(s for s in st["steps"]
                if s["segment"] == "plan" and s.get("source") == "mint" and s.get("dispatches"))
    carried = fresh["prefill"]["findings"]
    assert carried == "gap: the proof is untestable"
    assert "wants rewriting" not in carried      # rejected, not work here

    # and nothing projected: an incorporate releases nothing to execute
    assert not any(s.get("dispatches") == "run-a-gate" for s in st["steps"])


def test_the_conductors_orders_ride_ahead_of_the_writer_findings(workdir, capsys):
    """The route forms' `orders` field (2026-09-05): a conductor's own words
    for the next round cross into the incorporate's prefill ahead of the
    `writer`-called findings, marked as the conductor's -- so a ruling no
    finding says has a channel of its own instead of being written into
    `calls` as if the panel had returned it. A status word there (`waived:
    none`) is no order."""
    wid = _drive_to_plan_to_execute()
    panel = next(s for s in runmod.state(wid)["steps"] if s["id"] == "plan")["panel"]
    for n in range(1, len(panel) + 1):
        _dispatch_critic(wid, "plan", verdict="revise",
                         findings="gap: the proof is untestable", n=n)
    capsys.readouterr()
    _fill_plan_to_execute(
        wid, "incorporate",
        calls=('orders = "keep the walk general, not a skip-one"\n\n'
               '[[calls]]\nfinding = "gap: the proof is untestable"\ncall = "writer"\n'))
    cli.main([wid, "submit"])
    capsys.readouterr()
    st = runmod.state(wid)
    fresh = next(s for s in st["steps"]
                if s["segment"] == "plan" and s.get("source") == "mint" and s.get("dispatches"))
    assert fresh["prefill"]["findings"] == (
        "[conductor] keep the walk general, not a skip-one\n\ngap: the proof is untestable")


def test_a_waived_orders_field_carries_nothing(workdir, capsys):
    wid = _drive_to_plan_to_execute()
    panel = next(s for s in runmod.state(wid)["steps"] if s["id"] == "plan")["panel"]
    for n in range(1, len(panel) + 1):
        _dispatch_critic(wid, "plan", verdict="revise",
                         findings="gap: the proof is untestable", n=n)
    capsys.readouterr()
    _fill_plan_to_execute(
        wid, "incorporate",
        calls=('orders = "waived: none"\n\n'
               '[[calls]]\nfinding = "gap: the proof is untestable"\ncall = "writer"\n'))
    cli.main([wid, "submit"])
    capsys.readouterr()
    fresh = next(s for s in runmod.state(wid)["steps"]
                if s["segment"] == "plan" and s.get("source") == "mint" and s.get("dispatches"))
    assert fresh["prefill"]["findings"] == "gap: the proof is untestable"
