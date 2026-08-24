"""Ways the engine could lose or corrupt the record.

Every case here was found by a cold reviewer probing the running system, not
by the suite that was green at the time. The secretary's one duty is to keep
the record; each of these broke that duty silently.
"""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from engine import cli, journal, run as runmod  # noqa: E402


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONSTELLATION_SESSION", "test-session")
    return tmp_path


def _open(wid="issue17"):
    cli.main(["open", "run-an-issue", "--id", wid, "--title", "t"])


def test_a_torn_journal_reads_as_the_work_before_the_tear(workdir, capsys):
    """An append interrupted mid-block -- Ctrl-C, OOM, full disk -- must not
    brick every verb on the run. State is a fold over this file, so a raising
    read would make the run unusable until someone hand-repaired TOML."""
    _open()
    capsys.readouterr()
    before = len(journal.read("issue17"))

    with open(".agent-work/issue17/journal.toml", "a") as f:
        f.write('\n[[entry]]\nkind = "note"\nat = "2026-08-24T0')

    assert len(journal.read("issue17")) == before   # the torn tail is dropped
    cli.main(["issue17"])                            # and every verb still works
    assert "issue17" in capsys.readouterr().out
    cli.main(["issue17", "note", "observation", "still usable"])


def test_a_malformed_plan_field_refuses_before_anything_is_recorded(workdir, capsys):
    """A plan field of the wrong shape used to journal the submit and then die
    minting, leaving a run that looked advanced with no work in it."""
    _open()
    pathlib.Path(".agent-work/issue17/OPEN.toml").write_text(
        'issue = "gh:17"\nauthority = "Tommy."\nquestions = "not a list of blocks"\n')
    capsys.readouterr()

    with pytest.raises(SystemExit) as e:
        cli.main(["issue17", "submit"])
    assert "questions" in str(e.value)
    assert "nothing was recorded" in str(e.value)

    st = runmod.state("issue17")
    assert st["current"]["id"] == "open"                 # did not advance
    assert "open" not in st["done"]                      # and nothing was journaled
    assert not st["boards"]


def test_amended_step_ids_do_not_collide(workdir):
    """Ids were counted from what exists, so two sessions amending at once
    minted the same id -- and `done` is keyed by id, so one submit would
    complete every step sharing it, silently dropping the rest."""
    _open()
    for i in range(6):
        cli.main(["issue17", "amend", "add", "--segment", "plan", "--form",
                  "forms/PLAN.toml", "--reason", f"r{i}"])
    ids = [s["id"] for s in runmod.state("issue17")["steps"] if "-a" in s["id"]]
    assert len(ids) == len(set(ids)) == 6


def test_note_ids_do_not_collide_and_resumed_clears_its_block(workdir, capsys):
    """`note resumed <id>` is the command the engine prints in its own output;
    it recorded the target under the wrong key and never cleared anything."""
    _open()
    cli.main(["issue17", "note", "blocked", "needs a ruling"])
    st = runmod.state("issue17")
    block = runmod.blocks(st)[0]
    assert block["text"] == "needs a ruling"

    cli.main(["issue17", "note", "resumed", block["id"], "Tommy ruled"])
    assert runmod.blocks(runmod.state("issue17")) == []

    capsys.readouterr()
    cli.main(["issue17"])
    assert "BLOCKED" not in capsys.readouterr().out


def test_a_work_id_cannot_escape_the_work_tree(workdir):
    # an omitted --id legitimately mints one, so "" is not in this list
    for bad in ["../../escape", "a/b", "..", "a..b", "/abs/path", "x/../../y"]:
        with pytest.raises(SystemExit):
            cli.main(["open", "run-an-issue", "--id", bad, "--title", "t"])
    assert not list(workdir.glob("escape*"))
    assert not (workdir.parent / "escape").exists()


def test_a_hanging_check_refuses_instead_of_wedging_the_turn(workdir, monkeypatch):
    """A check command that never returns used to block forever, burning the
    agent's turn with no way out."""
    monkeypatch.setattr(cli, "CHECK_TIMEOUT", 1)
    pathlib.Path("constellation.toml").write_text('[models]\nstandard = "x"\n')
    cli.main(["open", "run-a-gate", "--id", "g1"])
    journal.append("g1", "prefill", fields={"done": "sleep 30"})
    pathlib.Path(".agent-work/g1/IMPLEMENT.toml").write_text(
        'change = "c"\ndeviations = "waived: none"\n')

    with pytest.raises(SystemExit) as e:
        cli.main(["g1", "submit"])
    msg = str(e.value)
    assert "did not finish" in msg
    assert "amend close" in msg  # the refusal states the way out


def test_closing_to_a_missing_parent_does_not_fabricate_one(workdir, capsys):
    """The return used to create the parent's journal from nothing: a run with
    no opening, no title, no assembly, sitting in the ledger."""
    _open("issue17")
    journal.append("issue17", "step", id="g1", segment="execute",
                   dispatches="run-a-gate", prefill={"purpose": "p"},
                   child="issue17.g1", source="mint")
    cli.main(["open", "run-a-gate", "--parent", "issue17", "--step", "g1"])
    child = "issue17.g1"
    pathlib.Path(f".agent-work/issue17/g1/IMPLEMENT.toml").write_text(
        'change = "c"\ndeviations = "waived: none"\n')
    cli.main([child, "submit"])
    # drive the review panel for real: one panelist, a pass verdict
    cli.main(["open", "give-a-verdict", "--parent", child, "--step", "review.p1"])
    panelist = f"{child}.review.p1"
    pathlib.Path(f".agent-work/issue17/g1/review/p1/REVIEW.toml").write_text(
        'verify = "read it"\nfindings = "none: waived: clean"\n'
        'vocabulary = "waived: consistent"\nverdict = "pass"\n')
    cli.main([panelist, "submit"])
    cli.main([panelist, "close"])
    pathlib.Path(f".agent-work/issue17/g1/GATE_CLOSE.toml").write_text(
        'residue = "waived: none"\n')
    cli.main([child, "submit"])

    # the parent's record disappears -- a wiped worktree, a bad cleanup
    pathlib.Path(".agent-work/issue17/journal.toml").unlink()
    capsys.readouterr()

    cli.main([child, "close"])
    assert "not found" in capsys.readouterr().out
    assert not journal.exists("issue17")          # no phantom parent minted
    assert runmod.blocks(runmod.state(child))     # the undelivered return is a block


