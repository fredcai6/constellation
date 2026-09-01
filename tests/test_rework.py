"""The rework round has its own form, and record-only is real.

A revise on run-an-issue's plan segment mints REWORK.toml -- the segment's
`rework-form` -- in place of the step-form; a replan, and a revise on a
segment without the key, mint the step-form exactly as before. The prefill
guard reads the producing step's form, so a rework round's record-only
ledger (`findings-addressed`, `deleted`) stays out of the next panelist's
prefill. Drives the real assemblies end to end, like test_nesting.py.
"""

import pathlib

import pytest

from engine import cli, run as runmod

from test_nesting import (
    _dispatch_and_close_child,
    _dispatch_and_close_plan,
    _dispatch_plan_critic,
    _dispatch_review,
    _fill_route,
    _fill,
    _fill_consolidate,
    _fill_gate_transition_replan,
    _fill_implement,
    _fill_open,
    _fill_plan,
    _fill_spec,
    _mint_n_gates,
    _work_the_board,
    _write_plan_artifact,
)


def _drive_to_revise(wid="issue17", findings="gap: gate 1 is untestable"):
    """Open a real run-an-issue, drive it to the plan-to-execute panel, and
    have the critic say revise."""
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    _dispatch_and_close_plan(wid)
    _dispatch_plan_critic(wid, verdict="revise", findings=findings)
    return wid


def _fresh_mint(st, segment):
    return next(s for s in st["steps"]
                if s["segment"] == segment and s.get("source") == "mint")


def _dispatch_rework_round(wid, fill_fn=None):
    """Dispatch the plan round current at `wid` -- a rework round or a
    replan alike, since every round dispatches now -- fill it, submit and
    close the child. `st["current"]` names it, not `_fresh_mint`: a run with
    more than one rework round behind it has more than one minted plan step,
    and only the current one is still open. `fill_fn` defaults to
    `_fill_rework`; a replan passes `_fill_plan` instead. Returns the
    child's work id."""
    step_id = runmod.state(wid)["current"]["id"]
    return _dispatch_and_close_plan(wid, step_id, fill_fn or _fill_rework)


# -- 1. a revise mints the segment's rework form, findings as prefill --------


def test_revise_mints_rework_form_with_findings_as_prefill(workdir, capsys):
    wid = _drive_to_revise()
    capsys.readouterr()

    st = runmod.state(wid)
    fresh = _fresh_mint(st, "plan")
    assert fresh["dispatches"] == "cut-a-gate"  # a rework round dispatches too
    assert fresh["form"] == "skills/planner/forms/REWORK.toml"  # the override
    assert "gate 1 is untestable" in fresh["prefill"]["findings"]
    assert st["current"]["id"] == fresh["id"]

    # the dispatched child materializes REWORK.toml, not another PLAN.toml
    cli.main(["open", "cut-a-gate", "--parent", wid, "--step", fresh["id"]])
    child = f"{wid}.{fresh['id']}"
    cli.main([child])
    capsys.readouterr()
    assert (runmod.journal.location(child) / "REWORK.toml").exists()


# -- 2. a replan mints the step-form ------------------------------------------


def test_replan_mints_the_step_form(workdir, capsys):
    _mint_n_gates(1)
    capsys.readouterr()
    _dispatch_and_close_child("issue17", "g1")
    capsys.readouterr()

    _fill_gate_transition_replan("issue17")
    cli.main(["issue17", "submit"])
    capsys.readouterr()

    fresh = _fresh_mint(runmod.state("issue17"), "plan")
    assert fresh["dispatches"] == "cut-a-gate"  # a replan dispatches too
    assert fresh["form"] == "skills/planner/forms/PLAN.toml"  # a replan re-plans from scratch


