"""An impasse ruling reaches the round it creates.

`forms/IMPASSE.toml` is the one form written for a conductor to rule on a
pattern rather than a round -- "Rule on the loop, not on the findings" -- and
its `ruling` note makes `rework` legitimate only where the conductor can
"name what that round changes that the last three did not". `why` is where
that naming goes. Nothing read it: the impasse step is minted with no panel,
so `_panel_judged_rework`'s guard returned nothing and the fresh round fell
back to the impasse step's own prefill -- the findings that produced the
loop. The round created to break the pattern arrived holding exactly what the
round before it held (#107, met three times on issue80's run and again on
issue96's).

The `up` path on the same form already carried it, which is what makes this a
defect rather than intent: see `test_pause_gate.py`'s own
`test_up_from_impasse_carries_why_into_the_ask`.
"""

from engine import cli, run as runmod

from test_nesting import (
    _dispatch_and_close_plan,
    _dispatch_plan_critic,
    _drive_plan_to_impasse,
    _fill_consolidate,
    _fill_open,
    _fill_plan_rework,
    _response,
    _work_the_board,
)

WHY = "the proof shape cannot carry this commitment; replace the AST reader"
FINDINGS = "gap: wrong artifact entirely"


def _at_the_plan_impasse(wid="issue17"):
    """A real run-an-issue driven to the plan segment's impasse form, every
    round having landed on the same objection."""
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    _dispatch_and_close_plan(wid)
    _drive_plan_to_impasse(wid, findings=FINDINGS)
    st = runmod.state(wid)
    assert st["current"]["form"] == "forms/IMPASSE.toml", (
        f"not standing on the impasse form: {st['current'].get('form')}")
    return wid


def _rule(wid, ruling="rework", why=WHY):
    cli.main([wid])  # materialize the ruling form
    _response(wid).write_text('ruling = "%s"\nwhy = """%s"""\n' % (ruling, why))
    cli.main([wid, "submit"])


# -- 1. the ruling reaches the round it mints -------------------------------


def test_an_impasse_rework_carries_the_rulings_why_into_the_round(workdir, capsys):
    wid = _at_the_plan_impasse()
    capsys.readouterr()
    _rule(wid)
    capsys.readouterr()

    prefill = runmod.state(wid)["current"]["prefill"]["findings"]
    assert WHY in prefill, (
        "the ruling that created this round never reached it -- the round is "
        f"holding only what the round before it held:\n{prefill}")
    assert "[conductor]" in prefill, (
        "the ruling arrived unattributed; a round cannot tell the conductor's "
        f"own order from a panelist's finding:\n{prefill}")


def test_the_findings_that_caused_the_impasse_are_still_carried(workdir, capsys):
    """The ruling goes ahead of them, never instead of them: a conductor
    ruling on the loop is not withdrawing what the panel found."""
    wid = _at_the_plan_impasse()
    _rule(wid)
    capsys.readouterr()

    prefill = runmod.state(wid)["current"]["prefill"]["findings"]
    assert FINDINGS in prefill, prefill
    assert prefill.index(WHY) < prefill.index(FINDINGS), (
        f"the ruling should lead the round's orders:\n{prefill}")


# -- 2. what it must not change ---------------------------------------------


def test_a_ruling_with_no_real_why_carries_what_it_always_did(workdir, capsys):
    """A status word is no ruling. The plain carry-what-caused-it behaviour
    is what this falls back to, unchanged."""
    wid = _at_the_plan_impasse()
    _rule(wid, why="waived: none")
    capsys.readouterr()

    prefill = runmod.state(wid)["current"]["prefill"]["findings"]
    assert FINDINGS in prefill and "[conductor]" not in prefill, prefill


def test_the_ruling_still_does_not_spend_the_count(workdir, capsys):
    """The outlet stays a way out rather than a wall: an impasse `rework`
    mints its round without spending through the panel-judged path, so the
    next revise reaches the impasse form again immediately."""
    wid = _at_the_plan_impasse()
    before = runmod.rework_rounds(runmod.state(wid),
                                  runmod.load_assembly("run-an-issue"), "plan")
    _rule(wid)
    capsys.readouterr()

    st = runmod.state(wid)
    after = runmod.rework_rounds(st, runmod.load_assembly("run-an-issue"), "plan")
    assert after == before + 1, (
        f"the ruling's own round changed the count's shape: {before} -> {after}")
    assert st["current"].get("dispatches") == "cut-a-gate", (
        "the ruling minted something other than a fresh planner round: "
        f"{st['current'].get('form')}")
