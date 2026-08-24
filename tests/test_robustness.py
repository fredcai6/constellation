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
