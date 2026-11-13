"""A consumer repository's commands and agents never see the engine's own
root on `PYTHONPATH`: there it shadows the repository's packages and breaks
its virtualenv's interpreter (story_time, 2026-11-06: 17 of 55 reviewers)."""
import os

from engine import checks


def test_a_proof_command_runs_without_the_engine_root_on_pythonpath(tmp_path, monkeypatch):
    root = str(checks._ROOT)
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join([root, "/somewhere/else"]))
    code, out = checks._run('printf %s "$PYTHONPATH"', str(tmp_path), 30)
    assert code == 0
    assert out == "/somewhere/else"


def test_a_proof_command_gets_no_pythonpath_when_the_root_was_all_of_it(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", str(checks._ROOT))
    code, out = checks._run('printf %s "${PYTHONPATH-unset}"', str(tmp_path), 30)
    assert (code, out) == (0, "unset")


def test_a_dispatched_process_gets_no_engine_root_and_the_runner_does(tmp_path, monkeypatch):
    root = str(checks._ROOT)
    monkeypatch.setenv("PYTHONPATH", root)
    for engine, expected in ((False, "unset"), (True, root)):
        log = tmp_path / f"log-{engine}"
        proc = checks._spawn(["/bin/sh", "-c", 'printf %s "${PYTHONPATH-unset}"'],
                             log, engine=engine)
        assert proc.wait(timeout=30) == 0
        assert log.read_text() == expected
