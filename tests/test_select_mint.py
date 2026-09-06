"""`select` chooses who reads the diff, and its submit mints the review step.

Obligations o3 and o4 (#57): a gate's beats are open → implement → select →
review → route → close, and `select` genuinely determines which reviewers
read the diff rather than recording a foregone pair. A panel is written once,
at the mint that makes the step, and every consumer sizes off it -- so a
`select` that edits a standing panel is not expressible, and `select` is
instead `work`'s own transition whose submit mints `review`'s: the panelists
it names and the route form their round is disposed of on, together.

Driven through the real assembly and the real forms throughout. The last test
here is the one that matters most: it is a regression against a guard that
looked fixed on paper twice, and it fails against the broken version rather
than asserting on the helper that holds it.
"""

import tomllib

from engine import cli, forms, journal, run as runmod
from conftest import REPO
from test_nesting import _fill, _fill_implement, _response, _select_panel
from test_verdict_panels import _fill_review

GATE = REPO / "assemblies" / "run-a-gate" / "ASSEMBLY.toml"


def _open_and_implement(gid="g1"):
    cli.main(["open", "run-a-gate", "--id", gid])
    _fill_implement(gid, f"{gid}-work-1")
    cli.main([gid, "submit"])
    return gid


# -- the mint: panel and route form, on the sole segment that could mean it --


def test_select_mints_the_panel_and_the_route_form_as_one_step(workdir, capsys):
    """One step carries both voices, exactly as a statically declared
    two-voices transition does -- the panel that reads and the form its round
    is disposed of on. The step is minted into the `review` segment with no
    name given anywhere: `_mint` resolves its target by structural shape,
    the sole segment declaring a `route-form`."""
    _open_and_implement()
    capsys.readouterr()

    _fill(_response("g1"), '''
omitted = "waived: none"

[[panelists]]
worker = "reviewer"
model = "standard"
criteria = "spec-fit: does the work fill the specification, whole and only"

[[panelists]]
worker = "reviewer"
model = "standard"
criteria = "test adequacy: are these the right tests"
''')
    cli.main(["g1", "submit"])
    capsys.readouterr()

    st = runmod.state("g1")
    review = st["current"]
    assert review["segment"] == "review"
    assert review["form"] == "forms/ROUTE.toml"     # the segment's own route-form
    assert review["filler"] == "conductor"          # the bare indirection, as declared
    assert review["anchor"] is True                 # copied off the transition declaration
    assert [p["criteria"] for p in review["panel"]] == [
        "spec-fit: does the work fill the specification, whole and only",
        "test adequacy: are these the right tests"]

    # and the diff reaches the readers: the implement round's own output is
    # carried onto the minted step, because by dispatch time the review
    # segment holds nothing but earlier review rounds
    assert review["prefill"]["change"].startswith("adjusted")
    cli.main(["open", "give-a-verdict", "--parent", "g1", "--step", f"{review['id']}.p2"])
    capsys.readouterr()
    pst = runmod.state(f"g1.{review['id']}.p2")
    assert pst["prefill"]["criteria"] == "test adequacy: are these the right tests"
    assert pst["prefill"]["change"] == review["prefill"]["change"]


def test_the_mint_resolves_its_target_with_no_name_anywhere_to_give_it(workdir):
    """Sole-match resolution, and nothing in the form to disambiguate with.
    `_board_segment`'s history is the order this follows: sole match first,
    a name branch only once a second consumer exists. So the claim under test
    is two-sided -- exactly one segment in run-a-gate carries `route-form`,
    and SELECT.toml declares no field that could name one."""
    gate = tomllib.load(open(GATE, "rb"))
    carriers = [s["id"] for s in gate["segment"] if s.get("route-form")]
    assert carriers == ["review"]

    form = forms.load(REPO / "assemblies" / "run-a-gate" / "forms" / "SELECT.toml")
    plan = next(f for f in form["fields"] if f["kind"] == "plan")
    assert plan["mints"] == "panelists"
    assert "board" not in plan and "segment" not in plan
    assert {i["id"] for i in plan["item"]} == {"worker", "model", "criteria"}


def test_an_omitted_lens_is_not_dispatched_and_its_reason_is_recorded(workdir, capsys):
    """An omission is a real answer. The panel that fires is exactly what was
    named -- one reader, not the two the form documents as defaults -- and
    the reason the second was left off is on the record at the step that left
    it off, in the conductor's own words."""
    _open_and_implement()
    capsys.readouterr()

    _fill(_response("g1"), '''
omitted = "test adequacy: this diff adds no code path, only prose in a form note"

[[panelists]]
worker = "reviewer"
model = "standard"
criteria = "spec-fit: does the work fill the specification, whole and only"
''')
    cli.main(["g1", "submit"])
    capsys.readouterr()

    st = runmod.state("g1")
    review = st["current"]
    assert len(review["panel"]) == 1                       # only what was named fired
    assert "test adequacy" not in str(review["panel"])
    assert "only prose in a form note" in st["done"]["select"]["fields"]["omitted"]

    cli.main(["g1"])
    out = capsys.readouterr().out
    assert "panelist p1" in out and "panelist p2" not in out


