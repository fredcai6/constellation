"""Tests for the rail: an advisory hook that must never raise or block.

Every never-raises scenario proves the same thing in a different failure
shape: the process exits clean and a bad journal never hides a good one.
The warn/silent tests prove the actual advisory content: it speaks only
when a run is open, and it never blocks -- there is nothing here that can
fail a turn.
"""

import io
import json

import pytest

from engine import journal, rail


@pytest.fixture(autouse=True)
def in_tmp_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CONSTELLATION_SESSION", raising=False)


def _stdin(monkeypatch, payload):
    text = json.dumps(payload) if payload is not None else ""
    monkeypatch.setattr("sys.stdin", io.StringIO(text))


def _open_run(wid="issue17", blocked=False):
    journal.append(wid, "run", title="fix the thing", assembly="run-an-issue")
    journal.append(wid, "step", id="execute", segment="execute", form="x.toml",
                   filler="conductor", anchor=True, terminal=False, validates="")
    if blocked:
        journal.append(wid, "note", id="n1", kind_detail="blocked",
                        text="waiting on a decision", step="execute")


def _close_run(wid="issue17"):
    journal.append(wid, "submit", step="execute", fields={})
    journal.append(wid, "closed")


# -- never raises, always exits 0, no output on failure ----------------------


def test_empty_stdin_exits_clean(monkeypatch, capsys):
    _stdin(monkeypatch, None)
    assert rail.main() == 0
    assert capsys.readouterr().out == ""


def test_missing_agent_work_exits_clean(monkeypatch, capsys):
    _stdin(monkeypatch, {"hook_event_name": "Stop"})
    assert rail.main() == 0
    assert capsys.readouterr().out == ""


def test_truncated_toml_journal_exits_clean(monkeypatch, capsys):
    path = journal.journal_path("issue17")
    path.parent.mkdir(parents=True)
    path.write_text('[[entry]]\nkind = "ru')  # unterminated string
    _stdin(monkeypatch, {"hook_event_name": "Stop"})
    assert rail.main() == 0
    assert capsys.readouterr().out == ""


def test_garbage_bytes_journal_exits_clean(monkeypatch, capsys):
    path = journal.journal_path("issue17")
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xff\xfe\x00not toml at all {{{")
    _stdin(monkeypatch, {"hook_event_name": "Stop"})
    assert rail.main() == 0
    assert capsys.readouterr().out == ""


def test_unreadable_directory_exits_clean(monkeypatch, tmp_path):
    _open_run("issue17")
    work_dir = tmp_path / ".agent-work" / "issue17"
    mode = work_dir.stat().st_mode
    try:
        work_dir.chmod(0)
        _stdin(monkeypatch, {"hook_event_name": "Stop"})
        assert rail.main() == 0
    finally:
        work_dir.chmod(mode)  # restore so tmp_path cleanup can remove it


def test_malformed_journal_does_not_hide_a_good_runs_warning(monkeypatch, capsys):
    bad = journal.journal_path("issuebad")
    bad.parent.mkdir(parents=True)
    bad.write_text("not valid toml {{{")
    _open_run("issue17")
    _stdin(monkeypatch, {"hook_event_name": "Stop"})

    assert rail.main() == 0
    out = capsys.readouterr().out
    assert "issue17" in out
    assert "issuebad" not in out


# -- the actual advisory content ---------------------------------------------


def test_silent_when_nothing_open(monkeypatch, capsys):
    _open_run("issue17")
    _close_run("issue17")
    _stdin(monkeypatch, {"hook_event_name": "Stop"})

    assert rail.main() == 0
    assert capsys.readouterr().out == ""


def test_stop_warns_by_name_position_and_continue_command(monkeypatch, capsys):
    _open_run("issue17")
    _stdin(monkeypatch, {"hook_event_name": "Stop"})

    assert rail.main() == 0
    out = capsys.readouterr().out
    assert "issue17" in out
    assert "execute" in out
    assert "spine issue17" in out


def test_stop_names_an_open_block(monkeypatch, capsys):
    _open_run("issue17", blocked=True)
    _stdin(monkeypatch, {"hook_event_name": "Stop"})

    assert rail.main() == 0
    out = capsys.readouterr().out
    assert "BLOCKED" in out
    assert "n1" in out
    assert "waiting on a decision" in out


def test_session_start_reinjects_resume_context(monkeypatch, capsys):
    _open_run("issue17")
    _stdin(monkeypatch, {"hook_event_name": "SessionStart"})

    assert rail.main() == 0
    out = capsys.readouterr().out
    assert "issue17" in out
    assert "spine issue17" in out


def test_missing_hook_event_name_defaults_sensibly(monkeypatch, capsys):
    _open_run("issue17")
    _stdin(monkeypatch, {})

    assert rail.main() == 0
    assert "issue17" in capsys.readouterr().out


def test_many_journals_are_capped_and_reported_as_a_count(monkeypatch, capsys):
    for i in range(rail.SCAN_CAP + 5):
        _open_run(f"issue{i}")
    _stdin(monkeypatch, {"hook_event_name": "Stop"})

    assert rail.main() == 0
    out = capsys.readouterr().out
    assert out != ""
    assert "more" in out
