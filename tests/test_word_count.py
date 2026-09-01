"""The corpus budget's instrument, held to the rule it claims to apply.

`palette:words` is read by people, not enforced by a check (docs/AGENT_GUIDE.md),
so a miscount would quietly move the budget rather than fail anything. These
cases are the ones where a naive `#`-per-line split would disagree with the
tokenizer: a `#` inside a TOML string is not a comment, trailing or not.
"""

from tools.count_lines import WORD, split_toml_comments, measure_words


def test_a_full_line_comment_is_pulled_out_and_a_trailing_one_too():
    body, comments = split_toml_comments('# note\nx = 1  # tail\ny = 2\n')
    assert WORD.findall(body) == ["x", "y"]
    assert WORD.findall(comments) == ["note", "tail"]


def test_a_hash_inside_a_basic_string_is_not_a_comment():
    body, comments = split_toml_comments('note = "a # b"\n')
    assert WORD.findall(body) == ["note", "a", "b"]
    assert comments == ""


def test_a_hash_inside_a_literal_string_is_not_a_comment():
    body, comments = split_toml_comments("note = 'a # b'\n")
    assert WORD.findall(body) == ["note", "a", "b"]
    assert comments == ""


def test_a_hash_inside_a_triple_quoted_string_is_not_a_comment_even_at_line_start():
    source = 'note = """\n# looks like a comment but is prose\n"""\n'
    body, comments = split_toml_comments(source)
    assert comments == ""
    assert "looks" in WORD.findall(body)


def test_a_comment_after_a_closed_triple_string_is_still_a_comment():
    source = 'note = """value"""  # real comment\n'
    body, comments = split_toml_comments(source)
    assert WORD.findall(body) == ["note", "value"]
    assert WORD.findall(comments) == ["real", "comment"]


def test_measure_words_counts_are_disjoint_and_exhaustive(tmp_path):
    """Every alphabetic token in the file lands in exactly one column: words
    plus comments equals the plain tokenizer sweep over the whole file."""
    f = tmp_path / "sample.toml"
    source = '# header\nkey = "value words"  # trailing note\n'
    f.write_text(source)
    words, comment_words = measure_words(str(f))
    assert (words, comment_words) == (3, 3)
    assert words + comment_words == len(WORD.findall(source))


def test_a_non_toml_file_has_no_comments_to_pull_out(tmp_path):
    f = tmp_path / "sample.md"
    f.write_text("# a markdown heading is not a TOML comment\n")
    words, comment_words = measure_words(str(f))
    assert comment_words == 0
    assert words == len(WORD.findall(f.read_text()))
