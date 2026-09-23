"""Shared fixtures: the tmp-path checkout every test stands on.

Two shapes, not one, because not every test wants the same tmp dir.
`workdir` is what most files need -- a checkout with the host repo's own
`constellation.toml` copied in, since the command palette (models, check
commands) is host-repo config and tests run in an isolated tmp cwd, so it
has to travel with them. `bare_workdir` is `test_robustness.py`,
`test_roundtrip.py` and `test_slow_proofs.py`'s own shape: a checkout with
no config seeded, either because the test writes its own (`test_slow_proofs`)
or because a bare `constellation.toml`-less checkout is exactly what's under
test. Two fixtures rather than one with a flag, so a reader sees which shape
a test stands on from its signature alone.

Neither is autouse. `tests/gitremote.py`'s own docstring explains why:
`test_code_map.py` asserts that a bare, non-checkout root is refused by
name, and an autouse fixture would turn that refusal green for the wrong
reason -- an ambient checkout the test never asked for -- rather than the
real one under test. A plain requested fixture leaves that assertion
meaning what it says.
"""

import json
import os
import pathlib
import re
import sys
import tempfile
import tomllib

import pytest

from gitremote import init_checkout

REPO = pathlib.Path(__file__).resolve().parent.parent


# [workdir-substitutes-dispatch]
# Rationale: `workdir` copies this repo's own `constellation.toml`
#   verbatim, and that file's `[commands]` carries a real `dispatch` entry
#   (a real `claude` invocation) -- so every fast-suite test that renders
#   or drives a dispatch or panel room through this fixture must never
#   reach that real entry. `o-fast-suite-safety-by-substitution` retires
#   "no dispatch entry at all" as a state worth modelling for that: every
#   way a start can fail now raises and is caught the same way
#   (`o-absent-dispatch-raises`), so an absent entry is no longer a second
#   world to render differently, only one more logged failure -- and a
#   present, harmless entry serves the safety purpose at least as well as
#   an absent one, which is the substitution `test_wait.py`'s own
#   `_throwaway_dispatch` already uses. This entry is a real,
#   near-instant `sys.executable` invocation -- never `claude` -- so a
#   test that drives `wait` or `drive` through it spawns a real, harmless
#   process rather than nothing at all; `test_dispatch_wiring.py`'s own
#   `test_the_fast_suites_workdir_never_touches_a_real_process` is the
#   proof that this never reaches `claude`, not that no process starts.
#   The substitution is airtight the same way the removal it replaces was:
#   `_dispatch_is_harmless` parses the result as TOML and confirms the
#   `[commands]` entry equals this constant -- never at the text -- so no
#   formatting of the entry (one line, several, reordered) can produce a
#   false pass.
# Rejected: an autouse fixture monkeypatching `checks.spawn_dispatch`.
#   That guard would live beside the fixture rather than in it, covering
#   every test in the session (including `test_spawn_dispatch.py`'s own
#   direct, deliberate calls) unless it were then taught to exempt them --
#   a second thing to keep in sync with the first. Editing the one file
#   `workdir` already writes needs nothing else to know about the guard.
_DISPATCH_ENTRY_RE = re.compile(r"(?ms)^dispatch[ \t]*=[ \t]*(?:\[.*?\]|[^\n]*)\n?")
_HARMLESS_DISPATCH_ENTRY = [sys.executable, "-c", "pass", "{brief}"]


def _dispatch_is_harmless(text):
    """The substitution's own postcondition: parse `text` as TOML and
    confirm `[commands] dispatch` is exactly the harmless stand-in, never
    the real entry it replaced. Judged against the parsed palette, never
    the text, so no line-wrapping or reordering of the entry can fool it
    either way. Raises loudly, naming what actually landed, rather than
    letting a real `dispatch` command travel into the fast suite quietly
    -- the spawn side cannot tell the two cases apart (see rationale
    above), so this is the only thing in the system that can."""
    palette = tomllib.loads(text)
    entry = palette.get("commands", {}).get("dispatch")
    if entry != _HARMLESS_DISPATCH_ENTRY:
        raise AssertionError(
            "workdir-substitutes-dispatch: constellation.toml's copy does "
            f"not carry the harmless stand-in -- got {entry!r}, and the "
            "fast suite would spawn whatever that actually names.")


def _with_a_harmless_dispatch_entry(text):
    substituted = _DISPATCH_ENTRY_RE.sub(
        "dispatch = " + json.dumps(_HARMLESS_DISPATCH_ENTRY) + "\n", text, count=1)
    _dispatch_is_harmless(substituted)
    return substituted


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONSTELLATION_SESSION", "test-session")
    # the command palette (models, check commands) is host-repo config;
    # tests run in an isolated tmp cwd, so it travels with them -- its real
    # `dispatch` entry is replaced, see `_with_a_harmless_dispatch_entry` above.
    (tmp_path / "constellation.toml").write_text(
        _with_a_harmless_dispatch_entry((REPO / "constellation.toml").read_text()))
    init_checkout(tmp_path)
    return tmp_path


@pytest.fixture
def bare_workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONSTELLATION_SESSION", "test-session")
    init_checkout(tmp_path)
    return tmp_path


# [tests-on-tmpfs]
# Rationale: `journal.append` fsyncs every entry -- 5.06ms against 0.03ms
#   without it, measured -- and that sync is load-bearing in production: it
#   is what keeps a run's record whole when an agent's process dies
#   mid-run. Tests need the write, never the durability, and they write
#   dozens of entries apiece: the whole suite runs 180s with the sync and
#   96s without it, so roughly half this suite's wall clock was buying a
#   guarantee no test has ever read. Relocating pytest's temp root onto
#   tmpfs makes the sync a no-op where it is worthless and changes nothing
#   about where it is not -- no engine code moves, and `fsync` still means
#   what it means everywhere a real run happens.
# Rejected: making the fsync conditional, on an env var or a flag. That
#   puts a knob on the one guarantee the journal exists to give, so that
#   tests run faster -- and the first time someone sets it outside a test
#   the record stops being a record.
# Rejected: `--basetemp`. It relocates the root but also discards pytest's
#   own `pytest-of-<user>` numbering and its keep-the-last-three retention,
#   so a failed run's tree is gone before anyone reads it.
_TMPFS_ROOTS = ("/dev/shm",)


def _tmpfs_temproot():
    """A writable tmpfs to hang pytest's temp root on, or None. None is the
    ordinary answer off Linux, and the suite simply runs where it always
    did -- correct, just paying the sync."""
    for name in _TMPFS_ROOTS:
        root = pathlib.Path(name)
        if not root.is_dir() or not os.access(root, os.W_OK):
            continue
        try:
            with tempfile.TemporaryDirectory(dir=root):
                pass
        except OSError:
            continue
        return root
    return None


def pytest_configure(config):
    """Point pytest's temp root at tmpfs when there is one, unless the caller
    already chose a location (`--basetemp`, or an environment that names one
    for its own reasons -- CI writing somewhere it can collect afterward)."""
    if config.getoption("basetemp") or os.environ.get("PYTEST_DEBUG_TEMPROOT"):
        return
    root = _tmpfs_temproot()
    if root is not None:
        os.environ["PYTEST_DEBUG_TEMPROOT"] = str(root)
