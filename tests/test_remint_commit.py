"""#231's second half: the gate a remint replaces leaves work uncommitted;
the replacement's landing commit must carry it, under the replacement's trailer."""

from engine import cli, checks, journal, run as runmod
from test_gate_commit import _dispatch_and_close_child_with_diff, _git
from test_nesting import _fill_gate_transition, _fill_gate_transition_remint, _mint_first_gate


def test_a_reminted_gate_lands_a_commit_the_next_gate_s_base_finds(workdir, capsys):
    _mint_first_gate()
    worktree = workdir / ".worktrees" / "issue17"
    _dispatch_and_close_child_with_diff("issue17", "g1", "first.txt")
    _fill_gate_transition_remint("issue17")
    cli.main(["issue17", "submit"])
    new = next(s["id"] for s in runmod.state("issue17")["steps"]
               if s.get("dispatches") == "run-a-gate" and s["id"] != "g1")
    _dispatch_and_close_child_with_diff("issue17", new, "second.txt")
    _fill_gate_transition("issue17")
    cli.main(["issue17", "submit"])
    capsys.readouterr()
    assert f"Work-Id: issue17.{new}" in _git(worktree, "log", "-1", "--format=%B").stdout
    assert checks.gate_base("issue17", worktree) == _git(worktree, "rev-parse", "HEAD").stdout.strip()
