"""Prefill reaches every dispatched child, not just a panelist -- and every
plan round dispatches, not only the first.

g1 made the plan segment's first round a dispatch, but left two gaps ruling 6
does not tolerate: a dispatched planner saw none of the run's own prefill --
the consolidated spec it exists to plan from -- and every round after the
first still filled a form on the issue-conductor's own worklist, the very
hand that judges it.

Both are closed here: `_open_child`'s non-panelist branch now merges the
run's own prefill beneath the step's own, the way a panelist's branch already
did (test 1, test 2); and `_mint_segment_round` mints a dispatch, not a
local form, whenever its segment declares `dispatches`, carrying a form
override so a rework round reaches REWORK.toml rather than PLAN.toml
(test 4). Test 3 pins the case the fix must not touch: a gate child's own
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
    consolidate's `carries = true`. This failed before the fix: a dispatched
    planner opened onto `{}`, blind to the spec it exists to plan from."""
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

    This held before the fix too: an unmerged step-only prefill trivially
    "wins" since nothing else is there to lose to. It is pinned here as a
    regression guard, not a proof of the fix -- the collision rule itself
    must survive the merge test 1 proves was missing."""
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
    The run's own prefill (consolidate's spec) now rides beneath it
    too, since the merge in `_open_child` is unconditional on every
    non-panelist dispatch -- ASSEMBLY.toml's own comment on `carries` says
    this is intended, not a side effect to suppress -- but the gate's own
    spec fields, which is what this test pins, held unchanged before the
    fix and must hold unchanged after it: the step's own keys win on
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
    """Before the fix, `_mint_segment_round` always minted a local form --
    the conductor that will judge the round was also the hand that filled
    it, on every round after the first. Now a segment that declares
    `dispatches` mints a dispatch on every round, the rework-form carried
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

    Before the open transition named its carried fields, the run's prefill was
    empty at this point: `carries` lived only on consolidate, so everything a
    principal ruled at open reached nobody and the convention bridging it --
    write the orders into the `issue` artifact too -- was undocumented for
    `authority` and unenforced anywhere."""
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
    """The other half of the same ruling, and the reason the open transition
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