def test_a_replan_restarts_the_rework_count(workdir, capsys):
    """The count is of rounds on one artifact, so a replan -- which is a new
    artifact -- starts it over. The principal ruled this against the
    alternative of counting every send-back."""
    wid = _drive_to_revise()
    _round(wid, "gap 1")
    asm = runmod.load_assembly("run-an-issue")
    assert runmod.rework_rounds(runmod.state(wid), asm, "plan") == 2

    # carry that plan through to a gate, then replan from the gate transition
    _dispatch_rework_round(wid)
    _dispatch_plan_critic(wid, verdict="pass")
    capsys.readouterr()
    _write_plan_artifact(runmod.journal.location(wid) / "plan.md")
    _fill(runmod.journal.location(wid) / "PLAN_TO_EXECUTE.toml", '''
plan = "%s/plan.md"
''' % runmod.journal.location(wid))
    cli.main([wid, "submit"])
    capsys.readouterr()
    _dispatch_and_close_child(wid, "g1")
    capsys.readouterr()
    _fill_gate_transition_replan(wid)
    cli.main([wid, "submit"])
    capsys.readouterr()

    assert runmod.rework_rounds(runmod.state(wid), asm, "plan") == 0


# -- 3. a revise on a segment without rework-form mints the step-form ---------


def test_revise_without_rework_form_mints_the_step_form(workdir, capsys):
    """run-a-gate's work segment declares no rework-form, so the round the
    review transition sends back refills with IMPLEMENT.toml exactly as
    before -- `_dispatch_review` drives both voices, the panel's revise and
    the conductor form's `rework` that acts on it."""
    cli.main(["open", "run-a-gate", "--id", "g1"])
    _fill_implement("g1", "work-1")
    cli.main(["g1", "submit"])
    capsys.readouterr()
    _dispatch_review("g1", verdict="revise", findings="gap: bound still off by one")
    capsys.readouterr()

    fresh = _fresh_mint(runmod.state("g1"), "work")
    assert fresh["form"] == "skills/implementer/forms/IMPLEMENT.toml"
    assert "bound still off by one" in fresh["prefill"]["findings"]


# -- 4. the rework ledger stays out of the next panelist's prefill ------------


def test_rework_record_only_fields_stay_out_of_the_next_panelists_prefill(workdir, capsys):
    wid = _drive_to_revise()
    capsys.readouterr()

    fresh = _fresh_mint(runmod.state(wid), "plan")
    child = f"{wid}.{fresh['id']}"
    cli.main(["open", "cut-a-gate", "--parent", wid, "--step", fresh["id"]])
    child_loc = runmod.journal.location(child)
    _write_plan_artifact(child_loc / "plan.md")
    _fill(child_loc / "REWORK.toml", '''
plan = "%s/plan.md"
purpose = "fix the parser to handle EOF without a trailing newline"
scope = "src/parser.c only"
proof = "true"
horizon = "waived: none yet"
findings-addressed = "accepted: rewrote gate 1's done as a runnable command"
deleted = "the restated approach section; the gates already carry it"
key-terms = "waived: none"
''' % child_loc)
    cli.main([child, "submit"])
    cli.main([child, "close"])
    capsys.readouterr()

    st = runmod.state(wid)
    panel_id = st["current"]["id"]
    assert panel_id != "plan"  # the refired panel, not the first round's
    cli.main(["open", "give-a-verdict", "--parent", wid, "--step", f"{panel_id}.p1"])
    capsys.readouterr()

    prefill = runmod.state(f"{wid}.{panel_id}.p1")["prefill"]
    assert "findings-addressed" not in prefill  # the producer's ledger stays behind
    assert "deleted" not in prefill
    assert prefill["plan"] == f"{child_loc}/plan.md"  # the artifact still rides
    assert prefill["key-terms"] == "waived: none"
    assert prefill["criteria"].startswith("intent-fit")


def _plan_measures(wid):
    """Prose lengths of the plan artifact, round by round. The `issue` field
    is an artifact too and is measured on the open step; the room reports
    drift per segment, so scoping here says what this test is about."""
    return [m["words"] for m in runmod.state(wid)["measures"] if m["field"] == "plan"]


