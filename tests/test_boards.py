"""Tests for engine/boards.py: rows, validate, askable, held, clusters,
summary."""

import pathlib

import pytest

from engine import boards, cli
from gitremote import init_checkout
from test_nesting import _response


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


def test_validate_against_real_seeded_board(tmp_path, monkeypatch, capsys):
    """Not a hand-written fixture: open a real run, seed the board through
    `spine open` + `submit` exactly as an agent would, then check it."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONSTELLATION_SESSION", "test-session")
    init_checkout(tmp_path)

    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "demo"])
    capsys.readouterr()

    # the `issue` field names a file in the work location, so write one
    issue = pathlib.Path(".agent-work/issue17/issue.md")
    issue.write_text("The parser drops the last record of a file with no "
                     "trailing newline.\n")
    open_form = _response("issue17")
    open_form.write_text(f"""issue = "{issue}"
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

    board_path = pathlib.Path(".agent-work/issue17/UNDERSTAND.toml")
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


# -- askable() / held() --------------------------------------------------


def test_askable_open_row_with_no_after_is_askable():
    rows = [{"id": "q1", "status": "open"}]
    assert boards.askable(rows) == rows


@pytest.mark.parametrize("status", ["answered", "moot", "up", "deferred: reason"])
def test_askable_excludes_non_open_own_status(status):
    assert boards.askable([{"id": "q1", "status": status}]) == []


def test_askable_row_blocked_by_open_dependency():
    rows = [
        {"id": "q1", "status": "open", "after": ["q2"]},
        {"id": "q2", "status": "open"},
    ]
    assert [r["id"] for r in boards.askable(rows)] == ["q2"]


def test_askable_row_blocked_by_up_dependency():
    rows = [
        {"id": "q1", "status": "open", "after": ["q2"]},
        {"id": "q2", "status": "up"},
    ]
    assert [r["id"] for r in boards.askable(rows)] == []


def test_askable_not_blocked_by_deferred_dependency():
    rows = [
        {"id": "q1", "status": "open", "after": ["q2"]},
        {"id": "q2", "status": "deferred: needs Tommy"},
    ]
    assert [r["id"] for r in boards.askable(rows)] == ["q1"]


def test_askable_not_blocked_by_moot_or_answered_dependency():
    rows = [
        {"id": "q1", "status": "open", "after": ["q2", "q3"]},
        {"id": "q2", "status": "moot"},
        {"id": "q3", "status": "answered"},
    ]
    assert [r["id"] for r in boards.askable(rows)] == ["q1"]


def test_askable_ignores_dangling_after_id():
    rows = [{"id": "q1", "status": "open", "after": ["ghost"]}]
    assert [r["id"] for r in boards.askable(rows)] == ["q1"]


def test_held_reports_the_ids_holding_it():
    rows = [
        {"id": "q1", "status": "open", "after": ["q2", "q3"]},
        {"id": "q2", "status": "open"},
        {"id": "q3", "status": "up"},
    ]
    held = boards.held(rows)
    assert len(held) == 1
    row, holders = held[0]
    assert row["id"] == "q1"
    assert holders == ["q2", "q3"]


def test_held_excludes_non_open_own_status():
    rows = [
        {"id": "q1", "status": "answered", "after": ["q2"]},
        {"id": "q2", "status": "open"},
    ]
    assert boards.held(rows) == []


def test_held_excludes_deferred_moot_answered_dependencies():
    rows = [
        {"id": "q1", "status": "open", "after": ["q2"]},
        {"id": "q2", "status": "deferred: reason"},
    ]
    assert boards.held(rows) == []


def test_held_ignores_dangling_after_id():
    rows = [{"id": "q1", "status": "open", "after": ["ghost"]}]
    assert boards.held(rows) == []


# -- clusters() -----------------------------------------------------------


def test_clusters_groups_by_tag():
    rows = [
        {"id": "q1", "status": "open", "cluster": "risk"},
        {"id": "q2", "status": "open", "cluster": "risk"},
        {"id": "q3", "status": "open"},
    ]
    result = boards.clusters(rows)
    assert [r["id"] for r in result["groups"]["risk"]] == ["q1", "q2"]
    assert "" not in result["groups"]


def test_clusters_empty_tag_never_groups():
    rows = [{"id": "q1", "status": "open", "cluster": ""}]
    assert boards.clusters(rows)["groups"] == {}


