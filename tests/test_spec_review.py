"""Understand holds a board and a step-form both: the spec-writer's own
round, ordered between the board and the segment's transition, judged by a
cold critic panel on that same transition -- the two-voices shape
plan-to-execute already uses, one segment earlier.

Drives the real `run-an-issue` assembly, not a synthetic fixture -- the
mint order, the panel's prefill, and the transition's three routes (back to
the board, back to the writer, or forward) are all real engine behavior,
not something a hand-built journal could stand in for without also proving
the assembly wires it the way it claims to. test_two_voices.py is the check
that plan-to-execute's own shape is unchanged by any of this; this file is
understand's own.
"""

import pathlib

import pytest

from engine import cli, journal, run as runmod


def _fill(path, text):
    pathlib.Path(path).write_text(text)


def _fill_open(wid):
    issue = f".agent-work/{wid}/issue.md"
    _fill(issue, "The parser drops the last record of a file with no "
                 "trailing newline.\n")
    _fill(f".agent-work/{wid}/OPEN.toml", f'''
issue = "{issue}"

authority = """
Principal: Tommy, live. I own driving this to a merged fix; gaps go to him."""

[[questions]]
question = "Which inputs drop the last record?"
type = "fact"
''')


def _work_the_board(wid):
    b = pathlib.Path(f".agent-work/{wid}/UNDERSTAND.toml")
    b.write_text(b.read_text().replace(
        'status = "open"', 'status = "answered"\nanswer = "EOF with no trailing newline."'))


def _fill_spec(wid):
    loc = pathlib.Path(f".agent-work/{wid}")
    (loc / "spec.md").write_text(
        "1. Fix the parser to handle EOF with no trailing newline.\n")
    _fill(loc / "SPEC.toml", 'spec = "%s/spec.md"\n' % loc)


def _fill_consolidate(wid):
    _fill(f".agent-work/{wid}/CONSOLIDATE.toml", '''
spec = ".agent-work/%s/spec.md"
key-terms = "waived: none"
settle = "waived: none"
''' % wid)


def _fill_critic(wid, verdict, findings="none: waived: clean"):
    _fill(journal.location(wid) / "CRITIC.toml", '''
findings = "%s"
vocabulary = "waived: consistent"
verdict = "%s"
''' % (findings, verdict))


def _dispatch_panel(pwid, step_id, verdict="pass", findings="none: waived: clean"):
    """Every panelist the transition's own step declares, not just the
    first -- the step completes on the last verdict."""
    panel = next(s for s in runmod.state(pwid)["steps"] if s["id"] == step_id)["panel"]
    for n in range(1, len(panel) + 1):
        tag = f"{step_id}.p{n}"
        cli.main(["open", "give-a-verdict", "--parent", pwid, "--step", tag])
        panelist = f"{pwid}.{tag}"
        _fill_critic(panelist, verdict, findings)
        cli.main([panelist, "submit"])
        cli.main([panelist, "close"])


def _open_to_spec_writer(wid="issue17"):
    """Open a real run-an-issue and drive it to the spec-writer's own step,
    the board answered and ready to crystallize."""
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    return wid


# -- 1. a board-and-step-form segment mints both, in order -------------------


def test_the_understand_segment_mints_its_board_seed_and_its_step_form_in_order(
        workdir, capsys):
    """`skeleton()` used to mint an interior step only for `interior ==
    "steps"`; a board segment got its transition alone, no matter what
    `step-form` it declared. `open`'s own plan field seeds the board
    separately (`_mint`, engine/cli.py) -- this proves the two together:
    the board exists once open is submitted, and the spec-writer's own
    step sits ahead of the transition, never after it."""
    wid = _open_to_spec_writer()
    capsys.readouterr()

    st = runmod.state(wid)
    ids = [s["id"] for s in st["steps"]]
    assert ids.index("understand-1") < ids.index("understand")
    assert ids[:3] == ["open", "understand-1", "understand"]

    spec_step = next(s for s in st["steps"] if s["id"] == "understand-1")
    assert spec_step["form"] == "skills/spec-writer/forms/SPEC.toml"
    assert spec_step["filler"] == "spec-writer"
    assert spec_step["segment"] == "understand"
    assert "dispatches" not in spec_step   # filled in place, not a child run

    assert pathlib.Path(f".agent-work/{wid}/UNDERSTAND.toml").exists()
    assert st["current"]["id"] == "understand-1"