def test_a_bare_run_a_gate_is_still_not_issue_tier(workdir):
    """The companion the new mint kind requires: `_PANEL_MINT` is engine
    vocabulary, so it is subtracted in `_issue_tier` the same way the other
    two engine literals are. Without it every assembly reads as issue tier,
    which is git and a worktree where commitment 7 says none belong."""
    gate = runmod.load_assembly("run-a-gate")
    assert cli._PANEL_MINT in cli._mintable(gate)
    assert not cli._issue_tier(gate)
    assert cli._issue_tier(runmod.load_assembly("run-an-issue"))  # still is, on `dispatches`


# -- the regression: the outlet still fires once review is its own segment ---


def _drive_gate_through(gid, rounds):
    """`rounds` revise rounds on one diff, each driven through the real forms
    end to end -- implement, select, the panelist's own verdict, and the
    conductor's `rework` on the route form. Returns the gate's work id.

    Driven, not constructed: a unit call into `_panel_judged_rework` with a
    hand-built `seg` is exactly the shape that let a broken guard look fixed,
    because the caller gets to choose the segment the guard compares against.
    """
    cli.main(["open", "run-a-gate", "--id", gid])
    for n in range(1, rounds + 1):
        _fill_implement(gid, runmod.state(gid)["current"]["id"])
        cli.main([gid, "submit"])
        _select_panel(gid)
        review = runmod.state(gid)["current"]["id"]
        panelist = f"{gid}.{review}.p1"
        cli.main(["open", "give-a-verdict", "--parent", gid, "--step", f"{review}.p1"])
        _fill_review(panelist, "revise", f"gap: the spec asks for something untestable ({n})")
        cli.main([panelist, "submit"])
        cli.main([panelist, "close"])
        _fill(_response(gid), 'resolution = "rework"\n')
        cli.main([gid, "submit"])
    return gid


def test_a_third_route_decided_rework_still_reaches_the_impasse_form(workdir, capsys):
    """The bug this gate inherited and fixes. `_panel_judged_rework` decides
    whether a rework was decided at a panel-bearing transition -- if it was,
    the fresh round carries the panel's findings and spends the segment's
    `impasse-after` count, and the third one gets the outlet instead of a
    third round (`impasse-after = 2`, ruling 2026-09-02: at most three
    critic dispatches per artifact).

    Its guard used to compare the deciding step's own segment against the
    rework verb's *target* segment, and its form against that segment's
    statically declared transition form. Both halves were trivially true
    while review and work were one segment and the verb was bare. Both fail
    the moment review is its own segment (`does = "rework work"` names a
    target, and review's transition declares no static form at all), so the
    guard returned `(None, "")` for the exact step it exists to recognize,
    the count never advanced, and the outlet silently stopped firing -- a
    gate looping forever with nothing to rule on the loop.

    Driven through the real forms to a third revise, which is the only way
    to see it: every earlier round looks identical whether the guard works or
    not.
    """
    _drive_gate_through("g1", 3)
    capsys.readouterr()

    st = runmod.state("g1")
    assert st["current"]["form"] == "forms/IMPASSE.toml", (
        "the third route-decided rework minted another implement round "
        "instead of the outlet -- the panel-judged guard did not recognize "
        f"the review step: {[(s['id'], s.get('form')) for s in st['steps']]}")
    assert st["current"]["prefill"]["arrival"] == "rework-rounds"
    assert "untestable (3)" in st["current"]["prefill"]["findings"]
    assert runmod.rework_rounds(st, runmod.load_assembly("run-a-gate"), "work") == 2


def test_the_guard_reads_the_step_alone_and_never_the_impasse_ruling(workdir, capsys):
    """The other half of the same guard, and the reason it can key on the
    step's own `panel` and nothing else: an impasse ruling's own `rework`
    must carry the prefill that caused it and must never spend the count
    again. The ruling step is a single-conductor decision minted with no
    `panel` key at all, so the guard misses it by construction rather than by
    a segment comparison."""
    _drive_gate_through("g1", 3)
    st = runmod.state("g1")
    impasse = st["current"]
    assert not impasse.get("panel")
    capsys.readouterr()

    _fill(_response("g1"),
          'ruling = "rework"\nwhy = "round three rewrites the check, not the diff"\n')
    cli.main(["g1", "submit"])
    capsys.readouterr()

    st = runmod.state("g1")
    fresh = st["current"]
    assert fresh["form"] == "skills/implementer/forms/IMPLEMENT.toml"
    # The ruling's own prefill, carried forward -- not re-derived findings.
    # Stated as three claims rather than one equality: the equality also
    # pinned the conductor's `why` being dropped, which is #107's defect, and
    # a fresh round now arrives holding the ruling that created it, ahead of
    # the findings that caused the impasse.
    assert fresh["prefill"]["findings"].endswith(impasse["prefill"]["findings"])
    assert fresh["prefill"]["findings"].startswith("[conductor] ")
    assert ({k: v for k, v in fresh["prefill"].items() if k != "findings"}
            == {k: v for k, v in impasse["prefill"].items() if k != "findings"})
    # the ruling walked out of the wall rather than into it: the guard
    # returned no outlet for a step with no panel, so a third round was
    # minted where a further panel-judged rework would have hit the outlet
    # again -- ruling 2's latch, driven the rest of the way below
    assert runmod.rework_rounds(st, runmod.load_assembly("run-a-gate"), "work") == 3


