"""`tools/code_map/build.py`'s parents summary (epic #138, finding 1's missing
call site): `parents.orphan_report`/`dangling_report` existed with nothing at
any seam calling them, which is exactly the failure mode
`docs/DERIVED_IS_CODE.md` names -- "unwired derivation is a missing call
site, not dead weight." `build()` is `constellation.toml`'s "closeout call"
seam, so this is where the counts get printed.

Same altitude as `tests/test_code_map_map_lines.py`'s `_build` helper: drive
`extract.run` + the function under test through a real tiny checkout, not
mocks. Two things checked throughout: the summary line names the right
counts, and neither orphans nor dangling entries ever change the return
code -- `parents.dangling_report`'s own docstring says a stale reference is
"raw material for a ranked backlog... not a commit-time gate," and this
suite holds `build()` to the same promise.
"""
import json
import subprocess

from tools.code_map import build


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


_MOD_PY = (
    "# [anchor-a]\n"
    "def f():\n"
    "    \"\"\"f's docstring.\"\"\"\n"
    "    pass\n"
)


def test_build_prints_a_parents_summary_line_with_counts(tmp_path, capsys):
    _git_repo(tmp_path, {"mod.py": _MOD_PY})
    rc = build.build(tmp_path, artifacts=tmp_path / ".code-map", out=tmp_path / "map")
    assert rc == 0
    out = capsys.readouterr().out
    assert "parents: 1 anchor(s), 0 parents.jsonl entr(ies) -- 1 orphaned, 0 dangling" in out
    assert "python3 -m tools.code_map.parents" in out
    assert str(tmp_path) in out    # points the detail command at this root


def test_build_return_status_does_not_change_when_every_anchor_is_orphaned(tmp_path):
    """No `map/parents.jsonl` at all -- the freshest-checkout case, where
    every anchor orphans -- still returns 0."""
    _git_repo(tmp_path, {"mod.py": _MOD_PY})
    rc = build.build(tmp_path, artifacts=tmp_path / ".code-map", out=tmp_path / "map")
    assert rc == 0


def test_build_return_status_does_not_change_when_parents_jsonl_is_dangling(tmp_path, capsys):
    """A `map/parents.jsonl` naming ids that are not anchors in the tree --
    the ordinary case of a spec writing a parents entry before the anchor
    lands -- still returns 0, and the summary names the dangling count."""
    _git_repo(tmp_path, {"mod.py": _MOD_PY})
    parents_path = tmp_path / "map" / "parents.jsonl"
    parents_path.parent.mkdir(parents=True, exist_ok=True)
    parents_path.write_text(
        json.dumps({"id": "not-an-anchor-yet", "parents": ["also-not-one"]}) + "\n",
        encoding="utf-8")
    rc = build.build(tmp_path, artifacts=tmp_path / ".code-map", out=tmp_path / "map")
    assert rc == 0
    out = capsys.readouterr().out
    assert "2 dangling" in out


def test_build_summary_reads_the_committed_parents_file_regardless_of_out(tmp_path, capsys):
    """`root / "map" / parents.jsonl` is the one committed location for the
    defined portion, no matter where `--out` sends the derived tree -- the
    same rule `render.run` itself follows (its own docstring: "read against
    root, never artifacts"). A narrowed/redirected `out` must not blind the
    summary to an already-populated parents file."""
    _git_repo(tmp_path, {"mod.py": _MOD_PY})
    parents_path = tmp_path / "map" / "parents.jsonl"
    parents_path.parent.mkdir(parents=True, exist_ok=True)
    parents_path.write_text(json.dumps({"id": "anchor-a", "parents": []}) + "\n",
                            encoding="utf-8")
    rc = build.build(tmp_path, artifacts=tmp_path / ".code-map",
                     out=tmp_path / "somewhere-else")
    assert rc == 0
    out = capsys.readouterr().out
    assert "1 anchor(s), 1 parents.jsonl entr(ies) -- 0 orphaned, 0 dangling" in out


def test_build_still_prints_the_summary_when_render_fails_on_a_duplicate_id(tmp_path, capsys):
    """A duplicate anchor id fails `render.run` (returns 1) on its own,
    unrelated grounds -- that failure must not swallow the parents summary,
    since orphan/dangling reporting is not gated on the rest of the build
    succeeding."""
    dup = "# [dup-anchor]\ndef g():\n    \"\"\"g's docstring.\"\"\"\n    pass\n"
    _git_repo(tmp_path, {"one.py": dup, "two.py": dup})
    rc = build.build(tmp_path, artifacts=tmp_path / ".code-map", out=tmp_path / "map")
    assert rc == 1
    out = capsys.readouterr().out
    assert "parents:" in out
    assert "python3 -m tools.code_map.parents" in out
