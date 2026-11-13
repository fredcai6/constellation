"""A child's blocked note reaches the run that dispatched it. The note used
to stay in the child's own journal: the dispatcher's room said only "gone
without returning" and `wait` restarted the child into the same wall."""
import re

from engine import cli, journal
from test_brief import _mint_dispatch_step
from test_wait import _dead_pid, _dispatch_entries, _record, _throwaway_dispatch


def _blocked_child(workdir, marker):
    _throwaway_dispatch(workdir, marker)
    _mint_dispatch_step(wid="d1", child="d1.g1")
    journal.append("d1.g1", "run", title="t", assembly="run-a-gate", parent="d1")
    cli.main(["d1.g1", "note", "blocked", "nothing", "is", "left", "to", "cut"])
    _record("d1", "d1.g1", _dead_pid())


def test_a_blocked_child_is_named_in_its_dispatchers_room_and_not_restarted(
        bare_workdir, capsys):
    marker = bare_workdir / "spawned"
    _blocked_child(bare_workdir, marker)
    capsys.readouterr()

    assert cli.main(["d1", "wait", "--for", "1"]) == 0
    out = capsys.readouterr().out

    assert len(_dispatch_entries("d1")) == 1 and not marker.exists()
    assert "d1.g1 (blocked -- it asked a question and stopped)" in out
    assert "BLOCKED -- nothing is left to cut" in out
    assert re.search(r"answer it: \S*spine d1\.g1 note resumed n\w+ \"<your answer>\"", out)


def test_the_child_is_told_its_dispatcher_sees_the_note_and_to_end_its_turn(
        bare_workdir, capsys):
    _blocked_child(bare_workdir, bare_workdir / "spawned")
    out = capsys.readouterr().out
    assert "noted blocked" in out
    assert "d1 sees this in its own room" in out and "End your turn now" in out


def test_an_answered_block_restarts_the_child_and_prints_the_answer_in_its_room(
        bare_workdir, capsys):
    marker = bare_workdir / "spawned"
    _blocked_child(bare_workdir, marker)
    note = next(e for e in journal.read("d1.g1") if e.get("kind_detail") == "blocked")

    cli.main(["d1.g1", "note", "resumed", note["id"], "close", "the", "cut:", "o3", "is", "done"])
    cli.main(["d1", "wait", "--for", "1"])
    capsys.readouterr()

    assert len(_dispatch_entries("d1")) == 2
    cli.main(["d1.g1"])
    room = capsys.readouterr().out
    assert "YOU ASKED — nothing is left to cut" in room
    assert "ANSWER — close the cut: o3 is done" in room


def test_help_after_a_work_id_or_a_verb_prints_usage_and_touches_nothing(bare_workdir, capsys):
    _mint_dispatch_step(wid="d1", child="d1.g1")
    before = journal.read("d1")
    assert cli.main(["d1", "--help"]) == 0
    assert "spine <work-id> submit" in capsys.readouterr().out
    assert cli.main(["d1", "amend", "--help"]) == 0
    out = capsys.readouterr().out
    assert "amend close <step-id>" in out and "submit" not in out
    assert journal.read("d1") == before
