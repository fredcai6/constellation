"""Nesting: dispatch, prefill, returns, close, and amend.

This drives the real `run-an-issue` and `run-a-gate` assemblies end to end --
not fixtures. A gate spec minted from PLAN_TO_EXECUTE.toml becomes a child
run's opening orders; the child's close stamps a return that completes the
parent's dispatch step; `close` and `amend` round out the verbs `main()`
dispatches.
"""

import json
import pathlib
import sys

import pytest

from engine import cli, journal, render, review_yield, run as runmod
from gitremote import read_archived, stub_gh


def _fill(path, text):
    path.write_text(text)


def _response(wid):
    """Where the step now current at `wid` takes its answer -- asked of the
    engine rather than spelled, since the name is the engine's to choose.
    `_response_path` folded the step id into the live filename (#118) so
    that spelling it here would have been wrong exactly when it mattered:
    the fixtures that hardcoded it never saw a second round at the same
    seam land on top of the first."""
    st = runmod.state(wid)
    return cli._response_path(st, st["current"])


def _write_plan_artifact(path, text="1. approach: adjust the loop bound.\n"
                                    "2. risk: none identified once tested.\n"):
    """The real file an artifact-kind `plan` field must point at (#45):
    `_check_artifact` (engine/cli.py) now refuses a submit whose value does
    not resolve to a readable path, so every fixture that answers one has to
    back it with content -- never overwriting a path a caller already
    seeded with content of its own, since some tests plant an exact word
    count there before filling the form."""
    path = pathlib.Path(path)
    if not path.exists():
        path.write_text(text)


def _fill_open(wid):
    # the `issue` field names a file in the work location, so write one
    issue = pathlib.Path(f".agent-work/{wid}/issue.md")
    _fill(issue, "The parser drops the last record of a file with no "
                 "trailing newline.\n")
    _fill(_response(wid), f'''
issue = "{issue}"

authority = """
Principal: Tommy, live. I own driving this to a merged fix; gaps go to him."""

[[questions]]
question = "Which inputs drop the last record?"
type = "fact"
''')


def _work_the_board(wid):
    """Resolve the seeded board, then take the spec-writer's own round
    through its cold panel -- both now stand between the board and
    consolidate, which validates the board (the engine refuses to leave
    understand with an unresolved row) but no longer drafts from it. A
    caller that used to reach consolidate straight off the board reaches it
    here instead, the spec already passed critique."""
    b = pathlib.Path(f".agent-work/{wid}/UNDERSTAND.toml")
    b.write_text(b.read_text().replace(
        'status = "open"',
        'status = "answered"\nanswer = "EOF without a trailing newline only."'))
    _fill_spec(wid)
    cli.main([wid, "submit"])
    _dispatch_plan_critic(wid)


def _fill_spec(wid):
    loc = pathlib.Path(f".agent-work/{wid}")
    (loc / "spec.md").write_text(
        "1. Fix the parser to handle EOF with no trailing newline.\n")
    _fill(_response(wid), 'spec = "%s/spec.md"\n' % loc)


def _fill_consolidate(wid, resolution="pass", calls=""):
    """The conductor's own route form at the understand seam (ruling 3's
    2026-09-03 follow-up, and one look, 2026-09-25): `resolution` is now the
    conductor's own typed decision, and the release-only fields -- `spec`,
    `key-terms`, `settle` -- are filled only where the round releases with
    something to record. `calls` (default none) is either one or more
    `[[calls]]` blocks, verbatim, for a caller narrowing an `incorporate` to
    the `writer` findings alone -- see `_fill_consolidate_route_with_calls`
    below -- or a bare `orders = "..."` line for a `rewrite`."""
    body = 'resolution = "%s"\n' % resolution
    if resolution in ("pass", "revise"):
        body += ('\nspec = ".agent-work/%s/spec.md"\n'
                 'key-terms = "waived: none"\n'
                 'settle = "waived: none"\n') % wid
    if calls:
        body += "\n" + calls
    _fill(_response(wid), body)


def _fill_consolidate_route_with_calls(wid, resolution, *calls):
    """The understand seam's own half of `_route_with_calls`
    (test_verdict_route.py): one `[[calls]]` block per (finding, call)
    pair, ruled by the conductor."""
    blocks = "".join('[[calls]]\nfinding = "%s"\ncall = "%s"\n\n' % c for c in calls)
    _fill_consolidate(wid, resolution, calls=blocks)


def _fill_plan(wid, purpose="fix the parser to handle EOF without a trailing newline",
               scope="src/parser.c only", proof="true", model="", direction=""):
    """Fill PLAN.toml at `wid`'s own current step -- `journal.location`,
    not string interpolation, so a dotted child id (`issue17.plan-1`, the
    first round's own dispatch) nests instead of colliding with a literal
    dot in a directory name. Also what a `replan` mints locally, since that
    round takes the same step-form the first round does. The gate spec
    (purpose/scope/proof, optional model/direction) is the round's own
    artifact now -- plan-to-execute projects it, it does not retype it."""
    loc = journal.location(wid)
    extra = ""
    if model:
        extra += 'model = "%s"\n' % model
    if direction:
        extra += 'direction = "%s"\n' % direction
    _write_plan_artifact(loc / "plan.md")
    _fill(_response(wid), '''
plan = "%s/plan.md"
purpose = "%s"
scope = "%s"
proof = "%s"
%shorizon = "waived: none yet"
key-terms = "waived: none"
''' % (loc, purpose, scope, proof, extra))


def _dispatch_and_close_plan(parent_wid, step_id="plan-1", fill_fn=None):
    """Open cut-a-gate at the plan segment's dispatch step, fill whichever
    form its own step names, submit and close it -- give-a-verdict's own
    shape, one form deep, so unlike `_dispatch_and_close_child` there is no
    separate review loop to drive. Every round dispatches, not only the
    first: `step_id` names which fresh mint to open, and `fill_fn` (default
    `_fill_plan`) lets a caller pass `_fill_rework` for a rework round, whose
    dispatch step carries a form override selecting REWORK.toml."""
    panel = next(s for s in runmod.state(parent_wid)["steps"] if s["id"] == step_id).get("panel")
    if not panel:
        cli.main(["open", "cut-a-gate", "--parent", parent_wid, "--step", step_id])
        child_wid = f"{parent_wid}.{step_id}"
        (fill_fn or _fill_plan)(child_wid)
        cli.main([child_wid, "submit"])
        cli.main([child_wid, "close"])
        return child_wid
    for n in range(1, len(panel) + 1):
        cli.main(["open", "give-a-verdict", "--parent", parent_wid, "--step", f"{step_id}.p{n}"])
        child_wid = f"{parent_wid}.{step_id}.p{n}"
        (fill_fn or _fill_plan)(child_wid)
        cli.main([child_wid, "submit"])
        cli.main([child_wid, "close"])
    return child_wid


def _fill_plan_to_execute(wid, resolution="pass", calls=""):
    """The conductor's own route form at the plan seam (ruling 3, and one
    look, 2026-09-25): `resolution` is now the conductor's own typed
    decision, and `plan` -- the pointer that projects the gate -- is filled
    only where the round releases with something to project. `calls`
    (default none) is either one or more `[[calls]]` blocks, verbatim, for a
    caller narrowing an `incorporate` to the `writer` findings alone -- see
    `_fill_plan_route_with_calls` below -- or a bare `orders = "..."` line
    for a `rewrite`."""
    body = 'resolution = "%s"\n' % resolution
    if resolution in ("pass", "revise"):
        _write_plan_artifact(pathlib.Path(f".agent-work/{wid}/plan.md"))
        body += '\nplan = ".agent-work/%s/plan.md"\n' % wid
    if calls:
        body += "\n" + calls
    _fill(_response(wid), body)


