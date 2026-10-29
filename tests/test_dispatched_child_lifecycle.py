"""A dispatched child's process ends with its run.

A gate child (`claude -p`, started through the palette `dispatch` command)
used to stay alive 10-50 minutes after its run closed, busy-polling the
parent's room, and a conductor tidying them killed a live rework round
because nothing told a finished child from a running one. Two halves: the
closed room tells the child its turn ends, and the parent's status names any
child whose process outlives its run.
"""

from engine import cli, journal
from test_onward import _gate_ready_to_close
from test_wait import _dead_pid, _record, _sleeper


def test_the_closed_room_ends_the_dispatched_sessions_turn(workdir, capsys):
    child = _gate_ready_to_close()
    capsys.readouterr()

    cli.main([child, "close"])
    out = capsys.readouterr().out

    assert "your turn ends here" in out
    assert "continue there:" in out   # the dispatching conductor's move stays named


def test_parent_status_names_a_child_process_alive_after_its_run_closed(workdir, capsys):
    child = _gate_ready_to_close()
    cli.main([child, "close"])
    proc = _sleeper(30)
    _record("issue17", child, proc.pid)
    capsys.readouterr()

    cli.main(["issue17"])
    out = capsys.readouterr().out
    proc.kill()
    proc.wait()

    assert f"still alive after its run closed: {child} (pid {proc.pid}" in out


def test_parent_status_is_silent_for_a_live_child_whose_run_is_open(workdir, capsys):
    """The live rework round a conductor once killed: its run is open, so
    its process is working, not lingering."""
    child = _gate_ready_to_close()
    proc = _sleeper(30)
    _record("issue17", child, proc.pid)
    capsys.readouterr()

    cli.main(["issue17"])
    out = capsys.readouterr().out
    proc.kill()
    proc.wait()

    assert "still alive after its run closed" not in out


def test_parent_status_is_silent_once_the_closed_childs_process_is_gone(workdir, capsys):
    child = _gate_ready_to_close()
    cli.main([child, "close"])
    _record("issue17", child, _dead_pid())
    capsys.readouterr()

    cli.main(["issue17"])
    out = capsys.readouterr().out

    assert "still alive after its run closed" not in out
