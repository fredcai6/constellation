"""The plan step's artifact is the next gate spec (#27).

Before this, gate specs were authored at PLAN_TO_EXECUTE.toml, after the
critic panel had already released -- so no critic had ever read one, and
`#7` shipped four unrunnable specs as a result. Now the plan round itself
cuts the gate (`purpose`, `scope`, `proof`, optional `model`/`direction`)
plus a `horizon` sketch of what plausibly follows; the critics read the
whole round, and plan-to-execute only projects the gate half forward --
never a second authoring pass. This drives the real `run-an-issue` assembly
end to end, the way test_nesting.py does, and pins the three properties the
gate spec's own scope named: one gate per pass, not k; the horizon stays
behind; and a real artifact path is actually measured.
"""

import pathlib

import pytest

from engine import cli, journal, run as runmod
from gitremote import init_checkout
from test_nesting import (
    _dispatch_and_close_plan,
    _dispatch_plan_critic,
    _fill,
    _fill_consolidate,
    _fill_open,
    _fill_plan,
    _fill_plan_to_execute,
    _work_the_board,
)

REPO = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONSTELLATION_SESSION", "test-session")
    (tmp_path / "constellation.toml").write_text((REPO / "constellation.toml").read_text())
    init_checkout(tmp_path)
    return tmp_path


def _drive_to_plan_to_execute(wid="issue17", fill_fn=None):
    """Open a real run-an-issue and drive it through one real plan round and
    a real critic pass, right up to the plan-to-execute form -- the same
    moment `test_nesting._mint_first_gate` stops one step later, at
    submit."""
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    _dispatch_and_close_plan(wid, fill_fn=fill_fn)
    _dispatch_plan_critic(wid)
    return wid


# -- 1. one gate minted per pass, not k ---------------------------------------


def test_one_gate_minted_per_pass_not_k(workdir, capsys):
    """PLAN_TO_EXECUTE.toml has nothing left to author -- no `[[gates]]`
    block a conductor could pad with several blocks in one pass. Submitting
    it, once the round the panel judged has a gate spec on it, mints exactly
    one dispatch/adjudicate pair -- never more, however many the plan's own
    horizon sketches."""
    wid = _drive_to_plan_to_execute()
    capsys.readouterr()

    _fill_plan_to_execute(wid)  # only `plan` -- there is no gates field to fill
    cli.main([wid, "submit"])
    capsys.readouterr()

    st = runmod.state(wid)
    gates = [s for s in st["steps"] if s.get("dispatches") == "run-a-gate"]
    assert [g["id"] for g in gates] == ["g1"]

    adjudications = [s for s in st["steps"] if s.get("form") == "forms/GATE_TRANSITION.toml"]
    assert [a["id"] for a in adjudications] == ["g1-adjudicate"]


# -- 2. the child's prefill carries the gate fields, and not the horizon -----


def test_childs_prefill_carries_gate_fields_and_not_horizon(workdir, capsys):
    """Ruling 3's contract, verbatim: purpose, scope, proof and the two
    optional overrides ride into the dispatched gate; `plan`, `horizon` and
    `key-terms` -- the plan round's own record, and the sketch of what comes
    after -- stay behind. 'The critics can see what the whole future plan
    is, but the actual gate focuses on its piece alone.'"""
    wid = _drive_to_plan_to_execute(fill_fn=lambda w: _fill_plan(
        w, purpose="fix the parser to handle EOF without a trailing newline",
        scope="src/parser.c only", proof="true", model="light",
        direction="whether the fix generalizes to CRLF too"))
    capsys.readouterr()

    _fill_plan_to_execute(wid)
    cli.main([wid, "submit"])
    capsys.readouterr()

    g1 = next(s for s in runmod.state(wid)["steps"] if s["id"] == "g1")
    prefill = g1["prefill"]
    assert prefill["purpose"] == "fix the parser to handle EOF without a trailing newline"
    assert prefill["scope"] == "src/parser.c only"
    assert prefill["proof"] == "true"
    assert prefill["model"] == "light"
    assert prefill["direction"] == "whether the fix generalizes to CRLF too"
    assert "horizon" not in prefill
    assert "plan" not in prefill
    assert "key-terms" not in prefill

    # the dispatched child's own opening orders carry the same restriction --
    # a projection, not a copy of the whole round
    cli.main(["open", "run-a-gate", "--parent", wid, "--step", "g1"])
    child_prefill = runmod.state(f"{wid}.g1")["prefill"]
    assert child_prefill["purpose"] == prefill["purpose"]
    assert "horizon" not in child_prefill