def test_the_plan_segments_measures_fold_into_the_parent_each_round(workdir, capsys):
    """A round is still measured in the dispatched child's own journal
    first, the same as it always was -- but the return that closes it now
    folds that measure into the parent, under the step that dispatched the
    round (`_fold_measures`, engine/cli.py). That is what gives the plan
    segment's own room something to compare across rounds again, the same
    way a local segment (run-a-gate's `work`) always could.

    Before that fold existed, this test proved the opposite: growth was
    invisible in this run's own room because every round dispatched and no
    round of it was ever local. `tests/test_round_carry.py` is the fuller
    account of the fix; this one stays as the rework-specific case, driven
    the same way the rest of this module drives everything else.
    """
    wid = "issue44"
    cli.main(["open", "run-an-issue", "--issue", "44", "--title", "a plan that grows"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])

    # round one: design-it-twice (ruling 10) -- three siblings, each
    # measured in its own child's journal first, each folding its own
    # measure into the parent at close. Filled identically here: this test
    # is the rework-specific case (test_round_carry.py is the fuller
    # account), not a proof of what the room does with three same-round
    # entries -- an open question ruling 10 did not settle.
    def _fill_ten_words(w):
        (runmod.journal.location(w) / "plan.md").write_text(
            "one two three four five six seven eight nine ten\n")
        _fill_plan(w)
    child = f"{wid}.plan-1.p1"
    cli.main(["open", "give-a-verdict", "--parent", wid, "--step", "plan-1.p1"])
    _fill_ten_words(child)
    cli.main([child, "submit"])
    assert _plan_measures(child) == [10]
    cli.main([child, "close"])
    for n in (2, 3):
        sib = f"{wid}.plan-1.p{n}"
        cli.main(["open", "give-a-verdict", "--parent", wid, "--step", f"plan-1.p{n}"])
        _fill_ten_words(sib)
        cli.main([sib, "submit"])
        cli.main([sib, "close"])
    capsys.readouterr()

    # every sibling's return folded its own measure into the parent
    assert _plan_measures(wid) == [10, 10, 10]

    _dispatch_plan_critic(wid, verdict="revise", findings="gap: thin")
    capsys.readouterr()

    # the rework round dispatches too -- measured in its own child's journal
    # first, same as round one
    fresh = _fresh_mint(runmod.state(wid), "plan")
    assert fresh["dispatches"] == "cut-a-gate"
    rework_child = f"{wid}.{fresh['id']}"
    cli.main(["open", "cut-a-gate", "--parent", wid, "--step", fresh["id"]])
    rework_art = runmod.journal.location(rework_child) / "plan.md"
    rework_art.write_text("one two three four five six seven eight nine ten eleven twelve\n")
    _fill(runmod.journal.location(rework_child) / "REWORK.toml", '''
plan = "%s"
purpose = "fix the parser to handle EOF without a trailing newline"
scope = "src/parser.c only"
proof = "true"
horizon = "waived: none yet"
findings-addressed = "accepted: thickened gate 1"
deleted = "nothing; the growth is all prose"
key-terms = "waived: none"
''' % rework_art)
    cli.main([rework_child, "submit"])
    assert _plan_measures(rework_child) == [12]
    cli.main([rework_child, "close"])
    capsys.readouterr()

    # both rounds are now in the parent's own journal, in order -- round
    # one's three siblings, then the rework round's single pass
    assert _plan_measures(wid) == [10, 10, 10, 12]


# -- 5. the outlet: a fourth revise mints a ruling, not a fourth round --------


def _fill_rework(wid):
    loc = runmod.journal.location(wid)
    _write_plan_artifact(loc / "plan.md")
    _fill(loc / "REWORK.toml", '''
plan = "%s/plan.md"
purpose = "fix the parser to handle EOF without a trailing newline"
scope = "src/parser.c only"
proof = "true"
horizon = "waived: none yet"
findings-addressed = "waived: first pass"
deleted = "waived: nothing"
key-terms = "none"
''' % loc)


def _round(wid, findings):
    """One rework round: dispatch the fresh REWORK.toml round, fill it,
    submit and close the child, and have the fresh panel say revise
    again."""
    _dispatch_rework_round(wid)
    _dispatch_plan_critic(wid, verdict="revise", findings=findings)


def _drive_to_impasse(wid="issue17"):
    """Three rework rounds, then the fourth revise -- which is the one the
    segment's `impasse-after` turns into a ruling."""
    _drive_to_revise(wid)
    for n in (1, 2, 3):
        _round(wid, f"gap: the proof still passes on an empty diff ({n})")
    return wid


