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

import pytest

from gitremote import init_checkout

REPO = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONSTELLATION_SESSION", "test-session")
    # the command palette (models, check commands) is host-repo config;
    # tests run in an isolated tmp cwd, so it travels with them
    (tmp_path / "constellation.toml").write_text((REPO / "constellation.toml").read_text())
    init_checkout(tmp_path)
    return tmp_path


@pytest.fixture
def bare_workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONSTELLATION_SESSION", "test-session")
    init_checkout(tmp_path)
    return tmp_path