def test_the_critics_read_the_horizon_the_implementer_never_sees(workdir, capsys):
    """The other half of the asymmetry: a panelist judging the round the
    plan just cut reads the horizon alongside the gate, since the critic
    panel is built from this segment's own prior return -- the same
    mechanism that keeps it out of the implementer's prefill just proves it
    the opposite way for the reader meant to see it."""
    wid = "issue21"
    cli.main(["open", "run-an-issue", "--issue", "21", "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    def _fill_with_horizon(w):
        _fill(journal.location(w) / "PLAN.toml", '''
plan = "%s/plan.md"
purpose = "fix the parser to handle EOF without a trailing newline"
scope = "src/parser.c only"
proof = "true"
horizon = "next: a regression test gate, once this one lands"
key-terms = "waived: none"
''' % journal.location(w))
    _dispatch_and_close_plan(wid, fill_fn=_fill_with_horizon)  # design-it-twice: three siblings
    capsys.readouterr()

    cli.main(["open", "give-a-verdict", "--parent", wid, "--step", "plan.p1"])
    prefill = runmod.state(f"{wid}.plan.p1")["prefill"]
    assert prefill["horizon"] == "next: a regression test gate, once this one lands"
    assert prefill["purpose"].startswith("fix the parser")


# -- 3. an artifact field holding prose is measured, not silently zero -------


def test_artifact_field_pointing_at_a_real_path_is_measured(workdir, capsys):
    """#45: the `plan` field's note used to describe the document's content
    -- "the approach, the gates it cuts into...the risks" -- reading like an
    invitation to write the plan inline rather than name where it lives.
    `_prose_words` treats the field's value as a path (`Path(...).read_text()`),
    so a value that is prose rather than a path raises `OSError`, is caught,
    and reports zero -- silently, since the engine only records a `measure`
    entry when the count is truthy. Given a real path instead, the words at
    that path land in the journal."""
    wid = "issue22"
    cli.main(["open", "run-an-issue", "--issue", "22", "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])

    cli.main(["open", "cut-a-gate", "--parent", wid, "--step", "plan-1"])
    child = f"{wid}.plan-1"
    plan_path = journal.location(child) / "plan.md"
    plan_path.write_text(" ".join(["word"] * 42) + "\n")
    _fill_plan(child)  # points `plan` at the real path, per the corrected note
    cli.main([child, "submit"])
    capsys.readouterr()

    measures = [e for e in journal.read(child) if e.get("kind") == "measure"]
    assert measures, "no measure entry -- the artifact path did not resolve"
    plan_measure = next(m for m in measures if m["field"] == "plan")
    assert plan_measure["words"] == 42


def test_an_artifact_field_holding_prose_inline_measures_zero_not_a_crash(workdir, capsys):
    """The failure mode #45 named, still possible if an agent ignores the
    note and writes the plan straight into the field: `_prose_words` cannot
    open a path that is actually a paragraph, so it reports zero rather than
    raising -- and the engine only journals a `measure` entry when the count
    is truthy, so nothing lands at all. Silent, not loud, which is exactly
    what made the bug easy to miss; this pins the behaviour so a future
    change to `_prose_words` cannot make it loud by accident without a test
    noticing the shape changed."""
    wid = "issue23"
    cli.main(["open", "run-an-issue", "--issue", "23", "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])

    cli.main(["open", "cut-a-gate", "--parent", wid, "--step", "plan-1"])
    child = f"{wid}.plan-1"
    _fill(journal.location(child) / "PLAN.toml", '''
plan = "the approach is to adjust the loop bound and add a regression test"
purpose = "fix the parser to handle EOF without a trailing newline"
scope = "src/parser.c only"
proof = "true"
horizon = "waived: none yet"
key-terms = "waived: none"
''')
    cli.main([child, "submit"])
    capsys.readouterr()

    measures = [e for e in journal.read(child) if e.get("kind") == "measure"]
    assert not any(m["field"] == "plan" for m in measures)
