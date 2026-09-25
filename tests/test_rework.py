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
    _fill_consolidate_route_with_calls,
    _fill_critic,
    _fill_gate_transition_replan,
    _fill_implement,
    _fill_open,
    _fill_plan,
    _fill_plan_route_with_calls,
    _fill_spec,
    _mint_n_gates,
    _response,
    _work_the_board,
    _write_plan_artifact,
)


def _drive_to_revise(wid="issue17", findings="gap: gate 1 is untestable", resolution=None):
    """Open a real run-an-issue, drive it to the plan-to-execute panel, and
    have the critic say revise. One look (2026-09-25): the conductor's own
    default word after a revise is `incorporate` -- one pass by the planner
    over the panel's findings, dispatched the same way the first cut is,
    with no panel on what it returns. `resolution` lets a caller choose a
    different word instead (`rewrite`, `up`, ...); `_dispatch_plan_critic`
    is what actually fills and submits the route form."""
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    _dispatch_and_close_plan(wid)
    _dispatch_plan_critic(wid, verdict="revise", findings=findings, resolution=resolution)
    return wid


def _fresh_mint(st, segment):
    """The segment's live minted round -- not yet done, so an impasse ruling
    already made ahead of it (`impasse-after = 0` puts one before every
    ruled rework round) is never mistaken for the round it ruled into
    being."""
    return next(s for s in st["steps"]
                if s["segment"] == segment and s.get("source") == "mint"
                and s["id"] not in st["done"])


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
    assert _response(child).exists()


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
    asm = runmod.load_assembly("run-an-issue")
    assert runmod.rework_rounds(runmod.state(wid), asm, "plan") == 1

    # carry that plan through to a gate, then replan from the gate transition.
    # The incorporated round mints no panel of its own (`[one-look]`), so the
    # route form stands here alone for the conductor's own fill below.
    _dispatch_rework_round(wid)
    capsys.readouterr()
    _write_plan_artifact(runmod.journal.location(wid) / "plan.md")
    _fill(_response(wid), '''
resolution = "pass"
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
    """The guard reads the producing step's form: `_round_artifact` is what
    a panelist's prefill is built from (`_open_child`), and a rework round's
    ledger is stripped there. No panel reads a plan-seam rework round any
    more (`panel-rounds = "opening"`), so the read is made directly against
    the real round's journal rather than through a panelist that the seam no
    longer dispatches; the conductor's own route room, by the form's own
    words, is meant to see the ledger."""
    wid = _drive_to_revise()
    capsys.readouterr()

    fresh = _fresh_mint(runmod.state(wid), "plan")
    child = f"{wid}.{fresh['id']}"
    cli.main(["open", "cut-a-gate", "--parent", wid, "--step", fresh["id"]])
    child_loc = runmod.journal.location(child)
    _write_plan_artifact(child_loc / "plan.md")
    _fill(_response(child), '''
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
    route_id = st["current"]["id"]
    assert route_id != "plan"  # the fresh route round, not the first round's
    assert not st["current"].get("panel")  # no panel after the opening cut
    asm = runmod.load_assembly("run-an-issue")
    prefill = cli._round_artifact(asm, st, "plan", route_id)
    assert "findings-addressed" not in prefill  # the producer's ledger stays behind
    assert "deleted" not in prefill
    assert prefill["plan"] == f"{child_loc}/plan.md"  # the artifact still rides
    assert prefill["key-terms"] == "waived: none"


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

    # round one: the single planner _mint_segment_round already mints for
    # every later round (design-it-twice's own three-sibling shape, ruling
    # 10, shelved -- #96), measured in its own child's journal first, then
    # folded into the parent at close.
    def _fill_ten_words(w):
        (runmod.journal.location(w) / "plan.md").write_text(
            "one two three four five six seven eight nine ten\n")
        _fill_plan(w)
    child = f"{wid}.plan-1"
    cli.main(["open", "cut-a-gate", "--parent", wid, "--step", "plan-1"])
    _fill_ten_words(child)
    cli.main([child, "submit"])
    assert _plan_measures(child) == [10]
    cli.main([child, "close"])
    capsys.readouterr()

    # the round's return folded its own measure into the parent
    assert _plan_measures(wid) == [10]

    _dispatch_plan_critic(wid, verdict="revise", findings="gap: thin")
    capsys.readouterr()

    # the incorporated round dispatches too -- measured in its own child's
    # journal first, same as round one
    fresh = _fresh_mint(runmod.state(wid), "plan")
    assert fresh["dispatches"] == "cut-a-gate"
    rework_child = f"{wid}.{fresh['id']}"
    cli.main(["open", "cut-a-gate", "--parent", wid, "--step", fresh["id"]])
    rework_art = runmod.journal.location(rework_child) / "plan.md"
    rework_art.write_text("one two three four five six seven eight nine ten eleven twelve\n")
    _fill(_response(rework_child), '''
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

    # both rounds are now in the parent's own journal, in order
    assert _plan_measures(wid) == [10, 12]


# -- 5. one look: incorporate is refused a second time, and an invalid word
#    is refused outright -- there is no impasse ruling left on this seam
#    (ruling, 2026-09-25). Repeated send-backs are bounded by round-cap
#    instead (`_drive_plan_to_pause`, test_nesting.py); `up` is still a
#    conductor's word here, just answered straight off the route form.


def _fill_rework(wid):
    loc = runmod.journal.location(wid)
    _write_plan_artifact(loc / "plan.md")
    _fill(_response(wid), '''
plan = "%s/plan.md"
purpose = "fix the parser to handle EOF without a trailing newline"
scope = "src/parser.c only"
proof = "true"
horizon = "waived: none yet"
findings-addressed = "waived: first pass"
deleted = "waived: nothing"
key-terms = "none"
''' % loc)


def _panel_says_revise(wid, findings):
    """Dispatch every panelist the transition current at `wid` declares,
    each saying revise, and stop -- short of `_dispatch_plan_critic`'s own
    auto-resolution (which always defaults to `incorporate`), so a caller
    can rule its own word on the live revise instead, `up` among them."""
    st = runmod.state(wid)
    step_id = st["current"]["id"]
    panel = next(s for s in st["steps"] if s["id"] == step_id).get("panel") or []
    for n in range(1, len(panel) + 1):
        cli.main(["open", "give-a-verdict", "--parent", wid, "--step", f"{step_id}.p{n}"])
        panelist = f"{wid}.{step_id}.p{n}"
        _fill_critic(panelist, "revise", findings)
        cli.main([panelist, "submit"])
        cli.main([panelist, "close"])


def test_an_invalid_resolution_refuses_rather_than_releasing_the_step(workdir, capsys):
    """No hand-rolled reader: an unhandled `resolution` is refused by the
    same generic mechanism that refuses CYCLE.toml's `decision` -- the
    segment's own declared `[[outcome]]` rows. The old impasse ruling had
    its own version of this test (`ruling = "keep going"`); this is the
    same guard at the one route form the seam now has."""
    wid = "issue17"
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    _dispatch_and_close_plan(wid)
    _dispatch_plan_critic(wid, verdict="pass")
    capsys.readouterr()
    before = len(runmod.journal.read(wid))
    _fill(_response(wid), 'resolution = "keep going"\n')
    with pytest.raises(SystemExit) as e:
        cli.main([wid, "submit"])
    msg = str(e.value)
    assert "resolution" in msg and "is not an outcome this step declares" in msg
    assert "pass | revise | incorporate | rewrite | up" in msg  # the assembly's own outcome rows
    assert len(runmod.journal.read(wid)) == before  # not even the submit landed
    assert runmod.state(wid)["current"]["form"] == "forms/PLAN_TO_EXECUTE.toml"


def test_a_second_incorporate_on_the_same_cut_is_refused(workdir, capsys):
    """`_check_one_look`: the writer gets one pass over the panel's findings;
    a second `incorporate` on the round it returns is refused before the
    submit lands, the release-or-rewrite fork the ruling actually drew."""
    wid = _drive_to_revise()
    capsys.readouterr()
    _dispatch_rework_round(wid)
    capsys.readouterr()
    before = len(runmod.journal.read(wid))
    _fill(_response(wid), 'resolution = "incorporate"\n')
    with pytest.raises(SystemExit) as e:
        cli.main([wid, "submit"])
    msg = str(e.value)
    assert "resolution" in msg
    assert "already incorporated" in msg
    assert len(runmod.journal.read(wid)) == before  # not even the submit landed


def test_up_pauses_the_plan_seam_rather_than_releasing(workdir, capsys):
    """commitment 3's ruling (issue84.g2): `up` stands an ask one tier up
    (self-minted here: this run's own run-an-issue has no parent) and the
    run stays open, rather than walking to its terminal form the way a bare
    `release` did. One look (2026-09-25) moved this off a dedicated ruling
    form onto the seam's own route form -- `up` still carries the panel's
    findings forward, now through the `calls` table rather than a `why`
    field of its own."""
    wid = "issue17"
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    _dispatch_and_close_plan(wid)
    _panel_says_revise(wid, "gate 1 is untestable")
    before = len(runmod.state(wid)["steps"])
    capsys.readouterr()
    _fill_plan_route_with_calls(wid, "up", ("gate 1 is untestable", "severe"))
    cli.main([wid, "submit"])
    capsys.readouterr()

    st = runmod.state(wid)
    assert st["open"] and not st["awaiting_close"], "up must pause the run, not close it"
    assert len(st["steps"]) == before + 2, "up must mint an ask and a marker"
    ask = st["current"]
    assert ask["form"] == "skills/gate-conductor/forms/ASK.toml", (
        f"up must mint an ask, not release -- current is {ask!r}")
    assert ask["resumes"] == wid
    assert "gate 1 is untestable" in ask["prefill"].get("findings", "")


def test_up_pauses_the_understand_seam_rather_than_releasing(workdir, capsys):
    """The same ruling (commitment 3), at `understand`'s own seam -- named
    separately from the test above since the two segments dispatch their
    rounds differently even though `up` itself is one policy."""
    wid = "issue84"
    cli.main(["open", "run-an-issue", "--issue", "84", "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    b = pathlib.Path(f".agent-work/{wid}/UNDERSTAND.toml")
    b.write_text(b.read_text().replace(
        'status = "open"',
        'status = "answered"\nanswer = "EOF without a trailing newline only."'))
    _fill_spec(wid)
    cli.main([wid, "submit"])
    _panel_says_revise(wid, "gap: assumes a trailing newline exists")
    before = len(runmod.state(wid)["steps"])
    capsys.readouterr()
    _fill_consolidate_route_with_calls(
        wid, "up", ("gap: assumes a trailing newline exists", "severe"))
    cli.main([wid, "submit"])
    capsys.readouterr()

    st = runmod.state(wid)
    assert st["open"] and not st["awaiting_close"], "up must pause the run, not close it"
    assert len(st["steps"]) == before + 2, "up must mint an ask and a marker"
    ask = st["current"]
    assert ask["form"] == "skills/gate-conductor/forms/ASK.toml", (
        f"up must mint an ask, not release -- current is {ask!r}")
    assert ask["resumes"] == wid
    assert "assumes a trailing newline exists" in ask["prefill"].get("findings", "")


# -- 6. the same outlet on run-a-gate, which has no rework form ---------------


def _drive_gate_to_impasse(child="issue17.g1"):
    """Three review revises on one diff, each disposed of on the review
    transition's own conductor form: the first two refill the interior
    through its `rework`, and the third is the one the outlet takes (ruling,
    2026-09-02: at most three critic dispatches per artifact -- `work`'s own
    `impasse-after` is 2). A revise releases on its own now, so the form's
    `rework` is the path the mint -- and the count with it -- actually runs
    on. run-a-gate's work segment declares no rework-form, so every refill
    mints the step-form again; the count is of those, and the opening step
    is not one."""
    _mint_n_gates(1)
    cli.main(["open", "run-a-gate", "--parent", "issue17", "--step", "g1"])
    for n in (1, 2, 3):
        _fill_implement(child, runmod.state(child)["current"]["id"])
        cli.main([child, "submit"])
        _dispatch_review(child, verdict="revise",
                         findings=f"gap: the spec asks for something untestable ({n})")
    return child


def test_a_third_revise_mints_the_impasse_form(workdir, capsys):
    child = _drive_gate_to_impasse()
    capsys.readouterr()

    st = runmod.state(child)
    assert st["current"]["form"] == "forms/IMPASSE.toml"
    assert "untestable (3)" in st["current"]["prefill"]["findings"]
    asm = runmod.load_assembly("run-a-gate")
    assert runmod.rework_rounds(st, asm, "work") == 2


def test_a_gates_advance_mints_its_transition_and_the_round_is_disposed_of(workdir, capsys):
    """`advance` mints one transition step, over the live revise, and never a
    fresh panel. It names `review` rather than the ruling segment's own
    `select`, because select would put a fourth reader on the diff -- the
    loop, not the way out of it. What the conductor is stood on is the route
    form alone, and `close` there walks the gate to GATE_CLOSE."""
    child = _drive_gate_to_impasse()
    capsys.readouterr()
    before = len(runmod.state(child)["steps"])
    _fill(_response(child),
          'ruling = "advance"\nwhy = "both reviews landed on the spec"\n')
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
    _fill(_response(child),
          'ruling = "rework"\nwhy = "round three rewrites the check, not the diff"\n')
    cli.main([child, "submit"])
    capsys.readouterr()

    st = runmod.state(child)
    assert st["current"]["form"] == "skills/implementer/forms/IMPLEMENT.toml"
    # The findings the displaced round was carrying ride into it, unfiltered:
    # the ruling step carries no `calls` table, so `_blocking_calls` reads
    # `None` and this caller's prefill is exactly what it always was. Asserted
    # on the content, not only on the form -- the neighbouring
    # `test_a_third_revise_mints_the_impasse_form` uses the same shape,
    # and without it a filter that dropped everything would pass here.
    assert "untestable (3)" in st["current"]["prefill"]["findings"]


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
    """The third revise mints the impasse outlet, and the hand it stands up
    follows the assembly's conductor the same way the close step does."""
    child = _drive_gate_to_impasse()
    capsys.readouterr()

    assert runmod.state(child)["current"]["form"] == "forms/IMPASSE.toml"
    assert _dispatched_role(child) == ("gate-conductor", "gate-conductor")


# -- 7. the same one-look shape on `understand`, whose round is local, not
#    dispatched --------------------------------------------------------------

# [understand-one-look]
# Rationale: `understand`'s revise is judged by the transition's own panel
#   the same way `plan`'s plan-to-execute panel is, so the driver below
#   reuses `_dispatch_plan_critic` unchanged. What differs is the round
#   itself: `understand` declares no `dispatches` and no `rework-form`, so
#   an `incorporate` (or a `rewrite`) refills the segment's own step-form
#   (SPEC.toml) as a local step, filled directly at
#   `.agent-work/<wid>/SPEC.<step-id>.toml` -- never a dispatched child the
#   way a plan round, or a gate's implement round, are.
# See: `_drive_to_revise` and `_drive_gate_to_impasse` above, the same
#   shape for `plan`'s dispatched round and `work`'s undispatched one.


def _drive_understand_to_revise(wid="issue84", findings="gap: assumes a trailing newline exists",
                                resolution=None):
    """Open a real run-an-issue and drive it through the board and the first
    spec-writer round to the consolidate panel, then have the critic say
    revise. `resolution` is forwarded to `_dispatch_plan_critic`, which
    defaults to `incorporate` -- the writer's own one pass over the panel's
    findings."""
    cli.main(["open", "run-an-issue", "--issue", "84", "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    b = pathlib.Path(f".agent-work/{wid}/UNDERSTAND.toml")
    b.write_text(b.read_text().replace(
        'status = "open"',
        'status = "answered"\nanswer = "EOF without a trailing newline only."'))
    _fill_spec(wid)
    cli.main([wid, "submit"])
    _dispatch_plan_critic(wid, verdict="revise", findings=findings, resolution=resolution)
    return wid


def test_understands_revise_mints_the_step_form_with_findings_as_prefill(workdir, capsys):
    """`understand` declares no rework-form, so an `incorporate` here refills
    the segment's own step-form (SPEC.toml) as a fresh local step -- never a
    dispatched child, since this segment declares no `dispatches` at all --
    carrying the panel's findings as prefill, no panel on the round it
    mints. The plan seam's own counterpart is
    `test_revise_mints_rework_form_with_findings_as_prefill` above; this is
    what the same one-look mechanism looks like where the segment has no
    rework-form of its own to override with."""
    wid = _drive_understand_to_revise()
    capsys.readouterr()

    st = runmod.state(wid)
    fresh = _fresh_mint(st, "understand")
    assert not fresh.get("dispatches")
    assert fresh["form"] == "skills/spec-writer/forms/SPEC.toml"
    assert "assumes a trailing newline exists" in fresh["prefill"]["findings"]
    assert st["current"]["id"] == fresh["id"]
    assert not st["current"].get("panel"), "no panel after the opening cut"


# -- 8. `_mint_segment_round`'s fresh transition round carries `filler` too --


def test_a_revised_understands_re_minted_transition_carries_its_declared_filler(
        workdir, capsys):
    """`understand` has a real interior (a board), so `_mint_segment_round`'s
    `fresh` transition dict used to set `filler` only inside the branch a
    segment with an interior never takes -- CONSOLIDATE's own re-minted round
    carried no `filler` key at all, though the transition declares one.
    Confirmed against the assembly's own declared value, the same one
    `skeleton()` gives round one."""
    wid = _drive_understand_to_revise()
    capsys.readouterr()

    st = runmod.state(wid)
    fresh = next(s for s in st["steps"]
                if s.get("source") == "panel" and s["segment"] == "understand")
    asm = runmod.load_assembly("run-an-issue")
    seg = next(s for s in asm["segment"] if s["id"] == "understand")
    assert fresh["filler"] == seg["transition"]["filler"] == "conductor"


def test_a_revised_understands_re_minted_transition_carries_its_declared_guards(
        workdir, capsys):
    """#110: the same `fresh` dict that used to drop `filler` also dropped
    `validates` and `carries`. Both are read as a bare `step.get(...)`, so a
    re-minted CONSOLIDATE skipped the board check on release and folded no
    spec into the run's prefill -- silently, with nothing refused and nothing
    journaled. Confirmed against the assembly's own declared values, the same
    ones `skeleton()` gives round one."""
    wid = _drive_understand_to_revise()
    capsys.readouterr()

    st = runmod.state(wid)
    fresh = next(s for s in st["steps"]
                 if s.get("source") == "panel" and s["segment"] == "understand")
    t = next(s for s in runmod.load_assembly("run-an-issue")["segment"]
             if s["id"] == "understand")["transition"]
    assert fresh["validates"] == t["validates"] == "board"
    assert fresh["carries"] == t["carries"]


def test_a_gates_reworked_select_carries_the_conductor_default(workdir, capsys):
    """`work`'s own transition (`select`) declares no `filler` at all -- its
    re-minted round used to carry none either, leaving `role_of`/`hat` to
    guess. Confirmed the re-mint carries the same bare `"conductor"` default
    `skeleton()` already gives round one's own `select`, minted at `open`."""
    _mint_n_gates(1)
    cli.main(["open", "run-a-gate", "--parent", "issue17", "--step", "g1"])
    child = "issue17.g1"
    _fill_implement(child, runmod.state(child)["current"]["id"])
    cli.main([child, "submit"])
    _dispatch_review(child, verdict="revise", findings="gap: untestable")
    capsys.readouterr()

    st = runmod.state(child)
    round_one_select = next(s for s in st["steps"] if s["id"] == "select")
    fresh_select = next(s for s in st["steps"]
                        if s.get("source") == "panel" and s["segment"] == "work")
    assert fresh_select["filler"] == round_one_select["filler"] == "conductor"
