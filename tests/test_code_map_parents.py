"""`map/parents.jsonl` -- the map's authored, defined portion (epic #138,
finding 1). `tools/code_map/parents.py` is a reader plus two reports over
it: orphans (an anchor with no entry) and dangling (an entry naming an id
that is neither an anchor in the tree nor a configured root claim --
`root_claim_ids`, epic #138 finding 10). Neither report refuses anything --
`report()`/`main()` always return 0 -- so these tests check what the reports
NAME, never that they exit nonzero.

Three altitudes: the pure functions (`orphan_report`, `dangling_report`) get
manufactured sets so every branch is reachable without a real checkout;
`anchor_ids` needs one (it shells to `git ls-files` through
`discovery.discover_corpus`), so those tests stand on `gitremote.init_checkout`
the way the rest of this suite does; `root_claim_ids` reads `constellation.toml`
and the documents it names straight off disk, no git required. The last group
runs the whole thing against THIS repository's own committed `map/parents.jsonl`
and `constellation.toml`, which is the actual deliverable.
"""
import json
import pathlib
import subprocess

from gitremote import init_checkout

from tools.code_map import discovery, extract, parents

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _write(tmp_path, name, anchors_above):
    """A tiny fixture module: one `def` per (slug, funcname) pair in
    `anchors_above`, each preceded by its own `# [slug]` anchor comment --
    the exact shape `extract.anchors_in` binds."""
    body = []
    for slug, fname in anchors_above:
        body.append(f"# [{slug}]")
        body.append(f"def {fname}():")
        body.append("    pass")
        body.append("")
    (tmp_path / name).write_text("\n".join(body) + "\n", encoding="utf-8")


def _write_md(tmp_path, name, anchors_above):
    """A tiny fixture document: one paragraph per (slug, text) pair in
    `anchors_above`, each preceded by its own `<!-- [slug] -->` anchor
    comment -- the exact shape `extract.md_anchors_in` binds."""
    body = []
    for slug, text in anchors_above:
        body.append(f"<!-- [{slug}] -->")
        body.append(text)
        body.append("")
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(body) + "\n", encoding="utf-8")


