"""Each gate's cut answers to the code and spec as they stand (2026-09-26).

Two changes carry it, beside `panel-rounds = "fresh"` (tests/
test_fresh_cut_panel.py):

- A gate carries two proofs. `proof` is what must be true when the issue
  ends: run at the cut, when the gate lands, and again at close.
  `gate-proof` is what must be true when the gate lands -- what it left
  alone -- run at the cut and when the gate lands, never at close. The
  prose rule that kept such clauses out of `proof` (#201) did not take: 12
  of 36 gate proofs across the next 12 runs still pinned `git diff --quiet
  <cut> -- <paths>`, and issue191's close could not survive one.
- Every dispatched child is handed what has landed (`_landed`): the
  commits past the run's cut point and the rows already settled, so a
  planner cuts from the state rather than reading the last plan.
"""

import pathlib
import subprocess

from engine import cli, forms, journal, run as runmod
from gitremote import stub_gh
from test_execution_state import _to_close_with_g1_satisfied
from test_gate_commit import _dispatch_and_close_child_with_diff
from test_nesting import _fill_gate_transition, _mint_first_gate


ROOT = pathlib.Path(__file__).resolve().parent.parent


def _fields(path):
    return {f["id"]: f for f in forms.load(ROOT / path)["fields"]}


def _gate_item_fields(path):
    """The item fields nested inside PLAN.toml/REWORK.toml's own `gates`
    field -- the one block every gate's `purpose`/`scope`/`proof`/
    `gate-proof`/... now live in, in place of top-level fields."""
    gates = _fields(path)["gates"]
    return {f["id"]: f for f in gates["item"]}


def _gate_checks(wid):
    """Every command the gate's own implement submits ran."""
    return [c["command"] for e in journal.read(wid)
            if e["kind"] == "submit" for c in e.get("checks") or []]


# -- the two proofs ----------------------------------------------------------


def test_every_form_that_carries_a_gate_spec_carries_both_proofs():
    """The planner writes both, the projection carries both, and the gate's
    implement step runs both."""
    for path in ("skills/planner/forms/PLAN.toml", "skills/planner/forms/REWORK.toml"):
        fields = _gate_item_fields(path)
        assert fields["proof"]["kind"] == "proof"
        assert fields["gate-proof"]["kind"] == "proof"
        assert fields["gate-proof"].get("optional")
    implement = _fields("skills/implementer/forms/IMPLEMENT.toml")
    assert implement["proof"]["kind"] == implement["gate-proof"]["kind"] == "check"
    assert "gate-proof" in cli._GATE_FIELDS


def test_a_gate_proof_runs_when_the_gate_lands_and_never_at_close(
        workdir, capsys, monkeypatch):
    """issue191 g6: a clause about what the gate left alone went false once a
    later change touched those paths, and close could not finish. As a
    `gate-proof` it runs when the gate lands and is never replayed."""
    stub_gh(monkeypatch)
    _to_close_with_g1_satisfied("test -f landed.txt", gate_proof="test ! -f later.txt")
    assert _gate_checks("issue17.g1") == ["test -f landed.txt", "test ! -f later.txt"]
    (journal.root_for("issue17") / "later.txt").write_text("a later gate's work\n")
    capsys.readouterr()

    cli.main(["issue17", "close"])

    out = capsys.readouterr().out
    assert "test ! -f later.txt" not in out
    assert runmod.state("issue17") is None or runmod.state("issue17")["closed"]


def test_a_waived_gate_proof_runs_nothing_at_the_gate(workdir, capsys, monkeypatch):
    stub_gh(monkeypatch)
    _to_close_with_g1_satisfied("test -f landed.txt", gate_proof="waived: none")
    assert _gate_checks("issue17.g1") == ["test -f landed.txt"]


# -- what has landed ---------------------------------------------------------


def test_a_child_is_handed_the_commits_past_the_cut_and_the_settled_rows(
        workdir, capsys, monkeypatch):
    """A planner re-cutting after a gate reads what landed off its prefill,
    not off the last plan: each gate's commit subject, and each row a gate
    settled, with its word."""
    stub_gh(monkeypatch)
    _to_close_with_g1_satisfied("test -f landed.txt")
    landed = cli._landed(runmod.state("issue17"), journal.root_for("issue17"))["landed"]
    assert "g1: fix the parser to handle EOF without a trailing newline" in landed
    assert landed.index("g1:") < landed.index("o1 -- satisfied")


def test_nothing_has_landed_on_the_opening_cut(workdir, capsys):
    from test_nesting import _fill_open
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    _fill_open("issue17")
    cli.main(["issue17", "submit"])
    capsys.readouterr()
    assert cli._landed(runmod.state("issue17"), journal.root_for("issue17")) == {}


# -- the base a gate's scope check diffs against -----------------------------
# issue299 g4 (sports-market-manager, 2026-10-26): every gate-proof diffed
# `origin/main...HEAD`, so gate N tripped on files gates 1..N-1 had landed on
# the branch. The engine now names the base: CONSTELLATION_GATE_BASE.


