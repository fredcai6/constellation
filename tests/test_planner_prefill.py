"""Prefill reaches every dispatched child, not just a panelist -- and every
plan round dispatches, not only the first.

A dispatched planner must see the run's own prefill -- the consolidated spec
it exists to plan from -- and no round of the plan segment fills a form on
the issue-conductor's own worklist, the very hand that judges it.

`_open_child`'s non-panelist branch merges the run's own prefill beneath the
step's own, the way a panelist's branch does (test 1, test 2); and `_mint_segment_round` mints a dispatch, not a
local form, whenever its segment declares `dispatches`, carrying a form
override so a rework round reaches REWORK.toml rather than PLAN.toml
(test 4). Test 3 pins the case the merge must not touch: a gate child's own
spec, unaffected by the run-level prefill riding beneath it.
"""

from engine import cli, journal, run as runmod

from test_nesting import (
    _dispatch_and_close_plan,
    _dispatch_plan_critic,
    _fill_consolidate,
    _fill_open,
    _mint_first_gate,
    _work_the_board,
)

# -- 1. a dispatched planner's journal carries the parent's prefill keys -----


def test_a_dispatched_planners_journal_carries_the_parents_prefill_keys(workdir, capsys):
    """`plan-1`'s own prefill (minted by `skeleton()`) is empty -- the spec
    it plans from lives only in the run's own prefill, carried down from
    consolidate's `carries = true`. Without the merge a dispatched
    planner opens onto `{}`, blind to the spec it exists to plan from."""
    wid = "issue17"
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    capsys.readouterr()

    cli.main(["open", "cut-a-gate", "--parent", wid, "--step", "plan-1"])
    capsys.readouterr()

    prefill = runmod.state(f"{wid}.plan-1")["prefill"]
    assert prefill["spec"] == f".agent-work/{wid}/spec.md"
    assert prefill["key-terms"] == "waived: none"


# -- 2. a step's own prefill wins over the run's on a shared key -------------


def test_a_steps_own_prefill_wins_over_the_runs_on_a_shared_key(workdir, capsys):
    """A dispatch step's own prefill is layered over the run's, not under
    it -- proved directly on the journal, the way test_planner_dispatch.py
    proves a dispatch step's shape generally.

    An unmerged step-only prefill trivially "wins" since nothing else is
    there to lose to, so this guards the collision rule itself surviving the
    merge test 1 proves."""
    journal.append("i1", "run", title="t", assembly="run-an-issue")
    journal.append("i1", "prefill", fields={"shared": "run"})
    journal.append("i1", "step", id="plan-1", segment="plan", dispatches="cut-a-gate",
                   filler="planner", prefill={"shared": "step"}, anchor=False,
                   terminal=False, validates="", source="open")
    capsys.readouterr()

    cli.main(["open", "cut-a-gate", "--parent", "i1", "--step", "plan-1"])
    capsys.readouterr()

    assert runmod.state("i1.plan-1")["prefill"]["shared"] == "step"


# -- 3. a gate child still receives its own spec unchanged -------------------


def test_a_gate_child_still_receives_its_own_spec_unchanged(workdir, capsys):
    """The execute segment's dispatch is a gate spec, not a planner's cut.
    The run's own prefill (consolidate's spec) rides beneath it
    too, since the merge in `_open_child` is unconditional on every
    non-panelist dispatch -- ASSEMBLY.toml's own comment on `carries` says
    this is intended, not a side effect to suppress -- but the gate's own
    spec fields, which is what this test pins, hold unchanged: the step's own keys win on
    collision, and a gate spec duplicates nothing the run-level prefill
    holds."""
    _mint_first_gate()
    capsys.readouterr()

    cli.main(["open", "run-a-gate", "--parent", "issue17", "--step", "g1"])
    capsys.readouterr()

    prefill = runmod.state("issue17.g1")["prefill"]
    assert prefill["purpose"].startswith("fix the parser")
    assert prefill["scope"] == "src/parser.c only"
    assert prefill["proof"] == "true"


# -- 4. an incorporation round opens as a dispatch and reaches the rework form


def test_an_incorporation_round_opens_as_a_dispatch_and_reaches_the_rework_form(workdir, capsys):
    """A segment that declares `dispatches` mints a dispatch on every round,
    not a local form the judging conductor would fill itself, the rework-form carried
    as a form override the dispatched child fills instead of its own
    PLAN.toml default."""
    wid = "issue17"
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    _dispatch_and_close_plan(wid)
    capsys.readouterr()

    _dispatch_plan_critic(wid, verdict="revise", findings="gap: gate 1 is untestable")
    capsys.readouterr()

    st = runmod.state(wid)
    fresh = next(s for s in st["steps"]
                if s["segment"] == "plan" and s.get("source") == "mint" and s.get("dispatches"))
    assert fresh["dispatches"] == "cut-a-gate"   # every round dispatches, not only the first
    assert st["current"]["id"] == fresh["id"]

    cli.main(["open", "cut-a-gate", "--parent", wid, "--step", fresh["id"]])
    capsys.readouterr()

    child = f"{wid}.{fresh['id']}"
    assert runmod.state(child)["current"]["form"] == "skills/planner/forms/REWORK.toml"


# -- 5. open carries the principal's authority, and not the seed questions ---


def test_a_gate_child_receives_the_principals_authority(workdir, capsys):
    """`authority` is the principal's own orders -- who the principal is, what
    the run owns, where gaps go. It is recorded at `open` and read segments
    later by a child that never met the human, so it has to ride the run's
    prefill the whole way down.

    Were the open transition not to name its carried fields, the run's prefill
    would be empty at this point (`carries` on consolidate alone), and
    everything a principal rules at open would reach nobody."""
    wid = "issue18"
    cli.main(["open", "run-an-issue", "--issue", "18", "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    capsys.readouterr()

    cli.main(["open", "cut-a-gate", "--parent", wid, "--step", "plan-1"])
    capsys.readouterr()

    prefill = runmod.state(f"{wid}.plan-1")["prefill"]
    assert "Principal: Tommy, live." in prefill["authority"]
    assert prefill["issue"] == f".agent-work/{wid}/issue.md"


def test_open_does_not_carry_its_seed_questions(workdir, capsys):
    """The other half of the same promise, and the reason the open transition
    names its fields instead of carrying `true`: `questions` is a starting cut
    the board supersedes the moment it is worked. A frozen copy of the seeds
    riding in every later child's prefill reads as orders it is not.

    This is the half that regresses silently -- `carries = true` would pass
    the test above and fail here -- so it is pinned on its own."""
    wid = "issue19"
    cli.main(["open", "run-an-issue", "--issue", "19", "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    capsys.readouterr()

    prefill = runmod.state(wid)["prefill"]
    assert "authority" in prefill      # the fold happened at all
    assert "questions" not in prefill  # and it was selective
