"""The code map's own integrity: an anchor that binds to nothing, and a
`See:` tag that names a target nothing checks.

Two defects to guard against, one shape: the map silently drops what it
cannot bind, and carries references it never checks resolve. `anchors_in`
binds a LINE to a list of slugs, so two brackets stacked above the same
definition both survive instead of the earlier one vanishing with nothing
at exit 0 to say so (`tests/test_code_map.py` covers the map's off-path;
this file covers its own honesty). `checks.anchor_accounting` is the
belt-and-braces invariant for what that does not itself guarantee: a
bracket whose target line the walk never actually visits. `checks.see_tags_resolve`
checks a `See:` tag's `file:line` and backtick-quoted symbol targets
against the source they claim to name."""

import json
import pathlib
import subprocess

from tools.code_map import checks, extract


def _git_repo(tmp_path, files):
    """`tmp_path` as a one-commit git checkout holding `files`
    (repo-relative path -> content) -- the minimum `discover_corpus` needs."""
    for rel, content in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    run = lambda *args: subprocess.run(   # noqa: E731
        ["git", *args], cwd=str(tmp_path), check=True, capture_output=True, text=True)
    run("init", "--quiet")
    run("config", "user.email", "test@example.com")
    run("config", "user.name", "test")
    run("add", "-A")
    run("commit", "--quiet", "-m", "initial")


def _extracted_map(tmp_path):
    """Extract `tmp_path`'s corpus and return a `MapUnderCheck` over it --
    no render needed, since `anchor_accounting`/`see_tags_resolve` only ever
    read `m.root`, `m.modules` and `m.scan`."""
    artifacts = tmp_path / ".code-map"
    extract.run(tmp_path, artifacts)
    return checks.MapUnderCheck(tmp_path, artifacts, tmp_path / "map")


# --------------------------------------------------- defect A: anchors_in

def test_two_anchors_stacked_above_one_definition_both_bind():
    src = "# [refusal-outranks-every-clean-word]\n# [quiet-needs-every-voice-quiet]\ndef verdict_fold():\n    pass\n"
    bound = extract.anchors_in(src)
    # A bare string holding the LAST bracket only would overwrite the first
    # with no signal.
    assert bound == {3: ["refusal-outranks-every-clean-word", "quiet-needs-every-voice-quiet"]}


def test_stacked_anchors_each_emit_their_own_anchored_statement(tmp_path):
    src = (
        "# [first-fact]\n"
        "# [second-fact]\n"
        "def verdict_fold():\n"
        "    return 1\n"
    )
    _git_repo(tmp_path, {"m.py": src})
    artifacts = tmp_path / ".code-map"
    extract.run(tmp_path, artifacts)
    statements = [json.loads(line) for line in
                  (artifacts / extract.STATEMENTS_NAME).read_text().splitlines()]
    slugs = sorted(st["o"] for st in statements if st["p"] == "anchored")
    # Both brackets' slugs reach the store, not only the second's.
    assert slugs == ["first-fact", "second-fact"]
    assert all(st["s"] == "m:verdict_fold" for st in statements if st["p"] == "anchored")


def test_anchor_accounting_is_clean_when_every_bindable_bracket_binds(tmp_path):
    _git_repo(tmp_path, {"m.py": (
        "# [first-fact]\n"
        "# [second-fact]\n"
        "def verdict_fold():\n"
        "    return 1\n"
    )})
    m = _extracted_map(tmp_path)
    assert checks.anchor_accounting(m) == []


def test_anchor_accounting_flags_a_bracket_the_walk_never_visits(tmp_path):
    # A bracket above the decorator and a SECOND bracket between the
    # decorator and `def` -- `Extractor.anchor` checks both lines but stops
    # at the first that carries anything, so the second bracket's own slug
    # never reaches the store. `anchor_accounting` is what still says so.
    _git_repo(tmp_path, {"m.py": (
        "# [above-decorator]\n"
        "@staticmethod\n"
        "# [between-decorator-and-def]\n"
        "def f():\n"
        "    return 1\n"
    )})
    m = _extracted_map(tmp_path)
    failures = checks.anchor_accounting(m)
    assert len(failures) == 1
    assert "2 `[slug]`" in failures[0] and "1 `anchored`" in failures[0]