def test_the_board_renders_beside_the_spec_writer_step_not_only_the_transition(
        workdir, capsys):
    """The render draws whatever board a step's own segment holds, keyed by
    segment id -- proven directly, since a board that only appeared once the
    spec-writer's round was already over would leave the writer with no way
    to read what it is meant to crystallize."""
    wid = _open_to_spec_writer()
    capsys.readouterr()

    cli.main([wid])
    out = capsys.readouterr().out
    assert "UNDERSTAND.toml" in out
    assert "SPEC.toml" in out   # the current step's own response form


# -- 2. the spec-writer's returns reach the critic panel ---------------------


def test_the_spec_writers_returns_reach_the_critic_panel(workdir, capsys):
    """The panel is the segment's own transition, so its prefill comes from
    `_open_child`'s ordinary rule -- the segment's most recent non-panel
    step -- with no `carries` needed: this is the same segment, not a
    boundary consolidate exists to cross."""
    wid = _open_to_spec_writer()
    _fill_spec(wid)
    cli.main([wid, "submit"])
    capsys.readouterr()

    st = runmod.state(wid)
    assert st["current"]["id"] == "understand"   # the transition, panel outstanding

    cli.main(["open", "give-a-verdict", "--parent", wid, "--step", "understand.p1"])
    capsys.readouterr()
    prefill = runmod.state(f"{wid}.understand.p1")["prefill"]
    assert prefill["spec"] == f".agent-work/{wid}/spec.md"
    assert prefill["criteria"].startswith("standalone")


# -- 3. the transition's three routes -----------------------------------------


def test_revise_routes_back_to_the_writer_with_findings_and_a_fresh_panel(workdir, capsys):
    wid = _open_to_spec_writer()
    _fill_spec(wid)
    cli.main([wid, "submit"])
    capsys.readouterr()

    _dispatch_panel(wid, "understand", verdict="revise",
                    findings="gap: commitment 1 is not numbered")
    capsys.readouterr()

    st = runmod.state(wid)
    assert "understand" in st["done"]        # the transition released, like any panel step

    fresh_writer = next(s for s in st["steps"]
                        if s["segment"] == "understand" and s.get("source") == "mint"
                        and s["form"] == "skills/spec-writer/forms/SPEC.toml")
    assert "commitment 1 is not numbered" in fresh_writer["prefill"]["findings"]
    assert "[p1]" in fresh_writer["prefill"]["findings"]     # attributed

    fresh_panel = next(s for s in st["steps"]
                       if s.get("panel") and s["segment"] == "understand"
                       and s["id"] != "understand")
    original = next(s for s in st["steps"] if s["id"] == "understand")
    assert fresh_panel["panel"] == original["panel"]
    assert st["current"]["id"] == fresh_writer["id"]   # the writer resumes, not the mint form


def test_pass_routes_forward_once_consolidate_is_filled(workdir, capsys):
    wid = _open_to_spec_writer()
    _fill_spec(wid)
    cli.main([wid, "submit"])
    _dispatch_panel(wid, "understand", verdict="pass")
    capsys.readouterr()

    st = runmod.state(wid)
    assert st["current"]["id"] == "understand"      # resolved, waiting on its own form now
    assert not runmod.panel_outstanding(st, st["current"])

    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    capsys.readouterr()

    st = runmod.state(wid)
    assert "understand" in st["done"]
    assert st["current"]["id"] == "plan-1"
    assert st["prefill"]["spec"] == f".agent-work/{wid}/spec.md"   # carried onto the run


def test_an_unresolved_board_routes_back_to_the_board_even_after_the_spec_passes(
        workdir, capsys):
    """The board is the last check, not the first: a spec can pass critique
    while a row still sits open, and consolidate is what refuses to let the
    segment close around it."""
    wid = _open_to_spec_writer()
    _fill_spec(wid)
    cli.main([wid, "submit"])
    _dispatch_panel(wid, "understand", verdict="pass")
    capsys.readouterr()

    board = pathlib.Path(f".agent-work/{wid}/UNDERSTAND.toml")
    board.write_text(board.read_text().replace(
        'status = "answered"\nanswer = "EOF with no trailing newline."', 'status = "open"'))
    _fill_consolidate(wid)

    with pytest.raises(SystemExit) as e:
        cli.main([wid, "submit"])
    msg = str(e.value)
    assert "q1" in msg
    assert "deferred:" in msg
    assert runmod.state(wid)["current"]["id"] == "understand"   # sent back, not advanced
