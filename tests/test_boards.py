"""Tests for engine/boards.py: rows, validate, summary."""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from engine import boards, cli  # noqa: E402


def _write(path, text):
    path.write_text(text)
    return path


CLEAN = """
[[question]]
id = "q1"
question = "Which inputs drop the last record?"
type = "fact"
status = "answered"
answer = "Files with no trailing newline; reproduced in repro.py."

[[question]]
id = "q2"
question = "Do third-party files need to parse too?"
type = "decision"
status = "answered"
answer = "No -- Tommy: skip third-party inputs entirely."
"""


# -- rows() -------------------------------------------------------------


def test_rows_missing_file_is_empty(tmp_path):
    assert boards.rows(tmp_path / "nope.toml") == []


def test_rows_reads_in_file_order(tmp_path):
    p = _write(tmp_path / "BOARD.toml", CLEAN)
    found = boards.rows(p)
    assert [r["id"] for r in found] == ["q1", "q2"]


# -- validate(): clean and each refusal ----------------------------------


def test_validate_clean_board_passes(tmp_path):
    p = _write(tmp_path / "BOARD.toml", CLEAN)
    assert boards.validate(p) == []


def test_validate_open_row_refuses_naming_its_id(tmp_path):
    p = _write(tmp_path / "BOARD.toml", """
[[question]]
id = "q1"
question = "Which inputs drop the last record?"
type = "fact"
status = "open"
""")
    problems = boards.validate(p)
    assert len(problems) == 1
    assert "q1" in problems[0]


def test_validate_up_row_refuses(tmp_path):
    p = _write(tmp_path / "BOARD.toml", """
[[question]]
id = "q1"
question = "Do third-party files need to parse too?"
type = "decision"
status = "up"
""")
    problems = boards.validate(p)
    assert len(problems) == 1
    assert "q1" in problems[0]


def test_validate_decision_answered_with_empty_answer_refuses(tmp_path):
    p = _write(tmp_path / "BOARD.toml", """
[[question]]
id = "q2"
question = "Do third-party files need to parse too?"
type = "decision"
status = "answered"
answer = ""
""")
    problems = boards.validate(p)
    assert len(problems) == 1
    assert "q2" in problems[0]


def test_validate_fact_answered_with_empty_answer_passes(tmp_path):
    # the empty-answer check is a decision-only failure mode; a fact
    # resolving without a recorded `answer` string is not this bug.
    p = _write(tmp_path / "BOARD.toml", """
[[question]]
id = "q1"
question = "Which inputs drop the last record?"
type = "fact"
status = "answered"
""")
    assert boards.validate(p) == []


def test_validate_deferred_with_reason_passes(tmp_path):
    p = _write(tmp_path / "BOARD.toml", """
[[question]]
id = "q2"
question = "Do third-party files need to parse too?"
type = "decision"
status = "deferred: needs Tommy"
""")
    assert boards.validate(p) == []


def test_validate_bare_deferred_refuses(tmp_path):
    p = _write(tmp_path / "BOARD.toml", """
[[question]]
id = "q2"
question = "Do third-party files need to parse too?"
type = "decision"
status = "deferred"
""")
    problems = boards.validate(p)
    assert len(problems) == 1
    assert "q2" in problems[0]


def test_validate_moot_passes(tmp_path):
    p = _write(tmp_path / "BOARD.toml", """
[[question]]
id = "q1"
question = "Which inputs drop the last record?"
type = "fact"
status = "moot"
answer = "superseded by q3"
""")
    assert boards.validate(p) == []


def test_validate_missing_question_or_type_is_malformed(tmp_path):
    p = _write(tmp_path / "BOARD.toml", """
[[question]]
id = "q1"
status = "answered"
""")
    problems = boards.validate(p)
    assert len(problems) == 1
    assert "q1" in problems[0]


def test_validate_malformed_file_yields_one_problem_no_traceback(tmp_path):
    p = _write(tmp_path / "BOARD.toml", "this is not [ valid toml")
    problems = boards.validate(p)
    assert len(problems) == 1
    assert isinstance(problems[0], str)


def test_validate_missing_file_is_clean(tmp_path):
    assert boards.validate(tmp_path / "nope.toml") == []


# -- summary() ------------------------------------------------------------


def test_summary_counts_by_status_and_type(tmp_path):
    p = _write(tmp_path / "BOARD.toml", CLEAN)
    s = boards.summary(p)
    assert s["total"] == 2
    assert s["by_status"] == {"answered": 2}
    assert s["by_type"] == {"fact": 1, "decision": 1}


def test_summary_empty_board(tmp_path):
    assert boards.summary(tmp_path / "nope.toml") == {"total": 0, "by_status": {}, "by_type": {}}


# -- against a board seeded by the real spine flow -------------------------


def test_validate_against_real_seeded_board(tmp_path, monkeypatch, capsys):
    """Not a hand-written fixture: open a real run, seed the board through
    `spine open` + `submit` exactly as an agent would, then check it."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONSTELLATION_SESSION", "test-session")

    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "demo"])
    capsys.readouterr()

    open_form = tmp_path / ".agent-work" / "issue17" / "OPEN.toml"
    open_form.write_text("""issue = "gh:17"
authority = \"\"\"
Principal: Tommy.\"\"\"
[[questions]]
question = "Which inputs drop the last record?"
type = "fact"
move = "reproduce"
[[questions]]
question = "Do third-party files need to parse too?"
type = "decision"
move = "ask"
""")
    cli.main(["issue17", "submit"])
    capsys.readouterr()

    board_path = tmp_path / ".agent-work" / "issue17" / "UNDERSTAND.toml"
    assert board_path.exists()

    seeded = boards.rows(board_path)
    assert [r["id"] for r in seeded] == ["q1", "q2"]
    assert all(r["status"] == "open" for r in seeded)

    # freshly seeded rows are open -- the board refuses until worked
    problems = boards.validate(board_path)
    assert len(problems) == 2
    assert any("q1" in p for p in problems)
    assert any("q2" in p for p in problems)

    # work the board as an agent would, then it passes
    text = board_path.read_text()
    text = text.replace(
        'id = "q1"\nstatus = "open"',
        'id = "q1"\nstatus = "answered"',
    ).replace(
        'move = "reproduce"',
        'move = "reproduce"\nanswer = "Files with no trailing newline."',
    ).replace(
        'id = "q2"\nstatus = "open"',
        'id = "q2"\nstatus = "deferred: needs Tommy"',
    )
    board_path.write_text(text)
    assert boards.validate(board_path) == []
