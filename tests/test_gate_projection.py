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

import pytest

from engine import cli, journal, run as runmod
from test_nesting import (
    _dispatch_and_close_plan,
    _dispatch_plan_critic,
    _fill,
    _fill_consolidate,
    _fill_open,
    _fill_plan,
    _fill_plan_rework,
    _fill_plan_to_execute,
    _response,
    _work_the_board,
)


def _plan_impasse_after():
    """The plan segment's `impasse-after`, read off the assembly rather than
    pinned (1 since the 2026-09-05 ruling)."""
    return next(s for s in runmod.load_assembly("run-an-issue")["segment"]
                if s["id"] == "plan")["impasse-after"]


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

    _fill_plan_to_execute(wid)  # resolution and the plan pointer -- no gates field to fill
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
        (journal.location(w) / "plan.md").write_text("the plan document.\n")
        _fill(_response(w), '''
plan = "%s/plan.md"
purpose = "fix the parser to handle EOF without a trailing newline"
scope = "src/parser.c only"
proof = "true"
horizon = "next: a regression test gate, once this one lands"
key-terms = "waived: none"
''' % journal.location(w))
    _dispatch_and_close_plan(wid, fill_fn=_fill_with_horizon)  # round one's single planner
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


def test_an_artifact_field_holding_prose_inline_is_refused_not_measured_zero(workdir, capsys):
    """#45's fix, the contract half: an agent that ignores the note and
    writes the plan straight into the field no longer measures zero in
    silence. `_check_artifact` (engine/cli.py) refuses the submit before
    anything is journaled -- the same point `_check_vocabulary` refuses at --
    naming the field and offering the escape every unanswered field gets
    (fill it with a real path, or answer waived:/unknown:). Before this
    check existed, this exact submit went through and journaled nothing;
    see the git history of this test for that shape, which is what made the
    bug invisible."""
    wid = "issue23"
    cli.main(["open", "run-an-issue", "--issue", "23", "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])

    cli.main(["open", "cut-a-gate", "--parent", wid, "--step", "plan-1"])
    child = f"{wid}.plan-1"
    _fill(_response(child), '''
plan = "the approach is to adjust the loop bound and add a regression test"
purpose = "fix the parser to handle EOF without a trailing newline"
scope = "src/parser.c only"
proof = "true"
horizon = "waived: none yet"
key-terms = "waived: none"
''')
    with pytest.raises(SystemExit) as e:
        cli.main([child, "submit"])
    assert "plan" in str(e.value)
    assert "not a readable path" in str(e.value)
    capsys.readouterr()

    measures = [e for e in journal.read(child) if e.get("kind") == "measure"]
    assert not any(m["field"] == "plan" for m in measures)
    assert not any(e.get("kind") == "submit" for e in journal.read(child))


def test_an_artifact_field_answered_waived_is_not_refused(workdir, capsys):
    """The null escape every field gets must still work on an `artifact`
    field: `waived:`/`unknown:` are not paths, and `_check_artifact` must
    stand down for them exactly as `_check_vocabulary` already does on a
    `decision` field's own vocabulary -- this is the one field kind that
    could plausibly be tempted to refuse a null too, since its whole point
    is that the value must resolve to a file."""
    wid = "issue24"
    cli.main(["open", "run-an-issue", "--issue", "24", "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])

    cli.main(["open", "cut-a-gate", "--parent", wid, "--step", "plan-1"])
    child = f"{wid}.plan-1"
    _fill(_response(child), '''
plan = "waived: no plan document for this trivial gate"
purpose = "fix the parser to handle EOF without a trailing newline"
scope = "src/parser.c only"
proof = "true"
horizon = "waived: none yet"
key-terms = "waived: none"
''')
    cli.main([child, "submit"])  # must not raise
    capsys.readouterr()

    assert any(e.get("kind") == "submit" for e in journal.read(child))
    measures = [e for e in journal.read(child) if e.get("kind") == "measure"]
    assert not any(m["field"] == "plan" for m in measures)


def test_a_release_with_a_blank_plan_is_refused(workdir, capsys):
    """#87's silent class: `plan` went optional so a `rework`/`up` -- neither
    releasing anything -- could leave it blank. The same optional flag let
    a `pass` leave it blank too and release anyway, `_mint_projected_gate`
    finding nothing to project and silently doing nothing -- a round the
    record calls released with no gate behind it.
    `_check_release_artifacts` (engine/cli.py) refuses this before anything
    is journaled, generic off `kind = "artifact"` and `_releases`: the same
    check that lets a `rework`/`up` leave the field blank is what proves a
    release cannot."""
    wid = _drive_to_plan_to_execute()
    _fill(_response(wid), 'resolution = "pass"\n')
    with pytest.raises(SystemExit) as e:
        cli.main([wid, "submit"])
    assert "plan" in str(e.value)
    assert "a release needs it" in str(e.value)
    capsys.readouterr()

    assert runmod.state(wid)["current"]["id"] == "plan"  # never advanced


def test_a_rework_with_a_blank_plan_is_still_accepted(workdir, capsys):
    """The fork `_check_release_artifacts` turns on: a `rework` has nothing
    intact to project, so leaving `plan` blank there is the correct answer,
    not a gap -- `_releases` is what keeps the new check off this path."""
    wid = _drive_to_plan_to_execute()
    _fill_plan_to_execute(wid, "rework")
    cli.main([wid, "submit"])  # must not raise
    capsys.readouterr()

    assert any(e.get("kind") == "submit" for e in journal.read(wid))


# -- 6. #87: an impasse advance projects the round the ruling approved -------


def _drive_to_impasse_with_varying_gates(wid="issue17"):
    """The same shape `test_rework._drive_to_impasse` drives -- one plan
    round, two reworks, the third revise landing on the ruling form -- but
    with each round cutting a *different* purpose/scope, unlike
    `_fill_plan`'s and `_fill_rework`'s own fixed defaults. Every fixture
    upstream fills the same three literal strings every round, so "most
    recent" and "first found" agree by accident and no test can tell the
    backward walk apart from a forward one. This is what lets a caller
    assert the minted gate actually carries the *last* round's own
    values, not merely a round's."""
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    _dispatch_and_close_plan(wid, fill_fn=lambda w: _fill_plan(
        w, purpose="round 1 purpose", scope="round 1 scope"))
    _dispatch_plan_critic(wid, verdict="revise", findings="gap: round 1 is untestable")
    # one rework per `impasse-after` (read off the assembly, never pinned),
    # the last of them the round the ruling approves
    last = _plan_impasse_after() + 1
    rounds = [(f"round {n} purpose", f"round {n} scope") for n in range(2, last)]
    rounds.append((f"round {last} purpose -- the one the ruling approves",
                   f"round {last} scope -- the one the ruling approves"))
    for n, (purpose, scope) in enumerate(rounds, start=2):
        st = runmod.state(wid)
        fresh = next(s for s in st["steps"]
                    if s["segment"] == "plan" and s.get("source") == "mint"
                    and s["id"] not in st["done"] and s.get("dispatches"))
        _dispatch_and_close_plan(
            wid, fresh["id"],
            lambda w, p=purpose, s=scope: _fill_plan_rework(w, purpose=p, scope=s))
        _dispatch_plan_critic(wid, verdict="revise", findings=f"gap: round {n} is untestable")
    return wid


def test_impasse_advance_projects_the_round_the_ruling_approved(workdir, capsys):
    """#87: an `advance` mints this same transition, and the step
    immediately behind it is then the ruling form -- `ruling`, `why`, never
    a gate field. Walking the segment's own prior steps backward instead of
    reading only the one immediately behind the transition finds the round
    the ruling actually approved -- the last rework round -- and this drive
    gives each of the three rounds its own purpose/scope, so the assertion
    below actually distinguishes "most recent" from "earliest" or "any":
    the review's own gap, mutating `reversed(prior)` into a forward walk
    left this test green until the gates it minted differed round to
    round. Obligations 4, 5 and 8 are one drive and one test, not three:
    the dispatch and adjudication pair this produces is numbered as the
    segment's next child and shaped exactly like the pair an ordinary
    release produces, and its prefill carries only the last round's own
    fields, not the first round's or the middle one's."""
    wid = _drive_to_impasse_with_varying_gates()
    capsys.readouterr()
    _fill(_response(wid),
          'ruling = "advance"\nwhy = "all three rounds landed on the proof"\n')
    cli.main([wid, "submit"])
    capsys.readouterr()
    # advance mints the transition alone -- no panel to argue with
    assert runmod.state(wid)["current"]["form"] == "forms/PLAN_TO_EXECUTE.toml"

    _fill_plan_to_execute(wid)
    cli.main([wid, "submit"])
    capsys.readouterr()

    st = runmod.state(wid)
    gates = [s for s in st["steps"] if s.get("dispatches") == "run-a-gate"]
    assert [g["id"] for g in gates] == ["g1"]
    adjudications = [s for s in st["steps"] if s.get("form") == "forms/GATE_TRANSITION.toml"]
    assert [a["id"] for a in adjudications] == ["g1-adjudicate"]

    g1 = next(s for s in st["steps"] if s["id"] == "g1")
    last = _plan_impasse_after() + 1
    assert g1["prefill"]["purpose"] == f"round {last} purpose -- the one the ruling approves"
    assert g1["prefill"]["scope"] == f"round {last} scope -- the one the ruling approves"
    assert g1["prefill"]["proof"] == "true"
    # not the first round's, and not any middle one's either
    assert g1["prefill"]["purpose"] not in {f"round {n} purpose" for n in range(1, last)}


def test_a_rework_on_the_transition_still_projects_nothing(workdir, capsys):
    """Obligation 6's other half, the one `test_one_gate_minted_per_pass_
    not_k` (the pass side) doesn't cover: a transition submitted with its
    round sent back releases nothing, so `_projected_source` returns
    `None` -- off `_releases`, before the walk ever runs -- and no gate is
    minted."""
    wid = _drive_to_plan_to_execute()
    _fill_plan_to_execute(wid, "rework")
    cli.main([wid, "submit"])
    capsys.readouterr()

    assert not any(s.get("dispatches") == "run-a-gate"
                  for s in runmod.state(wid)["steps"])


# -- 7. the true dead end refuses instead of walking on quietly -------------


def _synthetic_projecting_assembly():
    """A `plan` segment whose transition projects into `execute`, and an
    `execute` segment `_mint_gates` can reach -- the minimum shape
    `_projected_source` needs, built by hand because no assembly in the
    tree can actually reach the walk-finds-nothing case (plan.md's risk
    note): every real projecting transition sits behind at least one round
    that filled a gate field, since nothing dispatches it otherwise."""
    return {"segment": [
        {"id": "plan", "transition": {
            "form": "T.toml", "projects": "run-a-gate",
            "decides": "resolution",
            "outcome": [{"value": "pass", "does": "release"},
                       {"value": "rework", "does": "rework"}]}},
        {"id": "execute", "dispatches": "run-a-gate"},
    ]}


def test_the_walk_refuses_where_it_finds_no_round_to_project(workdir, capsys):
    """Obligation 3: a segment whose only prior round never carried a gate
    field is the true dead end this whole change is about -- the walk
    reaches the start of the segment with nothing to show for it, and
    `_check_projection` refuses before the submit is journaled rather than
    minting nothing in silence."""
    asm = _synthetic_projecting_assembly()
    step = {"id": "t1", "segment": "plan", "form": "T.toml"}
    st = {"steps": [{"id": "r1", "segment": "plan"}, step],
         "done": {"r1": {"fields": {"resolution": "pass"}}}}  # no gate field, ever
    fields = {"resolution": "pass"}

    with pytest.raises(SystemExit) as e:
        cli._check_projection(asm, step, st, fields)
    assert "t1" in str(e.value)
    assert "no round behind it" in str(e.value)

    # `_mint_projected_gate` itself is a no-op on the same input -- the
    # refusal above is what stands between this and a silent nothing-minted
    cli._mint_projected_gate("wid", asm, step, st, fields)


def test_the_widened_guard_returns_none_off_a_non_transition_step(workdir, capsys):
    """The guard `_projected_source` replaces used to be a subset of
    conditions re-derived at each caller; widened now to cover the whole
    applicability question in one place. A step inside a projecting
    segment that is not the transition itself -- an ordinary interior
    round -- is not this transition's own release, so `_check_projection`
    stands down rather than tripping on a narrower, hand-copied guard."""
    asm = _synthetic_projecting_assembly()
    step = {"id": "r1", "segment": "plan", "form": "PLAN.toml"}  # not the transition's form
    st = {"steps": [step], "done": {}}

    cli._check_projection(asm, step, st, {})  # must not raise
    assert cli._projected_source(step, st, asm, {}) is None