def test_clusters_ready_when_all_open_rows_askable():
    rows = [
        {"id": "q1", "status": "open", "cluster": "risk"},
        {"id": "q2", "status": "open", "cluster": "risk"},
    ]
    assert boards.clusters(rows)["ready"]["risk"] is True


def test_clusters_not_ready_when_an_open_row_is_held():
    rows = [
        {"id": "q1", "status": "open", "cluster": "risk", "after": ["q3"]},
        {"id": "q2", "status": "open", "cluster": "risk"},
        {"id": "q3", "status": "open"},
    ]
    assert boards.clusters(rows)["ready"]["risk"] is False


def test_clusters_ready_scoped_to_open_rows_across_sessions():
    # answering a cluster's first row must not retire the sitting -- boards
    # are worked over many sessions, not finished in one sitting.
    rows = [
        {"id": "q1", "status": "answered", "cluster": "risk"},
        {"id": "q2", "status": "open", "cluster": "risk"},
    ]
    assert boards.clusters(rows)["ready"]["risk"] is True


def test_clusters_not_ready_with_no_open_rows():
    rows = [{"id": "q1", "status": "answered", "cluster": "risk"}]
    assert boards.clusters(rows)["ready"]["risk"] is False


# -- summary() --------------------------------------------------------------


def test_summary_counts_by_status_and_type(tmp_path):
    p = _write(tmp_path / "BOARD.toml", CLEAN)
    result = boards.summary(p)
    assert result["total"] == 2
    assert result["by_status"] == {"answered": 2}
    assert result["by_type"] == {"fact": 1, "decision": 1}


def test_summary_missing_file_is_empty():
    result = boards.summary(pathlib.Path("/nonexistent/BOARD.toml"))
    assert result == {"total": 0, "by_status": {}, "by_type": {}}


# -- status renders the board's own state, standing on the board segment ---


def _open_with_board(tmp_path, monkeypatch, seeds):
    """A real run through `open` + `submit`, seeding the understand board
    from `seeds` -- exactly how an agent reaches the consolidate step with
    the board still open, which is where this render fires."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONSTELLATION_SESSION", "test-session")
    init_checkout(tmp_path)
    cli.main(["open", "run-an-issue", "--issue", "42", "--title", "t"])
    # the `issue` field names a file in the work location, so write one
    issue = pathlib.Path(".agent-work/issue42/issue.md")
    issue.write_text("The parser drops the last record of a file with no "
                     "trailing newline.\n")
    open_form = _response("issue42")
    open_form.write_text(f'issue = "{issue}"\nauthority = """\nPrincipal: Tommy."""\n'
                         + seeds)
    cli.main(["issue42", "submit"])


def test_status_shows_askable_held_and_ready_blocks(tmp_path, monkeypatch, capsys):
    _open_with_board(tmp_path, monkeypatch, """
[[questions]]
question = "What owns retry logic?"
type = "fact"
move = "read"
cluster = "risk"

[[questions]]
question = "Do we need backwards compat?"
type = "decision"
move = "ask"
cluster = "risk"

[[questions]]
question = "Is the cache warm on cold start?"
type = "fact"
move = "read"
after = ["q1"]
""")
    capsys.readouterr()
    cli.main(["issue42"])
    out = capsys.readouterr().out

    assert "3 rows -- status: open 3 -- type: decision 1, fact 2" in out
    assert "askable now" in out
    assert "q1" in out and "What owns retry logic?" in out
    assert "q2" in out and "Do we need backwards compat?" in out
    assert "held" in out and "q3" in out and "held by q1" in out
    assert "ready for one sitting" in out and "risk" in out and "q1, q2" in out


def test_status_ready_sitting_names_only_the_askable_row(tmp_path, monkeypatch, capsys):
    """A ready cluster keeps every member it was ever seeded with -- the
    render must not. Answering q1 leaves the cluster ready (q2 is still
    askable), but the sitting printed for the principal names q2 alone; q1
    is settled and re-asking it is the bug."""
    _open_with_board(tmp_path, monkeypatch, """
[[questions]]
question = "What owns retry logic?"
type = "fact"
move = "read"
cluster = "risk"

