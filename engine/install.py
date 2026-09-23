"""Install: copy the installable bundles to a destination, then link each
skill bundle into the host's flat skill directory. Nothing more.

The repo is born bundle-shaped -- skills/, assemblies/, standards/, engine/,
and spine are already exactly the shape an install needs, so installing is
copying directories, verbatim, preserving every internal repo-relative path
(a form's `skills/...` reference, `assemblies/<name>` lookups in run.py).
Wanting to rewrite a path inside a copied file is a sign repo shape and
installed shape have diverged -- that is v1's installer, not this one.

Claude Code discovers skills only at the flat `~/.claude/skills/<name>/
SKILL.md`, which disagrees with the tree's shape, so the tree is copied and
each bundle is additionally symlinked flat -- see docs/ENGINE_NOTES.md.
"""

import argparse
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
# One self-contained tree, because every internal reference is repo-relative
# (a form's `skills/...`, run.py's `assemblies/<name>`). A symlink, not a
# second copy, carries each bundle into the host's flat skill directory: it
# rewrites nothing, duplicates nothing, and cannot drift from the copy it
# points at.
DEFAULT_DEST = pathlib.Path.home() / ".claude" / "constellation"
DEFAULT_SKILLS_DIR = pathlib.Path.home() / ".claude" / "skills"
_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc")
# The one thing in the plan below that belongs to the reader rather than the
# engine: the palette is shipped so a fresh tree is configured on day one, and
# is then theirs to edit -- a `dispatch` entry for their own harness, their own
# model tiers. Every other entry is an engine-owned bundle whose whole purpose
# in a reinstall is to be replaced. So this one is placed, never overwritten,
# for the same reason `_place_link` refuses to remove a real directory: what a
# person put there is not this installer's to take away.
READER_OWNED = frozenset({"constellation.toml"})


def _plan(dest):
    """(source, dest, label), one entry per copied thing -- the fixed five
    plus one entry per skill bundle, so a report can name each bundle."""
    plan = [(ROOT / "assemblies", dest / "assemblies", "assemblies"),
            (ROOT / "standards", dest / "standards", "standards"),
            (ROOT / "engine", dest / "engine", "engine"),
            (ROOT / "spine", dest / "spine", "spine"),
            (ROOT / "constellation.toml", dest / "constellation.toml", "constellation.toml")]
    for bundle in sorted((ROOT / "skills").iterdir()):
        if bundle.is_dir():
            plan.append((bundle, dest / "skills" / bundle.name, f"skills/{bundle.name}"))
    return plan


def _link_plan(dest, skills_dir):
    """(target, link, label) for each skill bundle -- target is the copy
    install already placed under dest, link is where the host looks for it."""
    plan = []
    for bundle in sorted((ROOT / "skills").iterdir()):
        if bundle.is_dir():
            plan.append((dest / "skills" / bundle.name,
                         skills_dir / bundle.name,
                         f"skills/{bundle.name}"))
    return plan


def _place_link(target, link):
    """Make link a symlink to target: leave a link already pointing there
    alone, replace one pointing elsewhere, and refuse to touch a real
    directory -- something a person or another tool put at that name is not
    this installer's to remove, so it is reported and skipped instead."""
    if link.is_symlink():
        if link.resolve() == target.resolve():
            return "linked"
        link.unlink()
    elif link.exists():
        return "skipped: a real directory is already there"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(target, target_is_directory=True)
    return "linked"


def install(dest, skills_dir=None, dry_run=False):
    """Copy the plan to dest, then place a symlink for each skill bundle in
    skills_dir. skills_dir=None skips linking entirely. A dry run writes
    nothing and reports every copy and link it would make. Returns
    `(copied, linked)` -- copied is `(label, status)` per plan entry, where
    status is "copied" or "skipped: one is already there" for a
    `READER_OWNED` entry a previous install already placed."""
    copied = []
    for src, dst, label in _plan(dest):
        if label in READER_OWNED and dst.exists():
            copied.append((label, "skipped: one is already there"))
            continue
        if not dry_run:
            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True, ignore=_IGNORE)
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
        copied.append((label, "copied"))

    linked = []
    if skills_dir is not None:
        for target, link, label in _link_plan(dest, skills_dir):
            status = "would link" if dry_run else _place_link(target, link)
            linked.append((label, link, status))
    return copied, linked


def main(argv=None):
    p = argparse.ArgumentParser(prog="engine.install")
    p.add_argument("--dest", default=str(DEFAULT_DEST))
    p.add_argument("--skills-dir", default=str(DEFAULT_SKILLS_DIR))
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    dest = pathlib.Path(args.dest).expanduser()
    skills_dir = pathlib.Path(args.skills_dir).expanduser()
    copied, linked = install(dest, skills_dir=skills_dir, dry_run=args.dry_run)

    verb = "would copy" if args.dry_run else "copied"
    for label, status in copied:
        if status.startswith("skipped:"):
            print(f"{status} -- kept {dest / label} as it stands")
        else:
            print(f"{verb} {label} -> {dest / label}")
    for label, link, status in linked:
        if status.startswith("skipped:"):
            print(f"{status} -- {label} -> {link}")
        else:
            print(f"{status} {label} -> {link}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