def _sh(cwd, *argv):
    import subprocess
    return subprocess.run(list(argv), cwd=str(cwd), capture_output=True,
                          text=True).stdout


def test_the_first_gate_s_base_is_the_branch_point_off_main(
        workdir, capsys, monkeypatch):
    stub_gh(monkeypatch)
    _to_close_with_g1_satisfied(
        "test -f landed.txt",
        gate_proof='test -n "$CONSTELLATION_GATE_BASE" && test "$CONSTELLATION_GATE_BASE" = '
                   '"$(git rev-parse HEAD)"')
    assert _gate_checks("issue17.g1")[-1].startswith('test -n "$CONSTELLATION_GATE_BASE"')


def test_a_later_gate_s_base_is_the_last_landed_gate_commit_not_main(
        workdir, capsys, monkeypatch):
    """After g1 lands a file, g2's scope diff against the base is empty
    while the same diff against origin/main lists g1's file."""
    from engine import checks
    _mint_first_gate()
    worktree = workdir / ".worktrees" / "issue17"
    _dispatch_and_close_child_with_diff("issue17", "g1")
    _fill_gate_transition("issue17")
    cli.main(["issue17", "submit"])
    capsys.readouterr()

    landed = _sh(worktree, "git", "rev-parse", "HEAD").strip()
    base = checks.gate_base("issue17", worktree)
    assert base == landed
    cut = runmod.state("issue17")["from"].rpartition("@")[2]
    assert _sh(worktree, "git", "diff", "--name-only", cut + "...HEAD").split() == ["src.txt"]
    assert _sh(worktree, "git", "diff", "--name-only", base).split() == []
    code, out = checks._run('test "$(git diff --name-only "$CONSTELLATION_GATE_BASE" '
                            '| wc -l)" = 0', worktree, 30, base)
    assert code == 0, out


def test_a_proof_run_without_a_base_gets_none_rather_than_a_guess():
    from engine import checks
    code, out = checks._run('test -z "${CONSTELLATION_GATE_BASE+x}"', ".", 30, "")
    assert code == 0, out


def test_a_reminted_gate_s_commit_is_the_next_gate_s_base(tmp_path):
    """#231: a reminted gate lands as `issue4.g2-aec88`; the base must see it."""
    import subprocess
    from engine import checks
    def git(*a):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a],
                              cwd=tmp_path, capture_output=True, text=True, check=True).stdout.strip()
    git("init", "-q")
    for trailer in ("issue4.g1", "issue4.g2-aec88"):
        (tmp_path / trailer).write_text("x\n")
        git("add", "-A")
        git("commit", "-q", "-m", f"gate\n\nWork-Id: {trailer}")
    assert checks.gate_base("issue4", tmp_path) == git("rev-parse", "HEAD")


def test_the_previous_issue_s_gate_commit_is_never_this_run_s_base(
        tmp_path, monkeypatch):
    """Issues stacked on one branch: the run's history reaches the last
    issue's gate commits, and with no gate landed yet the base resolved to
    one of them. fe47e5e, story_time's issue52 cut, gave issue51's 40d6146,
    and the first gate's scope diff tripped on the last issue's close."""
    import subprocess
    from engine import checks
    def git(*a):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a],
                              cwd=tmp_path, capture_output=True, text=True, check=True).stdout.strip()
    def commit(name, message):
        (tmp_path / name).write_text("x\n")
        git("add", "-A")
        git("commit", "-q", "-m", message)
    git("init", "-q", "-b", "integration")
    commit("earlier", "gate\n\nWork-Id: issue51.g1-a14a4")
    commit("close", "close issue51, no gate trailer")
    cut = git("rev-parse", "HEAD")
    monkeypatch.setattr(runmod, "state", lambda wid: {"from": f"integration@{cut}"})
    git("checkout", "-q", "-b", "issue52")
    assert checks.gate_base("issue52", tmp_path) == cut
    commit("mine", "gate\n\nWork-Id: issue52.g1")
    assert checks.gate_base("issue52.g2", tmp_path) == git("rev-parse", "HEAD")


def test_a_repo_s_standing_rulings_open_with_every_run(workdir, capsys, monkeypatch):
    """A ruling about the repository outlives any one run's `approach`."""
    from engine import cli as engine_cli
    toml = workdir / "constellation.toml"
    toml.write_text(toml.read_text() + '\n[standing]\napproach = "own tests, then the suite"\n')
    subprocess.run(["git", "add", "-A"], cwd=workdir, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "standing"],
                   cwd=workdir, check=True)
    engine_cli.main(["open", "run-an-issue", "--id", "issue17", "--title", "t", "--issue", "17"])
    capsys.readouterr()
    assert runmod.state("issue17")["prefill"]["approach"] == "own tests, then the suite"
