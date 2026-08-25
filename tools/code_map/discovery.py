"""Enumerate the mappable corpus: the source files the map is derived from.

The corpus is every TRACKED Python file, minus the excluded prefixes below.
Tracked, because an untracked file is not yet part of the repository and a
generated one is not source. `git ls-files` is the enumerator, so .gitignore and
the index decide membership rather than a second rule that would drift from them.
"""

import subprocess
from pathlib import Path

# Prefixes cut from the mappable corpus. `.agent-work/` is run scratch, and it is
# deliberately TRACKED in this repo (run artifacts are durable history, per the
# .gitignore header), so git cannot exclude it and this rule must. Without it
# roughly a third of the map is scratch and every number derived from it is wrong.
EXCLUDED_PREFIXES = (".agent-work/",)


def is_mappable(rel):
    """True when a tracked repo-relative path belongs in the mappable corpus."""
    return rel.endswith(".py") and not rel.startswith(EXCLUDED_PREFIXES)


def tracked_python_files(root):
    """Every Python file git tracks under `root`, as sorted posix-relative paths."""
    out = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.py"],
        cwd=str(root), check=True, capture_output=True, text=True,
    ).stdout
    return sorted(p for p in out.split("\0") if p)


def discover_corpus(root):
    """The mappable corpus under `root`, as sorted posix-relative paths."""
    return sorted(p for p in tracked_python_files(root) if is_mappable(p))
