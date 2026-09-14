"""An accepted gate is one commit on the run's branch (#issue19.g3).

`execute`'s advance outcome used to `release`: the adjudicating step's own
amend was the record and nothing landed in git. Now it `commit`s -- the
engine itself stages and commits the gate's own worktree, on the issue's own
branch, the moment the parent accepts the return. GATE_CLOSE.toml no longer
asks the implementer to commit by hand; the field it asked for is gone.

Every case here reaches a **local bare repository** as `origin`, made fresh
per test by `gitremote.init_checkout` -- this suite runs constantly and must
never reach a live remote.
"""

import pathlib
import subprocess

from engine import cli, forms, journal, run as runmod
from test_nesting import (
    _dispatch_and_close_child, _fill_gate_transition, _mint_first_gate,
)


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)


def _dispatch_and_close_child_with_diff(parent_wid, step_id, filename="src.txt",
                                        content="v1\n"):
    """Like `test_nesting._dispatch_and_close_child`, but the implement round
    also touches a tracked file -- a real diff for the engine's commit to
    land, rather than the ordinary all-in-`.agent-work` case, which is
    gitignored and stages nothing."""
    cli.main(["open", "run-a-gate", "--parent", parent_wid, "--step", step_id])
    child_wid = f"{parent_wid}.{step_id}"
    pathlib.Path(filename).write_text(content)
    from test_nesting import _fill_implement, _dispatch_review, _fill_gate_close
    _fill_implement(child_wid, step_id)
    cli.main([child_wid, "submit"])
    _dispatch_review(child_wid)
    _fill_gate_close(child_wid)
    cli.main([child_wid, "submit"])
    cli.main([child_wid, "close"])
    return child_wid


# -- the engine commits, naming the gate, its purpose, and the work id ------