def test_the_next_revise_after_an_impasse_rework_re_latches_immediately(workdir, capsys):
    """Ruling 2 (2026-09-02): the count latches. `rework_rounds` counts every
    mint since the last step-form mint with no exception for where the mint
    came from, so the impasse ruling's own `rework` -- which mints a fresh
    round without spending through `_panel_judged_rework`'s own guard --
    still leaves the count at 3, already past `impasse-after` (2). The very
    next revise on that fresh round therefore reaches the impasse form again
    immediately, with no fresh allowance of rounds: the engine already does
    this (`rework_rounds` is never reset by an impasse), so this drives it
    rather than building it."""
    _drive_gate_through("g1", 3)
    capsys.readouterr()
    _fill(_response("g1"),
          'ruling = "rework"\nwhy = "one more pass, on the same proof"\n')
    cli.main(["g1", "submit"])
    capsys.readouterr()

    st = runmod.state("g1")
    assert st["current"]["form"] == "skills/implementer/forms/IMPLEMENT.toml"
    assert runmod.rework_rounds(st, runmod.load_assembly("run-a-gate"), "work") == 3

    _fill_implement("g1", st["current"]["id"])
    cli.main(["g1", "submit"])
    _select_panel("g1")
    review = runmod.state("g1")["current"]["id"]
    panelist = f"g1.{review}.p1"
    cli.main(["open", "give-a-verdict", "--parent", "g1", "--step", f"{review}.p1"])
    _fill_review(panelist, "revise", "gap: still off by one (latch)")
    cli.main([panelist, "submit"])
    cli.main([panelist, "close"])
    _fill(_response("g1"), 'resolution = "rework"\n')
    cli.main(["g1", "submit"])
    capsys.readouterr()

    st = runmod.state("g1")
    assert st["current"]["form"] == "forms/IMPASSE.toml", (
        "the latch did not hold: a revise on the ruling's own fresh round "
        "minted another implement round instead of re-reaching the impasse "
        f"immediately: {[(s['id'], s.get('form')) for s in st['steps']]}")
    assert "gap: still off by one (latch)" in st["current"]["prefill"]["findings"]


# --- #73: amend add --transition, against a segment with a route-form ------
#
# This gate's own g4 taught `_mint_transition` to fall back to the segment's
# `route-form` when the transition declares no `form` of its own. `_amend_add`
# was not taught it, and `review` is exactly that segment: it declares no
# `[segment.transition]` table at all. The amended-in step came out with no
# form, no panel and no dispatches -- nothing an agent can fill, and nothing
# `cmd_submit` can load a form for, which wedges the run the way #71 does by
# a different route.


def test_an_amended_transition_is_fillable_on_a_route_form_segment(workdir, capsys):
    """The amend exists so a live run can catch up with a template that grew;
    a step it mints that no agent can fill is worse than a refusal."""
    _open_and_implement("g1")
    capsys.readouterr()

    cli.main(["g1", "amend", "add", "--transition", "--segment", "review",
              "--reason", "catching up with the template"])
    capsys.readouterr()

    minted = [s for s in runmod.state("g1")["steps"]
              if s["segment"] == "review" and s.get("source") == "amend"]
    assert minted, "the amend minted nothing into review"
    step = minted[-1]
    assert step.get("form") or step.get("panel") or step.get("dispatches"), (
        "amend add --transition minted a step with no form, panel or dispatch "
        "-- no agent can fill it and cmd_submit has no form to load")
    assert step["form"] == "forms/ROUTE.toml", (
        "the segment's own route-form is what a minted review step stands on")


def test_an_amended_transition_still_reads_a_declared_form(workdir, capsys):
    """The fallback must not shadow the ordinary case: a segment whose
    transition declares its own `form` keeps it."""
    _open_and_implement("g1")
    capsys.readouterr()

    cli.main(["g1", "amend", "add", "--transition", "--segment", "close",
              "--reason", "catching up with the template"])
    capsys.readouterr()

    asm = runmod.load_assembly("run-a-gate")
    seg = next(s for s in asm["segment"] if s["id"] == "close")
    declared = seg.get("transition", {}).get("form") or seg.get("route-form")
    minted = [s for s in runmod.state("g1")["steps"]
              if s["segment"] == "close" and s.get("source") == "amend"]
    assert minted[-1].get("form") == declared