def _fill_plan_route_with_calls(wid, resolution, *calls):
    """The plan seam's own half of `_route_with_calls` (test_verdict_route.py):
    one `[[calls]]` block per (finding, call) pair, ruled by the conductor."""
    blocks = "".join('[[calls]]\nfinding = "%s"\ncall = "%s"\n\n' % c for c in calls)
    _fill_plan_to_execute(wid, resolution, calls=blocks)


def _fill_implement(wid, step_id):
    _fill(_response(wid), '''
change = "adjusted the loop bound in src/parser.c"
deviations = "waived: none"
''')


def _fill_gate_close(wid):
    _fill(_response(wid),
          'commit = "refuse-or-name-the-escape @ 0000000"\nresidue = "nothing surprising"\n')


def _fill_review(wid, verdict="pass", findings="none: waived: clean"):
    _fill(_response(wid), '''
verify = "read the diff line by line"
findings = "%s"
verdict = "%s"
''' % (findings, verdict))


def _fill_route(wid, resolution):
    """The conductor's own half of the review step: where the round the panel
    just judged goes next."""
    _fill(_response(wid), 'resolution = "%s"\n' % resolution)


def _dispatch_review(child_wid, verdict="pass", findings="none: waived: clean",
                     resolution=None):
    """Open every panelist the current review step's own declared panel
    names -- three on the opening round, the single `rework:` reader on
    every round after (`[rework-panel]`, engine/cli.py) -- fill and close
    each, then dispose of the round on the review step's own conductor
    form: the same nesting mechanics as a gate dispatch, one step down, plus
    the second voice. Neither of the panel's words acts on its own: both
    release, so the step stays open and `resolution` is what mints (or does
    not). It defaults to the answer the verdict argues for -- `rework`
    after a revise, `close` after a pass. Returns the step id that fired,
    since every round mints a fresh review step."""
    step_id = runmod.state(child_wid)["current"]["id"]
    panel = next(s for s in runmod.state(child_wid)["steps"]
                if s["id"] == step_id).get("panel") or []
    for n in range(1, len(panel) + 1):
        cli.main(["open", "give-a-verdict", "--parent", child_wid, "--step", f"{step_id}.p{n}"])
        panelist = f"{child_wid}.{step_id}.p{n}"
        _fill_review(panelist, verdict, findings)
        cli.main([panelist, "submit"])
        cli.main([panelist, "close"])
    _fill_route(child_wid, resolution or
                ("rework" if verdict == "revise" else "close"))
    cli.main([child_wid, "submit"])
    return step_id


PURPOSE_HOLDS = ('purpose-holds = "the parser reads EOF without a trailing newline; '
                 're-ran the gate\'s own check"\n')


def _fill_gate_transition(wid):
    _fill(_response(wid), PURPOSE_HOLDS + '''
findings = "the fix landed cleanly, no follow-on scope"
plan-holds = "advance"
''')


def _fill_gate_transition_drop(wid, gate_id):
    _fill(_response(wid), PURPOSE_HOLDS + '''
findings = "no longer needed"
plan-holds = "drop %s"
''' % gate_id)


def _fill_gate_transition_remint(wid, purpose="a corrected gate", scope="src/ only",
                                 proof="true"):
    _fill(_response(wid), PURPOSE_HOLDS + '''
findings = "the spec was wrong, needs a redo"
plan-holds = "remint"

[[gate-spec]]
purpose = "%s"
scope = "%s"
proof = "%s"
''' % (purpose, scope, proof))


def _fill_gate_transition_replan(wid, findings="the cut was wrong from the start"):
    _fill(_response(wid), PURPOSE_HOLDS + '''
findings = "%s"
plan-holds = "replan"
''' % findings)


def _fill_gate_transition_remint_no_spec(wid):
    _fill(_response(wid), PURPOSE_HOLDS + '''
findings = "reconsidering, but not sure what yet"
plan-holds = "remint"
''')


def _mint_n_gates(n, wid="issue17"):
    """`g1` from a real plan round and a real critic pass; `g2..gN` (when
    `n` > 1) seeded directly as journal entries in the shape `_mint_gates`
    itself produces -- the same move
    `test_drop_pairs_by_shared_child_not_by_id_suffix` already makes for its
    own "odd-one" pair. The plan segment mints one gate per round now, so
    getting several pending at once for a drop/remint/replan test is no
    longer something one submit can do; those tests are about what happens
    to gates once they exist, not about how they got there."""
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    _dispatch_and_close_plan(wid, fill_fn=lambda w: _fill_plan(
        w, purpose="gate 1 purpose", scope="gate 1 scope", proof="true"))
    _dispatch_plan_critic(wid)
    _fill_plan_to_execute(wid)
    cli.main([wid, "submit"])
    for i in range(2, n + 1):
        gid, child = f"g{i}", f"{wid}.g{i}"
        journal.append(wid, "step", id=gid, segment="execute", dispatches="run-a-gate",
                       prefill={"purpose": "gate %d purpose" % i, "scope": "gate %d scope" % i,
                                "proof": "true"},
                       child=child, anchor=False, terminal=False, source="mint")
        journal.append(wid, "step", id=f"{gid}-adjudicate", segment="execute",
                       form="forms/GATE_TRANSITION.toml", filler="conductor", child=child,
                       anchor=False, terminal=False, validates="", source="mint")


def _fill_close(wid):
    _fill(_response(wid), '''
disposition = "merged to main"
residue = "waived: none"
''')


def _fill_critic(wid, verdict, findings="none: waived: clean"):
    """The plan panel declares CRITIC.toml, which has no `verify` field -- a
    critic judges the plan's soundness, not what it exercised."""
    _fill(_response(wid),
          'findings = "%s"\nverdict = "%s"\n'
          % (findings, verdict))


def _fill_plan_rework(wid, purpose="fix the parser to handle EOF without a trailing newline",
                      scope="src/parser.c only", proof="true",
                      findings_addressed="waived: first pass", deleted="waived: nothing"):
    """A revise round's dispatched child fills REWORK.toml, not PLAN.toml --
    the form override `_mint_segment_round` carries on the fresh interior
    step."""
    loc = journal.location(wid)
    _write_plan_artifact(loc / "plan.md")
    _fill(_response(wid), '''
plan = "%s/plan.md"
purpose = "%s"
scope = "%s"
proof = "%s"
horizon = "waived: none yet"
findings-addressed = "%s"
deleted = "%s"
key-terms = "waived: none"
''' % (loc, purpose, scope, proof, findings_addressed, deleted))


def _drive_plan_to_pause(wid, findings="gap: wrong artifact entirely"):
    """`rewrite-cap = 1` is the only outlet left on this seam (ruling,
    2026-09-25): one major rewrite, then the question goes up. The opening
    cut's own revise is an `incorporate`, spent once per artifact and
    minting no panel; the conductor rewrites what comes back -- the one
    rewrite -- and that fresh cut's own panel finds the same gap, so the
    second `rewrite` pauses the seam rather than minting a third cut."""
    _dispatch_plan_critic(wid, verdict="revise", findings=findings, resolution="incorporate")
    st = runmod.state(wid)
    reworked = next(s for s in st["steps"]
                    if s["segment"] == "plan" and s.get("source") == "mint"
                    and s["id"] not in st["done"] and s.get("dispatches"))
    _dispatch_and_close_plan(wid, reworked["id"], _fill_plan_rework)
    # round two has no panel (`incorporate` mints none) -- the conductor
    # rewrites it directly: the seam's one rewrite
    _fill_plan_to_execute(wid, "rewrite", calls='orders = "%s -- replace it in kind"\n' % findings)
    cli.main([wid, "submit"])

    st = runmod.state(wid)
    fresh = next(s for s in st["steps"]
                 if s["segment"] == "plan" and s.get("source") == "mint"
                 and s["id"] not in st["done"] and s.get("dispatches"))
    _dispatch_and_close_plan(wid, fresh["id"], _fill_plan)
    # the rewrite's own panel: a second rewrite goes up instead
    _dispatch_plan_critic(wid, verdict="revise", findings=findings, resolution="rewrite")


