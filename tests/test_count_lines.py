"""The machinery cap's instrument, held to the rule it claims to apply.

`palette:lines` is the only number the Size section is argued against, and it
is read by people rather than by a check -- so a miscount does not fail
anything, it just quietly moves the budget. These cases are the ones where
"lines of code" and "lines" disagree: a docstring is prose, and a string that
merely sits on its own line inside a call is not.
"""

from tools.count_lines import code_lines, is_python, measure


def lines_of(source):
    return sorted(code_lines(source))


def test_a_docstring_is_prose_and_the_code_around_it_is_not():
    assert lines_of('"""module doc"""\nimport os\n') == [2]
    assert lines_of('def f():\n    """doc\n    spanning\n    """\n    return 1\n') == [1, 5]


def test_a_string_inside_a_call_is_code_though_it_opens_its_line():
    # tokenize emits NL inside brackets, so the second line looks like the
    # start of a statement unless bracket depth is tracked. It is not one.
    assert lines_of('print("a"\n      "b")\n') == [1, 2]
    assert lines_of('x = (\n    "a"\n    "b")\n') == [1, 2, 3]


def test_a_multi_line_string_held_as_a_value_is_code():
    assert lines_of('x = """\nvalue\n"""\n') == [1, 2, 3]


def test_a_comment_line_is_prose_and_a_trailing_comment_does_not_erase_its_line():
    assert lines_of("# comment\n\nx = 1  # trailing\n") == [3]


def test_every_line_lands_in_exactly_one_column(tmp_path):
    """Code plus prose plus blank is the raw count. Without that the prose
    column could hide growth rather than report it."""
    f = tmp_path / "sample.py"
    f.write_text('"""doc"""\n# note\n\nx = 1\ny = "s"  # tail\n')
    code, prose, blank = measure(str(f))
    assert (code, prose, blank) == (2, 2, 1)
    assert code + prose + blank == len(f.read_text().splitlines())


def test_python_is_recognised_by_shebang_because_spine_has_no_suffix():
    assert is_python("spine", ["#!/usr/bin/env python3"])
    assert is_python("engine/cli.py", [])
    assert not is_python("run.sh", ["#!/bin/sh"])


def test_a_file_python_cannot_parse_still_counts_as_machinery(tmp_path):
    """Counted by the coarser rule rather than dropped: a tree's size does not
    fall because one file in it stopped parsing."""
    f = tmp_path / "broken.py"
    f.write_text("def f(\n    # never closed\n")
    code, prose, blank = measure(str(f))
    assert code == 2 and prose == 0 and blank == 0
