"""Nesting: dispatch, prefill, returns, close, and amend.

This drives the real `run-an-issue` and `run-a-gate` assemblies end to end --
not fixtures. A gate spec minted from PLAN_TO_EXECUTE.toml becomes a child
run's opening orders; the child's close stamps a return that completes the
parent's dispatch step; `close` and `amend` round out the six verbs.
"""

import pathlib
import sys

import pytest
import tomllib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from engine import cli, journal, run as runmod  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONSTELLATION_SESSION", "test-session")
    # the command palette (models, check commands) is host-repo config;
    # tests run in an isolated tmp cwd, so it travels with them
    (tmp_path / "constellation.toml").write_text((REPO / "constellation.toml").read_text())
    return tmp_path


def _fill(path, text):
    path.write_text(text)


def _fill_open(wid):
    _fill(pathlib.Path(f".agent-work/{wid}/OPEN.toml"), '''
issue = "gh:17"

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


def _fill_plan(wid):
    """The plan segment opens with a step to plan in -- the interior's first
    step -- before its transition cuts the plan into gates."""
    _fill(pathlib.Path(f".agent-work/{wid}/PLAN.toml"), '''
plan = ".agent-work/%s/plan.md"
design-it-twice = "waived: reversible"
key-terms = "waived: none"
findings-addressed = "waived: first pass"
''' % wid)


def _fill_plan_to_execute(wid):
    _fill(pathlib.Path(f".agent-work/{wid}/PLAN_TO_EXECUTE.toml"), '''
plan = ".agent-work/%s/plan.md"

[[gates]]
purpose = "fix the parser to handle EOF without a trailing newline"
scope = "src/parser.c only"
done = "true"

[[gates]]
purpose = "add a regression test for the EOF case"
scope = "tests/parser directory"
done = "true"
model = "light"
''' % wid)


def _fill_implement(wid, step_id):
    _fill(journal.location(wid) / "IMPLEMENT.toml", '''
change = "adjusted the loop bound in src/parser.c"
deviations = "waived: none"
''')


def _fill_gate_close(wid):
    _fill(journal.location(wid) / "GATE_CLOSE.toml", 'residue = "nothing surprising"\n')


def _fill_gate_transition(wid):
    _fill(journal.location(wid) / "GATE_TRANSITION.toml", '''
learned = "the fix landed cleanly, no follow-on scope"
plan-holds = "advance"
''')


def _fill_close(wid):
    _fill(journal.location(wid) / "CLOSE.toml", '''
disposition = "merged to main"
triage = "waived: none"
residue = "waived: none"
''')


def _mint_two_gates(wid="issue17"):
    """Open a run-an-issue and drive it to the freshly minted g1 dispatch step."""
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "parser drops last record"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    _fill_plan(wid)
    cli.main([wid, "submit"])
    _fill_plan_to_execute(wid)
    cli.main([wid, "submit"])


def _dispatch_and_close_child(parent_wid, step_id, cycles=0):
    """Open the child a dispatch step names, work its implement steps, close it.

    A gate opens with one implement step already -- the work is what the gate
    is for. `cycles` counts the REWORK beyond that first pass, each added by
    amend the way a revise verdict would add it.
    """
    cli.main(["open", "run-a-gate", "--parent", parent_wid, "--step", step_id])
    child_wid = f"{parent_wid}.{step_id}"
    _fill_implement(child_wid, step_id)
    cli.main([child_wid, "submit"])
    for i in range(cycles):
        cli.main([child_wid, "amend", "add", "--segment", "work", "--form",
                  "skills/implementer/forms/IMPLEMENT.toml", "--reason", f"cycle {i+1}"])
        _fill_implement(child_wid, step_id)
        cli.main([child_wid, "submit"])
    _fill_gate_close(child_wid)
    cli.main([child_wid, "submit"])
    cli.main([child_wid, "close"])
    return child_wid


# -- 1. gates plan field mints dispatch + adjudication pairs -----------------


def test_gates_field_mints_dispatch_and_adjudicate_pairs_in_order(workdir, capsys):
    _mint_two_gates()
    capsys.readouterr()

    st = runmod.state("issue17")
    ids = [s["id"] for s in st["steps"]]
    assert ids == ["open", "understand", "plan-1", "plan", "g1", "g1-adjudicate",
                    "g2", "g2-adjudicate", "execute"]
    assert st["steps"][-1]["terminal"] is True  # the terminal close step still sorts last

    g1 = next(s for s in st["steps"] if s["id"] == "g1")
    assert g1["segment"] == "execute" and g1["dispatches"] == "run-a-gate"
    assert g1["source"] == "mint" and g1["child"] == "issue17.g1"
    assert g1["prefill"]["purpose"].startswith("fix the parser")
    assert "id" not in g1["prefill"]

    g1adj = next(s for s in st["steps"] if s["id"] == "g1-adjudicate")
    assert g1adj["form"] == "forms/GATE_TRANSITION.toml"
    assert g1adj["filler"] == "conductor"

    g2 = next(s for s in st["steps"] if s["id"] == "g2")
    assert g2["prefill"]["model"] == "light"


# -- 2. opening a child records prefill and nests its location ---------------


def test_open_child_records_prefill_and_nests_location(workdir, capsys):
    _mint_two_gates()
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
    _mint_two_gates()
    capsys.readouterr()
    cli.main(["issue17"])
    out = capsys.readouterr().out
    assert "claude-sonnet-5" in out  # standard tier, resolved from constellation.toml
    assert "spine open run-a-gate --parent issue17 --step g1" in out

    # a gate's own model override rides the prefill and resolves too
    _dispatch_and_close_child("issue17", "g1")
    cli.main(["issue17"])  # materializes the now-current g1-adjudicate form
    capsys.readouterr()
    _fill_gate_transition("issue17")
    cli.main(["issue17", "submit"])
    capsys.readouterr()
    cli.main(["issue17"])
    out = capsys.readouterr().out
    assert "claude-haiku-4-5-20251001" in out
    assert "spine open run-a-gate --parent issue17 --step g2" in out


# -- 4/5. child close returns to the parent, completes the dispatch step, --
#         and the mechanical summary carries cycles and checks no one typed


def test_child_close_completes_dispatch_step_and_carries_mechanical_summary(workdir, capsys):
    _mint_two_gates()
    capsys.readouterr()

    child_wid = _dispatch_and_close_child("issue17", "g1", cycles=2)
    capsys.readouterr()

    # the child's own close entry
    child_entries = journal.read(child_wid)
    closed = next(e for e in child_entries if e["kind"] == "closed")
    assert closed["fields"]["residue"] == "nothing surprising"

    # a return landed in the PARENT's journal, keyed to the dispatch step
    parent_entries = journal.read("issue17")
    ret = next(e for e in parent_entries if e["kind"] == "return")
    assert ret["step"] == "g1" and ret["child"] == "issue17.g1"
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

    # the mechanical summary: a first pass, two reworks, and a real engine-run
    # check -- none of it typed by the agent
    summary = ret["summary"]
    assert summary["steps_completed"] == 4  # first-pass implement + 2 rework + close
    # `cycles` counts rework beyond the first pass, which is the number that
    # tells the tier above a gate is churning
    assert {"segment": "work", "count": 2} in summary["cycles"]
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
