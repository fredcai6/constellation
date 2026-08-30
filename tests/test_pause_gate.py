"""`up` pauses a gate rather than ending its run (commitment 9), scoped to
run-a-gate's own two `up` rows: `work`'s own impasse ruling and `review`'s
own route form. An ask lands in the parent as a step it already stands on --
reordered ahead of the still-live dispatch/adjudicate pair that dispatched
this gate, never amend-closed -- and a marker stands in the child until the
parent's own answer resumes it as a fresh round.

Drives real `run-a-gate` end to end, the parent seeded directly in the shape
`_mint_gates` itself produces -- the same shortcut test_verdict_panels.py's
own single-gate scenarios already take, so this exercises the gate tier's
real mechanism without also driving the issue tier's understand/plan
machinery, which this gate does not touch.
"""

import pathlib
import shutil

import pytest

from engine import cli, journal, run as runmod
from gitremote import init_checkout

from test_verdict_panels import _fill_implement, _fill_review, _fill_route, _open_panelist, _select
from test_verdict_route import _route_with_calls

REPO = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONSTELLATION_SESSION", "test-session")
    (tmp_path / "constellation.toml").write_text((REPO / "constellation.toml").read_text())
    init_checkout(tmp_path)
    return tmp_path


def _fill(path, text):
    pathlib.Path(path).write_text(text)


def _seed_two_gates(pwid):
    """A parent holding two gate dispatch/adjudicate pairs -- `g1`, the one
    this file pauses, and `g2`, the sibling every assertion here holds
    untouched."""
    journal.append(pwid, "run", title="t", assembly="run-an-issue")
    for gid, purpose in (("g1", "fix the parser"), ("g2", "fix the linter")):
        child = f"{pwid}.{gid}"
        journal.append(pwid, "step", id=gid, segment="execute", dispatches="run-a-gate",
                       prefill={"purpose": purpose, "scope": "src/ only", "proof": "true"},
                       child=child, anchor=False, terminal=False, source="mint")
        journal.append(pwid, "step", id=f"{gid}-adjudicate", segment="execute",
                       form="forms/GATE_TRANSITION.toml", filler="conductor", child=child,
                       anchor=False, terminal=False, validates="", source="mint")


def _drive_to_up(pwid, gid):
    """One ordinary implement/select/review round, ruled `up` at route --
    the conductor's own word for "the spec, not the diff, is wrong"."""
    child = f"{pwid}.{gid}"
    cli.main(["open", "run-a-gate", "--parent", pwid, "--step", gid])
    _fill_implement(child)
    cli.main([child, "submit"])
    review = _select(child)
    panelist = _open_panelist(child, review)
    _fill_review(panelist, "pass")
    cli.main([panelist, "submit"])
    cli.main([panelist, "close"])
    _fill_route(child, "up")
    cli.main([child, "submit"])
    return child


def _drive_to_close(child):
    """The resumed round, driven all the way to a real close -- the same
    implement/select/review/route/close shape any ordinary gate takes."""
    _fill_implement(child)
    cli.main([child, "submit"])
    review = _select(child)
    panelist = _open_panelist(child, review)
    _fill_review(panelist, "pass")
    cli.main([panelist, "submit"])
    cli.main([panelist, "close"])
    _fill_route(child, "close")
    cli.main([child, "submit"])
    _fill(journal.location(child) / "GATE_CLOSE.toml", 'residue = "waived: none"\n')
    cli.main([child, "submit"])
    cli.main([child, "close"])


