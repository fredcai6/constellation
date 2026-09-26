"""A spawned form filler, seen from both sides: `wait` holds while one is
working on the current step, and the filler itself is told its step is done
once that step is no longer current, instead of being handed the next room.

Measured before this file existed (tennis_elo, 2026-09-24): issue71's select
filler, spawned on a heavy runner, read the next room after its own submit
as its own, then called `wait` 197 times in 30 minutes while a later step's
filler worked -- `wait` rendered at once beside a live filler.

Every process this file starts is a short-lived `python3 -c ...`.
"""

import os
import subprocess
import sys
import threading
import time

from engine import checks as checkrun
from engine import cli, journal
from engine import run as runmod
from test_brief import _mint_work_step
from test_drive import _filler_record
from test_wait import _dead_pid, _sleeper


def test_wait_holds_while_the_current_steps_filler_is_alive(bare_workdir, capsys, monkeypatch):
    monkeypatch.setattr(checkrun, "WAIT_POLL", 0.05)
    _mint_work_step(wid="f1", filler="implementer")
    proc = _sleeper(5)
    _filler_record("f1", "g1", proc.pid)

    def _submit_it():
        time.sleep(0.3)
        journal.append("f1", "submit", step="g1", fields={})
    threading.Thread(target=_submit_it, daemon=True).start()

    began = time.monotonic()
    code = cli.main(["f1", "wait", "--for", "5"])
    elapsed = time.monotonic() - began
    capsys.readouterr()

    assert code == 0
    assert 0.25 < elapsed < 3, f"elapsed {elapsed}"
    assert runmod.state("f1")["awaiting_close"]
    proc.kill()
    proc.wait()


def test_wait_stops_holding_when_the_filler_dies(bare_workdir, capsys, monkeypatch):
    monkeypatch.setattr(checkrun, "WAIT_POLL", 0.05)
    _mint_work_step(wid="f1", filler="implementer")
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.3)"])
    _filler_record("f1", "g1", proc.pid)

    began = time.monotonic()
    threading.Thread(target=proc.wait, daemon=True).start()  # reap it, no zombie
    code = cli.main(["f1", "wait", "--for", "5"])
    elapsed = time.monotonic() - began
    capsys.readouterr()

    assert code == 0
    assert elapsed < 3, f"elapsed {elapsed}"


def test_wait_beside_a_dead_filler_renders_at_once(bare_workdir, capsys):
    _mint_work_step(wid="f1", filler="implementer")
    _filler_record("f1", "g1", _dead_pid())

    began = time.monotonic()
    assert cli.main(["f1", "wait", "--for", "5"]) == 0
    assert time.monotonic() - began < 1


def test_the_filler_itself_never_waits_on_its_own_step(bare_workdir, capsys, monkeypatch):
    _mint_work_step(wid="f1", filler="implementer")
    proc = _sleeper(5)
    _filler_record("f1", "g1", proc.pid)
    monkeypatch.setenv(checkrun.FILLS_ENV, "f1:g1")

    began = time.monotonic()
    code = cli.main(["f1", "wait", "--for", "5"])
    out = capsys.readouterr().out

    assert code == 0
    assert time.monotonic() - began < 1
    assert "fill it, then:" in out        # its own room: the form is its to fill
    assert "form filler:        working" not in out
    proc.kill()
    proc.wait()


def test_a_filler_whose_step_moved_on_is_told_it_is_done(bare_workdir, capsys, monkeypatch):
    _mint_work_step(wid="f1", filler="implementer")
    journal.append("f1", "submit", step="g1", fields={})
    monkeypatch.setenv(checkrun.FILLS_ENV, "f1:g1")

    assert cli.main(["f1"]) == 0
    out = capsys.readouterr().out
    assert "Your step is done" in out
    assert "End your turn now" in out


def test_a_filler_env_for_another_run_changes_nothing(bare_workdir, capsys, monkeypatch):
    _mint_work_step(wid="f1", filler="implementer")
    monkeypatch.setenv(checkrun.FILLS_ENV, "other:g1")

    assert cli.main(["f1"]) == 0
    out = capsys.readouterr().out
    assert "Your step is done" not in out
    assert "fill it, then:" in out


def test_spawn_stamps_the_filled_step_and_never_passes_it_on(tmp_path, monkeypatch):
    """A form filler's process carries `<wid>:<step>`; any other spawn --
    including one a filler itself starts -- carries none."""
    monkeypatch.setenv(checkrun.FILLS_ENV, "inherited:x")
    script = (f"import os, pathlib; pathlib.Path({str(tmp_path)!r}, 'env')"
              f".write_text(os.environ.get({checkrun.FILLS_ENV!r}, '<none>'))")
    argv = [sys.executable, "-c", script]

    checkrun._spawn(argv, tmp_path / "a.log", fills="f1:g1").wait()
    assert (tmp_path / "env").read_text() == "f1:g1"

    checkrun._spawn(argv, tmp_path / "b.log").wait()
    assert (tmp_path / "env").read_text() == "<none>"
