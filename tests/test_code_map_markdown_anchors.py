"""`extract.md_anchors_in` -- the anchor grammar's markdown spelling (epic
#138 finding 10). `anchors_in`'s `# [slug]` cannot be reused as-is above a
markdown claim: `#` opens a heading there, so the same bracket would render.
`md_anchors_in` calls the same forward-scan through the same `anchors_in`
with markdown's own wrapper instead -- `<!-- [slug] -->`, a construct
CommonMark already renders as nothing -- and its own notion of a comment
line to skip past while scanning forward, which must NOT be "starts with
`#`": that would skip past a real heading as if it were a comment.

The second half of this file anchors it to the two documents finding 10
actually places brackets on: `docs/PURPOSE.md`'s own claims and
`standards/approach.md`'s five. A drift here -- a bracket added, removed, or
misplaced without updating this file -- is caught by the exact slugs and
line count asserted below."""

import pathlib

from tools.code_map import extract

ROOT = pathlib.Path(__file__).resolve().parent.parent


# ------------------------------------------------------------ the grammar


def test_md_anchor_binds_the_html_comment_bracket_to_the_next_content_line():
    src = "# Title\n\n<!-- [some-claim] -->\nThe claim, in one sentence.\n"
    assert extract.md_anchors_in(src) == {4: ["some-claim"]}


def test_two_md_anchors_stacked_above_one_claim_both_bind():
    src = (
        "<!-- [first-fact] -->\n"
        "<!-- [second-fact] -->\n"
        "The one claim both brackets name.\n"
    )
    assert extract.md_anchors_in(src) == {3: ["first-fact", "second-fact"]}


def test_md_anchor_does_not_treat_a_heading_as_a_comment_to_skip():
    # `anchors_in`'s Python default treats a line starting with `#` as a
    # comment to skip past while forward-scanning. Markdown headings start
    # with `#` too and are real content, not a hidden comment -- if
    # `md_anchors_in` shared that predicate it would bind past the heading
    # to the paragraph below it instead of to the heading itself.
    src = "<!-- [what-this-is-for] -->\n## What this is for\n\nBody text.\n"
    assert extract.md_anchors_in(src) == {2: ["what-this-is-for"]}


def test_md_anchor_is_invisible_once_rendered():
    # The one thing every markdown renderer guarantees: an HTML comment
    # never produces visible output. Asserted here as the shape check a
    # renderer would agree with, not by rendering -- no renderer is a
    # dependency of this suite.
    assert extract.MD_ANCHOR.match("<!-- [some-claim] -->")
    assert not extract.MD_ANCHOR.match("[some-claim]")       # would render
    assert not extract.MD_ANCHOR.match("# [some-claim]")     # a heading, not hidden


def test_a_python_style_anchor_does_not_match_the_markdown_pattern():
    # One shape (`[slug]`), two wrappers -- not two grammars. `# [slug]`
    # stays Python-only; it must not also bind under `MD_ANCHOR`.
    assert extract.md_anchors_in("# [some-claim]\ndef f():\n    pass\n") == {}


# ------------------------------------------------------- the real documents


def test_purpose_md_carries_six_anchored_claims():
    src = (ROOT / "docs" / "PURPOSE.md").read_text(encoding="utf-8")
    bound = extract.md_anchors_in(src)
    slugs = sorted(s for slugs in bound.values() for s in slugs)
    assert slugs == sorted([
        "purpose-keeps-the-why-attached",
        "spec-gives-permission-to-stop",
        "critic-argues-from-a-position",
        "delete-only-what-you-can-justify-or-refute",
        "good-enough-is-only-decisions-left",
        "engine-changes-only-for-a-found-defect",
    ])
    assert len(slugs) == len(set(slugs))          # no two claims share a slug


def test_approach_md_carries_exactly_its_five_as_anchors():
    src = (ROOT / "standards" / "approach.md").read_text(encoding="utf-8")
    bound = extract.md_anchors_in(src)
    slugs = [s for _, ss in sorted(bound.items()) for s in ss]
    # In source order, matching "The five" as numbered 1-5.
    assert slugs == [
        "explore-and-play",
        "drill-down-until-understood",
        "build-so-it-will-not-break",
        "short-loops",
        "make-mechanical-things-mechanical",
    ]
