"""Tests for install: a directory copy plus a flat skill link, both
idempotent, and inert on --dry-run.

Every path here goes through a tmp_path destination -- never ~/.claude.
"""

import pathlib

from engine import install


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