def _rule_impasse(wid, ruling="rework", why="the next round replaces the proof in kind"):
    """Rule on the impasse form the run is standing on -- run-a-gate's
    `work` segment, unchanged by the one-look ruling (2026-09-25): only
    run-an-issue's `understand` and `plan` seams lost their impasse outlet,
    since a spec or a cut gets one round of review now, not a loop of them."""
    st = runmod.state(wid)
    assert st["current"].get("form") == "forms/IMPASSE.toml", (
        f"not standing on the impasse form: {st['current']}")
    _fill(_response(wid), 'ruling = "%s"\nwhy = """%s"""\n' % (ruling, why))
    cli.main([wid, "submit"])


def _dispatch_plan_critic(wid, verdict="pass", findings="none: waived: clean",
                          resolution=None):
    """Open every panelist the current transition's own panel declares --
    plan-to-execute's or consolidate's, whichever is `current` -- fill and
    close each. Both of a two-voices transition's own words release (ruling
    3, and its 2026-09-03 follow-up at consolidate), so the step holds open
    for its own form either way, the same shape run-a-gate's review/ROUTE.toml
    already has: where the panel just returned is still `current` after this.
    A `verdict="revise"` also disposes of the round on that form, defaulting
    to `resolution` (`"incorporate"` unless the caller names another).

    A round with no panel -- every plan-seam round after the run's opening
    cut, save a `rewrite`'s own fresh one (`panel-rounds = "opening"`,
    `[one-look]`) -- dispatches nothing; a `revise` there is the
    conductor's own send-back, `findings` riding as its `orders`. One look
    (2026-09-25): a spec or a cut gets no impasse outlet any more -- the
    first revise is `incorporate` by default here, and a caller wanting a
    `rewrite` instead names `resolution="rewrite"`, which always carries
    `findings` forward as `orders` (a rewrite starts from orders alone,
    whether or not a panel judged the round it replaces).

    Driven off the assembly's own panel length rather than a pinned count:
    the step completes on the last verdict, so a test that closes one of
    three leaves the transition outstanding. `verdict` and `findings` apply
    to every panelist; a caller wanting them to differ opens its own.
    """
    st = runmod.state(wid)
    step_id = st["current"]["id"]
    panel = next(s for s in st["steps"] if s["id"] == step_id).get("panel") or []
    for n in range(1, len(panel) + 1):
        cli.main(["open", "give-a-verdict", "--parent", wid, "--step", f"{step_id}.p{n}"])
        panelist = f"{wid}.{step_id}.p{n}"
        _fill_critic(panelist, verdict, findings)
        cli.main([panelist, "submit"])
        cli.main([panelist, "close"])
    current = runmod.state(wid).get("current")
    form = current.get("form") if current else ""
    if (verdict == "revise" and current and current["id"] == step_id
            and form in ("forms/PLAN_TO_EXECUTE.toml", "forms/CONSOLIDATE.toml")):
        word = resolution or "incorporate"
        if word == "rewrite":
            body = 'orders = "%s"\n' % findings
        elif panel:
            body = ""   # no calls table: carries every finding the panel returned, as `writer`
        else:
            body = 'orders = "%s"\n' % findings
        if form == "forms/PLAN_TO_EXECUTE.toml":
            _fill_plan_to_execute(wid, word, calls=body)
        else:
            _fill_consolidate(wid, word, calls=body)
        cli.main([wid, "submit"])
    return step_id


def _mint_first_gate(wid="issue17"):
    """Open a run-an-issue and drive it, through one real plan round and a
    real critic pass, to the freshly projected g1 dispatch step. One gate
    per plan round now (#27) -- a second real gate takes a second round, via
    `_replan_to_next_gate`."""
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "parser drops last record"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    _dispatch_and_close_plan(wid)
    _dispatch_plan_critic(wid)
    _fill_plan_to_execute(wid)
    cli.main([wid, "submit"])


def _replan_to_next_gate(wid, step_id, purpose="a second gate", scope="scope 2",
                               proof="true", model=""):
    """Adjudicate `step_id` as `replan` (accepted, and there is more to do)
    and drive the fresh plan round it opens through to its own projected
    gate -- the real route to a second gate now that one plan round cuts
    exactly one."""
    _fill(_response(wid), PURPOSE_HOLDS + '''
findings = "landed clean; more of the issue remains"
plan-holds = "replan"
''')
    cli.main([wid, "submit"])
    fresh_plan = next(s for s in runmod.state(wid)["steps"]
                      if s["segment"] == "plan" and s.get("source") == "mint")
    _dispatch_and_close_plan(wid, fresh_plan["id"], fill_fn=lambda w: _fill_plan(
        w, purpose=purpose, scope=scope, proof=proof, model=model))
    _dispatch_plan_critic(wid)
    _fill_plan_to_execute(wid)
    cli.main([wid, "submit"])


def _dispatch_and_close_child(parent_wid, step_id, cycles=0):
    """Open the child a dispatch step names, work its implement steps and
    its review panel, close it.

    A gate opens with one implement step already -- the work is what the
    gate is for. `cycles` drives the real review mechanism through `cycles`
    revise rounds -- a panelist raising a real finding, a fresh implement
    step prefilled with it, before the eventual pass.
    """
    cli.main(["open", "run-a-gate", "--parent", parent_wid, "--step", step_id])
    child_wid = f"{parent_wid}.{step_id}"
    _fill_implement(child_wid, step_id)
    cli.main([child_wid, "submit"])
    for i in range(cycles):
        _dispatch_review(child_wid, verdict="revise", findings=f"gap: needs rework {i+1}")
        cur = runmod.state(child_wid)["current"]["id"]
        _fill_implement(child_wid, cur)
        cli.main([child_wid, "submit"])
    _dispatch_review(child_wid)
    _fill_gate_close(child_wid)
    cli.main([child_wid, "submit"])
    cli.main([child_wid, "close"])
    return child_wid


# -- 1. gates plan field mints dispatch + adjudication pairs -----------------


def test_gate_projection_mints_one_dispatch_and_adjudicate_pair_in_order(workdir, capsys):
    """The plan-to-execute projection (#27, `tests/test_gate_projection.py`
    covers it end to end) still lands through `_mint_gates`, so the pairing
    shape it produces -- ids in order, the dispatch/adjudicate pair, `id`
    stripped from the prefill -- is pinned here on the one gate a round
    actually cuts."""
    _mint_first_gate()
    capsys.readouterr()

    st = runmod.state("issue17")
    ids = [s["id"] for s in st["steps"]]
    assert ids == ["open", "understand-1", "understand", "plan-1", "plan",
                  "g1", "g1-adjudicate", "execute"]
    assert st["steps"][-1]["terminal"] is True  # the terminal close step still sorts last

    g1 = next(s for s in st["steps"] if s["id"] == "g1")
    assert g1["segment"] == "execute" and g1["dispatches"] == "run-a-gate"
    assert g1["source"] == "mint" and g1["child"] == "issue17.g1"
    assert g1["prefill"]["purpose"].startswith("fix the parser")
    assert "id" not in g1["prefill"]
    assert "horizon" not in g1["prefill"]  # the horizon stays with the plan round

    g1adj = next(s for s in st["steps"] if s["id"] == "g1-adjudicate")
    assert g1adj["form"] == "forms/GATE_TRANSITION.toml"
    assert g1adj["filler"] == "conductor"


