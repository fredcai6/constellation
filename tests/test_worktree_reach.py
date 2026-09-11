"""Work-id resolution across two roots (#52): a run addresses the same tree
whether the caller stands in the top-level checkout or inside the issue
worktree its work location actually lives in.

Four cwd-relative reads used to disagree the moment a worktree existed:
`journal.location` itself, the ledger's and the rail's open-run scan, the
check's `palette:` resolution and the subprocess it drives, and a measured
artifact's stored path. All four are exercised here, driven for real rather
than read off the source -- and the write side too: `_open_child` must nest
a freshly dispatched gate or panelist inside its parent's actual worktree,
never wherever the dispatching shell happens to be standing, or g4's later
archive move cannot find it.
"""

import pathlib
import subprocess

import pytest

from engine import cli, journal, rail, render, run as runmod
from test_nesting import _fill_implement, _fill_open, _fill_consolidate, _fill_plan, \
    _dispatch_and_close_plan, _dispatch_plan_critic, _select_panel, \
    _work_the_board, _fill_plan_to_execute


def _open_one_gate(wid, issue, proof):
    """Drive a run-an-issue open to one freshly minted gate dispatch step,
    with a caller-chosen `proof` -- the shape a check-resolution test needs,
    which `test_nesting._mint_first_gate` does not expose. The proof is the
    plan round's own field now (#27): it has to ride in through `_fill_plan`,
    not a PLAN_TO_EXECUTE.toml block -- a stale `[[gates]]` block there is
    silently ignored rather than refused, which is exactly the trap this
    comment is here to name for the next reader. `_fill_plan_to_execute`
    (test_nesting.py) is the route form's own conductor fill now (ruling 3):
    `resolution` and, on a pass, the `plan` pointer that projects the gate."""
    cli.main(["open", "run-an-issue", "--issue", issue, "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    _dispatch_and_close_plan(wid, fill_fn=lambda w: _fill_plan(
        w, purpose="gate purpose", scope="gate scope", proof=proof))
    _dispatch_plan_critic(wid)
    _fill_plan_to_execute(wid)
    cli.main([wid, "submit"])


# -- an unknown id says where it looked, and refuses loudly (#67) -----------


def test_unknown_id_from_a_bare_cwd_says_none_here_and_refuses_nonzero(
        tmp_path, monkeypatch):
    """A subagent's cwd resets between bash calls, so a bare `spine <id>
    note ...` from a conductor thread that never `cd`'d anywhere lands in a
    directory with no `.agent-work` and no `.worktrees` -- the exact shape
    that used to read as a silently lost note. `none here` says the search
    space was empty, not merely that this one id was not in it."""
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as e:
        cli.main(["xyz", "note", "observation", "text"])
    msg = str(e.value)
    assert "none here" in msg
    assert "run this from the checkout or the worktree" in msg


def test_unknown_id_names_the_agent_work_roots_actually_present(
        workdir, capsys, monkeypatch):
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    capsys.readouterr()
    monkeypatch.chdir(workdir)  # back at the top level; issue17 lives in its worktree

    with pytest.raises(SystemExit) as e:
        cli.main(["nope", "note", "observation", "text"])
    msg = str(e.value)
    assert "none here" not in msg
    assert str(pathlib.Path(".worktrees", "issue17", ".agent-work")) in msg


def test_a_subprocess_run_from_a_bare_cwd_exits_nonzero(tmp_path):
    """Driven end to end, not just through `runmod.state`'s own return: the
    real failure mode is a caller's `&&` chain, so the exit code has to be
    the process's own, not merely a Python exception a test harness caught."""
    r = subprocess.run([render.spine_cmd(), "xyz", "note", "observation", "text"],
                       cwd=tmp_path, capture_output=True, text=True, timeout=20)
    assert r.returncode != 0
    # an uncaught SystemExit with a message writes it to stderr, never stdout
    assert "none here" in r.stderr


# -- the read side: an id resolves from the top level -------------------


def test_a_run_status_resolves_from_the_top_level_when_it_lives_in_a_worktree(
        workdir, capsys, monkeypatch):
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "parser eof"])
    capsys.readouterr()
    monkeypatch.chdir(workdir)  # the shell never followed the printed `cd`

    assert journal.exists("issue17")
    assert runmod.state("issue17") is not None
    cli.main(["issue17"])  # must not raise "no run named issue17"
    assert "issue17" in capsys.readouterr().out


def test_bare_ledger_from_the_top_level_lists_a_run_living_in_a_worktree(
        workdir, capsys, monkeypatch):
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "parser eof"])
    capsys.readouterr()
    monkeypatch.chdir(workdir)

    cli.main([])
    out = capsys.readouterr().out
    assert "issue17" in out and "parser eof" in out


def test_rail_scan_reaches_a_run_living_in_a_worktree(workdir, capsys, monkeypatch):
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "parser eof"])
    capsys.readouterr()
    monkeypatch.chdir(workdir)

    runs = rail._open_runs()
    assert any(st["id"] == "issue17" for st in runs)


def test_trace_from_the_top_level_reaches_a_run_living_in_a_worktree(
        workdir, capsys, monkeypatch):
    """`cmd_trace` derives each nested run's id relative to this run's own
    `.agent-work` -- not a literal cwd-relative one -- since a traced run's
    tree may be a worktree's rather than here."""
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "parser eof"])
    capsys.readouterr()
    monkeypatch.chdir(workdir)

    cli.main(["issue17", "trace"])  # must not raise
    out = capsys.readouterr().out
    assert "issue17" in out


# -- a check resolves and runs against the run's own tree, not the shell ----