def test_a_fourth_revise_mints_the_impasse_form_not_another_round(workdir, capsys):
    wid = _drive_to_impasse()
    capsys.readouterr()

    st = runmod.state(wid)
    assert st["current"]["form"] == "forms/IMPASSE.toml", (
        f"the fourth revise minted {st['current']['form']!r} -- the segment "
        "declares impasse-after = 3, so this round is the ruling")
    assert "empty diff (3)" in st["current"]["prefill"]["findings"]
    # no fourth panel: another fresh-context reader is the loop, not the way out
    assert not any(s.get("source") == "panel" and s["id"] not in st["done"]
                   for s in st["steps"]), "the impasse minted a panel"


def test_the_count_reaches_the_outlet_on_the_round_after_the_third(workdir, capsys):
    """The boundary, both sides. The first revise mints round one, so the
    count is already 1 before any loop runs."""
    wid = _drive_to_revise()
    asm = runmod.load_assembly("run-an-issue")
    counts = [runmod.rework_rounds(runmod.state(wid), asm, "plan")]
    for n in (1, 2):
        _round(wid, f"gap {n}")
        counts.append(runmod.rework_rounds(runmod.state(wid), asm, "plan"))
    capsys.readouterr()
    assert counts == [1, 2, 3]
    # three rounds is still a round -- the revise that follows is the ruling
    assert runmod.state(wid)["current"]["form"] == "skills/planner/forms/REWORK.toml"
    _round(wid, "gap 3")
    capsys.readouterr()
    assert runmod.state(wid)["current"]["form"] == "forms/IMPASSE.toml"


def test_an_unhandled_ruling_refuses_rather_than_releasing_the_step(workdir, capsys):
    """The ruling has no check of its own any more: it is refused by the same
    generic mechanism that refuses CYCLE.toml's `decision` -- the segment's
    own declared `[[outcome]]` rows, not a hand-rolled reader."""
    wid = _drive_to_impasse()
    capsys.readouterr()
    before = len(runmod.journal.read(wid))
    _fill(runmod.journal.location(wid) / "IMPASSE.toml",
          'ruling = "keep going"\nwhy = "it is nearly there"\n')
    with pytest.raises(SystemExit) as e:
        cli.main([wid, "submit"])
    msg = str(e.value)
    assert "ruling" in msg and "is not an outcome this step declares" in msg
    assert "advance | rework | up" in msg        # the assembly's own outcome rows
    assert len(runmod.journal.read(wid)) == before  # not even the submit landed
    assert runmod.state(wid)["current"]["form"] == "forms/IMPASSE.toml"


def test_advance_takes_the_plan_to_its_transition_over_a_live_revise(workdir, capsys):
    wid = _drive_to_impasse()
    capsys.readouterr()
    _fill(runmod.journal.location(wid) / "IMPASSE.toml",
          'ruling = "advance"\nwhy = "three rounds all landed on the proof"\n')
    cli.main([wid, "submit"])
    capsys.readouterr()

    st = runmod.state(wid)
    assert st["current"]["form"] == "forms/PLAN_TO_EXECUTE.toml"
    assert st["current"].get("source") == "mint"
    assert not st["current"].get("panel"), "advance minted a fresh panel to argue with"


def test_rework_runs_the_round_the_outlet_displaced(workdir, capsys):
    wid = _drive_to_impasse()
    capsys.readouterr()
    _fill(runmod.journal.location(wid) / "IMPASSE.toml",
          'ruling = "rework"\nwhy = "round four changes the proof, not the prose"\n')
    cli.main([wid, "submit"])
    capsys.readouterr()

    st = runmod.state(wid)
    assert st["current"]["form"] == "skills/planner/forms/REWORK.toml"
    assert "empty diff (3)" in st["current"]["prefill"]["findings"]