def test_a_second_real_gate_carries_its_own_model_override(workdir, capsys):
    """A gate's `model` override still rides the projected prefill -- proven
    on a genuine second round now that one round cuts one gate. Its default
    id collides with "g1" (still done, still on record) the same way a
    remint's does, so it takes a suffix rather than landing on "g2"."""
    _mint_first_gate()
    _dispatch_and_close_child("issue17", "g1")
    capsys.readouterr()
    _replan_to_next_gate("issue17", "g1-adjudicate", model="light")
    capsys.readouterr()

    g2 = next(s for s in runmod.state("issue17")["steps"]
              if s.get("dispatches") == "run-a-gate" and s["id"] != "g1")
    assert g2["prefill"]["model"] == "light"


# -- 2. opening a child records prefill and nests its location ---------------


def test_open_child_records_prefill_and_nests_location(workdir, capsys):
    _mint_first_gate()
    capsys.readouterr()
    cli.main(["open", "run-a-gate", "--parent", "issue17", "--step", "g1"])
    capsys.readouterr()

    assert journal.location("issue17.g1") == pathlib.Path(".agent-work", "issue17", "g1")
    assert journal.exists("issue17.g1")

    cst = runmod.state("issue17.g1")
    assert cst["assembly"] == "run-a-gate"
    assert cst["parent"] == "issue17" and cst["parent_step"] == "g1"
    assert cst["prefill"]["purpose"].startswith("fix the parser")
    assert cst["prefill"]["scope"] == "src/parser.c only"
    assert cst["model"] == "standard"  # execute segment's default tier, no override on g1


# -- 2b. consolidate's carries fold is a list, not everything ----------------


def test_consolidate_carries_only_the_spec_seam_fields_into_prefill(workdir, capsys):
    """`carries` on the understand seam's consolidate transition names the
    fields that outlive this seam -- `spec`, `key-terms`, `settle`,
    `obligations` -- not `true`, which would fold every field the step
    submitted, including this seam's own bookkeeping: `resolution` (its
    ruling on the spec) and `orders`/`calls` (its ruling on the panel's
    findings). Those are spent the moment the round releases; frozen into
    prefill they would ride into every later dispatch and collide with the
    plan seam's identically-named fields -- measured on issue112, where a
    stale `resolution`/`orders` from this seam's `rework` round read to the
    next planner as the ruling on a gate, and the wrong gate was cut.

    Driven for real: a genuine run-an-issue through the board and a real
    consolidate release, then asserted on the run's own `prefill` journal
    entry (`runmod.state(wid)["prefill"]`) -- not on the assembly's
    `carries` declaration, which a reader could get right by eye while the
    fold itself still froze too much."""
    cli.main(["open", "run-an-issue", "--issue", "112", "--title", "t"])
    wid = "issue112"
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    capsys.readouterr()

    prefill = runmod.state(wid)["prefill"]
    for field in ("spec", "key-terms", "settle"):
        assert field in prefill, f"{field!r} missing from prefill"
    for field in ("resolution", "orders", "calls"):
        assert field not in prefill, f"{field!r} leaked into prefill"


# -- 3. dispatch status renders the resolved runner and open command ---------


def test_dispatch_status_resolves_runner_and_open_command(workdir, capsys):
    """The room itself never prints a dispatch step's runner or open
    command any more (`o-single-dispatch-room`) -- `_dispatch_descriptor`
    is what still resolves both, for whatever process `wait` goes on to
    start, so this drives that resolution directly rather than scanning a
    room that no longer carries either."""
    _mint_first_gate()
    capsys.readouterr()
    st = runmod.state("issue17")
    asm = runmod.load_assembly(st["assembly"])
    _role, tier, open_cmd, _finish_form = cli._dispatch_descriptor("issue17", asm, st["current"])
    assert cli._runner(tier) == "claude-sonnet-5"  # standard tier, resolved from constellation.toml
    assert open_cmd == "spine open run-a-gate --parent issue17 --step g1"

    # a second gate's own model override rides the prefill and resolves too
    _dispatch_and_close_child("issue17", "g1")
    cli.main(["issue17"])  # materializes the now-current g1-adjudicate form
    capsys.readouterr()
    _replan_to_next_gate("issue17", "g1-adjudicate", model="light")
    capsys.readouterr()
    st2 = runmod.state("issue17")
    asm2 = runmod.load_assembly(st2["assembly"])
    g2 = next(s for s in st2["steps"]
             if s.get("dispatches") == "run-a-gate" and s["id"] != "g1")
    _role2, tier2, open_cmd2, _finish_form2 = cli._dispatch_descriptor("issue17", asm2, g2)
    assert cli._runner(tier2) == "claude-haiku-4-5-20251001"
    assert open_cmd2 == f"spine open run-a-gate --parent issue17 --step {g2['id']}"


# -- 4/5. child close returns to the parent, completes the dispatch step, --
#         and the mechanical summary carries cycles and checks no one typed


def test_child_close_completes_dispatch_step_and_carries_mechanical_summary(workdir, capsys):
    _mint_first_gate()
    capsys.readouterr()

    child_wid = _dispatch_and_close_child("issue17", "g1", cycles=2)
    capsys.readouterr()

    # the child's own close entry
    child_entries = journal.read(child_wid)
    closed = next(e for e in child_entries if e["kind"] == "closed")
    assert closed["fields"]["residue"] == "nothing surprising"

    # a return landed in the PARENT's journal, keyed to the dispatch step --
    # not the first return overall, since the plan-to-execute panel's own
    # return landed earlier
    parent_entries = journal.read("issue17")
    ret = next(e for e in parent_entries if e["kind"] == "return" and e["step"] == "g1")
    assert ret["child"] == "issue17.g1"
    assert ret["fields"]["residue"] == "nothing surprising"

    # the return completes "g1" in the parent's fold; "g1-adjudicate" is current
    pst = runmod.state("issue17")
    assert "g1" in pst["done"]
    assert pst["done"]["g1"]["kind"] == "return"
    assert pst["current"]["id"] == "g1-adjudicate"

    # its status shows the returns
    cli.main(["issue17"])
    out = capsys.readouterr().out
    assert "returns" in out
    assert "nothing surprising" in out

    # the mechanical summary: a first pass, two reworks each driven by a real
    # review panelist, a final pass, and a real engine-run check -- none of
    # it typed by the agent
    summary = ret["summary"]
    # first-pass implement + first review + 2 rework rounds
    # (implement + review each) + final review + close
    assert summary["steps_completed"] == 7
    # `cycles` counts rework beyond the first pass -- the re-fired review
    # step does not double-count it, only the fresh implement steps do
    assert {"segment": "work", "count": 2} in summary["cycles"]
    assert summary["verdict"] == "pass"  # the panel's final verdict rides the summary
    assert any(c["command"] == "true" and c["exit"] == 0 for c in summary["checks"])
    assert summary["model"] == "standard"


# -- 6. amend add / close / reorder, each requiring a reason ------------------