def test_a_gates_check_resolves_and_runs_against_the_runs_own_worktree(
        workdir, capsys, monkeypatch):
    """`palette:canary` must expand against the worktree's own
    constellation.toml -- not the top-level checkout's, which never gained
    the entry -- and the command it expands to must then run with the
    worktree as cwd -- not wherever the submitting shell stands -- proven by
    a file the command can only see from inside the worktree."""
    _open_one_gate("issue17", "17", "palette:canary")
    capsys.readouterr()
    worktree = workdir / ".worktrees" / "issue17"

    # the new entry belongs inside the existing [commands] table, not a
    # second one shadowing it, so insert right after the table header
    toml = worktree / "constellation.toml"
    text = toml.read_text()
    assert text.count("[commands]") == 1
    toml.write_text(text.replace(
        "[commands]\n", '[commands]\ncanary = "test -f canary.txt"\n', 1))
    (worktree / "canary.txt").write_text("only visible from inside the worktree\n")

    st = runmod.state("issue17")
    step_id = st["current"]["id"]
    cli.main(["open", "run-a-gate", "--parent", "issue17", "--step", step_id])
    child_wid = f"issue17.{step_id}"
    _fill_implement(child_wid, step_id)
    capsys.readouterr()

    monkeypatch.chdir(workdir)  # the shell drifted back to the top level
    cli.main([child_wid, "submit"])  # must not raise -- the check must pass

    checks = [e for e in journal.read(child_wid) if e.get("kind") == "submit"][-1]["checks"]
    assert checks and checks[0]["exit"] == 0, checks


# -- a measured artifact resolves against the run's own tree ---------------


def test_measured_artifact_resolves_against_the_runs_own_tree_from_any_cwd(
        workdir, capsys, monkeypatch):
    """The `plan` field stores a work-location-inclusive path
    (`.agent-work/issue21/plan-1/plan.md`). Measuring it from a cwd that is
    not the run's own worktree must still find the real file -- resolved
    against the run's own tree, not doubled against its own work location.
    Proven on the plan segment's own dispatch child, which inherits the
    parent's tree (ruling 8) exactly the way a gate's child does."""
    cli.main(["open", "run-an-issue", "--issue", "21", "--title", "t"])
    wid = "issue21"
    worktree = workdir / ".worktrees" / wid
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])

    cli.main(["open", "cut-a-gate", "--parent", wid, "--step", "plan-1"])
    child = f"{wid}.plan-1"
    plan_path = worktree / ".agent-work" / wid / "plan-1" / "plan.md"
    plan_path.write_text(" ".join(["word"] * 50) + "\n")
    _fill_plan(child)
    capsys.readouterr()

    monkeypatch.chdir(workdir)  # a fresh session that never cd'd into the worktree
    cli.main([child, "submit"])

    measures = [e for e in journal.read(child) if e.get("kind") == "measure"]
    assert measures, "no measure entry -- the artifact path did not resolve"
    assert measures[-1]["words"] >= 50


# -- the write side: a dispatched child nests inside its parent's tree -----


def test_a_gate_dispatched_from_a_cwd_that_is_not_the_parents_worktree_still_nests_inside_it(
        workdir, capsys, monkeypatch):
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    wid = "issue17"
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    _dispatch_and_close_plan(wid)
    _dispatch_plan_critic(wid)
    _fill_plan_to_execute(wid)
    cli.main([wid, "submit"])
    step_id = runmod.state(wid)["current"]["id"]
    capsys.readouterr()

    monkeypatch.chdir(workdir)  # the conductor's shell never followed `open`'s cd
    cli.main(["open", "run-a-gate", "--parent", wid, "--step", step_id])

    child_wid = f"{wid}.{step_id}"
    worktree = workdir / ".worktrees" / wid
    assert (worktree / ".agent-work" / wid / step_id / "journal.toml").exists()
    assert not (workdir / ".agent-work").exists()  # no stray top-level work location
    assert journal.exists(child_wid)
    assert journal.location(child_wid).resolve() == worktree / ".agent-work" / wid / step_id
    cli.main([child_wid])  # must not raise -- resolves from the top level too


# -- render.brief names the worktree and the branch ------------------------


def test_dispatch_brief_names_the_worktree_and_branch_for_a_root_run(workdir, capsys):
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    wid = "issue17"
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    _dispatch_and_close_plan(wid)
    _dispatch_plan_critic(wid)
    _fill_plan_to_execute(wid)
    cli.main([wid, "submit"])
    capsys.readouterr()

    cli.main([wid])
    out = capsys.readouterr().out
    worktree = workdir / ".worktrees" / wid
    assert str(worktree.resolve()) in out
    assert "branch" in out and wid in out


def test_review_panel_brief_on_a_nested_gate_names_the_parents_worktree_and_branch(
        workdir, capsys):
    """A gate's own run entry carries no branch or worktree of its own --
    only a root run's does -- so its review panel's brief must climb to the
    issue that dispatched it rather than come up empty."""
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    wid = "issue17"
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    _dispatch_and_close_plan(wid)
    _dispatch_plan_critic(wid)
    _fill_plan_to_execute(wid)
    cli.main([wid, "submit"])
    step_id = runmod.state(wid)["current"]["id"]
    cli.main(["open", "run-a-gate", "--parent", wid, "--step", step_id])
    child_wid = f"{wid}.{step_id}"
    _fill_implement(child_wid, step_id)
    cli.main([child_wid, "submit"])
    _select_panel(child_wid)               # mints the review step and its panel
    capsys.readouterr()

    cli.main([child_wid])  # now standing on the review panel
    out = capsys.readouterr().out
    worktree = workdir / ".worktrees" / wid
    assert str(worktree.resolve()) in out
    assert f"branch {wid}" in out
