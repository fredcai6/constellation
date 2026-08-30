"""Close archives, sweeps and opens the PR (issue19.g4).

`cmd_close`'s root-run path now pushes the branch, opens the PR through
`gh`, moves the work location into the top-level checkout's own archive,
and only then removes the worktree -- in that order, because the work
location lives inside the worktree and would otherwise be destroyed along
with it, and because a push or PR failure must leave an intact run the same
`spine <id> close` retries rather than one journaled closed, archived and
swept with no PR and no defined recovery.

Every case here reaches a **local bare repository** as `origin`, and `gh`
is stubbed on argv (`gitremote.stub_gh`) exactly the way
`tests/test_eval_harness.py` already stubs `claude` -- this suite runs
constantly and a test that could open a real pull request against this
repo is not a test, it is an accident waiting for a contributor.
"""

import pathlib
import subprocess

import pytest

from engine import cli, journal, run as runmod
from gitremote import init_checkout, read_archived, stub_gh
from test_nesting import (
    _dispatch_and_close_child, _dispatch_review, _fill_close, _fill_gate_close,
    _fill_gate_transition, _fill_implement, _mint_two_gates,
)

REPO = pathlib.Path(__file__).resolve().parent.parent


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONSTELLATION_SESSION", "test-session")
    (tmp_path / "constellation.toml").write_text((REPO / "constellation.toml").read_text())
    init_checkout(tmp_path)
    return tmp_path


def _drive_issue_to_awaiting_close(wid="issue17"):
    """Two gates, both advanced -- `execute`'s terminal (CLOSE.toml) is only
    reachable once every dispatched gate has returned and been adjudicated."""
    _mint_two_gates(wid)
    for step in ("g1", "g2"):
        _dispatch_and_close_child(wid, step)
        _fill_gate_transition(wid)
        cli.main([wid, "submit"])
    _fill_close(wid)
    cli.main([wid, "submit"])


# -- the happy path: push, PR, archive, sweep --------------------------------


def test_close_archives_the_work_location_and_its_children_pushes_and_prs(
        workdir, capsys, monkeypatch):
    _drive_issue_to_awaiting_close()
    capsys.readouterr()
    worktree = workdir / ".worktrees" / "issue17"
    tip = _git(worktree, "rev-parse", "issue17").stdout.strip()
    calls = []
    stub_gh(monkeypatch, calls=calls)

    cli.main(["issue17", "close"])
    capsys.readouterr()

    # the PR command actually ran
    assert any(c[:3] == ["gh", "pr", "create"] for c in calls), calls

    # close's own push carried the gate commits made since open -- not just
    # the empty branch open already pushed
    remote = workdir.parent / f"{workdir.name}-remote.git"
    assert _git(remote, "rev-parse", "issue17").stdout.strip() == tip

    # the worktree is gone
    assert not worktree.exists()
    assert "issue17" not in _git(workdir, "worktree", "list").stdout

    # the record landed in the top-level checkout's archive, children too --
    # nested by the ordinary dotted-id layout, no work of their own
    archived = workdir / ".agent-work" / "archive" / "issue17"
    assert (archived / "journal.toml").exists()
    assert (archived / "g1" / "journal.toml").exists()
    assert (archived / "g2" / "journal.toml").exists()
    closed = read_archived(workdir, "issue17", "closed")
    assert closed["kind"] == "closed"

    # the ledger does not list it, mangled or otherwise
    cli.cmd_ledger()
    out = capsys.readouterr().out
    assert "issue17" not in out
    assert "archive" not in out


# -- refusals: named, and moving nothing -------------------------------------


def test_close_refuses_a_destination_that_already_exists_having_moved_nothing(
        workdir, capsys, monkeypatch):
    _drive_issue_to_awaiting_close()
    capsys.readouterr()
    worktree = workdir / ".worktrees" / "issue17"
    archive_dir = workdir / ".agent-work" / "archive" / "issue17"
    archive_dir.mkdir(parents=True)
    marker = archive_dir / "keep.txt"
    marker.write_text("a prior close already used this id\n")
    calls = []
    stub_gh(monkeypatch, calls=calls)

    with pytest.raises(SystemExit) as e:
        cli.main(["issue17", "close"])
    assert "archive" in str(e.value)
    assert "already exists" in str(e.value)

    # nothing moved, nothing pushed, no PR opened
    assert marker.exists() and marker.read_text() == "a prior close already used this id\n"
    assert worktree.is_dir()
    assert (worktree / ".agent-work" / "issue17" / "journal.toml").exists()
    assert calls == []
    assert not runmod.state("issue17")["closed"]


