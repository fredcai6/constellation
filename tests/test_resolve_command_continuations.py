"""A gate's proof may be written as multi-line shell with backslash-newline
continuations; the engine must run it as the shell would, not glue an
escaped space onto the word before each continuation."""

from engine import cli


def test_backslash_newline_folds_to_a_space_before_the_split():
    text = "grep -q needle README.md \\\n  && echo ok"
    assert cli._resolve_command(text) == "grep -q needle README.md && echo ok"


def test_a_continuation_inside_one_piece_is_folded_too():
    text = "python3 -c 'print(1)' \\\n  --flag"
    assert cli._resolve_command(text) == "python3 -c 'print(1)' --flag"


def test_plain_chains_are_unchanged():
    assert cli._resolve_command("a && b") == "a && b"