[[questions]]
question = "Do we need backwards compat?"
type = "decision"
move = "ask"
cluster = "risk"
""")
    board = pathlib.Path(".agent-work/issue42/UNDERSTAND.toml")
    text = board.read_text().replace(
        'id = "q1"\nstatus = "open"',
        'id = "q1"\nstatus = "answered"',
    ).replace(
        'move = "read"',
        'move = "read"\nanswer = "the retry module"',
        1,
    )
    board.write_text(text)
    capsys.readouterr()
    cli.main(["issue42"])
    out = capsys.readouterr().out

    assert "ready for one sitting" in out
    lines = [ln for ln in out.splitlines() if ln.strip().startswith("risk")]
    assert len(lines) == 1
    assert "q2" in lines[0]
    assert "q1" not in lines[0]


def test_status_prints_no_heading_over_an_empty_block(tmp_path, monkeypatch, capsys):
    """Every row answered: nothing askable, nothing held, no cluster ready --
    proves a heading is never printed over an empty list."""
    _open_with_board(tmp_path, monkeypatch, """
[[questions]]
question = "What owns retry logic?"
type = "fact"
move = "read"
""")
    board = pathlib.Path(".agent-work/issue42/UNDERSTAND.toml")
    board.write_text(board.read_text()
                     .replace('status = "open"', 'status = "answered"')
                     .replace('move = "read"', 'move = "read"\nanswer = "the retry module"'))
    capsys.readouterr()
    cli.main(["issue42"])
    out = capsys.readouterr().out

    assert "1 rows -- status: answered 1 -- type: fact 1" in out
    assert "askable now" not in out
    assert "held" not in out
    assert "ready for one sitting" not in out


# [test-open-command-on-a-row]
# Rationale: the commitment is discoverability, so the assertion is the whole
#   command as an agent would copy it -- id, `--parent`, `--row`, and an
#   assembly that exists. Asserting on the heading alone would pass on a
#   block that printed the word "excursion" and no way to open one, which is
#   the state this gate was opened to end.
def test_board_render_prints_the_open_command(tmp_path, monkeypatch, capsys):
    """An askable row carries the command that takes it off the board.

    q3 is held by q1, so it is not a row the interrogator can act on yet and
    it gets no command -- the same scoping `askable now` already uses."""
    _open_with_board(tmp_path, monkeypatch, """
[[questions]]
question = "What owns retry logic?"
type = "fact"
move = "read"

[[questions]]
question = "Do we need backwards compat?"
type = "decision"
move = "ask"

[[questions]]
question = "Is the cache warm on cold start?"
type = "fact"
move = "read"
after = ["q1"]
""")
    capsys.readouterr()
    cli.main(["issue42"])
    out = capsys.readouterr().out

    assert "off the board" in out
    for rid in ("q1", "q2"):
        assert f"open find-prior-art --parent issue42 --row {rid}" in out, \
            f"no open command on askable row {rid}"
    assert "--row q3" not in out, "a held row was offered an excursion"
    for kind in ("find-prior-art", "build-a-prototype", "draw-a-picture"):
        assert kind in out, f"the block does not name {kind}"
        assert (pathlib.Path(__file__).resolve().parent.parent
                / "assemblies" / kind / "ASSEMBLY.toml").exists()
    assert cli.render.spine_cmd() in out, "the command is not the runnable path"


def test_status_still_names_the_board_path(tmp_path, monkeypatch, capsys):
    _open_with_board(tmp_path, monkeypatch, """
[[questions]]
question = "What owns retry logic?"
type = "fact"
move = "read"
""")
    capsys.readouterr()
    cli.main(["issue42"])
    out = capsys.readouterr().out
    assert "the board:" in out and "UNDERSTAND.toml" in out


# -- the template states what a column IS, not a rule the engine now owns --


def test_understand_template_drops_the_two_engine_owned_rules():
    template = (pathlib.Path(__file__).resolve().parent.parent
               / "skills/interrogator/forms/UNDERSTAND.toml")
    lines = [ln[1:].strip() if ln.startswith("#") else ln
            for ln in template.read_text().splitlines()]
    text = " ".join(" ".join(lines).split())

    assert ("A row is askable when nothing in `after` is open and nothing "
            "has mooted it.") not in text
    assert "add rows, resolve, moot with reasons, cluster." not in text
    assert "add rows, resolve, moot with reasons." in text
    # the column still says what it IS -- that part is not the deleted rule
    assert 'cluster = "" # optional — rows taken to the principal in one sitting' in text