def test_a_failed_push_refuses_leaving_the_worktree_and_work_location_intact(
        workdir, capsys, monkeypatch):
    _drive_issue_to_awaiting_close()
    capsys.readouterr()
    worktree = workdir / ".worktrees" / "issue17"
    real_remote = workdir.parent / f"{workdir.name}-remote.git"
    # a local path that does not exist -- a real push failure, never the network
    _git(workdir, "remote", "set-url", "origin", str(workdir / "no-such-remote.git"))
    calls = []
    stub_gh(monkeypatch, calls=calls)

    with pytest.raises(SystemExit) as e:
        cli.main(["issue17", "close"])
    assert "push" in str(e.value)

    assert worktree.is_dir()
    assert (worktree / ".agent-work" / "issue17" / "journal.toml").exists()
    assert calls == []  # push failed before gh was ever reached
    assert not runmod.state("issue17")["closed"]

    # fix the cause and retry -- the exact command again, no cleanup of our own
    _git(workdir, "remote", "set-url", "origin", str(real_remote))
    cli.main(["issue17", "close"])

    assert not worktree.exists()
    assert (workdir / ".agent-work" / "archive" / "issue17" / "journal.toml").exists()


def test_a_failed_pr_refuses_leaving_the_worktree_and_work_location_intact(
        workdir, capsys, monkeypatch):
    _drive_issue_to_awaiting_close()
    capsys.readouterr()
    worktree = workdir / ".worktrees" / "issue17"
    stub_gh(monkeypatch, ok=False, stderr="a pull request for branch \"issue17\" already exists")

    with pytest.raises(SystemExit) as e:
        cli.main(["issue17", "close"])
    assert "pr" in str(e.value)

    assert worktree.is_dir()
    assert (worktree / ".agent-work" / "issue17" / "journal.toml").exists()
    assert not runmod.state("issue17")["closed"]

    # the branch really did reach the remote even though the PR failed
    remote = workdir.parent / f"{workdir.name}-remote.git"
    assert "issue17" in _git(remote, "branch", "--list", "issue17").stdout

    # retry succeeds once gh does -- the push half is idempotent
    stub_gh(monkeypatch, ok=True)
    cli.main(["issue17", "close"])

    assert not worktree.exists()


# -- the guard: git is the issue tier's, and only the issue tier's ----------


def test_a_non_issue_tier_close_never_reaches_git_or_gh(workdir, capsys, monkeypatch):
    """Closing a bare `run-a-gate` root -- never how a real one opens; always
    dispatched with `--parent` -- must never touch git or `gh`. The same
    structural guard `_commit_gate` already applies at advance."""
    cli.main(["open", "run-a-gate", "--id", "g1"])
    _fill_implement("g1", "work-1")
    cli.main(["g1", "submit"])
    _dispatch_review("g1")
    _fill_gate_close("g1")
    cli.main(["g1", "submit"])
    calls = []
    stub_gh(monkeypatch, calls=calls)
    before = _git(workdir, "rev-parse", "HEAD").stdout.strip()

    cli.main(["g1", "close"])

    assert calls == []
    after = _git(workdir, "rev-parse", "HEAD").stdout.strip()
    assert after == before
    assert not (workdir / ".agent-work" / "archive").exists()


def test_an_issue_tier_run_with_no_branch_or_worktree_stamped_closes_without_archiving(
        workdir, capsys, monkeypatch):
    """`issue19`'s exact shape (opened before the worktree feature existed):
    `_issue_tier` is true, but neither `branch` nor `worktree` names
    anything real. `cmd_close` must close ordinarily, never reach git or
    `gh` -- the corollary rules out a refusal here, since neither condition
    names a field the agent could fill or a fix within its reach."""
    journal.append("issue18", "run", title="t", assembly="run-an-issue", conductor="")
    journal.append("issue18", "step", id="close", segment="execute", terminal=True,
                   anchor=True, form="forms/CLOSE.toml", filler="conductor")
    _fill_close("issue18")
    cli.main(["issue18", "submit"])
    calls = []
    stub_gh(monkeypatch, calls=calls)

    cli.main(["issue18", "close"])

    assert calls == []
    assert runmod.state("issue18")["closed"]
    assert not (workdir / ".agent-work" / "archive").exists()