# -------------------------------------------------- defect B: See: tags

_JOURNAL_SRC = (
    "def stamp():\n"
    "    return 1\n"
    "\n"
    "\n"
    "def append():\n"
    "    return 2\n"
)


def test_see_tag_file_line_paired_with_a_symbol_whose_span_does_not_cover_it(tmp_path):
    # journal.py's own shape: `append` moves, and the tag still names the
    # line `stamp` sits on.
    (tmp_path / "engine").mkdir()
    (tmp_path / "engine" / "journal.py").write_text(_JOURNAL_SRC, encoding="utf-8")
    tag_text = "`journal.py:1` -- `journal.append`'s own thing."
    failures = checks._see_tag_failures(tmp_path, "engine/cli.py", tag_text, set())
    assert failures  # line 1 is `stamp`, not `append`
    assert "journal.py:1" in failures[0]


def test_see_tag_file_line_paired_with_a_symbol_whose_span_covers_it(tmp_path):
    (tmp_path / "engine").mkdir()
    (tmp_path / "engine" / "journal.py").write_text(_JOURNAL_SRC, encoding="utf-8")
    tag_text = "`journal.py:5` -- `journal.append`'s own thing."
    failures = checks._see_tag_failures(tmp_path, "engine/cli.py", tag_text, set())
    assert failures == []


def test_the_real_journal_py_see_tag_now_resolves():
    """A `See:` tag in `engine/cli.py` must name the line its symbol sits
    on: `See: journal.py:119 -- journal.append's own mkdir(...)` would be a
    dead reference when line 119 of `engine/journal.py` is `stamp()`, not
    `append()`."""
    root = pathlib.Path(__file__).resolve().parents[1]
    cli_src = (root / "engine" / "cli.py").read_text(encoding="utf-8")
    tags = extract.tags_in(cli_src)
    see_texts = [t["text"] for tag_list in tags.values() for t in tag_list
                 if t["kind"] == "See" and "journal.py" in t["text"]]
    assert len(see_texts) == 1
    failures = checks._see_tag_failures(root, "engine/cli.py", see_texts[0], set())
    assert failures == []


def test_see_tag_with_only_a_bare_issue_number_is_not_checked():
    # A stated non-goal: an issue number points outside the tree, and there
    # is no in-tree form to resolve it against.
    failures = checks._see_tag_failures(
        None, "engine/cli.py", "#32 -- gate adjudication still carries its own interpreter.", set())
    assert failures == []


def test_see_tag_anchor_reference_must_be_a_bound_slug():
    failures = checks._see_tag_failures(None, "engine/cli.py", "[some-slug]", set())
    assert failures == ["[some-slug]: not a bound anchor"]
    assert checks._see_tag_failures(None, "engine/cli.py", "[some-slug]", {"some-slug"}) == []


def test_see_tags_resolve_over_a_synthetic_corpus(tmp_path):
    """`see_tags_resolve` itself -- not just `_see_tag_failures` -- wired to
    a real `MapUnderCheck`: the bound-slug set comes from `m.scan.anchor_ids`,
    the tags come from `tags_in` over every mapped file."""
    _git_repo(tmp_path, {
        "engine/journal.py": (
            "def stamp():\n"
            "    return 1\n"
            "\n"
            "\n"
            "def append():\n"
            "    return 2\n"
        ),
        "engine/cli.py": (
            "# See: `journal.py:5` -- `journal.append`'s own thing.\n"
            "def good():\n"
            "    return 1\n"
            "\n"
            "\n"
            "# See: `journal.py:1` -- `journal.append`'s own thing.\n"
            "def bad():\n"
            "    return 1\n"
        ),
    })
    m = _extracted_map(tmp_path)
    failures = checks.see_tags_resolve(m)
    assert len(failures) == 1
    assert "journal.py:1" in failures[0]