def test_up_pauses_the_plan_impasse_rather_than_releasing(workdir, capsys):
    """commitment 3's ruling (issue84.g2): `up` is kept as a conductor's
    shorthand at this impasse, repointed from `release` to `pause` -- so
    ruling it here now stands an ask one tier up (self-minted: `_drive_to_
    impasse`'s own run-an-issue has no parent) and the run stays open,
    rather than walking to its terminal form the way a bare `release` did."""
    wid = _drive_to_impasse()
    before = len(runmod.state(wid)["steps"])
    capsys.readouterr()
    why = "the plan may be solving the wrong problem"
    _fill(runmod.journal.location(wid) / "IMPASSE.toml",
          'ruling = "up"\nwhy = "%s"\n' % why)
    cli.main([wid, "submit"])
    capsys.readouterr()

    st = runmod.state(wid)
    assert st["open"] and not st["awaiting_close"], "up must pause the run, not close it"
    assert len(st["steps"]) == before + 2, "up must mint an ask and a marker"
    ask = st["current"]
    assert ask["form"] == "skills/gate-conductor/forms/ASK.toml", (
        f"up must mint an ask, not release -- current is {ask!r}")
    assert ask["resumes"] == wid
    assert ask["prefill"].get("findings") == why
    ruling_step = next(s for s in st["steps"] if s.get("form") == "forms/IMPASSE.toml")
    ruling = st["done"][ruling_step["id"]]["fields"]
    assert ruling["ruling"] == "up" and "wrong problem" in ruling["why"]


def test_up_pauses_the_understand_impasse_rather_than_releasing(workdir, capsys):
    """The same ruling (commitment 3), at `understand`'s own impasse --
    shares `forms/IMPASSE.toml` with `plan` above, and now shares the
    outcome verb too: named separately from the test above, the way
    `test_understands_fourth_revise_mints_the_impasse_form_not_another_
    spec_round` already stands apart from `plan`'s own impasse tests,
    since the two segments dispatch their rounds differently even though
    the ruling itself is one policy."""
    wid = _drive_understand_to_impasse()
    before = len(runmod.state(wid)["steps"])
    capsys.readouterr()
    why = "the spec may be answering the wrong question"
    _fill(runmod.journal.location(wid) / "IMPASSE.toml",
          'ruling = "up"\nwhy = "%s"\n' % why)
    cli.main([wid, "submit"])
    capsys.readouterr()

    st = runmod.state(wid)
    assert st["open"] and not st["awaiting_close"], "up must pause the run, not close it"
    assert len(st["steps"]) == before + 2, "up must mint an ask and a marker"
    ask = st["current"]
    assert ask["form"] == "skills/gate-conductor/forms/ASK.toml", (
        f"up must mint an ask, not release -- current is {ask!r}")
    assert ask["resumes"] == wid
    assert ask["prefill"].get("findings") == why


# -- 6. the same outlet on run-a-gate, which has no rework form ---------------


def _drive_gate_to_impasse(child="issue17.g1"):
    """Four review revises on one diff, each disposed of on the review
    transition's own conductor form: the first three refill the interior
    through its `rework`, and the fourth is the one the outlet takes. A
    revise releases on its own now, so the form's `rework` is the path the
    mint -- and the count with it -- actually runs on. run-a-gate's work
    segment declares no rework-form, so every refill mints the step-form
    again; the count is of those, and the opening step is not one."""
    _mint_n_gates(1)
    cli.main(["open", "run-a-gate", "--parent", "issue17", "--step", "g1"])
    for n in (1, 2, 3, 4):
        _fill_implement(child, runmod.state(child)["current"]["id"])
        cli.main([child, "submit"])
        _dispatch_review(child, verdict="revise",
                         findings=f"gap: the spec asks for something untestable ({n})")
    return child


def test_a_gates_fourth_revise_mints_the_impasse_form(workdir, capsys):
    child = _drive_gate_to_impasse()
    capsys.readouterr()

    st = runmod.state(child)
    assert st["current"]["form"] == "forms/IMPASSE.toml"
    assert "untestable (4)" in st["current"]["prefill"]["findings"]
    asm = runmod.load_assembly("run-a-gate")
    assert runmod.rework_rounds(st, asm, "work") == 3