def test_amend_add_close_reorder_each_work_and_require_reason(workdir, capsys):
    cli.main(["open", "run-an-issue", "--issue", "20", "--title", "t"])
    capsys.readouterr()

    with pytest.raises(SystemExit) as e:
        cli.main(["issue20", "amend", "add", "--segment", "execute", "--form",
                  "skills/implementer/forms/IMPLEMENT.toml"])
    assert "reason" in str(e.value)

    cli.main(["issue20", "amend", "add", "--segment", "execute", "--form",
              "skills/implementer/forms/IMPLEMENT.toml", "--reason", "r1"])
    cli.main(["issue20", "amend", "add", "--segment", "execute", "--form",
              "skills/implementer/forms/IMPLEMENT.toml", "--reason", "r2"])
    capsys.readouterr()

    st = runmod.state("issue20")
    added = [s["id"] for s in st["steps"] if s["segment"] == "execute" and s["source"] == "amend"]
    assert len(added) == 2
    first, second = added
    execute_idx = st["steps"].index(next(s for s in st["steps"] if s["id"] == "execute"))
    assert st["steps"].index(next(s for s in st["steps"] if s["id"] == first)) < execute_idx

    with pytest.raises(SystemExit):
        cli.main(["issue20", "amend", "reorder", second, "--before", first])  # no reason
    cli.main(["issue20", "amend", "reorder", second, "--before", first, "--reason", "priority"])
    capsys.readouterr()
    st = runmod.state("issue20")
    amend_ids = [s["id"] for s in st["steps"] if s["source"] == "amend"]
    assert amend_ids == [second, first]

    with pytest.raises(SystemExit):
        cli.main(["issue20", "amend", "close", first])  # no reason
    cli.main(["issue20", "amend", "close", first, "--reason", "no longer needed"])
    capsys.readouterr()
    st = runmod.state("issue20")
    assert first not in [s["id"] for s in st["steps"]]
    assert second in [s["id"] for s in st["steps"]]


# -- amending an anchor is allowed, and the summary flags it -----------------


def test_amend_on_anchor_is_allowed_and_flagged(workdir, capsys):
    cli.main(["open", "run-an-issue", "--issue", "21", "--title", "t"])
    capsys.readouterr()
    open_step = next(s for s in runmod.state("issue21")["steps"] if s["id"] == "open")
    assert open_step["anchor"] is True

    cli.main(["issue21", "amend", "close", "open", "--reason", "skip: no fresh understanding needed"])
    capsys.readouterr()

    entries = journal.read("issue21")
    amend = next(e for e in entries if e["kind"] == "amend")
    assert amend["action"] == "close" and amend["step"] == "open"
    assert amend["anchor"] is True  # the freeze is enforced by the reader, not a refusal

    st = runmod.state("issue21")
    assert "open" not in [s["id"] for s in st["steps"]]
    assert st["current"]["id"] == "understand-1"  # the anchor is really gone


# -- amend waive: the panel waived, the step standing for its own form -------
#
# issue811 on f1Brainz (2026-09-07): a principal ruled "hand this gate off to
# be built rather than review it again", and the only verb was `amend close`
# on the two-voices step -- which took the route form with the panel, walked
# the run to its close form with the gate never projected, and cost three
# hand re-adds of PLAN_TO_EXECUTE.toml. `amend waive` is that ruling as one
# journaled amend: the panelists still out are waived with the reason, the
# step stops waiting for them, and its form stays the conductor's to fill.


