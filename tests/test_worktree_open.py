"""The issue tier's own git (ruling 8): `spine open`'s root-run path.

A root run resolves the project's top-level checkout, refuses by name when
it cannot make a pushed branch and worktree there, and otherwise works
inside the worktree it just made. `_open_child` is untouched -- a dispatched
child inherits its parent's tree rather than making one of its own.

Every case here reaches a **local bare repository** as `origin`, made fresh
per test by `gitremote.init_checkout` -- this suite runs constantly and must
never reach a live remote.
"""

import pathlib
import subprocess

import pytest

from engine import cli, journal, render, run as runmod
from gitremote import init_checkout
from test_nesting import _mint_two_gates

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


# -- the happy path: a pushed worktree, worked from inside it ---------------


def test_root_open_makes_a_pushed_worktree_and_works_inside_it(workdir, capsys):
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    capsys.readouterr()

    worktree = workdir / ".worktrees" / "issue17"
    assert worktree.is_dir()
    # the work location landed inside the worktree, not the top-level checkout
    assert (worktree / ".agent-work" / "issue17" / "journal.toml").exists()
    assert not (workdir / ".agent-work").exists()
    # the process itself now stands inside the worktree
    assert pathlib.Path.cwd() == worktree.resolve()

    assert "issue17" in _git(workdir, "branch", "--list", "issue17").stdout
    upstream = _git(worktree, "rev-parse", "--abbrev-ref",
                    "issue17@{upstream}").stdout.strip()
    assert upstream == "origin/issue17"

    run_entry = next(e for e in journal.read("issue17") if e["kind"] == "run")
    assert run_entry["branch"] == "issue17"
    assert run_entry["worktree"] == str(worktree)


def test_open_names_the_worktree_and_the_cd_that_reaches_it(workdir, capsys):
    """`os.chdir` moves the process `open` runs in, not the shell that
    launched it -- that shell is left in the top-level checkout once `open`
    exits, so every command `open` prints has to be reachable from there.
    Naming the worktree and the exact `cd` is what makes it so; this is
    driven, not just read off stdout: a fresh process, nothing on PATH,
    standing wherever the printed `cd` lands, is where `spine issue99` must
    actually resolve."""
    cli.main(["open", "run-an-issue", "--issue", "99", "--title", "t"])
    out = capsys.readouterr().out

    worktree = workdir / ".worktrees" / "issue99"
    assert str(worktree) in out
    line = next(l for l in out.splitlines() if l.strip().startswith("cd "))
    assert line.strip().split() == ["cd", str(worktree)]

    r = subprocess.run([render.spine_cmd(), "issue99"], capture_output=True,
                       text=True, env={}, cwd=worktree, timeout=20)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "issue99" in r.stdout, r.stdout


def test_root_open_journals_the_ordinary_nothing_staged_commit_as_a_no_op(workdir):
    # .agent-work is gitignored (gitremote.init_checkout mirrors this repo's
    # own .gitignore), so the commit `open` attempts stages nothing -- the
    # ordinary case, not an edge case the suite has to go looking for.
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    notes = [e for e in journal.read("issue17") if e["kind"] == "note"]
    assert any(n.get("about") == "commit" for n in notes)


def test_a_second_root_open_from_inside_the_first_worktree_lands_beside_it(workdir):
    """Top-level resolution must survive being called again from inside a
    worktree `open` just produced -- an agent opening a second, unrelated
    issue without first leaving the one it is standing in. Resolving via
    `--show-toplevel` would name the current worktree itself and nest the
    second issue's worktree inside the first; `--git-common-dir` (shared by
    every worktree of one repository) names the original checkout instead."""
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    cli.main(["open", "run-an-issue", "--issue", "18", "--title", "u"])

    assert (workdir / ".worktrees" / "issue18").is_dir()
    assert not (workdir / ".worktrees" / "issue17" / ".worktrees").exists()


# -- git stays inside the issue tier (ruling 8) --------------------------


def test_an_idea_run_gets_no_worktree_no_branch_no_push(workdir):
    """`explore-an-idea` has no segment that dispatches gates -- it produces
    a spec, not a diff, and has no gate to commit. Only an issue-shaped
    assembly (one whose plan dispatches gates) is the issue tier ruling 8
    scopes git to; everything else works in place, in the checkout it was
    opened from."""
    before_worktrees = _git(workdir, "worktree", "list").stdout
    before_branches = _git(workdir, "branch", "--list").stdout
    cwd_before = pathlib.Path.cwd()

    cli.main(["open", "explore-an-idea", "--id", "idea1", "--title", "t"])

    assert not (workdir / ".worktrees" / "idea1").exists()
    assert _git(workdir, "worktree", "list").stdout == before_worktrees
    assert _git(workdir, "branch", "--list").stdout == before_branches
    assert pathlib.Path.cwd() == cwd_before  # never moved -- there was nowhere to move to

    assert journal.exists("idea1")
    assert journal.location("idea1") == pathlib.Path(".agent-work", "idea1")
    run_entry = next(e for e in journal.read("idea1") if e["kind"] == "run")
    assert run_entry["worktree"] == str(cwd_before)