def test_a_gates_advance_mints_its_transition_and_the_round_is_disposed_of(workdir, capsys):
    """`advance` mints one transition step, over the live revise, and never a
    fresh panel. It names `review` rather than the ruling segment's own
    `select`, because select would put a fourth reader on the diff -- the
    loop, not the way out of it. What the conductor is stood on is the route
    form alone, and `close` there walks the gate to GATE_CLOSE."""
    child = _drive_gate_to_impasse()
    capsys.readouterr()
    before = len(runmod.state(child)["steps"])
    _fill(runmod.journal.location(child) / "IMPASSE.toml",
          'ruling = "advance"\nwhy = "three reviews all landed on the spec"\n')
    cli.main([child, "submit"])
    capsys.readouterr()

    st = runmod.state(child)
    assert len(st["steps"]) == before + 1, "advance minted more than its transition"
    assert st["current"]["form"] == "forms/ROUTE.toml"
    assert not st["current"].get("panel"), "advance minted a fresh panel to argue with"

    _fill_route(child, "close")
    cli.main([child, "submit"])
    capsys.readouterr()
    assert runmod.state(child)["current"]["form"] == "forms/GATE_CLOSE.toml"


def test_a_gates_rework_mints_the_step_form_again(workdir, capsys):
    child = _drive_gate_to_impasse()
    capsys.readouterr()
    _fill(runmod.journal.location(child) / "IMPASSE.toml",
          'ruling = "rework"\nwhy = "round four rewrites the check, not the diff"\n')
    cli.main([child, "submit"])
    capsys.readouterr()

    st = runmod.state(child)
    assert st["current"]["form"] == "skills/implementer/forms/IMPLEMENT.toml"
    # The findings the displaced round was carrying ride into it, unfiltered:
    # the ruling step carries no `calls` table, so `_blocking_calls` reads
    # `None` and this caller's prefill is exactly what it always was. Asserted
    # on the content, not only on the form -- the neighbouring
    # `test_a_gates_fourth_revise_mints_the_impasse_form` uses the same shape,
    # and without it a filter that dropped everything would pass here.
    assert "untestable (4)" in st["current"]["prefill"]["findings"]


def test_the_opening_step_is_not_a_send_back(workdir, capsys):
    """A gate that has never been reviewed is at zero, not one."""
    _mint_n_gates(1)
    cli.main(["open", "run-a-gate", "--parent", "issue17", "--step", "g1"])
    capsys.readouterr()
    asm = runmod.load_assembly("run-a-gate")
    assert runmod.rework_rounds(runmod.state("issue17.g1"), asm, "work") == 0


# -- who a gate dispatches, driven rather than grepped -------------------------
#
# [gate-dispatch-role]
# Rationale: run-a-gate's conductor field is an indirection, and the two steps
#   below are the ones that resolve it -- the close transition (no `filler` of
#   its own) and the impasse outlet minted in `_perform` with a bare
#   `filler="conductor"`. Reading the assembly file for `conductor =
#   "gate-conductor"` would pass while either step still stood up the
#   implementer, which is exactly what a hardcoded `filler = "implementer"` on
#   the close transition did until this test existed.
# Rejected: asserting on the rendered room's text instead. `role_of`/`hat` are
#   what the room and a dispatch brief both call, so resolving through them
#   proves the same fact without pinning the assertion to a print format.


def _dispatched_role(child):
    """Who the step in front of a gate resolves to, through the same two calls
    a rendered room and a dispatch brief both make."""
    st = runmod.state(child)
    asm = runmod.load_assembly("run-a-gate")
    return runmod.role_of(asm, st["current"]), runmod.hat(asm, st["current"], st)


def test_a_gates_close_step_is_filled_by_its_conductor(workdir, capsys):
    """Drive a gate through one implement round and a passing review to the
    close step itself, then ask who fills it: whoever conducts run-a-gate."""
    _mint_n_gates(1)
    cli.main(["open", "run-a-gate", "--parent", "issue17", "--step", "g1"])
    child = "issue17.g1"
    _fill_implement(child, runmod.state(child)["current"]["id"])
    cli.main([child, "submit"])
    _dispatch_review(child)     # pass, disposed of with `close`
    capsys.readouterr()

    st = runmod.state(child)
    assert st["current"]["form"] == "forms/GATE_CLOSE.toml"
    assert "filler" not in runmod.load_assembly("run-a-gate")["segment"][-1]["transition"], (
        "the close transition names a filler again, so it no longer follows a rename")
    assert _dispatched_role(child) == ("gate-conductor", "gate-conductor")


