"""One look (ruling, 2026-09-25): run-an-issue's spec and plan seams get a
single round of critic review, never a loop. `incorporate` is the writer's
own pass over what the panel found -- taken or rejected on its own
judgement, no second panel reading what comes back; `rewrite` is the escape
hatch for a `severe` finding, a fresh artifact from the conductor's own
`orders` alone, judged by a panel of its own. `round-cap` is what still
stops a seam that keeps sending the round back, now built from rewrites
rather than an impasse loop -- and a round a paused seam's own resume opens
starts that count over (#177).

Drives the real `run-an-issue` assembly end to end through `cli.main`, the
same style test_nesting.py and test_spec_review.py already use, reusing
their fixtures rather than hand-rolling a journal.

KNOWN BLOCKER: `engine/cli.py`'s `_releases(outcome)` (~line 2707) still
tests the outcome verb against the literal strings `"rework"`/`"pause"`,
never updated when the ASSEMBLY.toml outcome tables were renamed to
`incorporate`/`rewrite`. It reads an `incorporate`/`rewrite` outcome as a
release, so `_check_release_artifacts` wrongly demands the round's blank
`spec`/`plan` field the moment ANY incorporate or rewrite submits -- before
`_check_one_look`'s own orders/severe/second-incorporate checks are ever
reached. Every test in this file drives at least one incorporate or
rewrite, so every one of them currently fails on that single defect
(`SystemExit: spec: a release needs it ...` / `plan: a release needs it
...`), not on anything below. This is reported, not fixed here (engine code
is out of scope for this file) -- these tests are written to the ruling's
actual intended behavior and will pass once `_releases` is taught the new
verbs.
"""

import pathlib

import pytest

from engine import cli, journal, run as runmod

from test_nesting import (
    _dispatch_and_close_plan,
    _dispatch_plan_critic,
    _drive_plan_to_pause,
    _fill,
    _fill_consolidate,
    _fill_consolidate_route_with_calls,
    _fill_critic,
    _fill_open,
    _fill_plan,
    _fill_plan_rework,
    _fill_plan_route_with_calls,
    _fill_plan_to_execute,
    _fill_spec,
    _response,
    _work_the_board,
    _write_plan_artifact,
)


def _resolve_board(wid):
    b = pathlib.Path(f".agent-work/{wid}/UNDERSTAND.toml")
    b.write_text(b.read_text().replace(
        'status = "open"', 'status = "answered"\nanswer = "EOF with no trailing newline."'))


