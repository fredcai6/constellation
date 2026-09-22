"""Tests for install: a directory copy plus a flat skill link, both
idempotent, and inert on --dry-run.

Every path here goes through a tmp_path destination -- never ~/.claude.
"""

import pathlib
import re

from engine import cli, install
from engine import run as runmod


def test_dry_run_writes_nothing(tmp_path):
    dest = tmp_path / "dest"
    copied = install.install(dest, dry_run=True)

    assert copied  # it still reports what it would have done
    assert not dest.exists()


def test_copies_skills_assemblies_standards_engine_and_spine(tmp_path):
    dest = tmp_path / "dest"
    install.install(dest)

    assert (dest / "assemblies" / "run-an-issue" / "ASSEMBLY.toml").exists()
    assert (dest / "standards" / "glossary.md").exists()
    assert (dest / "engine" / "run.py").exists()
    assert (dest / "spine").exists()
    assert (dest / "skills" / "implementer" / "forms" / "IMPLEMENT.toml").exists()
    assert (dest / "skills" / "interrogator" / "forms" / "UNDERSTAND.toml").exists()
    assert (dest / "skills" / "reviewer" / "forms" / "REVIEW.toml").exists()


def test_copy_is_verbatim_byte_for_byte(tmp_path):
    dest = tmp_path / "dest"
    install.install(dest)

    root = pathlib.Path(install.__file__).resolve().parent.parent
    src = root / "engine" / "run.py"
    assert (dest / "engine" / "run.py").read_bytes() == src.read_bytes()

    palette_src = root / "constellation.toml"
    assert (dest / "constellation.toml").read_bytes() == palette_src.read_bytes()


def test_a_fresh_install_resolves_every_shipped_role_with_no_refusal(tmp_path, monkeypatch):
    """`_role_tier` and `_runner` read `constellation.toml` off the cwd
    (`_palette`, `engine/cli.py`), so chdir-ing into a freshly installed
    tree and calling them there exercises its own copy of the `[roles]`
    table -- not the source tree's, even though this process still has the
    source tree's `engine` package imported. Every filler `runmod.skeleton`
    mints, across every shipped assembly, must resolve -- the same
    enumeration this obligation's own spec used to find the three roles
    that did not."""
    dest = tmp_path / "dest"
    install.install(dest)
    monkeypatch.chdir(dest)

    fillers = set()
    for name in runmod.assemblies():
        asm = runmod.load_assembly(name)
        for step in runmod.skeleton(asm):
            fillers.add(step["filler"])
    assert {"conductor", "implementer", "planner", "excursion",
            "reviewer", "spec-writer"} <= fillers

    for filler in fillers:
        tier = cli._role_tier(filler)
        assert cli._runner(tier), f"{filler!r} resolved to tier {tier!r} with no runner"

    cut = runmod.load_assembly("cut-a-gate")
    transition = next(s for s in runmod.skeleton(cut) if s["segment"] == "cut")
    assert transition["filler"] == "planner"
    assert cli._runner(cli._role_tier(transition["filler"]))

    issue = runmod.load_assembly("run-an-issue")
    understand_1 = next(s for s in runmod.skeleton(issue) if s["id"] == "understand-1")
    assert understand_1["filler"] == "spec-writer"
    assert cli._runner(cli._role_tier(understand_1["filler"]))


def test_spine_stays_executable(tmp_path):
    dest = tmp_path / "dest"
    install.install(dest)

    root = pathlib.Path(install.__file__).resolve().parent.parent
    src_mode = (root / "spine").stat().st_mode
    dst_mode = (dest / "spine").stat().st_mode
    assert src_mode == dst_mode


def test_running_twice_is_idempotent(tmp_path):
    dest = tmp_path / "dest"
    first = install.install(dest)
    snapshot = sorted(p.relative_to(dest) for p in dest.rglob("*"))

    second = install.install(dest)

    assert first == second
    assert sorted(p.relative_to(dest) for p in dest.rglob("*")) == snapshot


def test_pycache_is_not_copied(tmp_path):
    dest = tmp_path / "dest"
    install.install(dest)

    assert not list(dest.rglob("__pycache__"))


def test_links_bundles_into_skills_dir(tmp_path):
    dest = tmp_path / "dest"
    skills_dir = tmp_path / "skills"
    install.install(dest, skills_dir=skills_dir)

    link = skills_dir / "implementer"
    assert link.is_symlink()
    assert (link / "SKILL.md").read_bytes() == \
        (dest / "skills" / "implementer" / "SKILL.md").read_bytes()


def test_dry_run_makes_no_links(tmp_path):
    dest = tmp_path / "dest"
    skills_dir = tmp_path / "skills"
    install.install(dest, skills_dir=skills_dir, dry_run=True)

    assert not skills_dir.exists()


def test_linking_twice_is_idempotent(tmp_path):
    dest = tmp_path / "dest"
    skills_dir = tmp_path / "skills"
    install.install(dest, skills_dir=skills_dir)
    target = (skills_dir / "implementer").resolve()

    install.install(dest, skills_dir=skills_dir)

    link = skills_dir / "implementer"
    assert link.is_symlink()
    assert link.resolve() == target


def test_a_real_directory_at_the_link_name_is_not_clobbered(tmp_path):
    dest = tmp_path / "dest"
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    real = skills_dir / "implementer"
    real.mkdir()
    (real / "sentinel.txt").write_text("not this installer's to remove")

    install.install(dest, skills_dir=skills_dir)

    assert not real.is_symlink()
    assert (real / "sentinel.txt").read_text() == "not this installer's to remove"


# -- the install boundary: engine never reaches for what it does not ship ---


_TOOLS_IMPORT = re.compile(r'^\s*(?:import\s+tools\b|from\s+tools\b)', re.MULTILINE)


def test_engine_imports_nothing_from_tools():
    """`_plan` above ships exactly five things plus skill bundles:
    assemblies, standards, engine, spine, constellation.toml, skills/<bundle>
    -- `tools/` is not among them. An `engine/*.py` module that imports it
    works only in this source tree, where `tools/` happens to sit beside
    `engine/`; the same import in any installed copy raises `ModuleNotFoundError` the first
    time a run's own path reaches the call, and only then. Static, not an
    import check, on purpose: a bad import three functions deep is dead
    until the runtime shape that calls it exists, and this catches it
    before that -- issue166's own `_land_reserved_rungs` first shipped
    exactly this, `from tools.code_map import parents`, reading `anchor_ids`
    and `read_parents` for a check `engine/` now does with `git grep` and a
    JSONL read of its own instead."""
    root = pathlib.Path(install.__file__).resolve().parent.parent
    bad = [p.name for p in sorted((root / "engine").glob("*.py"))
          if _TOOLS_IMPORT.search(p.read_text(encoding="utf-8"))]
    assert bad == [], f"engine module(s) importing tools/: {bad}"