def test_the_off_path_never_shows_a_traceback(workdir):
    """A fresh agent meets these by mistyping. Each must answer with the way
    forward, not a Python line number."""
    for argv, want in [
        (["open"], "assemblies:"),
        (["open", "bogus", "--title", "t"], "no assembly named"),
        (["nosuchrun"], "no run named"),
    ]:
        with pytest.raises(SystemExit) as e:
            cli.main(argv)
        assert want in str(e.value)


def test_a_near_miss_note_kind_refuses_instead_of_no_opping(workdir):
    """`note block ...` printed success and did nothing -- only the exact word
    is ever acted on, so a near miss must not look like a hit."""
    _open()
    with pytest.raises(SystemExit) as e:
        cli.main(["issue17", "note", "block", "oops"])
    assert "blocked" in str(e.value)


def test_status_names_the_board_it_will_validate(workdir, capsys):
    """The board was invisible in status while the imperative claimed it was
    already worked -- the room description lying about the room."""
    _open()
    pathlib.Path(".agent-work/issue17/OPEN.toml").write_text(
        'issue = "gh:17"\nauthority = "T."\n[[questions]]\nquestion = "q?"\ntype = "fact"\n')
    cli.main(["issue17", "submit"])
    out = capsys.readouterr().out
    assert "UNDERSTAND.toml" in out
    assert "will not pass while a row is open" in out


def test_every_refusal_states_an_escape_that_works(workdir):
    """A refusal used to append one hardcoded suffix -- correct for a form
    field, wrong for a board row (which takes deferred:, not waived:), and
    nonsensical for a lookup. Printing an escape that does not work is worse
    than printing none."""
    _open()
    pathlib.Path(".agent-work/issue17/OPEN.toml").write_text(
        'issue = "gh:17"\nauthority = "T."\n[[questions]]\nquestion = "q?"\ntype = "fact"\n')
    cli.main(["issue17", "submit"])
    pathlib.Path(".agent-work/issue17/CONSOLIDATE.toml").write_text(
        'learnings = "x"\nkey-terms = "waived: none"\nsettle = "waived: none"\n')

    with pytest.raises(SystemExit) as e:
        cli.main(["issue17", "submit"])
    msg = str(e.value)
    assert "deferred:" in msg
    assert "waived:" not in msg   # the escape boards.validate does not accept

    with pytest.raises(SystemExit) as e:
        cli.main(["issue17", "amend", "close", "nosuch", "--reason", "r"])
    assert "pending:" in str(e.value)   # names the ids that were in scope all along


def test_a_crash_is_never_a_refusal(workdir):
    """Two paths raised bare Python errors: nothing journaled, no way forward.
    Worse than an illegitimate refusal."""
    _open()
    with pytest.raises(SystemExit):
        cli.main(["issue17", "amend"])            # was IndexError

    pathlib.Path(".agent-work/issue17/OPEN.toml").write_text('issue = "unclosed\n')
    with pytest.raises(SystemExit) as e:
        cli.main(["issue17", "submit"])           # was TOMLDecodeError
    assert "not valid TOML" in str(e.value)
    assert "nothing was recorded" in str(e.value)


def test_an_amended_anchor_is_flagged_where_it_will_be_read(workdir):
    """The design's freeze is visibility, not refusal: amending an anchor is
    allowed and must be loud in the record the tier above reads."""
    _open()
    cli.main(["issue17", "amend", "close", "understand",
              "--reason", "issue already states it"])
    from engine import render
    lines = render.amends(runmod.state("issue17")["amends"])
    assert lines and lines[0].startswith("ANCHOR ")
    assert "issue already states it" in lines[0]


def test_a_field_in_hand_is_not_mistaken_for_an_answer(workdir, capsys):
    """`working: <what is left>` is the status an agent sets while a field is
    still in hand. Submitting it would record work-in-progress as an answer,
    and the next reader could not tell the difference."""
    cli.main(["open", "run-a-gate", "--id", "g1"])
    pathlib.Path(".agent-work/g1/IMPLEMENT.toml").write_text(
        'change = "working: still tracing the EOF branch"\n'
        'deviations = "waived: none"\n')
    capsys.readouterr()

    with pytest.raises(SystemExit) as e:
        cli.main(["g1", "submit"])
    msg = str(e.value)
    assert "still tracing" in msg           # says what is left, not just that it is
    assert "waived:" in msg                 # and the honest ways to close it

    cli.main(["g1"])                        # status surfaces it unasked
    out = capsys.readouterr().out
    assert "still in hand" in out and "still tracing the EOF branch" in out

    # finishing it is one edit
    pathlib.Path(".agent-work/g1/IMPLEMENT.toml").write_text(
        'change = "traced it; flushed at capacity"\ndeviations = "waived: none"\n')
    cli.main(["g1", "submit"])
    assert "work-1" in runmod.state("g1")["done"]