def test_a_gates_impasse_step_is_filled_by_its_conductor(workdir, capsys):
    """The fourth revise mints the impasse outlet, and the hand it stands up
    follows the assembly's conductor the same way the close step does."""
    child = _drive_gate_to_impasse()
    capsys.readouterr()

    assert runmod.state(child)["current"]["form"] == "forms/IMPASSE.toml"
    assert _dispatched_role(child) == ("gate-conductor", "gate-conductor")


# -- 7. the same outlet on `understand`, whose round is local, not dispatched -

# [understand-impasse]
# Rationale: `understand`'s revise is judged by the transition's own panel
#   the same way `plan`'s plan-to-execute panel is, so the driver below
#   reuses `_dispatch_plan_critic` unchanged. What differs is the round
#   itself: `understand` declares no `dispatches`, so a revise refills the
#   segment's step-form (SPEC.toml) as a local step, filled directly at
#   `.agent-work/<wid>/SPEC.toml` -- never a dispatched child the way a plan
#   round, or a gate's implement round, are.
# See: `_drive_to_impasse` and `_drive_gate_to_impasse` above, the same
#   shape for `plan`'s dispatched round and `work`'s undispatched one.


def _drive_understand_to_revise(wid="issue84", findings="gap: assumes a trailing newline exists"):
    """Open a real run-an-issue and drive it through the board and the first
    spec-writer round to the consolidate panel, then have the critic say
    revise -- the send-back `understand`'s rework loop counts."""
    cli.main(["open", "run-an-issue", "--issue", "84", "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    b = pathlib.Path(f".agent-work/{wid}/UNDERSTAND.toml")
    b.write_text(b.read_text().replace(
        'status = "open"',
        'status = "answered"\nanswer = "EOF without a trailing newline only."'))
    _fill_spec(wid)
    cli.main([wid, "submit"])
    _dispatch_plan_critic(wid, verdict="revise", findings=findings)
    return wid


def _understand_round(wid, findings):
    """One more spec-writer round: no rework-form, so the revise refills the
    same step-form (SPEC.toml) as a fresh local step -- then the fresh panel
    says revise again."""
    _fill_spec(wid)
    cli.main([wid, "submit"])
    _dispatch_plan_critic(wid, verdict="revise", findings=findings)


def _drive_understand_to_impasse(wid="issue84"):
    """Three more spec-writer rounds after the first revise, then the fourth
    revise -- the one `understand`'s own `impasse-after` turns into a
    ruling."""
    _drive_understand_to_revise(wid)
    for n in (1, 2, 3):
        _understand_round(wid, f"gap: still assumes a trailing newline ({n})")
    return wid


def test_understands_fourth_revise_mints_the_impasse_form_not_another_spec_round(workdir, capsys):
    """Pins the fix: before it, `understand`'s transition decided on
    `resolution` alone, an outcome table of `pass | revise` with no third
    word, so a spec the panel kept sending back had no exit but a passing
    panel. `understand` now declares `impasse-after`, `impasse-form` and its
    own `decides = "ruling"`, the same shape `plan` already has, so a fourth
    revise mints the impasse form instead of a fifth spec-writer round."""
    wid = _drive_understand_to_impasse()
    capsys.readouterr()

    st = runmod.state(wid)
    assert st["current"]["form"] == "forms/IMPASSE.toml", (
        f"the fourth revise minted {st['current']['form']!r} -- the segment "
        "declares impasse-after = 3, so this round is the ruling")
    assert "trailing newline (3)" in st["current"]["prefill"]["findings"]
    # no fourth panel: another fresh-context reader is the loop, not the way out
    assert not any(s.get("source") == "panel" and s["id"] not in st["done"]
                   for s in st["steps"]), "the impasse minted a panel"
    asm = runmod.load_assembly("run-an-issue")
    assert runmod.rework_rounds(st, asm, "understand") == 3
