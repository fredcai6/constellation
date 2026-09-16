"""Both portions of the map on one page (epic #138, finding 5): an entity's
rendered page shows the DEFINED portion (`map/parents.jsonl` -- its parents,
or ORPHAN when nothing is recorded yet) and the computed reverse of a
`See:` tag (finding 2) -- who points at this anchor, without anyone
authoring the reverse edge.

`render.map_lines` is the single new seat both findings share; this file
drives it through `render.run` end to end, the same altitude
`test_code_map_anchors_and_see.py` already uses for `checks.see_tags_resolve`.
"""

import json
import subprocess

from tools.code_map import extract, render


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


def _build(tmp_path, files, parents_jsonl=None):
    """Extract + render `files` under `tmp_path`, with `map/parents.jsonl`
    pre-seeded to `parents_jsonl` (raw text) when given. `--out` defaults to
    `<root>/map`, the real CLI's own default, so this exercises the same
    directory both the derived tree and the committed parents file share.
    Returns the `map/` directory the pages landed in."""
    _git_repo(tmp_path, files)
    if parents_jsonl is not None:
        p = tmp_path / "map" / "parents.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(parents_jsonl, encoding="utf-8")
    artifacts = tmp_path / ".code-map"
    out = tmp_path / "map"
    assert extract.run(tmp_path, artifacts) == 0
    assert render.run(tmp_path, artifacts, out) == 0
    return out


# `alpha` carries the anchor `anchor-a` and nothing else. `beta` carries its
# own anchor, `anchor-b`, plus a `See:` tag naming `anchor-a` -- the authored
# forward edge whose computed reverse this file is testing.
MOD_PY = (
    "# [anchor-a]\n"
    "def alpha():\n"
    "    pass\n"
    "\n"
    "\n"
    "# See: [anchor-a]\n"
    "# [anchor-b]\n"
    "def beta():\n"
    "    pass\n"
)


def test_entity_with_no_anchor_gets_no_map_section(tmp_path):
    out = _build(tmp_path, {"mod.py": "def gamma():\n    pass\n"})
    page = (out / "mod" / "gamma.md").read_text(encoding="utf-8")
    assert "parents:" not in page
    assert "referenced by (See:)" not in page


def test_anchored_entity_with_no_parents_file_is_an_orphan(tmp_path):
    out = _build(tmp_path, {"mod.py": MOD_PY})
    page = (out / "mod" / "alpha.md").read_text(encoding="utf-8")
    assert "[anchor-a]" in page
    assert "parents: ORPHAN -- no entry in map/parents.jsonl" in page


def test_anchored_entity_with_a_parents_entry_shows_its_parents(tmp_path):
    parents_jsonl = json.dumps({"id": "anchor-a", "parents": ["some-purpose"]}) + "\n"
    out = _build(tmp_path, {"mod.py": MOD_PY}, parents_jsonl=parents_jsonl)
    page = (out / "mod" / "alpha.md").read_text(encoding="utf-8")
    assert "parents: [some-purpose]" in page
    assert "ORPHAN" not in page


def test_anchored_entity_declared_a_root_shows_none_not_orphan(tmp_path):
    """An entry with an explicit empty `parents` list is a deliberate root,
    not the same silence as no entry at all -- `parents.orphan_report`
    already draws this line and rendering must not blur it back out."""
    parents_jsonl = json.dumps({"id": "anchor-a", "parents": []}) + "\n"
    out = _build(tmp_path, {"mod.py": MOD_PY}, parents_jsonl=parents_jsonl)
    page = (out / "mod" / "alpha.md").read_text(encoding="utf-8")
    assert "parents: none -- declared root" in page
    assert "ORPHAN" not in page


def test_a_see_tag_renders_as_a_back_reference_on_its_targets_page(tmp_path):
    out = _build(tmp_path, {"mod.py": MOD_PY})
    page = (out / "mod" / "alpha.md").read_text(encoding="utf-8")
    assert "referenced by (See:): mod:beta" in page


def test_an_anchor_nothing_points_at_shows_none_found(tmp_path):
    out = _build(tmp_path, {"mod.py": MOD_PY})
    page = (out / "mod" / "beta.md").read_text(encoding="utf-8")
    assert "referenced by (See:): none found" in page


def test_a_see_tag_from_outside_the_narrowed_render_still_counts(tmp_path):
    """`--render-only` narrows which modules get PAGES, never the walk
    (`in_render_scope`'s own docstring) -- a `See:` tag authored in a module
    that never gets a page of its own must still show up as a back-reference
    on the page it names."""
    files = {
        "engine/mod.py": "# [anchor-a]\ndef alpha():\n    pass\n",
        "tools/other.py": "# See: [anchor-a]\ndef watcher():\n    pass\n",
    }
    tmp_path_files = files
    _git_repo(tmp_path, tmp_path_files)
    artifacts = tmp_path / ".code-map"
    out = tmp_path / "map"
    assert extract.run(tmp_path, artifacts) == 0
    assert render.run(tmp_path, artifacts, out, ("engine",)) == 0
    page = (out / "engine.mod" / "alpha.md").read_text(encoding="utf-8")
    assert "referenced by (See:): tools.other:watcher" in page


def test_render_preserves_parents_jsonl_across_a_rebuild(tmp_path):
    """`out` defaults to `<root>/map`, the same directory `parents.jsonl` is
    committed into. A render must never be what deletes the one authored
    file the whole defined portion lives in."""
    parents_jsonl = json.dumps({"id": "anchor-a", "parents": []}) + "\n"
    out = _build(tmp_path, {"mod.py": MOD_PY}, parents_jsonl=parents_jsonl)
    assert (out / "parents.jsonl").read_text(encoding="utf-8") == parents_jsonl