def test_advance_commits_the_gate_naming_purpose_and_carrying_the_workid_trailer(
        workdir, capsys):
    _mint_first_gate()
    capsys.readouterr()
    worktree = workdir / ".worktrees" / "issue17"
    before = _git(worktree, "rev-parse", "HEAD").stdout.strip()

    _dispatch_and_close_child_with_diff("issue17", "g1")
    capsys.readouterr()

    _fill_gate_transition("issue17")  # plan-holds = "advance"
    cli.main(["issue17", "submit"])
    capsys.readouterr()

    after = _git(worktree, "rev-parse", "HEAD").stdout.strip()
    assert after != before  # a real commit landed

    branch = _git(worktree, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    assert branch == "issue17"  # on the run's own branch, not detached

    message = _git(worktree, "log", "-1", "--format=%B").stdout
    assert message.startswith("g1:")                      # names the gate
    assert "fix the parser" in message                     # ... and its spec purpose
    assert "Work-Id: issue17.g1" in message                 # the work id, as a trailer

    stat = _git(worktree, "show", "--stat", "HEAD").stdout
    assert "src.txt" in stat  # the gate's own diff is what landed


def test_advance_with_nothing_staged_is_a_journaled_no_op_never_a_refusal_or_empty_commit(
        workdir, capsys):
    _mint_first_gate()
    capsys.readouterr()
    worktree = workdir / ".worktrees" / "issue17"
    before = _git(worktree, "rev-parse", "HEAD").stdout.strip()

    # the ordinary case: implement only touches .agent-work, which is
    # gitignored, so there is nothing for the engine to stage
    _dispatch_and_close_child("issue17", "g1")
    capsys.readouterr()

    _fill_gate_transition("issue17")
    cli.main(["issue17", "submit"])  # must not raise
    capsys.readouterr()

    after = _git(worktree, "rev-parse", "HEAD").stdout.strip()
    assert after == before  # no empty commit

    notes = [e for e in journal.read("issue17") if e["kind"] == "note"]
    assert any(n.get("about") == "commit" for n in notes)


# -- the record is excluded by the engine, never by trust in a .gitignore --


def test_no_gitignore_entry_for_agent_work_still_keeps_it_out_of_the_commit(
        workdir, capsys):
    """`init_checkout` writes `.agent-work/` and `.worktrees/` into the
    checkout's own `.gitignore` -- overwritten here with something that
    names neither, the shape a real host repository was found in (#issue20:
    51 files of `.agent-work` landed in a gate's commit because the host's
    own `.gitignore` never covered it). The engine's own pathspec exclusion
    is what has to keep the record out from here, not the ignore file."""
    _mint_first_gate()
    capsys.readouterr()
    worktree = workdir / ".worktrees" / "issue17"
    (worktree / ".gitignore").write_text("*.log\n")

    _dispatch_and_close_child_with_diff("issue17", "g1")
    capsys.readouterr()

    _fill_gate_transition("issue17")
    cli.main(["issue17", "submit"])
    capsys.readouterr()

    stat = _git(worktree, "show", "--stat", "HEAD").stdout
    assert ".agent-work" not in stat
    assert "src.txt" in stat


# -- one commit per gate, not one for the gate and one for its record ------


def test_one_commit_lands_across_a_gates_close_and_its_adjudicate(workdir, capsys):
    """A gate's own close (the child `run-a-gate` closing, returning to the
    parent) and the parent's own adjudicate (`execute`'s `advance`, which
    `commit`s) are the two places a commit could come from. Only the second
    one does -- this counts commits on the branch across both and asserts
    there is exactly one, not the pair a real run once produced (#issue20)."""
    _mint_first_gate()
    capsys.readouterr()
    worktree = workdir / ".worktrees" / "issue17"
    before = _git(worktree, "rev-list", "--count", "HEAD").stdout.strip()

    _dispatch_and_close_child_with_diff("issue17", "g1")  # the gate's own close
    capsys.readouterr()

    _fill_gate_transition("issue17")
    cli.main(["issue17", "submit"])  # the parent's adjudicate
    capsys.readouterr()

    after = _git(worktree, "rev-list", "--count", "HEAD").stdout.strip()
    assert int(after) - int(before) == 1


# -- GATE_CLOSE no longer asks for what the engine now does itself ---------


def test_gate_close_no_longer_carries_a_commit_field():
    """The engine commits the gate itself now, at `execute`'s advance -- the
    implementer is no longer told to commit by hand before closing, and the
    field that recorded a hand-made sha is gone with the instruction."""
    asm = runmod.load_assembly("run-a-gate")
    form = forms.load(runmod.resolve_form(asm, "forms/GATE_CLOSE.toml"))
    ids = [f["id"] for f in form["fields"]]
    assert "commit" not in ids
    assert "residue" in ids  # the rest of the form is untouched


# -- git is declared, not hardcoded: walk every assembly's own outcomes ----


def test_only_executes_advance_outcome_declares_commit_across_every_assembly():
    """`_perform`'s `commit` verb is reachable from any segment's `does`
    string -- what keeps it inside the issue tier's execute segment alone is
    the assemblies' own declarations, not a second list the engine checks
    against. Walking `runmod.assemblies()` here, rather than asserting the
    one file this gate touched, is what catches a future outcome anywhere
    quietly picking up git."""
    hits = []
    for name in runmod.assemblies():
        asm = runmod.load_assembly(name)
        for seg in asm["segment"]:
            specs = [(seg, seg["id"])]
            if seg.get("transition"):
                specs.append((seg["transition"], f"{seg['id']}.transition"))
            for spec, where in specs:
                for outcome in spec.get("outcome", []):
                    if "commit" in outcome.get("does", ""):
                        hits.append((name, where, outcome["value"]))
    assert hits == [("run-an-issue", "execute", "advance")]


# -- the guards: a stamped or missing field is a no-op, never a refusal ----


def test_commit_journals_a_no_op_on_a_non_issue_tier_run_rather_than_touching_git(
        workdir, capsys):
    """`cmd_open` stamps `branch` and `worktree` onto every root run's
    opening entry, including a non-issue-tier one where neither names
    anything real (`branch=wid` unconditionally, `worktree=cwd`). A commit
    verb reached some other way than `execute`'s advance -- an amend, a
    future assembly -- must still never touch git, but the corollary
    (docs/V2_DESIGN.md) rules out a refusal here too: `commit` names no
    field the agent could fill or waive, so the guard lands a journaled
    no-op instead and the run advances."""
    cli.main(["open", "explore-an-idea", "--id", "idea1", "--title", "t"])
    capsys.readouterr()
    asm = runmod.load_assembly("explore-an-idea")
    before = _git(workdir, "rev-parse", "HEAD").stdout.strip()

    cli._commit_gate("idea1", asm, {})  # must not raise

    after = _git(workdir, "rev-parse", "HEAD").stdout.strip()
    assert after == before  # nothing landed in the checkout it opened from

    notes = [e for e in journal.read("idea1") if e["kind"] == "note"]
    assert any(n.get("about") == "commit" for n in notes)


def test_commit_journals_a_no_op_on_an_issue_tier_run_with_no_branch_or_worktree_stamped(
        workdir, capsys):
    """`issue19` is exactly this shape: opened before the worktree feature
    existed, its `run` entry carries neither `branch` nor `worktree`.
    `_issue_tier` is true here -- it is a `run-an-issue` -- so this reaches
    the second guard, not the first, and must land the same journaled
    no-op rather than the refusal `commit: ... fill it, or answer waived:`
    used to print, an escape the agent has no field to take."""
    journal.append("issue18", "run", title="t", assembly="run-an-issue", conductor="")
    asm = runmod.load_assembly("run-an-issue")
    before = _git(workdir, "rev-parse", "HEAD").stdout.strip()

    cli._commit_gate("issue18", asm, {})  # must not raise

    after = _git(workdir, "rev-parse", "HEAD").stdout.strip()
    assert after == before  # nothing landed in the checkout it opened from

    notes = [e for e in journal.read("issue18") if e["kind"] == "note"]
    assert any(n.get("about") == "commit" for n in notes)


# -- a dispatch closed by amend still names the purpose it minted with ----


def test_advance_after_amend_closing_the_dispatch_step_still_names_the_purpose(
        workdir, capsys):
    """A dispatch that never returns -- crashed, or worked around by hand --
    is closed by amend before the parent ever adjudicates it, the same
    route `test_pause_gate.py`'s "amended away in the meantime" case takes.
    Evidence: a real cycle (`/tmp/cycle-evidence/run-772s`) whose three
    `run-a-gate` dispatches for `r1.g1` all crashed on an empty model
    string; the run closed `g1` by hand with `amend close` and finished the
    work itself, then adjudicated `advance` -- and the gate's own commit
    landed with the bare subject `r1.g1:`, its purpose gone. `amend close`
    drops the closed step from `state()["steps"]` entirely (`_apply_amend`),
    and `_commit_gate` used to look for the gate's purpose only there."""
    _mint_first_gate()
    capsys.readouterr()
    worktree = workdir / ".worktrees" / "issue17"

    cli.main(["open", "run-a-gate", "--parent", "issue17", "--step", "g1"])
    pathlib.Path("src.txt").write_text("v1\n")
    cli.main(["issue17", "amend", "close", "g1", "--reason",
             "dispatch failed; work completed by hand"])
    capsys.readouterr()
    assert not any(s["id"] == "g1" for s in runmod.state("issue17")["steps"])

    _fill_gate_transition("issue17")
    cli.main(["issue17", "submit"])
    capsys.readouterr()

    message = _git(worktree, "log", "-1", "--format=%B").stdout
    assert message.startswith("g1:")               # names the gate, not the raw child id
    assert "fix the parser" in message              # ... and its spec purpose survives


# -- the subject is prose stripped for git, not the plan's markdown verbatim


def test_gate_subject_strips_markdown_and_a_redundant_leading_label():
    """A plan's purpose field is written for a human reading the spec and
    sometimes carries both markdown emphasis and its own gate id as a label
    (`**g8. Break the thing.**`) -- neither belongs in a commit subject,
    which already names the gate id itself."""
    assert cli._gate_subject("g8", "**g8. Break the thing.**") == "g8: Break the thing."


def test_gate_subject_reaches_the_real_commit_message(workdir, capsys):
    """End to end: a gate whose plan purpose carries the markdown and label
    `_gate_subject` strips lands a clean subject on the real commit."""
    from test_nesting import (
        _fill_open, _work_the_board, _fill_consolidate, _dispatch_and_close_plan,
        _dispatch_plan_critic, _fill_plan_to_execute, _fill_plan,
    )
    wid = "issue17"
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "parser drops last record"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    _dispatch_and_close_plan(wid, fill_fn=lambda w: _fill_plan(
        w, purpose="**g1. Break the thing.**"))
    _dispatch_plan_critic(wid)
    _fill_plan_to_execute(wid)
    cli.main([wid, "submit"])
    capsys.readouterr()
    worktree = workdir / ".worktrees" / wid

    _dispatch_and_close_child_with_diff(wid, "g1")
    capsys.readouterr()

    _fill_gate_transition(wid)
    cli.main([wid, "submit"])
    capsys.readouterr()

    message = _git(worktree, "log", "-1", "--format=%B").stdout
    assert message.startswith("g1: Break the thing.\n")