def _open_to_spec_reviewed(wid, issue, findings):
    """A real run-an-issue driven to CONSOLIDATE.toml, with one panelist per
    entry in `findings` each returning a distinct revise -- proving a
    reader downstream (`_incorporated`) attributes each to its own voice
    rather than folding them into one blob."""
    cli.main(["open", "run-an-issue", "--issue", issue, "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _resolve_board(wid)
    _fill_spec(wid)
    cli.main([wid, "submit"])
    st = runmod.state(wid)
    step_id = st["current"]["id"]
    panel = next(s for s in st["steps"] if s["id"] == step_id)["panel"]
    assert len(panel) == len(findings), "one finding per panelist, or the fixture is wrong"
    for n, finding in enumerate(findings, start=1):
        cli.main(["open", "give-a-verdict", "--parent", wid, "--step", f"{step_id}.p{n}"])
        panelist = f"{wid}.{step_id}.p{n}"
        _fill_critic(panelist, "revise", finding)
        cli.main([panelist, "submit"])
        cli.main([panelist, "close"])
    return wid


def _open_to_plan_reviewed(wid, issue, findings, fill_fn=None):
    """A real run-an-issue driven to PLAN_TO_EXECUTE.toml, the opening cut's
    own panel each returning a distinct revise."""
    cli.main(["open", "run-an-issue", "--issue", issue, "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    _dispatch_and_close_plan(wid, fill_fn=fill_fn)
    st = runmod.state(wid)
    step_id = st["current"]["id"]
    panel = next(s for s in st["steps"] if s["id"] == step_id)["panel"]
    assert len(panel) == len(findings), "one finding per panelist, or the fixture is wrong"
    for n, finding in enumerate(findings, start=1):
        cli.main(["open", "give-a-verdict", "--parent", wid, "--step", f"{step_id}.p{n}"])
        panelist = f"{wid}.{step_id}.p{n}"
        _fill_critic(panelist, "revise", finding)
        cli.main([panelist, "submit"])
        cli.main([panelist, "close"])
    return wid


def _fill_plan_with_horizon(wid, horizon, purpose="fix the parser to handle EOF without a "
                            "trailing newline", scope="src/parser.c only", proof="true"):
    """`_fill_plan` (test_nesting.py) always writes `horizon = "waived: none
    yet"` -- this variant lets a caller give the opening cut a real horizon,
    so a test can tell an incorporate's carried `horizon` apart from an
    empty placeholder."""
    loc = journal.location(wid)
    _write_plan_artifact(loc / "plan.md")
    _fill(_response(wid), '''
plan = "%s/plan.md"
purpose = "%s"
scope = "%s"
proof = "%s"
horizon = "%s"
key-terms = "waived: none"
''' % (loc, purpose, scope, proof, horizon))


# -- 1. incorporate on understand: every panelist's findings, orders ahead --


def test_incorporate_on_understand_mints_a_spec_round_holding_every_panelists_findings_with_orders_ahead(
        workdir, capsys):
    wid = "issue1"
    findings = ("gap: the boundary between parsed and unparsed input is unclear",
               "gap: nothing says how a reader would tell this is done",
               "gap: the purpose chain never reaches a root")
    _open_to_spec_reviewed(wid, "1", findings)
    capsys.readouterr()

    orders = "keep the boundary at src/parser.c only, nothing else in scope"
    _fill_consolidate(wid, "incorporate", calls='orders = "%s"\n' % orders)
    cli.main([wid, "submit"])
    capsys.readouterr()

    st = runmod.state(wid)
    fresh_writer = next(s for s in st["steps"]
                        if s["segment"] == "understand" and s.get("source") == "mint"
                        and s["form"] == "skills/spec-writer/forms/SPEC.toml")
    prefill = fresh_writer["prefill"]
    assert prefill["findings"].startswith(f"[conductor] {orders}"), (
        "the conductor's own orders do not lead the round's findings: "
        f"{prefill['findings']!r}")
    for n, finding in enumerate(findings, start=1):
        assert f"[p{n}] {finding}" in prefill["findings"], (
            f"panelist p{n}'s own finding is missing or unattributed: {prefill['findings']!r}")

    fresh_transition = next(s for s in st["steps"]
                            if s.get("source") == "panel" and s["segment"] == "understand"
                            and s["id"] != "understand")
    assert fresh_transition["form"] == "forms/CONSOLIDATE.toml"
    assert "panel" not in fresh_transition, "incorporate's own round stood a second panel"
    assert st["current"]["id"] == fresh_writer["id"], "the writer resumes, not the route form"


# -- 2. incorporate on plan: a REWORK.toml dispatch, carrying the horizon ---


def test_incorporate_on_plan_mints_a_rework_dispatch_carrying_the_prior_horizon(workdir, capsys):
    wid = "issue2"
    horizon = "gate 2: harden the writer path once this lands"
    findings = ("gap: the split argues for two gates where one would do",
               "gap: the proof passes on an empty diff",
               "gap: the scope reaches past the parser")
    _open_to_plan_reviewed(wid, "2", findings,
                           fill_fn=lambda w: _fill_plan_with_horizon(w, horizon))
    capsys.readouterr()

    _fill_plan_to_execute(wid, "incorporate")
    cli.main([wid, "submit"])
    capsys.readouterr()

    st = runmod.state(wid)
    fresh_writer = next(s for s in st["steps"]
                        if s["segment"] == "plan" and s.get("source") == "mint"
                        and s["id"] not in st["done"] and s.get("dispatches"))
    assert fresh_writer["form"] == "skills/planner/forms/REWORK.toml", (
        "incorporate did not mint the plan seam's own rework-form")
    prefill = fresh_writer["prefill"]
    assert prefill["horizon"] == horizon, "the prior round's own horizon did not carry forward"
    for n, finding in enumerate(findings, start=1):
        assert f"[p{n}] {finding}" in prefill["findings"]

    fresh_transition = next(s for s in st["steps"]
                            if s.get("source") == "panel" and s["segment"] == "plan"
                            and s["id"] != "plan")
    assert fresh_transition["form"] == "forms/PLAN_TO_EXECUTE.toml"
    assert "panel" not in fresh_transition, "incorporate's own round stood a second panel"
    assert st["current"]["id"] == fresh_writer["id"]


# -- 3. a second incorporate on the same artifact refuses, journals nothing -


def test_a_second_incorporate_on_the_same_artifact_is_refused_and_journals_nothing(
        workdir, capsys):
    wid = "issue3"
    _open_to_spec_reviewed(wid, "3", ("gap: p1's own finding", "gap: p2's own finding",
                                      "gap: p3's own finding"))
    capsys.readouterr()

    _fill_consolidate(wid, "incorporate")
    cli.main([wid, "submit"])
    capsys.readouterr()

    st = runmod.state(wid)
    assert st["current"]["form"] == "skills/spec-writer/forms/SPEC.toml"
    _fill_spec(wid)   # the writer's own pass over the panel's findings
    cli.main([wid, "submit"])
    capsys.readouterr()

    assert runmod.state(wid)["current"]["form"] == "forms/CONSOLIDATE.toml", (
        "the writer's own pass should stand the route form alone, no panel")

    before = len(journal.read(wid))
    _fill_consolidate(wid, "incorporate")
    with pytest.raises(SystemExit) as e:
        cli.main([wid, "submit"])
    assert "already incorporated" in str(e.value), str(e.value)
    assert len(journal.read(wid)) == before, "the refused submit journaled something anyway"


# -- 4. incorporate with a severe call refuses ------------------------------


def test_an_incorporate_with_a_severe_call_is_refused(workdir, capsys):
    wid = "issue4"
    findings = ("gap: the wording could be tighter",
                "gap: this run is solving the wrong problem entirely",
                "gap: a minor typo in the boundary sentence")
    _open_to_spec_reviewed(wid, "4", findings)
    capsys.readouterr()

    _fill_consolidate_route_with_calls(
        wid, "incorporate",
        (findings[0], "writer"),
        (findings[1], "severe"),
        (findings[2], "writer"))
    with pytest.raises(SystemExit) as e:
        cli.main([wid, "submit"])
    assert "severe" in str(e.value) and "rewrite" in str(e.value), str(e.value)


# -- 5. rewrite with blank or waived orders refuses -------------------------


def test_a_rewrite_with_blank_or_waived_orders_is_refused(workdir, capsys):
    wid = "issue5"
    _open_to_plan_reviewed(wid, "5", ("gap: needs a rewrite, not a patch",
                                      "gap: the proof is weak", "gap: scope creeps"))
    capsys.readouterr()

    _fill_plan_to_execute(wid, "rewrite")   # no orders at all
    with pytest.raises(SystemExit) as e:
        cli.main([wid, "submit"])
    assert "orders" in str(e.value), str(e.value)

    _fill_plan_to_execute(wid, "rewrite", calls='orders = "waived: nothing to add"\n')
    with pytest.raises(SystemExit) as e:
        cli.main([wid, "submit"])
    assert "orders" in str(e.value), str(e.value)


# -- 6. rewrite mints the step-form, orders alone, count restarts, panel ----


def test_a_rewrite_mints_the_step_form_with_orders_alone_restarting_the_count_and_carrying_a_panel(
        workdir, capsys):
    wid = "issue6"
    _open_to_plan_reviewed(wid, "6", ("gap: this cut builds the wrong gate",
                                      "gap: the proof is weak", "gap: scope creeps"))
    capsys.readouterr()

    orders = "cut a narrower gate: only the EOF branch in src/parser.c"
    _fill_plan_to_execute(wid, "rewrite", calls='orders = "%s"\n' % orders)
    cli.main([wid, "submit"])
    capsys.readouterr()

    st = runmod.state(wid)
    fresh = next(s for s in st["steps"]
                if s["segment"] == "plan" and s.get("source") == "mint"
                and s["id"] not in st["done"] and s.get("dispatches"))
    assert fresh["form"] == "skills/planner/forms/PLAN.toml", (
        "a rewrite should mint a fresh first cut, not the rework-form")
    assert fresh["prefill"] == {"orders": orders}, (
        f"a rewrite's prefill should be orders alone, no findings: {fresh['prefill']!r}")
    assert fresh["sent_back"] == 0, "a rewrite should restart the send-back count"

    fresh_transition = next(s for s in st["steps"]
                            if s.get("source") == "panel" and s["segment"] == "plan"
                            and s["id"] != "plan")
    assert fresh_transition["form"] == "forms/PLAN_TO_EXECUTE.toml"
    assert fresh_transition.get("panel"), "a rewrite's fresh artifact should get its own look"
    assert st["current"]["id"] == fresh["id"]


# -- 7. writer narrows what incorporate carries; beyond still journals -----


def test_a_writer_called_calls_table_narrows_what_incorporate_carries_and_beyond_still_journals(
        workdir, capsys):
    wid = "issue7"
    findings = ("gap: the boundary sentence needs fixing",
                "gap: this run should also add a caching layer",
                "gap: nothing else to add here")
    _open_to_spec_reviewed(wid, "7", findings)
    capsys.readouterr()

    _fill_consolidate_route_with_calls(
        wid, "incorporate",
        (findings[0], "writer"),
        (findings[1], "beyond"),
        (findings[2], "writer"))
    cli.main([wid, "submit"])
    capsys.readouterr()

    st = runmod.state(wid)
    fresh_writer = next(s for s in st["steps"]
                        if s["segment"] == "understand" and s.get("source") == "mint"
                        and s["form"] == "skills/spec-writer/forms/SPEC.toml")
    prefill_findings = fresh_writer["prefill"]["findings"]
    assert findings[0] in prefill_findings
    assert findings[2] in prefill_findings
    assert findings[1] not in prefill_findings, (
        f"a beyond call rode into the incorporate round: {prefill_findings!r}")

    triage = [n.get("text", "") for n in runmod.state(wid)["notes"]
             if n.get("kind_detail") == "triage"]
    assert triage == [findings[1]], triage


# -- 8. round-cap still pauses after five non-released rounds ---------------


def _open_to_plan(wid, issue):
    cli.main(["open", "run-an-issue", "--issue", issue, "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    _dispatch_and_close_plan(wid)


def test_a_second_rewrite_before_release_goes_up_as_an_ask(workdir, capsys):
    """One major rewrite, then the question goes up (`rewrite-cap = 1`)."""
    wid = "issue8"
    _open_to_plan(wid, "8")
    _drive_plan_to_pause(wid)
    capsys.readouterr()

    paused = runmod.state(wid)["current"]
    assert paused["form"] == "skills/gate-conductor/forms/ASK.toml"
    reason = paused["prefill"]["ask"]
    assert "plan" in reason
    assert "rewritten 1 time" in reason and "rewrite-cap of 1" in reason


def test_the_one_rewrite_is_still_incorporated_and_released(workdir, capsys):
    """The cap counts rewrites, not rounds: a rewritten cut gets its own
    look, the writer's one pass over it, and a release -- nothing about
    having spent the seam's one rewrite stops the ordinary path."""
    wid = "issue10"
    _open_to_plan(wid, "10")
    _dispatch_plan_critic(wid, verdict="revise", findings="gap: wrong chunk entirely",
                          resolution="rewrite")
    capsys.readouterr()

    st = runmod.state(wid)
    _dispatch_and_close_plan(wid, st["current"]["id"], fill_fn=lambda w: _fill_plan(
        w, purpose="the right chunk", scope="src/parser.c only"))
    _dispatch_plan_critic(wid, verdict="revise", findings="gap: the proof is thin",
                          resolution="incorporate")
    capsys.readouterr()
    st = runmod.state(wid)
    assert st["current"]["form"] == "skills/planner/forms/REWORK.toml", (
        f"the rewritten cut was not handed back to the planner: {st['current'].get('form')}")

    _dispatch_and_close_plan(wid, st["current"]["id"], fill_fn=_fill_plan_rework)
    _fill_plan_to_execute(wid, "pass")
    cli.main([wid, "submit"])
    capsys.readouterr()
    st = runmod.state(wid)
    assert any(s["segment"] == "execute" and s.get("dispatches") for s in st["steps"]), (
        "the incorporated rewrite did not release into a gate")


def test_a_round_a_resumed_pause_opens_is_not_capped_again_on_the_very_next_send_back(
        workdir, capsys):
    """#177: the principal's answer is the ruling round-cap exists to
    obtain, so the round it opens starts the count over -- the very next
    send-back must not immediately re-trip the cap."""
    wid = "issue9"
    _open_to_plan(wid, "9")
    _drive_plan_to_pause(wid)
    capsys.readouterr()

    answer = "narrow the gate to src/parser.c only and try again"
    _fill(_response(wid), 'answer = "%s"\n' % answer)
    cli.main([wid, "submit"])
    capsys.readouterr()

    st = runmod.state(wid)
    assert st["current"]["form"] == "skills/planner/forms/PLAN.toml"
    assert st["current"]["prefill"] == {"answer": answer}
    resumed_transition = next((s for s in st["steps"] if s.get("resumed")), None)
    assert resumed_transition is not None, "no fresh round was stamped resumed"
    assert resumed_transition["form"] == "forms/PLAN_TO_EXECUTE.toml"

    _dispatch_and_close_plan(wid, st["current"]["id"], fill_fn=lambda w: _fill_plan(
        w, purpose="narrowed gate", scope="src/parser.c only"))
    _dispatch_plan_critic(wid, verdict="revise", findings="gap: still too broad",
                          resolution="rewrite")
    capsys.readouterr()

    # A rewrite mints a fresh planner round; a re-tripped cap would have
    # stood the run on the principal's ask instead.
    after = runmod.state(wid)["current"]
    assert after["form"] == "skills/planner/forms/PLAN.toml", (
        "the very next send-back after a resume tripped round-cap again -- "
        f"landed on {after.get('form')!r} instead")
