"""The round trip: open a real assembly, read the room, fill the file, submit.

This drives `assemblies/run-an-issue/ASSEMBLY.toml` and its real forms -- not
fixtures. If the shape of an assembly or a form changes, this test is what
notices.
"""

import pathlib

import pytest
import tomllib

from engine import cli, journal, run as runmod
from gitremote import init_checkout


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONSTELLATION_SESSION", "test-session")
    init_checkout(tmp_path)
    return tmp_path


def test_open_mints_the_skeleton(workdir, capsys):
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "parser drops last record"])
    capsys.readouterr()

    st = runmod.state("issue17")
    assert st["assembly"] == "run-an-issue"
    assert st["title"] == "parser drops last record"
    # per segment: its first interior step (when it declares one), then its
    # transition. A worklist starts with one step -- the work is what the
    # segment is for.
    assert [s["id"] for s in st["steps"]] == [
        "open", "understand-1", "understand", "plan-1", "plan", "execute"]
    assert st["current"]["id"] == "open"
    assert all(s["anchor"] for s in st["steps"] if not s["id"].endswith("-1"))

    # the plan segment's transition declares both a form and a critic panel;
    # its step carries both, unabridged
    plan = next(s for s in st["steps"] if s["id"] == "plan")
    assert plan["form"] == "forms/PLAN_TO_EXECUTE.toml"
    assert plan["panel"][0]["form"] == "skills/critic/forms/CRITIC.toml"
    assert plan["panel"][0]["worker"] == "critic"


def test_run_a_gate_skeleton_mints_a_review_step_for_its_panel(workdir, capsys):
    # run-a-gate's review transition declares a panel -- it used to mint
    # nothing at all, which is why a gate ran implement -> close with no
    # reviewer ever involved. It declares a conductor form beside the panel
    # now, so one skeleton step carries both voices: the panel fires first
    # and the form disposes of the round it judged.
    steps = runmod.skeleton(runmod.load_assembly("run-a-gate"))
    assert [s["id"] for s in steps] == ["work-1", "review", "close"]

    review = steps[1]
    assert review["form"] == "forms/REVIEW_ROUND.toml"
    assert review["filler"] == "conductor"  # the bare indirection, not a named role
    assert review["panel"] == [{
        "form": "skills/reviewer/forms/REVIEW.toml",
        "worker": "reviewer",
        "model": "standard",
        "criteria": "the gate spec, whole and only",
    }]

    # close's transition still declares only a form -- unaffected by the fix
    close = steps[2]
    assert close["form"] == "forms/GATE_CLOSE.toml"
    assert "panel" not in close


def test_status_is_a_room_description(workdir, capsys):
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "parser drops last record"])
    out = capsys.readouterr().out

    assert "issue17 · run-an-issue · open (1 of 6)" in out
    assert "issue17: parser drops last record" in out
    # the imperative is rendered, not the raw form
    assert "Confirm what this run is solving" in out
    # every legal move is spelled out; the agent never guesses a verb
    assert "spine issue17 submit" in out
    assert "spine issue17 note" in out
    assert ".agent-work/issue17/OPEN.toml" in out


def test_response_form_is_materialized_and_parses(workdir, capsys):
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    capsys.readouterr()
    dest = pathlib.Path(".agent-work/issue17/OPEN.toml")
    assert dest.exists()
    tomllib.load(open(dest, "rb"))  # always valid TOML, even blank


def test_refusal_names_the_field_and_the_way_out(workdir, capsys):
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    capsys.readouterr()
    with pytest.raises(SystemExit) as e:
        cli.main(["issue17", "submit"])
    msg = str(e.value)
    assert "issue" in msg or "authority" in msg  # names a field
    assert "waived:" in msg and "unknown:" in msg  # always offers the escape


def _fill_open(path):
    # the `issue` field names a file in the work location, so write one
    issue = path.parent / "issue.md"
    issue.write_text("The parser drops the last record of a file with no "
                     "trailing newline.\n")
    path.write_text(f'''
issue = "{issue}"

authority = """
Principal: Tommy, live. I own driving this to a merged fix; gaps go to him."""

[[questions]]
question = "Which inputs drop the last record -- EOF without newline only?"
type = "fact"
move = "reproduce"

[[questions]]
question = "Do third-party files without trailing newlines need to parse too?"
type = "decision"
move = "ask"
''')


def test_submit_advances_and_seeds_the_board(workdir, capsys):
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    capsys.readouterr()
    _fill_open(pathlib.Path(".agent-work/issue17/OPEN.toml"))

    cli.main(["issue17", "submit"])
    out = capsys.readouterr().out

    st = runmod.state("issue17")
    assert "open" in st["done"]
    assert st["current"]["id"] == "understand-1"          # the spec-writer's own round
    assert "understand (2 of 6)" in out          # the room header names the segment, not the step

    # the plan field minted board rows, and the board keeps its guidance
    board = pathlib.Path(".agent-work/issue17/UNDERSTAND.toml")
    assert board.exists()
    rows = tomllib.load(open(board, "rb"))["question"]
    assert [r["type"] for r in rows] == ["fact", "decision"]
    assert [r["status"] for r in rows] == ["open", "open"]
    assert "never self-answer" in board.read_text()  # the interrogator's guidance survives


