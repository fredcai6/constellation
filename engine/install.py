"""Install: copy the installable bundles to a destination. Nothing more.

The repo is born bundle-shaped -- skills/, assemblies/, standards/, engine/,
and spine are already exactly the shape an install needs, so installing is
copying directories, verbatim, preserving every internal repo-relative path
(a form's `skills/...` reference, `assemblies/<name>` lookups in run.py).
Wanting to rewrite a path inside a copied file is a sign repo shape and
installed shape have diverged -- that is v1's installer, not this one.
"""

import argparse
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
# One self-contained tree, because every internal reference is repo-relative
# (a form's `skills/...`, run.py's `assemblies/<name>`). Wiring these bundles
# into a host's skill discovery is a separate, unsettled step -- see
# docs/ENGINE_NOTES.md. Do not solve it by rewriting paths in copied files.
DEFAULT_DEST = pathlib.Path.home() / ".claude" / "constellation"
_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc")


def _plan(dest):
    """(source, dest, label), one entry per copied thing -- the fixed four
    plus one entry per skill bundle, so a report can name each bundle."""
    plan = [(ROOT / "assemblies", dest / "assemblies", "assemblies"),
            (ROOT / "standards", dest / "standards", "standards"),
            (ROOT / "engine", dest / "engine", "engine"),
            (ROOT / "spine", dest / "spine", "spine")]
    for bundle in sorted((ROOT / "skills").iterdir()):
        if bundle.is_dir():
            plan.append((bundle, dest / "skills" / bundle.name, f"skills/{bundle.name}"))
    return plan


def install(dest, dry_run=False):
    """Copy the plan to dest; report the labels copied. A dry run writes nothing."""
    copied = []
    for src, dst, label in _plan(dest):
        if not dry_run:
            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True, ignore=_IGNORE)
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
        copied.append(label)
    return copied


def main(argv=None):
    p = argparse.ArgumentParser(prog="engine.install")
    p.add_argument("--dest", default=str(DEFAULT_DEST))
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    dest = pathlib.Path(args.dest).expanduser()
    copied = install(dest, dry_run=args.dry_run)
    verb = "would copy" if args.dry_run else "copied"
    for label in copied:
        print(f"{verb} {label} -> {dest / label}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