def test_up_stands_the_ask_at_the_parent_and_resumes_to_a_real_close(workdir, capsys):
    _seed_two_gates("issue1")
    child = _drive_to_up("issue1", "g1")
    capsys.readouterr()

    # -- right after the pause fires: the parent's own pair for this gate is
    # still not-done and still present, and the ask is what it stands on --
    pst = runmod.state("issue1")
    assert "g1" not in pst["done"] and "g1-adjudicate" not in pst["done"]
    assert any(s["id"] == "g1" for s in pst["steps"])
    assert any(s["id"] == "g1-adjudicate" for s in pst["steps"])
    ask = pst["current"]
    assert ask["form"] == "skills/gate-conductor/forms/ASK.toml"
    assert ask["resumes"] == child
    assert ask["prefill"]["gate"] == child

    # the sibling pair is exactly as it was -- pause touches nothing it has
    # no business touching
    assert "g2" not in pst["done"] and "g2-adjudicate" not in pst["done"]

    # -- the child itself reads paused, not awaiting close ------------------
    cst = runmod.state(child)
    assert cst["open"] and not cst["awaiting_close"]
    assert runmod.paused(cst["current"])

    # (1) submit while paused refuses rather than raising -- `_current_form`'s
    # fallthrough is `step["form"]`, bracket access, and the marker has none
    with pytest.raises(SystemExit) as exc:
        cli.main([child, "submit"])
    assert "paused" in str(exc.value)

    # (2) close while paused offers neither of cmd_close's two wrong escapes
    with pytest.raises(SystemExit) as exc:
        cli.main([child, "close"])
    msg = str(exc.value)
    assert "fill its form and submit it" not in msg
    assert "open its child" not in msg

    # -- the parent answers, and the answer resumes the child ---------------
    answer = "narrow the scope to src/parser.c and drop the rest"
    _fill(journal.location("issue1") / "ASK.toml", 'answer = "%s"\n' % answer)
    cli.main(["issue1", "submit"])
    capsys.readouterr()

    cst = runmod.state(child)
    assert not runmod.paused(cst["current"])
    assert cst["current"]["form"] == "skills/implementer/forms/IMPLEMENT.toml"
    assert cst["current"]["prefill"] == {"answer": answer}

    # (3) driven all the way to an actual close: the parent's pair is still
    # the one the return lands on, and the gate still adjudicates -- the
    # exact defect a quietly-restored retirement would have caused
    _drive_to_close(child)
    capsys.readouterr()

    pst = runmod.state("issue1")
    # the return lands on the dispatch step itself (`state()["parent_step"]`,
    # stamped at open) -- the same site an ordinary, never-paused gate's
    # return always lands on. What pausing had to not break is that this
    # step is still the live one it was before the pause: not amend-closed,
    # and its adjudication still reachable right behind it.
    assert "g1" in pst["done"], "the return did not land on the live dispatch step"
    assert pst["returns_by_child"].get(child), "no return reached the parent"
    assert pst["current"]["id"] == "g1-adjudicate", "the adjudication step is not reachable"

    _fill(journal.location("issue1") / "GATE_TRANSITION.toml", '''
findings = "the narrowed scope landed cleanly"
plan-holds = "advance"
''')
    cli.main(["issue1", "submit"])
    capsys.readouterr()

    pst = runmod.state("issue1")
    assert "g1-adjudicate" in pst["done"], "the gate never adjudicated"

    # (5) the sibling pair, never touched by any of the above
    assert "g2" not in pst["done"] and "g2-adjudicate" not in pst["done"]
    sib = next(s for s in pst["steps"] if s["id"] == "g2")
    assert sib["prefill"]["purpose"] == "fix the linter"


def _drive_to_impasse(pwid, gid):
    """Three implement/review rounds, each revised and reworked, followed by
    a fourth revise that reaches `work`'s own `impasse-after` threshold
    (assemblies/run-a-gate/ASSEMBLY.toml, `impasse-after = 3`) and mints
    IMPASSE.toml in place of a fifth step-form round -- the same shape
    `test_rework.py`'s own `_drive_gate_to_impasse` drives, adapted to the
    `_seed_two_gates` parent instead of a full run-an-issue mint."""
    child = f"{pwid}.{gid}"
    cli.main(["open", "run-a-gate", "--parent", pwid, "--step", gid])
    for n in (1, 2, 3, 4):
        _fill_implement(child)
        cli.main([child, "submit"])
        review = _select(child)
        panelist = _open_panelist(child, review)
        _fill_review(panelist, "revise", findings=f"gap: untestable ({n})")
        cli.main([panelist, "submit"])
        cli.main([panelist, "close"])
        _fill_route(child, "rework")
        cli.main([child, "submit"])
    return child