def test_the_journal_is_the_only_state(workdir):
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    _fill_open(pathlib.Path(".agent-work/issue17/OPEN.toml"))
    cli.main(["issue17", "submit"])

    # every fact above is recoverable from the file alone
    kinds = [e["kind"] for e in journal.read("issue17")]
    assert kinds[0] == "run"
    assert kinds.count("step") == 6
    assert "submit" in kinds and "board" in kinds
    assert not list(pathlib.Path(".agent-work/issue17").glob("*state*"))


def test_note_blocked_surfaces_first(workdir, capsys):
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    cli.main(["issue17", "note", "blocked", "needs a ruling on scope"])
    capsys.readouterr()
    cli.main(["issue17"])
    out = capsys.readouterr().out
    assert "BLOCKED" in out and "needs a ruling on scope" in out
    assert out.index("BLOCKED") < out.index("your response form")


def test_ledger_lists_open_runs(workdir, capsys, monkeypatch):
    """Each root run works inside its own worktree (ruling 8): opening
    issue18 moves the process into `.worktrees/issue18`, a directory that
    does not nest under issue17's own -- top-level resolution (see
    test_worktree_reach.py) lands it beside issue17 instead. `cmd_ledger`
    now scans both roots -- this checkout's own `.agent-work` and every
    sibling worktree's -- so bare `spine` from the top level lists both runs
    together, not just each from inside its own tree."""
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "parser eof"])
    capsys.readouterr()
    monkeypatch.chdir(workdir)  # back to the top level, not issue17's own worktree

    cli.main(["open", "run-an-issue", "--issue", "18", "--title", "writer atomicity"])
    capsys.readouterr()
    monkeypatch.chdir(workdir)  # back to the top level, not issue18's own worktree

    cli.main([])
    out = capsys.readouterr().out
    assert "issue17" in out and "parser eof" in out
    assert "issue18" in out and "writer atomicity" in out


def _pass_spec(wid):
    """Take the spec-writer's own round through its cold panel, board rows
    left untouched -- so the transition ahead (consolidate) is reachable to
    prove what it alone still checks: the board, not the spec."""
    loc = pathlib.Path(f".agent-work/{wid}")
    (loc / "spec.md").write_text("1. placeholder commitment.\n")
    (loc / "SPEC.toml").write_text('spec = "%s/spec.md"\n' % loc)
    cli.main([wid, "submit"])
    panel = next(s for s in runmod.state(wid)["steps"] if s["id"] == "understand")["panel"]
    for n in range(1, len(panel) + 1):
        tag = f"understand.p{n}"
        cli.main(["open", "give-a-verdict", "--parent", wid, "--step", tag])
        panelist = f"{wid}.{tag}"
        (journal.location(panelist) / "CRITIC.toml").write_text(
            'findings = "none: waived: clean"\n'
            'vocabulary = "waived: consistent"\nverdict = "pass"\n')
        cli.main([panelist, "submit"])
        cli.main([panelist, "close"])


def _board(path, **repl):
    t = path.read_text()
    for old, new in repl.items():
        t = t.replace(old.replace("_", " ") if False else old, new, 1)
    path.write_text(t)


def test_consolidate_refuses_an_unworked_board(workdir, capsys):
    """The assembly declares validates = "board" and CONSOLIDATE.toml tells the
    agent the engine checks it. This proves the engine actually does -- the
    wiring was missing once, and a form that lies about the engine is the
    worst failure available to a system whose doctrine lives in forms."""
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    _fill_open(pathlib.Path(".agent-work/issue17/OPEN.toml"))
    cli.main(["issue17", "submit"])
    _pass_spec("issue17")
    capsys.readouterr()

    pathlib.Path(".agent-work/issue17/CONSOLIDATE.toml").write_text(
        'spec = ".agent-work/issue17/spec.md"\nkey-terms = "waived: none"\n'
        'settle = "waived: none"\n')

    with pytest.raises(SystemExit) as e:
        cli.main(["issue17", "submit"])
    msg = str(e.value)
    assert "q1" in msg and "q2" in msg          # names every unresolved row
    assert "deferred:" in msg                    # and states the way out
    assert runmod.state("issue17")["current"]["id"] == "understand"  # did not advance


def test_the_board_escape_is_one_step(workdir, capsys):
    """deferred: <reason> passes in a single edit -- the corollary that makes
    this check legal at all."""
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    _fill_open(pathlib.Path(".agent-work/issue17/OPEN.toml"))
    cli.main(["issue17", "submit"])
    _pass_spec("issue17")
    pathlib.Path(".agent-work/issue17/CONSOLIDATE.toml").write_text(
        'spec = ".agent-work/issue17/spec.md"\nkey-terms = "waived: none"\n'
        'settle = "waived: none"\n')

    board = pathlib.Path(".agent-work/issue17/UNDERSTAND.toml")
    board.write_text(board.read_text()
                     .replace('status = "open"', 'status = "deferred: principal away"'))
    capsys.readouterr()

    cli.main(["issue17", "submit"])
    assert runmod.state("issue17")["current"]["id"] == "plan-1"