# -- refusals, named ----------------------------------------------------


def test_refuses_by_name_when_not_a_git_checkout(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONSTELLATION_SESSION", "test-session")
    (tmp_path / "constellation.toml").write_text((REPO / "constellation.toml").read_text())

    with pytest.raises(SystemExit) as e:
        cli.main(["open", "run-an-issue", "--id", "x", "--title", "t"])
    assert "checkout" in str(e.value)
    assert "not a git checkout" in str(e.value)
    assert not journal.exists("x")


def test_refuses_by_name_when_the_checkout_has_no_remote(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONSTELLATION_SESSION", "test-session")
    (tmp_path / "constellation.toml").write_text((REPO / "constellation.toml").read_text())
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "test")
    (tmp_path / ".gitkeep").write_text("")
    _git(tmp_path, "add", ".gitkeep")
    _git(tmp_path, "commit", "--quiet", "-m", "initial")

    with pytest.raises(SystemExit) as e:
        cli.main(["open", "run-an-issue", "--id", "x", "--title", "t"])
    assert "remote" in str(e.value)
    assert not journal.exists("x")


def test_a_push_failure_cleans_up_so_the_retry_is_the_same_command(workdir):
    # a local path that does not exist -- a real push failure, never the network
    real_remote = workdir.parent / f"{workdir.name}-remote.git"
    _git(workdir, "remote", "set-url", "origin", str(workdir / "no-such-remote.git"))

    # run-an-issue, not run-a-gate: only the issue tier makes a worktree now,
    # so a bare `run-a-gate` root open (never how a real one is opened -- it
    # is always dispatched with --parent) would not reach the push at all.
    argv = ["open", "run-an-issue", "--id", "g1", "--title", "t"]
    with pytest.raises(SystemExit) as e:
        cli.main(argv)
    assert "push" in str(e.value)
    assert not journal.exists("g1")
    assert not (workdir / ".worktrees" / "g1").exists()
    assert "g1" not in _git(workdir, "branch", "--list", "g1").stdout

    # fix the cause and retry -- the exact command again, no cleanup of our own
    _git(workdir, "remote", "set-url", "origin", str(real_remote))
    cli.main(argv)

    assert journal.exists("g1")
    assert (workdir / ".worktrees" / "g1").is_dir()


def test_push_runs_from_the_toplevel_checkout_so_a_relative_remote_resolves(workdir):
    """`origin` is configured relative to the top-level checkout, where the
    caller set it up -- not to the worktree `git worktree add` just made one
    level deeper. A push that runs with the worktree as cwd resolves a
    relative remote against the wrong directory and fails; run from the
    top-level checkout, the same relative path resolves the way it was
    configured to."""
    remote = workdir.parent / f"{workdir.name}-remote.git"
    _git(workdir, "remote", "set-url", "origin", f"../{remote.name}")

    cli.main(["open", "run-an-issue", "--issue", "42", "--title", "t"])

    worktree = workdir / ".worktrees" / "issue42"
    assert worktree.is_dir()
    upstream = _git(worktree, "rev-parse", "--abbrev-ref",
                    "issue42@{upstream}").stdout.strip()
    assert upstream == "origin/issue42"


# -- _open_child is untouched -------------------------------------------


def test_open_child_inherits_the_parent_tree_and_makes_no_worktree_of_its_own(workdir):
    _mint_two_gates("issue17")
    before = _git(workdir, "worktree", "list").stdout

    st = runmod.state("issue17")
    step_id = st["current"]["id"]
    cli.main(["open", "run-a-gate", "--parent", "issue17", "--step", step_id])

    after = _git(workdir, "worktree", "list").stdout
    assert before == after  # no worktree minted for the child

    child_wid = f"issue17.{step_id}"
    assert f"issue17.{step_id}" not in _git(workdir, "branch", "--list").stdout
    assert journal.exists(child_wid)
    # nested under the parent's own work location, inside the parent's worktree
    assert journal.location(child_wid) == pathlib.Path(".agent-work", "issue17", step_id)
