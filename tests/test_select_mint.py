"""The impasse guard that decides whether a `rework` was decided at a
panel-bearing transition.

`select` and its `panelists` mint are gone (ruling, 2026-09-25): `work`'s own
transition -- `review` -- is a declared two-voices step now, the same shape
as run-an-issue's plan seam, and its panel is the assembly's own three
readers on the opening round or the single `rework:` reader after
(`[rework-panel]`, engine/cli.py). `test_gate_declared_panel.py` covers that
declaration directly.

What is left here is the regression `_panel_judged_rework` guards against:
`_drive_gate_through` drives the real forms to a third revise, which is the
only way to see whether the guard still recognizes the review step once it
moved from a `select`-minted step in its own segment to `work`'s own
declared transition.
"""

from engine import cli, run as runmod
from test_nesting import _fill, _fill_implement, _response
from test_verdict_panels import _fill_review


def _drive_gate_through(gid, rounds):
    """`rounds` revise rounds on one diff, each driven through the real forms
    end to end -- implement, every panelist the round's own declared panel
    names, and the conductor's `rework` on the route form. Returns the
    gate's work id.

    Every panelist on the step is opened and closed: the opening round's
    three, or the single `rework:` reader on every round after
    (`len(step["panel"])`, not a pinned count) -- a round disposed of with
    one panelist still outstanding refuses at submit.

    Driven, not constructed: a unit call into `_panel_judged_rework` with a
    hand-built `seg` is exactly the shape that let a broken guard look fixed,
    because the caller gets to choose the segment the guard compares against.
    """
    cli.main(["open", "run-a-gate", "--id", gid])
    for n in range(1, rounds + 1):
        _fill_implement(gid, runmod.state(gid)["current"]["id"])
        cli.main([gid, "submit"])
        review = runmod.state(gid)["current"]["id"]
        panel = next(s for s in runmod.state(gid)["steps"]
                    if s["id"] == review).get("panel") or []
        for i in range(1, len(panel) + 1):
            panelist = f"{gid}.{review}.p{i}"
            cli.main(["open", "give-a-verdict", "--parent", gid, "--step", f"{review}.p{i}"])
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
    review = runmod.state("g1")["current"]["id"]
    panel = next(s for s in runmod.state("g1")["steps"] if s["id"] == review).get("panel") or []
    for i in range(1, len(panel) + 1):
        panelist = f"g1.{review}.p{i}"
        cli.main(["open", "give-a-verdict", "--parent", "g1", "--step", f"{review}.p{i}"])
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


def test_an_amended_transition_still_reads_a_declared_form(workdir, capsys):
    """`amend add --transition` mints a step no agent can fill (no form, no
    panel, no dispatch) unless it carries the target segment's own declared
    transition. Driven against `close`, whose transition names a plain
    `form` with no panel at all."""
    cli.main(["open", "run-a-gate", "--id", "g1"])
    _fill_implement("g1", "work-1")
    cli.main(["g1", "submit"])
    capsys.readouterr()

    cli.main(["g1", "amend", "add", "--transition", "--segment", "close",
              "--reason", "catching up with the template"])
    capsys.readouterr()

    asm = runmod.load_assembly("run-a-gate")
    seg = next(s for s in asm["segment"] if s["id"] == "close")
    declared = seg.get("transition", {}).get("form")
    minted = [s for s in runmod.state("g1")["steps"]
              if s["segment"] == "close" and s.get("source") == "amend"]
    assert minted[-1].get("form") == declared
