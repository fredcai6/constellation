"""Enumerate the mappable corpus: the source files the map is derived from.

The corpus is every TRACKED Python file, minus the excluded prefixes below.
Tracked, because an untracked file is not yet part of the repository and a
generated one is not source. `git ls-files` is the enumerator, so .gitignore and
the index decide membership rather than a second rule that would drift from them.
"""

import subprocess
from pathlib import Path

# Prefixes cut from the mappable corpus. `.agent-work/` is run scratch. Some hosts
# gitignore it (this one does) and some track it deliberately, run artifacts being
# durable history -- so git cannot be relied on to exclude it and this rule must.
# Without it, on a host that tracks it, roughly a third of the map is scratch and
# every number derived from it is wrong.
EXCLUDED_PREFIXES = (".agent-work/",)


def is_mappable(rel):
    """True when a tracked repo-relative path belongs in the mappable corpus."""
    return rel.endswith(".py") and not rel.startswith(EXCLUDED_PREFIXES)


def tracked_python_files(root):
    """Every Python file git tracks under `root`, as sorted posix-relative paths.

    git is the enumerator, so its absence and a `--root` outside a checkout are
    both ordinary conditions with a stated answer, not tracebacks. An agent meets
    them by pointing `--root` at the wrong directory, and a CalledProcessError
    tells it nothing about what to do next."""
    if not Path(root).is_dir():
        raise SystemExit(f"code_map: --root {root} is not a directory -- "
                         "point it at the repository to map")
    try:
        proc = subprocess.run(
            ["git", "ls-files", "-z", "--", "*.py"],
            cwd=str(root), capture_output=True, text=True,
        )
    except OSError:
        raise SystemExit("code_map: git is not on PATH, and the mappable corpus is "
                         "whatever git tracks -- install git, or map a checkout "
                         "from a machine that has it")
    if proc.returncode != 0:
        detail = proc.stderr.strip().splitlines()
        raise SystemExit(f"code_map: {root} is not a git checkout, so there is no "
                         "tracked corpus to map -- run this from inside the "
                         "repository, or pass --root <checkout>"
                         + (f"\n  git said: {detail[0]}" if detail else ""))
    return sorted(p for p in proc.stdout.split("\0") if p)


def discover_corpus(root):
    """The mappable corpus under `root`, as sorted posix-relative paths."""
    return sorted(p for p in tracked_python_files(root) if is_mappable(p))