def _reach_plan_panel(wid, issue):
    """Open a run-an-issue and drive it to the plan seam's own two-voices
    step: panel declared, no panelist dispatched yet, the route form behind
    them still the conductor's to fill."""
    cli.main(["open", "run-an-issue", "--issue", issue, "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    _dispatch_and_close_plan(wid)
    st = runmod.state(wid)
    assert st["current"]["id"] == "plan" and st["current"].get("panel")


def _configure_throwaway_dispatch(wid, marker_dir):
    """A real `dispatch` entry in the run's own palette -- the tree
    `_tree_info` reads it from -- the same python-only shape
    `test_wait._throwaway_dispatch` writes, added to the palette `workdir`
    seeded rather than replacing it, so `[models]` stays. One marker file
    per spawn makes an actual start observable rather than inferred."""
    script = ("import pathlib, sys, time\n"
              f"d = pathlib.Path({str(marker_dir)!r})\n"
              "d.mkdir(parents=True, exist_ok=True)\n"
              "(d / f'{time.time_ns()}.brief').write_text(sys.argv[1])\n")
    entry = [sys.executable, "-c", script, "{brief}"]
    palette = journal.root_for(wid) / "constellation.toml"
    palette.write_text(palette.read_text().replace(
        "[commands]\n", "[commands]\ndispatch = " + json.dumps(entry) + "\n", 1))


def test_amend_waive_before_dispatch_starts_nothing_and_the_form_submits(workdir, capsys):
    """Waived before any panelist was started: a later `wait` spawns none
    of them (no `dispatch-started` record, no marker file), renders the
    route form's own room with the waiver and its reason on it, and the
    conductor's submit is accepted -- the step completes and the gate it
    names is projected, which is exactly what `amend close` lost."""
    wid = "issue23"
    _reach_plan_panel(wid, "23")
    marker = workdir / "spawned"
    _configure_throwaway_dispatch(wid, marker)
    reason = "principal's ruling: hand this gate off to be built rather than review it again"
    cli.main([wid, "amend", "waive", "plan", "--reason", reason])
    waive = [e for e in journal.read(wid) if e["kind"] == "amend" and e["action"] == "waive"]
    assert len(waive) == 1
    assert waive[0]["waived"] == [f"{wid}.plan.p{n}" for n in (1, 2, 3)]
    assert waive[0]["reason"] == reason
    capsys.readouterr()

    code = cli.main([wid, "wait", "--for", "1"])
    out = capsys.readouterr().out
    assert code == 0
    assert not [e for e in journal.read(wid) if e["kind"] == "dispatch-started"]
    assert not marker.exists()
    flat = " ".join(out.split())  # the sentence wraps; read it as one line
    assert f"The panel here was waived. Reason: {reason}" in flat
    assert "your response form" in out
    assert "panelist p1" not in out

    _fill_plan_to_execute(wid, "pass")
    cli.main([wid, "submit"])
    st = runmod.state(wid)
    assert "plan" in st["done"]
    assert st["current"]["segment"] == "execute"
    assert st["current"].get("dispatches") == "run-a-gate"


def test_amend_waive_after_a_return_keeps_it_and_waives_only_the_rest(workdir, capsys):
    """One critic already returned with a finding when the waiver lands:
    that return stays folded, only the two still out are waived, a waived
    panelist that closes later lands nothing on the step, and the yield
    reports the round with its one finding, its call, and the two waived
    voices with the reason."""
    wid = "issue24"
    _reach_plan_panel(wid, "24")
    p1 = f"{wid}.plan.p1"
    cli.main(["open", "give-a-verdict", "--parent", wid, "--step", "plan.p1"])
    _fill_critic(p1, "revise", "gap: the loop bound is untested")
    cli.main([p1, "submit"])
    cli.main([p1, "close"])

    with pytest.raises(SystemExit) as e:  # still two out: refused, and told the way out
        cli.main([wid, "submit"])
    assert "amend waive plan --reason" in str(e.value)

    reason = "principal's ruling: no further critic round on this cut"
    cli.main([wid, "amend", "waive", "plan", "--reason", reason])
    waive = next(e for e in journal.read(wid) if e["kind"] == "amend" and e["action"] == "waive")
    assert waive["waived"] == [f"{wid}.plan.p2", f"{wid}.plan.p3"]
    st = runmod.state(wid)
    assert [r["child"] for r in st["returns"]["plan"]] == [p1]
    assert st["current"]["id"] == "plan"
    assert not runmod.panel_outstanding(st, st["current"])

    # p2 was live when the waiver landed and closes later: its return is in
    # the journal and folds nowhere -- not a return, not a voice, not done
    p2 = f"{wid}.plan.p2"
    cli.main(["open", "give-a-verdict", "--parent", wid, "--step", "plan.p2"])
    _fill_critic(p2, "pass")
    cli.main([p2, "submit"])
    cli.main([p2, "close"])
    st = runmod.state(wid)
    assert any(e["kind"] == "return" and e["child"] == p2 for e in journal.read(wid))
    assert [r["child"] for r in st["returns"]["plan"]] == [p1]
    assert p2 not in st["returns_by_child"]
    assert st["current"]["id"] == "plan"

    with pytest.raises(SystemExit) as e:  # nothing left to waive
        cli.main([wid, "amend", "waive", "plan", "--reason", "again"])
    assert "nothing outstanding to waive" in str(e.value)
    capsys.readouterr()

    cli.main([wid])
    flat = " ".join(capsys.readouterr().out.split())
    assert ("2 of the 3 panelists here were waived -- the 1 that returned still "
            f"counts. Reason: {reason}") in flat

    _fill_plan_route_with_calls(
        wid, "pass", ("gap: the loop bound is untested", "writer"))
    cli.main([wid, "submit"])
    assert "plan" in runmod.state(wid)["done"]

    entries = review_yield.run_yield(wid)
    plan = next(e for e in entries if e["label"] == "plan-to-execute")
    assert plan["rounds"] == [{"verdict": "revise", "revising": 0, "findings": 1,
                               "called": True, "calls": {"writer": 1},
                               "waived": 2, "reason": reason}]
    assert f"r1  revise   1 finding   1 writer   2 waived -- {reason}" in \
        render.review_yield(entries)


def test_amend_waive_refuses_where_nothing_stands_to_fill(workdir, capsys):
    """A step with no panel has nothing to waive; a panel-only step is its
    panel, so waiving it whole would leave nothing to complete it -- the
    refusal names `amend close` as the move instead. A reason is journaled,
    never judged: the one check on it is that it was given."""
    cli.main(["open", "run-an-issue", "--issue", "25", "--title", "t"])
    with pytest.raises(SystemExit) as e:
        cli.main(["issue25", "amend", "waive", "open", "--reason", "r"])
    assert "no panel to waive" in str(e.value)
    with pytest.raises(SystemExit) as e:
        cli.main(["issue25", "amend", "waive", "plan"])
    assert "reason" in str(e.value)

    journal.append("g9", "run", title="t", assembly="run-a-gate")
    journal.append("g9", "step", id="review", segment="work",
                   panel=[{"worker": "reviewer", "criteria": "c"}])
    with pytest.raises(SystemExit) as e:
        cli.main(["g9", "amend", "waive", "review", "--reason", "r"])
    assert "panel-only" in str(e.value) and "amend close review" in str(e.value)
    assert not [e for e in journal.read("g9") if e["kind"] == "amend"]


# -- close refuses while a step is unfinished --------------------------------


def test_close_refuses_while_a_step_is_unfinished(workdir, capsys):
    cli.main(["open", "run-an-issue", "--issue", "22", "--title", "t"])
    capsys.readouterr()
    with pytest.raises(SystemExit) as e:
        cli.main(["issue22", "close"])
    assert "open" in str(e.value)
    assert "waived:" in str(e.value) or "submit" in str(e.value)


# -- GATE_TRANSITION's outcome: the engine acts on the decision --------------


def test_advance_performs_no_amends(workdir, capsys):
    _mint_first_gate()
    capsys.readouterr()
    _dispatch_and_close_child("issue17", "g1")
    capsys.readouterr()

    before = len(journal.read("issue17"))
    _fill_gate_transition("issue17")  # plan-holds = "advance"
    cli.main(["issue17", "submit"])
    capsys.readouterr()

    # advance now commits the gate (issue19.g3) -- here the implement round
    # only touched `.agent-work`, gitignored, so the engine's own commit
    # attempt stages nothing and journals its no-op note rather than an
    # amend; either way, advance itself never amends anything, and it mints
    # nothing further -- the one gate this round cut was the only one, so
    # the run walks straight on to its own terminal close step
    new_entries = journal.read("issue17")[before:]
    assert new_entries[0]["kind"] == "submit"
    assert not any(e["kind"] == "amend" for e in new_entries)
    assert runmod.state("issue17")["current"]["form"] == "forms/CLOSE.toml"


def test_drop_closes_only_the_named_gate_and_never_the_deciding_step(workdir, capsys):
    _mint_n_gates(3)
    capsys.readouterr()
    _dispatch_and_close_child("issue17", "g1")
    capsys.readouterr()

    assert runmod.state("issue17")["current"]["id"] == "g1-adjudicate"

    _fill_gate_transition_drop("issue17", "g3")
    cli.main(["issue17", "submit"])
    capsys.readouterr()

    amends = [e for e in journal.read("issue17") if e["kind"] == "amend"]
    assert {a["step"] for a in amends} == {"g3", "g3-adjudicate"}
    assert all(a["action"] == "close" and a["reason"] == "drop g3" for a in amends)

    st = runmod.state("issue17")
    ids = {s["id"] for s in st["steps"]}
    assert not ({"g3", "g3-adjudicate"} & ids)             # the named gate is gone
    assert {"g2", "g2-adjudicate"} <= ids                   # the other gate: untouched
    assert "g2" not in st["done"]
    assert st["current"]["id"] == "g2"                      # skips the dropped gate
    # the deciding step landed via its own submit, never as an amend target
    assert st["done"]["g1-adjudicate"]["kind"] == "submit"


def test_an_undeclared_outcome_refuses_and_a_declared_one_carries_its_reason(
        workdir, capsys):
    """`plan-holds` used to be matched whole, so a word with a reason after it
    performed nothing and released the step anyway. Now the leading word is the
    decision and the rest is the reason -- so an undeclared word is refused
    against the four its note lists, and a declared one is performed with its
    prose intact. A bare `drop` is a known move missing its argument, and is
    refused one check later, where the pending gates are named.

    Renamed from `test_a_prose_outcome_refuses_instead_of_advancing_the_run`,
    which is what it asserted while the two matching rules disagreed.
    """
    _mint_n_gates(3)
    capsys.readouterr()
    _dispatch_and_close_child("issue17", "g1")
    capsys.readouterr()

    before = len(journal.read("issue17"))
    _fill(_response("issue17"), PURPOSE_HOLDS + '''
findings = "the fix landed"
plan-holds = "the plan holds, carry on"
''')
    with pytest.raises(SystemExit) as e:
        cli.main(["issue17", "submit"])
    msg = str(e.value)
    assert "plan-holds" in msg
    assert "advance | remint | drop <gate-id> | replan" in msg

    # a bare `drop` is a known move missing its argument -- past the
    # vocabulary check, refused one check later where the gates are named
    _fill_gate_transition_drop("issue17", "")
    with pytest.raises(SystemExit) as e:
        cli.main(["issue17", "submit"])
    assert "drop needs a gate id" in str(e.value)
    assert "g2" in str(e.value) and "g3" in str(e.value)

    assert len(journal.read("issue17")) == before   # no attempt journaled anything
    assert runmod.state("issue17")["current"]["id"] == "g1-adjudicate"

    # and a declared word with its reason after it is performed, reason kept
    _fill(_response("issue17"), PURPOSE_HOLDS + '''
findings = "the cut was wrong from the start"
plan-holds = "replan, the gates were cut along the wrong seam"
''')
    cli.main(["issue17", "submit"])
    st = runmod.state("issue17")
    assert st["current"]["segment"] == "plan", "replan did not refill the plan"
    submitted = [e for e in journal.read("issue17")
                 if e["kind"] == "submit" and e.get("step") == "g1-adjudicate"][-1]
    assert submitted["fields"]["plan-holds"].endswith("wrong seam"), \
        "the reason was dropped on the way through"


def test_drop_on_a_gate_not_pending_refuses_and_names_pending(workdir, capsys):
    _mint_n_gates(3)
    capsys.readouterr()
    _dispatch_and_close_child("issue17", "g1")
    capsys.readouterr()

    before = len(journal.read("issue17"))

    # its own gate is never a legal target, even though its dispatch and
    # adjudication are the only steps "current" points near
    _fill_gate_transition_drop("issue17", "g1")
    with pytest.raises(SystemExit) as e:
        cli.main(["issue17", "submit"])
    assert "g2" in str(e.value) and "g3" in str(e.value)

    # a made-up id refuses the same way, naming the same pending set
    _fill_gate_transition_drop("issue17", "gXX")
    with pytest.raises(SystemExit) as e:
        cli.main(["issue17", "submit"])
    assert "g2" in str(e.value) and "g3" in str(e.value)

    # neither refused attempt journaled anything -- not even the submit
    assert len(journal.read("issue17")) == before
    assert runmod.state("issue17")["current"]["id"] == "g1-adjudicate"


def test_remint_with_empty_spec_refuses(workdir, capsys):
    _mint_first_gate()
    capsys.readouterr()
    _dispatch_and_close_child("issue17", "g1")
    capsys.readouterr()

    before = len(journal.read("issue17"))
    _fill_gate_transition_remint_no_spec("issue17")
    with pytest.raises(SystemExit) as e:
        cli.main(["issue17", "submit"])
    assert "gate-spec" in str(e.value)
    assert len(journal.read("issue17")) == before
    assert runmod.state("issue17")["current"]["id"] == "g1-adjudicate"


def test_remint_mints_a_gate_that_is_reachable_not_already_done(workdir, capsys):
    _mint_first_gate()
    capsys.readouterr()
    _dispatch_and_close_child("issue17", "g1")
    capsys.readouterr()

    _fill_gate_transition_remint("issue17", purpose="redo the fix", scope="src/parser.c")
    cli.main(["issue17", "submit"])
    capsys.readouterr()

    st = runmod.state("issue17")
    new_gates = [s for s in st["steps"] if s.get("dispatches") == "run-a-gate"
                and s["id"] not in ("g1", "g2")]
    assert len(new_gates) == 1
    new_gate = new_gates[0]
    assert new_gate["id"] != "g1"                # default "g1" collided, took a suffix
    assert new_gate["id"].startswith("g1-a")
    assert new_gate["id"] not in st["done"]
    assert f"{new_gate['id']}-adjudicate" not in st["done"]
    assert new_gate["prefill"]["purpose"] == "redo the fix"

    # remint closed nothing -- least of all the gate that just ran
    assert not any(e["kind"] == "amend" for e in journal.read("issue17"))
    assert "g1" in st["done"] and "g1-adjudicate" in st["done"]

    # genuinely reachable, not a step that merely looks done: drive it closed
    child_wid = _dispatch_and_close_child("issue17", new_gate["id"])
    assert journal.exists(child_wid)
    assert new_gate["id"] in runmod.state("issue17")["done"]


def test_drop_closes_a_remint_minted_pair_too(workdir, capsys):
    """The pairing `drop` relies on is derived from `child`, written on both
    halves of a pair by `_mint_gates` -- and `_mint_gates` runs from two call
    sites, plan-minted gates and a remint. This drives the remint route: a
    pair minted mid-run, never part of the original plan cut, dropped like
    any other."""
    _mint_n_gates(2)
    capsys.readouterr()
    _dispatch_and_close_child("issue17", "g1")
    capsys.readouterr()

    _fill_gate_transition_remint("issue17", purpose="redo the fix", scope="src/parser.c")
    cli.main(["issue17", "submit"])
    capsys.readouterr()

    new_gate = next(s for s in runmod.state("issue17")["steps"]
                    if s.get("dispatches") == "run-a-gate" and s["id"] not in ("g1", "g2"))
    new_id = new_gate["id"]

    _dispatch_and_close_child("issue17", "g2")
    capsys.readouterr()
    assert runmod.state("issue17")["current"]["id"] == "g2-adjudicate"

    _fill_gate_transition_drop("issue17", new_id)
    cli.main(["issue17", "submit"])
    capsys.readouterr()

    amends = [e for e in journal.read("issue17") if e["kind"] == "amend"]
    assert {a["step"] for a in amends} == {new_id, f"{new_id}-adjudicate"}

    ids = {s["id"] for s in runmod.state("issue17")["steps"]}
    assert not ({new_id, f"{new_id}-adjudicate"} & ids)


def test_drop_pairs_by_shared_child_not_by_id_suffix(workdir, capsys):
    """Every pair `_mint_gates` produces carries the `-adjudicate` suffix by
    construction, so driving `drop` only through the normal mint path proves
    nothing about *how* the engine finds the pair -- suffix parsing and
    `child` grouping agree on every fixture `_mint_gates` can produce. Here
    the two steps sharing a `child` are journaled directly, with ids that
    share no prefix at all: suffix parsing cannot pair them, `child`
    grouping can."""
    _mint_first_gate()
    capsys.readouterr()
    _dispatch_and_close_child("issue17", "g1")
    capsys.readouterr()
    assert runmod.state("issue17")["current"]["id"] == "g1-adjudicate"

    journal.append("issue17", "step", id="odd-one", segment="execute",
                   dispatches="run-a-gate",
                   prefill={"purpose": "p", "scope": "s", "proof": "true"},
                   child="issue17.odd-one", anchor=False, terminal=False, source="mint")
    journal.append("issue17", "step", id="its-mate", segment="execute",
                   form="forms/GATE_TRANSITION.toml", filler="conductor",
                   child="issue17.odd-one", anchor=False, terminal=False,
                   validates="", source="mint")

    _fill_gate_transition_drop("issue17", "odd-one")
    cli.main(["issue17", "submit"])
    capsys.readouterr()

    amends = [e for e in journal.read("issue17") if e["kind"] == "amend"]
    assert {a["step"] for a in amends} == {"odd-one", "its-mate"}, amends

    ids = {s["id"] for s in runmod.state("issue17")["steps"]}
    assert not ({"odd-one", "its-mate"} & ids)


def test_reminting_twice_derives_distinct_ids_from_the_same_default(workdir, capsys):
    """Two reminds that both leave the id blank both derive the same default
    ("g1", position 1 within their own block) and both collide with the
    original g1 -- this is what the suffix mechanism must actually resolve,
    not merely tolerate once."""
    _mint_n_gates(2)
    capsys.readouterr()

    _dispatch_and_close_child("issue17", "g1")
    _fill_gate_transition_remint("issue17", purpose="first redo")
    cli.main(["issue17", "submit"])
    capsys.readouterr()
    st = runmod.state("issue17")
    first_new = next(s["id"] for s in st["steps"]
                     if s.get("dispatches") == "run-a-gate" and s["id"] not in ("g1", "g2"))

    _dispatch_and_close_child("issue17", "g2")
    _fill_gate_transition_remint("issue17", purpose="second redo")
    cli.main(["issue17", "submit"])
    capsys.readouterr()
    st = runmod.state("issue17")
    new_ids = {s["id"] for s in st["steps"] if s.get("dispatches") == "run-a-gate"} \
        - {"g1", "g2"}
    second_new = (new_ids - {first_new}).pop()

    assert first_new != second_new
    assert first_new.startswith("g1-a") and second_new.startswith("g1-a")


# -- replan: close every pending gate by name, re-enter plan -----------------


def test_replan_closes_every_pending_gate_by_name_leaving_closed_gates_and_the_decider_untouched(
        workdir, capsys):
    _mint_n_gates(3)
    capsys.readouterr()
    _dispatch_and_close_child("issue17", "g1")
    capsys.readouterr()
    assert runmod.state("issue17")["current"]["id"] == "g1-adjudicate"

    _fill_gate_transition_replan("issue17", findings="the cut was wrong from the start")
    cli.main(["issue17", "submit"])
    capsys.readouterr()

    amends = [e for e in journal.read("issue17") if e["kind"] == "amend"]
    closed = {a["step"] for a in amends}
    assert closed == {"g2", "g2-adjudicate", "g3", "g3-adjudicate"}  # every pending gate, named
    assert all(a["action"] == "close" and a["reason"] == "replan" for a in amends)
    assert "g1" not in closed and "g1-adjudicate" not in closed  # the deciding step: untouched
                                                                  # by its own outcome

    st = runmod.state("issue17")
    ids = {s["id"] for s in st["steps"]}
    assert not ({"g2", "g2-adjudicate", "g3", "g3-adjudicate"} & ids)  # gone from the worklist
    assert "g1" in st["done"] and "g1-adjudicate" in st["done"]        # closed gate: untouched
    assert st["done"]["g1-adjudicate"]["kind"] == "submit"             # via its own submit,
                                                                        # never as an amend target


def test_replan_with_nothing_pending_closes_nothing_and_still_reenters_plan(workdir, capsys):
    """A replan on the last (only) gate has no other pending gate to close --
    it should mint the fresh plan round and journal no amends at all, rather
    than refusing for lack of anything to sweep."""
    _mint_n_gates(1)
    capsys.readouterr()
    _dispatch_and_close_child("issue17", "g1")
    capsys.readouterr()

    before = len(journal.read("issue17"))
    _fill_gate_transition_replan("issue17")
    cli.main(["issue17", "submit"])
    capsys.readouterr()

    entries = journal.read("issue17")
    assert not any(e["kind"] == "amend" for e in entries)  # nothing pending, nothing closed
    assert len(entries) == before + 3  # the submit, plus the two fresh "plan" steps minted
    assert "g1" in runmod.state("issue17")["done"]


def test_replan_reenters_plan_with_a_fresh_step_and_the_conductors_route_form_genuinely_reachable(
        workdir, capsys):
    """A replan's fresh round is a dispatch plus the conductor's own route
    form -- and no critic panel: the panel reads the run's opening cut only
    (`panel-rounds = "opening"`), so a re-cut stands PLAN_TO_EXECUTE alone."""
    _mint_n_gates(2)
    capsys.readouterr()
    _dispatch_and_close_child("issue17", "g1")
    capsys.readouterr()

    _fill_gate_transition_replan("issue17", findings="the cut was wrong from the start")
    cli.main(["issue17", "submit"])
    capsys.readouterr()

    st = runmod.state("issue17")
    fresh_plan = next(s for s in st["steps"]
                      if s["segment"] == "plan" and s.get("source") == "mint")
    assert fresh_plan["dispatches"] == "cut-a-gate"  # a replan dispatches too -- every round does
    assert fresh_plan["form"] == "skills/planner/forms/PLAN.toml"  # no override -- plans from scratch
    assert fresh_plan["prefill"]["findings"] == "the cut was wrong from the start"

    fresh_route = next(s for s in st["steps"] if s.get("source") == "panel")
    assert fresh_route["segment"] == "plan"
    assert fresh_route["form"] == "forms/PLAN_TO_EXECUTE.toml"   # the conductor's form
    assert "panel" not in fresh_route                            # and no critic beside it
    assert next(s for s in st["steps"] if s["id"] == "plan")["panel"]  # the opening cut's stays

    # genuinely reachable, not a step that merely looks minted
    assert st["current"]["id"] == fresh_plan["id"]

    _dispatch_and_close_plan("issue17", fresh_plan["id"], fill_fn=lambda w: _fill_plan(
        w, purpose="redo the cut correctly", scope="src/ only", proof="true"))
    capsys.readouterr()
    st = runmod.state("issue17")
    assert st["current"]["id"] == fresh_route["id"]  # straight to the form, nothing to wait on
    assert not runmod.panel_outstanding(st, st["current"])

    _fill_plan_to_execute("issue17")
    cli.main(["issue17", "submit"])
    capsys.readouterr()

    st = runmod.state("issue17")
    # g1 (already done) is still on record; g2 was swept by the replan --
    # the only other dispatch step left is the fresh cut
    new_gates = [s for s in st["steps"] if s.get("dispatches") == "run-a-gate" and s["id"] != "g1"]
    assert len(new_gates) == 1
    assert new_gates[0]["prefill"]["purpose"] == "redo the cut correctly"


def test_incorporate_still_goes_through_the_shared_primitive_unchanged(workdir, capsys):
    """An `incorporate` mints through `_mint_segment_round`, the same
    primitive replan uses -- this pins its round's shape: the rework form as
    the fresh interior, findings attributed, and the route form re-minted
    with no panel of its own (the panel reads the opening cut, and a
    rewrite's fresh one, only -- `[one-look]`)."""
    wid = "issue18"
    cli.main(["open", "run-an-issue", "--issue", "18", "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    _dispatch_and_close_plan(wid)
    capsys.readouterr()

    _dispatch_plan_critic(wid, verdict="revise", findings="gap: gate 1 is untestable",
                          resolution="incorporate")
    capsys.readouterr()

    st = runmod.state(wid)
    fresh_plan = next(s for s in st["steps"]
                      if s["segment"] == "plan" and s.get("source") == "mint"
                      and s.get("dispatches"))
    assert fresh_plan["form"] == "skills/planner/forms/REWORK.toml"  # incorporate reworks
    assert "gate 1 is untestable" in fresh_plan["prefill"]["findings"]
    assert "[p1]" in fresh_plan["prefill"]["findings"]

    fresh_route = next(s for s in st["steps"]
                       if s.get("source") == "panel" and s["segment"] == "plan")
    assert fresh_route["form"] == "forms/PLAN_TO_EXECUTE.toml"
    assert "panel" not in fresh_route  # incorporate's own round has no panel
    assert st["current"]["id"] == fresh_plan["id"]


def test_the_close_summary_carries_a_two_voices_verdict(workdir, capsys, monkeypatch):
    """The summary's verdict was read off panel-only steps, so a run whose
    critics had ruled on the plan closed carrying the empty string where the
    panel's word belongs -- and a run that reached round-cap this way, which
    is exactly the one a principal reads the summary of, said nothing at all.

    An issue-tier close now pushes and opens a PR before it archives, so
    `gh` is stubbed here (never a real remote) and the closed entry is read
    off the archive rather than through `journal.read`, which no longer
    resolves an id once `close` has swept it there."""
    wid = "issue19"
    cli.main(["open", "run-an-issue", "--issue", "19", "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    _dispatch_and_close_plan(wid)
    _drive_plan_to_pause(wid)
    capsys.readouterr()

    # round-cap paused the seam rather than releasing it to close (plan and
    # understand declare no impasse of their own any more, ruling
    # 2026-09-25), and this test's own subject is the close summary once the
    # run *does* reach `forms/CLOSE.toml`, not the pause itself -- so the ask
    # it minted is amend-closed directly rather than routed through a resume
    # this test does not exist to drive.
    paused = runmod.state(wid)["current"]
    assert paused["form"] == "skills/gate-conductor/forms/ASK.toml"
    journal.append(wid, "amend", action="close", segment=paused["segment"],
                   step=paused["id"],
                   reason="the critics read the plan against the wrong issue",
                   anchor=paused.get("anchor", False))
    marker = next(s for s in runmod.state(wid)["steps"]
                 if s["segment"] == paused["segment"] and s.get("paused")
                 and s["id"] not in runmod.state(wid)["done"])
    journal.append(wid, "amend", action="close", segment=marker["segment"],
                   step=marker["id"], reason="not resuming this pause",
                   anchor=marker.get("anchor", False))
    _fill_close(wid)
    cli.main([wid, "submit"])
    stub_gh(monkeypatch)
    cli.main([wid, "close"])
    capsys.readouterr()

    closed = read_archived(workdir, wid, "closed")
    assert closed["summary"]["verdict"] == "revise", (
        "the close summary of a run that hit round-cap carries "
        f"{closed['summary']['verdict']!r} where the panel last ruled revise")
