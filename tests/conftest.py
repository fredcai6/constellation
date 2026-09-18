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

import pathlib
import re
import tomllib

import pytest

from gitremote import init_checkout

REPO = pathlib.Path(__file__).resolve().parent.parent


# [workdir-drops-dispatch]
# Rationale: `workdir` copies this repo's own `constellation.toml`
#   verbatim, and that file's `[commands]` now carries a real `dispatch`
#   entry (a real `claude` invocation) -- so every existing fast-suite test
#   that renders a dispatch or panel room through this fixture would spawn
#   a real subprocess in the background the instant that entry became real,
#   with the failure invisible (`_spawn`'s `Popen` is fire-and-forget, its
#   errors caught and logged, never raised into the render). Dropping the
#   key here is airtight rather than merely tidy: `engine/checks.py`'s own
#   `spawn_dispatch` refuses to spawn anything when `"dispatch" not in
#   commands`, so a workdir-based render has nothing left to call even if
#   some later change to the engine forgot to guard the call site. The
#   removal itself establishes key absence directly: a best-effort text
#   strip is checked by its own postcondition, `_dispatch_is_absent`,
#   which parses the result as TOML and looks for the key -- never at the
#   text -- so no formatting of the entry (one line, several, reordered)
#   can produce a false pass. A survival is not silent: the postcondition
#   raises, naming the entry, before the fixture hands the copy to a test.
# Rejected: an autouse fixture monkeypatching `checks.spawn_dispatch`.
#   That guard would live beside the fixture rather than in it, covering
#   every test in the session (including `test_spawn_dispatch.py`'s own
#   direct, deliberate calls) unless it were then taught to exempt them --
#   a second thing to keep in sync with the first. Editing the one file
#   `workdir` already writes needs nothing else to know about the guard.
_DISPATCH_ENTRY_RE = re.compile(r"(?ms)^dispatch[ \t]*=[ \t]*(?:\[.*?\]|[^\n]*)\n?")


def _dispatch_is_absent(text):
    """The removal's own postcondition: parse `text` as TOML and confirm
    `[commands]` carries no `dispatch` key. Judged against the parsed
    palette, never the text, so no line-wrapping or reordering of the
    entry can fool it either way. Raises loudly, naming the surviving
    entry, rather than letting a kept `dispatch` command travel into the
    fast suite quietly -- the spawn side cannot tell the two cases apart
    (see rationale above), so this is the only thing in the system that
    can."""
    palette = tomllib.loads(text)
    if "dispatch" in palette.get("commands", {}):
        raise AssertionError(
            "workdir-drops-dispatch: constellation.toml's copy still "
            "carries a `dispatch` command -- the removal meant to strip "
            "it did not, and the fast suite would spawn a real process.")


def _without_dispatch_entry(text):
    stripped = _DISPATCH_ENTRY_RE.sub("", text, count=1)
    _dispatch_is_absent(stripped)
    return stripped


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONSTELLATION_SESSION", "test-session")
    # the command palette (models, check commands) is host-repo config;
    # tests run in an isolated tmp cwd, so it travels with them -- its real
    # `dispatch` entry is dropped, see `_without_dispatch_entry` above.
    (tmp_path / "constellation.toml").write_text(
        _without_dispatch_entry((REPO / "constellation.toml").read_text()))
    init_checkout(tmp_path)
    return tmp_path


@pytest.fixture
def bare_workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONSTELLATION_SESSION", "test-session")
    init_checkout(tmp_path)
    return tmp_path
