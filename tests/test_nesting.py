"""Nesting: dispatch, prefill, returns, close, and amend.

This drives the real `run-an-issue` and `run-a-gate` assemblies end to end --
not fixtures. A gate spec minted from PLAN_TO_EXECUTE.toml becomes a child
run's opening orders; the child's close stamps a return that completes the
parent's dispatch step; `close` and `amend` round out the seven verbs.
"""

import pathlib

import pytest

from engine import cli, journal, run as runmod
from gitremote import init_checkout, read_archived, stub_gh

REPO = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONSTELLATION_SESSION", "test-session")
    # the command palette (models, check commands) is host-repo config;
    # tests run in an isolated tmp cwd, so it travels with them
    (tmp_path / "constellation.toml").write_text((REPO / "constellation.toml").read_text())
    init_checkout(tmp_path)
    return tmp_path


def _fill(path, text):
    path.write_text(text)


def _fill_open(wid):
    # the `issue` field names a file in the work location, so write one
    issue = pathlib.Path(f".agent-work/{wid}/issue.md")
    _fill(issue, "The parser drops the last record of a file with no "
                 "trailing newline.\n")
    _fill(pathlib.Path(f".agent-work/{wid}/OPEN.toml"), f'''
issue = "{issue}"

authority = """
Principal: Tommy, live. I own driving this to a merged fix; gaps go to him."""

[[questions]]
question = "Which inputs drop the last record?"
type = "fact"
''')


def _work_the_board(wid):
    """Resolve the seeded board before the transition that validates it --
    the engine refuses to leave understand with an unresolved row."""
    b = pathlib.Path(f".agent-work/{wid}/UNDERSTAND.toml")
    b.write_text(b.read_text().replace(
        'status = "open"',
        'status = "answered"\nanswer = "EOF without a trailing newline only."'))


def _fill_consolidate(wid):
    _fill(pathlib.Path(f".agent-work/{wid}/CONSOLIDATE.toml"), '''
learnings = "EOF without a trailing newline drops the last record."
key-terms = "waived: none"
settle = "waived: none"
''')