def test_up_from_impasse_carries_why_into_the_ask(workdir, capsys):
    """scope's other `up` row -- `work`'s own impasse ruling, reached once
    review has sent the same diff back `impasse-after` times, never through
    `review`'s route form -- maps IMPASSE.toml's own `why` field into the
    ask's `findings` key when `_pause_gate` finds no `calls` table
    (cli.py:1204-1205). Nothing existing drives this half: every
    `_drive_gate_to_impasse` caller in test_rework.py rules advance, rework
    or filler, never `up`."""
    _seed_two_gates("issue4")
    child = _drive_to_impasse("issue4", "g1")
    capsys.readouterr()

    why = "the spec asks for something no proof can check"
    _fill(journal.location(child) / "IMPASSE.toml",
          'ruling = "up"\nwhy = "%s"\n' % why)
    cli.main([child, "submit"])
    capsys.readouterr()

    pst = runmod.state("issue4")
    ask = pst["current"]
    assert ask["form"] == "skills/gate-conductor/forms/ASK.toml"
    assert ask["resumes"] == child
    assert ask["prefill"].get("findings") == why


def test_up_with_calls_carries_findings_into_the_ask(workdir, capsys):
    """scope names the review's own `calls` table (or `why`'s fallback) as
    the content `_pause_gate` maps into the ask's own `findings` key
    (cli.py:1199-1205) -- commitment 9's own text. `_drive_to_up` only ever
    routes `up` through `_fill_route`, which fills no `calls` table at all,
    so nothing bound proves this mapping survives; the ask that scenario
    mints carries no `findings` key whatsoever. Driven here instead through
    `test_verdict_route.py`'s own `_route_with_calls` helper -- already in
    the tree, unused until now -- with one `[[calls]]` block, so the ask
    landing at the parent has something to carry."""
    _seed_two_gates("issue2")
    child = "issue2.g1"
    cli.main(["open", "run-a-gate", "--parent", "issue2", "--step", "g1"])
    _fill_implement(child)
    cli.main([child, "submit"])
    review = _select(child)
    panelist = _open_panelist(child, review)
    _fill_review(panelist, "pass")
    cli.main([panelist, "submit"])
    cli.main([panelist, "close"])
    _route_with_calls(child, "up", ("gap: the parser drops the trailing token", "blocking"))
    cli.main([child, "submit"])
    capsys.readouterr()

    pst = runmod.state("issue2")
    ask = pst["current"]
    assert ask["form"] == "skills/gate-conductor/forms/ASK.toml"
    assert ask["resumes"] == child
    assert "gap: the parser drops the trailing token" in ask["prefill"].get("findings", "")


def test_resuming_a_child_whose_journal_is_gone_notes_rather_than_fabricates_one(
        workdir, capsys):
    """(4) `journal.append`'s own `mkdir(parents=True, exist_ok=True)`
    (journal.py:119) means an unguarded resume would fabricate a phantom
    journal for a child swept to the archive or removed by hand. The guard
    is `journal.exists` checked before anything is written into the child --
    proved here by removing the child's own journal outright."""
    _seed_two_gates("issue3")
    child = _drive_to_up("issue3", "g1")
    capsys.readouterr()
    shutil.rmtree(journal.location(child))
    assert not journal.exists(child)

    _fill(journal.location("issue3") / "ASK.toml", 'answer = "too late -- already gone"\n')
    cli.main(["issue3", "submit"])  # must not raise, and must not fabricate a journal
    capsys.readouterr()

    assert not journal.exists(child), "a phantom journal was fabricated for a gone child"
    notes = [e for e in journal.read("issue3") if e.get("kind") == "note"]
    assert any(child in n.get("text", "") for n in notes), "no note recorded the missing child"
