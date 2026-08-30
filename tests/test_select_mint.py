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

import pathlib
import tomllib

import pytest

from engine import cli, forms, journal, run as runmod
from gitremote import init_checkout
from test_nesting import _fill, _fill_implement, _select_panel
from test_verdict_panels import _fill_review

REPO = pathlib.Path(__file__).resolve().parent.parent
GATE = REPO / "assemblies" / "run-a-gate" / "ASSEMBLY.toml"


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONSTELLATION_SESSION", "test-session")
    (tmp_path / "constellation.toml").write_text((REPO / "constellation.toml").read_text())
    init_checkout(tmp_path)
    return tmp_path


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

    _fill(journal.location("g1") / "SELECT.toml", '''
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

    _fill(journal.location("g1") / "SELECT.toml", '''
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
        _fill(journal.location(gid) / "ROUTE.toml", 'resolution = "rework"\n')
        cli.main([gid, "submit"])
    return gid


def test_a_fourth_route_decided_rework_still_reaches_the_impasse_form(workdir, capsys):
    """The bug this gate inherited and fixes. `_panel_judged_rework` decides
    whether a rework was decided at a panel-bearing transition -- if it was,
    the fresh round carries the panel's findings and spends the segment's
    `impasse-after` count, and the fourth one gets the outlet instead of a
    fourth round.

    Its guard used to compare the deciding step's own segment against the
    rework verb's *target* segment, and its form against that segment's
    statically declared transition form. Both halves were trivially true
    while review and work were one segment and the verb was bare. Both fail
    the moment review is its own segment (`does = "rework work"` names a
    target, and review's transition declares no static form at all), so the
    guard returned `(None, "")` for the exact step it exists to recognize,
    the count never advanced, and the three-round outlet silently stopped
    firing -- a gate looping forever with nothing to rule on the loop.

    Driven through the real forms to a fourth revise, which is the only way
    to see it: every earlier round looks identical whether the guard works or
    not.
    """
    _drive_gate_through("g1", 4)
    capsys.readouterr()

    st = runmod.state("g1")
    assert st["current"]["form"] == "forms/IMPASSE.toml", (
        "the fourth route-decided rework minted another implement round "
        "instead of the outlet -- the panel-judged guard did not recognize "
        f"the review step: {[(s['id'], s.get('form')) for s in st['steps']]}")
    assert st["current"]["prefill"]["arrival"] == "rework-rounds"
    assert "untestable (4)" in st["current"]["prefill"]["findings"]
    assert runmod.rework_rounds(st, runmod.load_assembly("run-a-gate"), "work") == 3


def test_the_guard_reads_the_step_alone_and_never_the_impasse_ruling(workdir, capsys):
    """The other half of the same guard, and the reason it can key on the
    step's own `panel` and nothing else: an impasse ruling's own `rework`
    must carry the prefill that caused it and must never spend the count
    again. The ruling step is a single-conductor decision minted with no
    `panel` key at all, so the guard misses it by construction rather than by
    a segment comparison."""
    _drive_gate_through("g1", 4)
    st = runmod.state("g1")
    impasse = st["current"]
    assert not impasse.get("panel")
    capsys.readouterr()

    _fill(journal.location("g1") / "IMPASSE.toml",
          'ruling = "rework"\nwhy = "round four rewrites the check, not the diff"\n')
    cli.main(["g1", "submit"])
    capsys.readouterr()

    st = runmod.state("g1")
    fresh = st["current"]
    assert fresh["form"] == "skills/implementer/forms/IMPLEMENT.toml"
    # the ruling's own prefill, carried forward -- not re-derived findings
    assert fresh["prefill"] == impasse["prefill"]
    # the ruling walked out of the wall rather than into it: the guard
    # returned no outlet for a step with no panel, so a fourth round was
    # minted where a fifth panel-judged rework would have hit the outlet again
    assert runmod.rework_rounds(st, runmod.load_assembly("run-a-gate"), "work") == 4