def _write_roots_config(tmp_path, documents):
    """`constellation.toml` with a `[roots] documents = [...]` table --
    `root_claim_ids` reads this list rather than any hardcoded path (see
    its own rationale: `standards/approach.md` travels between
    repositories, `docs/PURPOSE.md` does not)."""
    lines = ["[roots]", "documents = [" + ", ".join(json.dumps(d) for d in documents) + "]"]
    (tmp_path / "constellation.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- read_parents


def test_read_parents_is_empty_for_a_file_that_does_not_exist(tmp_path):
    assert parents.read_parents(tmp_path / "nope.jsonl") == {}


def test_read_parents_parses_the_pure_hierarchy_shape(tmp_path):
    p = tmp_path / "parents.jsonl"
    p.write_text(
        json.dumps({"id": "child-a", "parents": ["root-a", "root-b"]}) + "\n"
        + json.dumps({"id": "root-a", "parents": []}) + "\n",
        encoding="utf-8")
    got = parents.read_parents(p)
    assert got == {"child-a": ("root-a", "root-b"), "root-a": ()}


def test_read_parents_defaults_a_missing_parents_key_to_empty(tmp_path):
    p = tmp_path / "parents.jsonl"
    p.write_text(json.dumps({"id": "lonely"}) + "\n", encoding="utf-8")
    assert parents.read_parents(p) == {"lonely": ()}


# ---------------------------------------------------------- orphan_report


def test_orphan_report_names_every_anchor_absent_from_parents():
    anchors = {"a", "b", "c"}
    have = {"a": ("root",)}
    assert parents.orphan_report(anchors, have) == ["b", "c"]


def test_orphan_report_is_empty_once_every_anchor_has_an_entry():
    anchors = {"a", "b"}
    have = {"a": (), "b": ("a",)}
    assert parents.orphan_report(anchors, have) == []


def test_a_parents_entry_for_an_id_that_is_no_longer_an_anchor_is_not_an_orphan():
    """Orphan names an ANCHOR with no entry, not an entry with no anchor --
    that direction is `dangling_report`'s job, checked separately below."""
    anchors = {"a"}
    have = {"a": (), "stale": ()}
    assert parents.orphan_report(anchors, have) == []


# --------------------------------------------------------- dangling_report


def test_dangling_report_flags_a_parent_that_is_not_an_anchor():
    anchors = {"a", "b"}
    have = {"a": ("b", "nonexistent-parent")}
    assert parents.dangling_report(anchors, have) == ["nonexistent-parent"]


def test_dangling_report_flags_an_entrys_own_id_when_it_is_not_an_anchor():
    anchors = {"b"}
    have = {"renamed-away": ("b",)}
    assert parents.dangling_report(anchors, have) == ["renamed-away"]


def test_dangling_report_is_empty_when_every_named_id_is_an_anchor():
    anchors = {"a", "b", "c"}
    have = {"a": ("b", "c"), "b": ()}
    assert parents.dangling_report(anchors, have) == []


def test_dangling_report_does_not_flag_orphans():
    """An anchor with no entry at all is silent here -- `dangling` only ever
    reads ids `parents.jsonl` itself names."""
    anchors = {"a", "b"}
    have = {}
    assert parents.dangling_report(anchors, have) == []


# -------------------------------------------------------------- anchor_ids


def test_anchor_ids_collects_every_anchor_in_the_mappable_corpus(tmp_path):
    _write(tmp_path, "one.py", [("first-anchor", "f")])
    _write(tmp_path, "two.py", [("second-anchor", "g"), ("third-anchor", "h")])
    init_checkout(tmp_path)
    assert parents.anchor_ids(tmp_path) == {
        "first-anchor", "second-anchor", "third-anchor"}


def test_anchor_ids_ignores_untracked_files(tmp_path):
    """`discover_corpus` walks `git ls-files`; a file dropped in after the
    commit `init_checkout` makes is not part of the mappable corpus."""
    _write(tmp_path, "tracked.py", [("tracked-anchor", "f")])
    init_checkout(tmp_path)
    _write(tmp_path, "untracked.py", [("untracked-anchor", "g")])
    assert parents.anchor_ids(tmp_path) == {"tracked-anchor"}


# ------------------------------------------------------------ root_claim_ids


def test_root_claim_ids_is_empty_with_no_constellation_toml(tmp_path):
    """No config at all is an ordinary condition -- no root set configured,
    not an error -- matching `discovery.py`'s own "missing git, missing
    directory" voice."""
    assert parents.root_claim_ids(tmp_path) == set()


def test_root_claim_ids_is_empty_with_no_roots_table(tmp_path):
    (tmp_path / "constellation.toml").write_text(
        "[models]\nlight = \"x\"\n", encoding="utf-8")
    assert parents.root_claim_ids(tmp_path) == set()


def test_root_claim_ids_is_empty_with_no_documents_key(tmp_path):
    (tmp_path / "constellation.toml").write_text("[roots]\n", encoding="utf-8")
    assert parents.root_claim_ids(tmp_path) == set()


def test_root_claim_ids_skips_a_listed_document_that_does_not_exist(tmp_path):
    """A listed document missing from disk is skipped, not a traceback --
    the same "ordinary condition" contract as the config file itself being
    absent."""
    _write_roots_config(tmp_path, ["docs/NOSUCHFILE.md"])
    assert parents.root_claim_ids(tmp_path) == set()


def test_root_claim_ids_collects_markdown_anchors_from_listed_documents(tmp_path):
    _write_md(tmp_path, "docs/PURPOSE.md", [("root-a", "Claim A.")])
    _write_md(tmp_path, "standards/approach.md", [("root-b", "Claim B.")])
    _write_roots_config(tmp_path, ["docs/PURPOSE.md", "standards/approach.md"])
    assert parents.root_claim_ids(tmp_path) == {"root-a", "root-b"}


def test_root_claim_ids_ignores_a_markdown_anchor_outside_the_listed_documents(tmp_path):
    """Narrow by design: a document not named in `[roots] documents` is not
    part of the root set even if it uses the same anchor syntax -- only the
    listed roots resolve, not the whole markdown tree."""
    _write_md(tmp_path, "docs/PURPOSE.md", [("root-a", "Claim A.")])
    _write_md(tmp_path, "docs/OTHER.md", [("not-a-root", "Not a root claim.")])
    _write_roots_config(tmp_path, ["docs/PURPOSE.md"])
    assert parents.root_claim_ids(tmp_path) == {"root-a"}


def test_root_claim_ids_ignores_a_python_anchor_sharing_a_slug_shape(tmp_path):
    """The grammar, not just the directory, gates membership: a `# [slug]`
    Python anchor never counts as a root claim, even inside a listed
    document's own directory."""
    _write_md(tmp_path, "docs/PURPOSE.md", [("root-a", "Claim A.")])
    _write(tmp_path, "docs/helper.py", [("not-markdown", "f")])
    _write_roots_config(tmp_path, ["docs/PURPOSE.md"])
    assert parents.root_claim_ids(tmp_path) == {"root-a"}


def test_this_repos_root_claims_resolve_from_its_own_constellation_toml():
    """The real deliverable: `constellation.toml`'s `[roots] documents`
    against this repository's own `docs/PURPOSE.md` and
    `standards/approach.md` names the eleven root claims epic #138 finding
    10 put there."""
    got = parents.root_claim_ids(ROOT)
    assert "purpose-keeps-the-why-attached" in got
    assert "explore-and-play" in got
    assert len(got) == 11


# ----------------------------------------------------------------- report


def test_report_on_a_fresh_checkout_with_no_parents_file_orphans_every_anchor(tmp_path):
    _write(tmp_path, "mod.py", [("a1", "f"), ("a2", "g")])
    init_checkout(tmp_path)
    result = parents.report(tmp_path, tmp_path / "map" / "parents.jsonl")
    assert result["anchors"] == 2
    assert result["parents_entries"] == 0
    assert sorted(result["orphans"]) == ["a1", "a2"]
    assert result["dangling"] == []


def test_report_with_a_full_defined_portion_orphans_nothing(tmp_path):
    _write(tmp_path, "mod.py", [("a1", "f"), ("a2", "g")])
    init_checkout(tmp_path)
    parents_path = tmp_path / "map" / "parents.jsonl"
    parents_path.parent.mkdir(exist_ok=True)
    parents_path.write_text(
        json.dumps({"id": "a1", "parents": []}) + "\n"
        + json.dumps({"id": "a2", "parents": ["a1"]}) + "\n",
        encoding="utf-8")
    result = parents.report(tmp_path, parents_path)
    assert result["orphans"] == []
    assert result["dangling"] == []


def test_report_dangling_resolves_a_parents_entry_naming_a_root_claim(tmp_path):
    """The defect this closes: every purpose chain terminates at a root
    claim, and all eleven of those are markdown -- `anchor_ids` alone never
    sees them, so a correct row naming one as a parent must not read as
    dangling."""
    _write(tmp_path, "mod.py", [("a1", "f")])
    _write_md(tmp_path, "docs/PURPOSE.md", [("root-a", "Claim A.")])
    _write_roots_config(tmp_path, ["docs/PURPOSE.md"])
    init_checkout(tmp_path)
    parents_path = tmp_path / "map" / "parents.jsonl"
    parents_path.parent.mkdir(exist_ok=True)
    parents_path.write_text(
        json.dumps({"id": "a1", "parents": ["root-a"]}) + "\n", encoding="utf-8")
    result = parents.report(tmp_path, parents_path)
    assert result["dangling"] == []


def test_report_dangling_still_flags_an_id_that_is_no_root_claim_and_no_anchor(tmp_path):
    """Root-claim resolution is not a blanket amnesty: a parent naming
    neither an anchor nor a configured root claim is still dangling."""
    _write(tmp_path, "mod.py", [("a1", "f")])
    _write_md(tmp_path, "docs/PURPOSE.md", [("root-a", "Claim A.")])
    _write_roots_config(tmp_path, ["docs/PURPOSE.md"])
    init_checkout(tmp_path)
    parents_path = tmp_path / "map" / "parents.jsonl"
    parents_path.parent.mkdir(exist_ok=True)
    parents_path.write_text(
        json.dumps({"id": "a1", "parents": ["totally-nonexistent-slug"]}) + "\n",
        encoding="utf-8")
    result = parents.report(tmp_path, parents_path)
    assert result["dangling"] == ["totally-nonexistent-slug"]


def test_report_orphans_never_include_a_root_claim(tmp_path):
    """A root claim is a chain's terminus, never itself a `parents.jsonl`
    row -- folding it into `anchors` for the orphan check would flag every
    root claim forever, on every build, for a gap that can never close."""
    _write(tmp_path, "mod.py", [("a1", "f")])
    _write_md(tmp_path, "docs/PURPOSE.md", [("root-a", "Claim A.")])
    _write_roots_config(tmp_path, ["docs/PURPOSE.md"])
    init_checkout(tmp_path)
    parents_path = tmp_path / "map" / "parents.jsonl"
    parents_path.parent.mkdir(exist_ok=True)
    parents_path.write_text(
        json.dumps({"id": "a1", "parents": ["root-a"]}) + "\n", encoding="utf-8")
    result = parents.report(tmp_path, parents_path)
    assert "root-a" not in result["orphans"]
    assert result["orphans"] == []


def test_main_never_refuses_even_with_dangling_and_orphaned_entries(tmp_path, capsys):
    """Neither report is a gate (epic #138): `main` always returns 0, whether
    the defined portion is empty, complete, or naming ids that rotted away."""
    _write(tmp_path, "mod.py", [("a1", "f")])
    init_checkout(tmp_path)
    parents_path = tmp_path / "map" / "parents.jsonl"
    parents_path.parent.mkdir(exist_ok=True)
    parents_path.write_text(
        json.dumps({"id": "stale-id", "parents": ["also-stale"]}) + "\n",
        encoding="utf-8")
    rc = parents.main(["--root", str(tmp_path), "--parents", str(parents_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "a1" in out            # orphaned: never mentioned in parents.jsonl
    assert "stale-id" in out      # dangling: named, not an anchor
    assert "also-stale" in out    # dangling: named as a parent, not an anchor


# --------------------------------------------------- this repository's own map


def test_this_repos_committed_parents_file_is_tracked_not_ignored():
    """The trap named in epic #138: `.gitignore`'s `map/` line plus a bare
    negation does nothing at all, because git will not re-include a path
    inside an ignored directory. `map/*` + `!map/parents.jsonl` is the shape
    that actually works -- this is the same check `git add` proves by hand,
    run here so a later edit to `.gitignore` cannot silently regress it."""
    proc = subprocess.run(["git", "check-ignore", "map/parents.jsonl"],
                          cwd=str(ROOT), capture_output=True, text=True)
    assert proc.returncode == 1, "map/parents.jsonl is gitignored and should not be"

    proc = subprocess.run(["git", "ls-files", "--error-unmatch", "map/parents.jsonl"],
                          cwd=str(ROOT), capture_output=True, text=True)
    assert proc.returncode == 0, "map/parents.jsonl is not tracked by git"


def test_this_repos_derived_map_directory_stays_gitignored():
    """The rest of `map/` is still derived and gitignored -- the exception is
    narrow, not a hole that swallowed the whole directory."""
    proc = subprocess.run(["git", "check-ignore", "map/some-derived-file.md"],
                          cwd=str(ROOT), capture_output=True, text=True)
    assert proc.returncode == 0, "map/ stopped being gitignored outside its one exception"


def test_orphan_count_on_this_repos_clean_tree_equals_the_total_anchor_count():
    """The relationships that hold no matter how many rows `map/parents.jsonl`
    carries: every anchor with no entry is an orphan, and nothing dangles.
    Regressing this means the reader and `extract.anchors_in` stopped
    agreeing on the anchor set, or a row went dangling -- not that the file
    stopped being empty, which finding 1 never promised to stay true."""
    parents_path = ROOT / "map" / "parents.jsonl"
    anchors = parents.anchor_ids(ROOT)
    have = parents.read_parents(parents_path)
    result = parents.report(ROOT, parents_path)

    assert anchors
    assert set(result["orphans"]) == anchors - set(have)
    assert result["dangling"] == []


def test_orphans_and_dangling_tolerate_a_declared_root_row(tmp_path):
    """`map/parents.jsonl` may carry a root purpose's own declared-root row --
    a row whose id is anchored in a roots document (`standards/purpose.md`)
    rather than in the Python tree, rendered by `render.PARENTS_ROOT`. That
    id is never in `anchor_ids` (it is markdown, not Python), so it can never
    satisfy an orphan and can never gain an entry of its own from the orphan
    report's point of view -- but it must not read as dangling either, and
    it must not disturb the ordinary anchor's own orphan/dangling status.
    Pins the same two relationships
    `test_orphan_count_on_this_repos_clean_tree_equals_the_total_anchor_count`
    asserts against this repository's own tree, against a small tree that
    carries one ordinary anchor row and one declared-root row."""
    _write(tmp_path, "mod.py", [("a1", "f")])
    _write_md(tmp_path, "docs/PURPOSE.md", [("root-a", "Claim A.")])
    _write_roots_config(tmp_path, ["docs/PURPOSE.md"])
    init_checkout(tmp_path)
    parents_path = tmp_path / "map" / "parents.jsonl"
    parents_path.parent.mkdir(exist_ok=True)
    parents_path.write_text(
        json.dumps({"id": "a1", "parents": ["root-a"]}) + "\n"
        + json.dumps({"id": "root-a", "parents": []}) + "\n",
        encoding="utf-8")

    anchors = parents.anchor_ids(tmp_path)
    have = parents.read_parents(parents_path)
    result = parents.report(tmp_path, parents_path)

    assert anchors
    assert set(result["orphans"]) == anchors - set(have)
    assert result["dangling"] == []


def test_no_anchor_id_is_claimed_at_more_than_one_site():
    """`anchor_ids`'s own docstring says why it returns a set rather than a
    count: "two anchors sharing one slug in different files is a duplicate
    id -- a separate authoring defect this reader does not paper over by
    counting positions instead of identities." A set alone cannot report
    THAT defect, only hide it -- this walks the same corpus and grammar but
    keeps every occurrence, so a shared slug fails here instead of nowhere.

    Epic #138 finding 10 found exactly one collision in the tree:
    `response-path-by-step`, claimed by both `engine/cli.py`'s own
    `_response_path` and `evals/harness.py`'s `response_path`. `render.py`'s
    own build-time duplicate check (`ids` grouped by slug) catches the same
    thing at a different altitude; this is the corpus-level version, cheap
    enough to run without a full build."""
    sites = {}
    for rel in discovery.discover_corpus(ROOT):
        src = (ROOT / rel).read_text(encoding="utf-8")
        for line, slugs in extract.anchors_in(src).items():
            for slug in slugs:
                sites.setdefault(slug, []).append(f"{rel}:{line}")
    dupes = {slug: where for slug, where in sites.items() if len(where) > 1}
    assert dupes == {}