def _fill_plan(wid, purpose="fix the parser to handle EOF without a trailing newline",
               scope="src/parser.c only", proof="true", model="", direction=""):
    """Fill PLAN.toml at `wid`'s own work location -- `journal.location`,
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
    _fill(loc / "PLAN.toml", '''
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
    cli.main(["open", "cut-a-gate", "--parent", parent_wid, "--step", step_id])
    child_wid = f"{parent_wid}.{step_id}"
    (fill_fn or _fill_plan)(child_wid)
    cli.main([child_wid, "submit"])
    cli.main([child_wid, "close"])
    return child_wid


def _fill_plan_to_execute(wid):
    """Nothing to author here now (#27): the round the panel just passed
    already cut the gate, and submitting this projects it. Only the plan
    artifact pointer is this form's own to fill."""
    _fill(pathlib.Path(f".agent-work/{wid}/PLAN_TO_EXECUTE.toml"), '''
plan = ".agent-work/%s/plan.md"
''' % wid)


def _fill_implement(wid, step_id):
    _fill(journal.location(wid) / "IMPLEMENT.toml", '''
change = "adjusted the loop bound in src/parser.c"
deviations = "waived: none"
''')


def _fill_gate_close(wid):
    _fill(journal.location(wid) / "GATE_CLOSE.toml",
          'commit = "refuse-or-name-the-escape @ 0000000"\nresidue = "nothing surprising"\n')


def _fill_review(wid, verdict="pass", findings="none: waived: clean"):
    _fill(journal.location(wid) / "REVIEW.toml", '''
verify = "read the diff line by line"
findings = "%s"
vocabulary = "waived: consistent"
verdict = "%s"
''' % (findings, verdict))


def _dispatch_review(child_wid, verdict="pass", findings="none: waived: clean"):
    """Open the review panel's one panelist, fill and close it -- the same
    nesting mechanics as a gate dispatch, one step down. Returns the step id
    that fired, since a revise round mints a fresh review step."""
    step_id = runmod.state(child_wid)["current"]["id"]
    cli.main(["open", "give-a-verdict", "--parent", child_wid, "--step", f"{step_id}.p1"])
    panelist = f"{child_wid}.{step_id}.p1"
    _fill_review(panelist, verdict, findings)
    cli.main([panelist, "submit"])
    cli.main([panelist, "close"])
    return step_id


def _fill_gate_transition(wid):
    _fill(journal.location(wid) / "GATE_TRANSITION.toml", '''
findings = "the fix landed cleanly, no follow-on scope"
plan-holds = "advance"
''')


def _fill_gate_transition_drop(wid, gate_id):
    _fill(journal.location(wid) / "GATE_TRANSITION.toml", '''
findings = "no longer needed"
plan-holds = "drop %s"
''' % gate_id)


def _fill_gate_transition_remint(wid, purpose="a corrected gate", scope="src/ only",
                                 proof="true"):
    _fill(journal.location(wid) / "GATE_TRANSITION.toml", '''
findings = "the spec was wrong, needs a redo"
plan-holds = "remint"

[[gate-spec]]
purpose = "%s"
scope = "%s"
proof = "%s"
''' % (purpose, scope, proof))


def _fill_gate_transition_replan(wid, findings="the cut was wrong from the start"):
    _fill(journal.location(wid) / "GATE_TRANSITION.toml", '''
findings = "%s"
plan-holds = "replan"
''' % findings)


def _fill_gate_transition_remint_no_spec(wid):
    _fill(journal.location(wid) / "GATE_TRANSITION.toml", '''
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
    _fill(journal.location(wid) / "CLOSE.toml", '''
disposition = "merged to main"
triage = "waived: none"
residue = "waived: none"
''')


def _fill_critic(wid, verdict, findings="none: waived: clean"):
    """The plan panel declares CRITIC.toml, which has no `verify` field -- a
    critic judges the plan's soundness, not what it exercised."""
    _fill(journal.location(wid) / "CRITIC.toml",
          'findings = "%s"\nvocabulary = "waived: consistent"\nverdict = "%s"\n'
          % (findings, verdict))


def _dispatch_plan_critic(wid, verdict="pass", findings="none: waived: clean"):
    """Open every one of plan-to-execute's panelists, fill and close each --
    the two-voices transition's panel half, which must pass before its form
    (PLAN_TO_EXECUTE.toml) is even reachable.

    Driven off the assembly's own panel length rather than a pinned count:
    the step completes on the last verdict, so a test that closes one of
    three leaves the transition outstanding. `verdict` and `findings` apply
    to every panelist; a caller wanting them to differ opens its own.
    """
    st = runmod.state(wid)
    step_id = st["current"]["id"]
    panel = next(s for s in st["steps"] if s["id"] == step_id)["panel"]
    for n in range(1, len(panel) + 1):
        cli.main(["open", "give-a-verdict", "--parent", wid, "--step", f"{step_id}.p{n}"])
        panelist = f"{wid}.{step_id}.p{n}"
        _fill_critic(panelist, verdict, findings)
        cli.main([panelist, "submit"])
        cli.main([panelist, "close"])
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
    _fill(journal.location(wid) / "GATE_TRANSITION.toml", '''
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
    assert ids == ["open", "understand", "plan-1", "plan", "g1", "g1-adjudicate", "execute"]
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


# -- 3. dispatch status renders the resolved runner and open command ---------


def test_dispatch_status_renders_runner_and_open_command(workdir, capsys):
    _mint_first_gate()
    capsys.readouterr()
    cli.main(["issue17"])
    out = capsys.readouterr().out
    assert "claude-sonnet-5" in out  # standard tier, resolved from constellation.toml
    assert "spine open run-a-gate --parent issue17 --step g1" in out

    # a second gate's own model override rides the prefill and resolves too
    _dispatch_and_close_child("issue17", "g1")
    cli.main(["issue17"])  # materializes the now-current g1-adjudicate form
    capsys.readouterr()
    _replan_to_next_gate("issue17", "g1-adjudicate", model="light")
    capsys.readouterr()
    g2 = next(s for s in runmod.state("issue17")["steps"]
             if s.get("dispatches") == "run-a-gate" and s["id"] != "g1")
    cli.main(["issue17"])
    out = capsys.readouterr().out
    assert "claude-haiku-4-5-20251001" in out
    assert f"spine open run-a-gate --parent issue17 --step {g2['id']}" in out


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
    # first-pass implement + first review + 2 rework rounds (implement +
    # review each) + final review + close
    assert summary["steps_completed"] == 7
    # `cycles` counts rework beyond the first pass -- the re-fired review
    # steps do not double-count it, only the fresh implement steps do
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
    assert st["current"]["id"] == "understand"  # the anchor is really gone


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
    _fill(journal.location("issue17") / "GATE_TRANSITION.toml", '''
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
    _fill(journal.location("issue17") / "GATE_TRANSITION.toml", '''
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


def test_replan_reenters_plan_with_a_fresh_step_and_its_critic_panel_genuinely_reachable(
        workdir, capsys):
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

    fresh_panel = next(s for s in st["steps"] if s.get("source") == "panel")
    assert fresh_panel["segment"] == "plan"
    assert fresh_panel["form"] == "forms/PLAN_TO_EXECUTE.toml"   # the two-voices shape survives
    assert fresh_panel["panel"][0]["criteria"].startswith("intent-fit")  # the real critic panel

    # genuinely reachable, not a step that merely looks minted
    assert st["current"]["id"] == fresh_plan["id"]

    _dispatch_and_close_plan("issue17", fresh_plan["id"], fill_fn=lambda w: _fill_plan(
        w, purpose="redo the cut correctly", scope="src/ only", proof="true"))
    capsys.readouterr()
    assert runmod.state("issue17")["current"]["id"] == fresh_panel["id"]

    # carry the fresh plan through its critic to confirm the panel really fires
    _dispatch_plan_critic("issue17", verdict="pass")
    capsys.readouterr()
    st = runmod.state("issue17")
    assert st["current"]["id"] == fresh_panel["id"]  # resolved, waiting on its own form now

    _fill_plan_to_execute("issue17")
    cli.main(["issue17", "submit"])
    capsys.readouterr()

    st = runmod.state("issue17")
    # g1 (already done) is still on record; g2 was swept by the replan --
    # the only other dispatch step left is the fresh cut
    new_gates = [s for s in st["steps"] if s.get("dispatches") == "run-a-gate" and s["id"] != "g1"]
    assert len(new_gates) == 1
    assert new_gates[0]["prefill"]["purpose"] == "redo the cut correctly"


def test_revise_still_goes_through_the_shared_primitive_unchanged(workdir, capsys):
    """`_act_on_verdicts` mints through `_mint_segment_round`, the same
    primitive replan uses -- this pins the revise round's shape: the rework
    form as the fresh interior, findings attributed, the panel refired."""
    wid = "issue18"
    cli.main(["open", "run-an-issue", "--issue", "18", "--title", "t"])
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
    fresh_plan = next(s for s in st["steps"]
                      if s["segment"] == "plan" and s.get("source") == "mint")
    assert fresh_plan["form"] == "skills/planner/forms/REWORK.toml"  # a revise reworks
    assert "gate 1 is untestable" in fresh_plan["prefill"]["findings"]
    assert "[p1]" in fresh_plan["prefill"]["findings"]

    fresh_panel = next(s for s in st["steps"]
                       if s.get("panel") and s["id"] != "plan")
    assert fresh_panel["form"] == "forms/PLAN_TO_EXECUTE.toml"
    assert fresh_panel["panel"] == st["steps"][3]["panel"]  # same panel config
    assert st["current"]["id"] == fresh_plan["id"]


def test_the_close_summary_carries_a_two_voices_verdict(workdir, capsys, monkeypatch):
    """The summary's verdict was read off panel-only steps, so a run whose
    critics had ruled on the plan closed carrying the empty string where the
    panel's word belongs -- and an escalated run, which is exactly the one a
    principal reads the summary of, said nothing at all.

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
    _dispatch_plan_critic(wid, verdict="escalate", findings="gap: wrong artifact entirely")
    capsys.readouterr()

    # the outlet the escalate minted: rule `up`, which is the move that ends
    # the run and makes the ruling the record
    assert runmod.state(wid)["current"]["form"] == "forms/IMPASSE.toml"
    _fill(journal.location(wid) / "IMPASSE.toml",
          'ruling = "up"\nwhy = "the critics read the plan against the wrong issue"\n')
    cli.main([wid, "submit"])
    _fill_close(wid)
    cli.main([wid, "submit"])
    stub_gh(monkeypatch)
    cli.main([wid, "close"])
    capsys.readouterr()

    closed = read_archived(workdir, wid, "closed")
    assert closed["summary"]["verdict"] == "escalate", (
        "the close summary of an escalated run carries "
        f"{closed['summary']['verdict']!r} where three critics ruled")
