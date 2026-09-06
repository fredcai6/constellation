"""A submitted response form is moved aside, so the next round opens blank.

The live response path is named for the *form* (`_response_path`:
`pathlib.Path(step["form"]).stem`), not for the round that fills it, and
`cmd_status` materializes only `if not dest.exists()`. Round two at a seam
therefore used to open round one's filled form -- its `resolution`, its
`calls`, all of it -- and a conductor that edited the fields it thought of
carried the rest forward as this round's record (#118). Archiving on submit
makes the existing guard correct rather than working around it: the file is
gone from the live path the moment it stops being the answer, and the filled
copy stays on disk beside it under an ordinal.

Both seams' impasse steps declare the same form, so this is also what keeps
a consolidate ruling out of the plan seam's `IMPASSE.toml`.
"""

import pytest

from engine import cli, journal, run as runmod

from test_nesting import (
    _dispatch_and_close_plan,
    _dispatch_plan_critic,
    _fill_consolidate,
    _fill_open,
    _work_the_board,
)
from test_rework import _dispatch_rework_round, _drive_to_revise


def _live(wid, name):
    return journal.location(wid) / name


# -- 1. the live path is emptied, the answer is kept -------------------------


def test_a_submit_moves_its_response_form_aside(workdir, capsys):
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    _fill_open("issue17")
    live = _live("issue17", "OPEN.toml")
    assert live.exists()

    cli.main(["issue17", "submit"])
    capsys.readouterr()

    assert not live.exists(), (
        "the submitted form is still at the live path -- the next round at "
        "this seam would open it already filled")
    kept = _live("issue17", "OPEN.1.toml")
    assert kept.exists(), "the filled answer was destroyed rather than archived"


def test_each_submit_takes_the_next_ordinal(workdir, capsys):
    """Two rounds at one seam leave two archived files, not one overwritten
    one -- the ordinal is the lowest unused, so nothing already on disk is
    ever the rename's target."""
    wid = _drive_to_revise()
    _dispatch_rework_round(wid)
    _dispatch_plan_critic(wid, verdict="pass")
    capsys.readouterr()

    assert _live(wid, "PLAN_TO_EXECUTE.1.toml").exists()


# -- 2. the round-two room, which is what #118 measured ----------------------


def test_round_two_at_a_seam_opens_a_blank_route_form(workdir, capsys):
    """#118's own evidence, as a test: round one disposed of its round with
    `resolution = "rework"`; the room round two renders must not be holding
    that word."""
    wid = _drive_to_revise()
    _dispatch_rework_round(wid)
    _dispatch_plan_critic(wid, verdict="pass")
    capsys.readouterr()

    st = runmod.state(wid)
    assert st["current"]["form"] == "forms/PLAN_TO_EXECUTE.toml", (
        "this test no longer stands on the route form: "
        f"{st['current'].get('form')}")

    cli.main([wid])  # the room materializes it
    capsys.readouterr()
    body = _live(wid, "PLAN_TO_EXECUTE.toml").read_text()
    assert 'resolution = "rework"' not in body, (
        "round two's room opened round one's filled route form:\n" + body)


# -- 3. the two seams that share one impasse form ---------------------------


def test_the_shared_impasse_form_does_not_cross_seams(workdir, capsys):
    """`understand` and `plan` both declare `forms/IMPASSE.toml`, so they
    share a live path. A consolidate ruling left behind there is what the
    plan seam's own impasse used to open."""
    asm = runmod.load_assembly("run-an-issue")
    forms_declared = {s["id"]: s.get("impasse-form", "")
                      for s in asm["segment"] if s.get("impasse-form")}
    assert len(set(forms_declared.values())) == 1 and len(forms_declared) > 1, (
        "the seams no longer share one impasse form -- this test's premise "
        f"is gone: {forms_declared}")

    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    _fill_open("issue17")
    cli.main(["issue17", "submit"])
    _work_the_board("issue17")
    _fill_consolidate("issue17")
    cli.main(["issue17", "submit"])
    capsys.readouterr()

    # whatever the understand seam left behind, it is not at the live path
    assert not _live("issue17", "CONSOLIDATE.toml").exists()
