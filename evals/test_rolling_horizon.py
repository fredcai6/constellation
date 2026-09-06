"""End to end through the new understand -> plan -> execute cycle, on a real
light model. Everything else in this repo can go green on a tree where the
new cycle is unreachable, because nothing renders the command that reaches
it -- that was #43's own lesson, measured on `test_an_excursion_gets_
dispatched_from_a_board_row.py`, and it is why this file drives the real CLI
instead of asserting on the assembly's TOML.

This pins DESIRED behaviour, not current: the whole new cycle -- a spec
crystallized and passed by a cold critic panel, a one-gate plan cut by
round one's three siblings and passed by a second panel, the gate itself
dispatched from a projection of that plan, its adjudication disposing the
spec's own obligations, and the engine settling the run closed because
every obligation now carries a disposition -- is the thing this wave
built. Before it, none of this existed to drive.

No subagent dispatch is available to the single driven session either, the
same constraint a conductor without one is under: every panelist and every
dispatched child is opened and carried to its own close by the one agent,
in the same session, exactly the way the room's own brief tells any
conductor without a subagent to. That is not a shortcut around the design;
it is the fallback path the design itself names.

The lightest model is deliberate, same as this file's neighbours: if
reaching close needs a strong model, a step's brief is at fault, not the
model. A single drive plays every role because that is what one agent
working this room alone actually does -- a conductor with subagents would
fan them out, but the room is exactly as sufficient either way.

Sizing the drive: a smaller slice of this same cycle (board through the
spec's own cold panel) has measured 96s, 289s and 348s in this repo, on the
excursion eval's own drive. This test walks the whole cycle -- that same
segment, plus a design-it-twice round and its own second panel, plus the
gate itself and its review, plus adjudication and close -- so 300s is not
the number to reuse: two hand runs of this exact test, both driving
correctly the whole way (three planner siblings, a real revise round on a
genuine finding, three more critics), still had not reached the gate's own
review by 300s. The drive budget below is sized from that measurement, not
the smaller one; it is why the assertions below -- mirroring the excursion
eval's own -- separate "cut off before the run ever closed, so this
measured nothing conclusive" from a real finding. A drive that is merely
slow is retried; a drive that finished on its own and still did not close,
or closed with an obligation left open, is not.
"""

import os
import pathlib
import shutil
import subprocess

import pytest

from engine import boards
from evals import harness

# [fake-gh]
# Rationale: a root run's own `close` pushes a branch and opens a PR
# (`cmd_close`, engine/cli.py) -- the fast suite intercepts `gh` in-process
# (`tests/gitremote.py`'s `stub_gh`, monkeypatching `subprocess.run`), but
# that seam does not cross into a driven `claude` subprocess: the model
# shells out to a real `gh` binary in a real child process, which
# monkeypatch never touches. This eval needs its own interception, on
# PATH, ahead of whatever real `gh` the host has -- never acceptable to
# reach even once, the same ruling `stub_gh` states for the fast suite.
# Rejected: skipping the close step and asserting one short of it. Closing
# on the obligation board is the very claim this eval exists to check; an
# assertion that stops short of `closed` would pass on a run that never
# actually got there.
_FAKE_GH = """#!/bin/sh
if [ "$1" = "pr" ] && [ "$2" = "create" ]; then
  echo "https://example.invalid/pr/1"
  exit 0
fi
exit 0
"""


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    shutil.copy(harness.ROOT / "constellation.toml", tmp_path)
    harness.init_checkout(tmp_path)
    fakebin = tmp_path.parent / f"{tmp_path.name}-fakebin"
    fakebin.mkdir()
    gh = fakebin / "gh"
    gh.write_text(_FAKE_GH)
    gh.chmod(0o755)
    # `harness.drive` builds its own subprocess env from `os.environ` at call
    # time, so patching the process's own PATH here is what a PATH entry
    # `drive` never adds a hook for actually requires.
    monkeypatch.setenv("PATH", f"{fakebin}:{os.environ.get('PATH', '')}")
    return tmp_path


def seed_open(workdir, wid):
    """Fill the minted OPEN.toml directly -- a small, single-obligation ask
    whose one seed question already carries its own answer, so the board
    resolves in one edit and the run has a real, but tiny, spec to cut a
    one-gate plan from. Small on purpose: this eval measures whether the
    cycle turns, not whether a light model can plan a large change."""
    p = harness.response_path(workdir, wid)
    p.write_text('''issue = "issue-rolling-horizon"

authority = """
No live principal is in reach for this run -- there is nobody to ask, and
asking as if there were would fabricate their words. Every seeded row is a
fact you resolve yourself, with evidence. You own the understanding.
"""

[[questions]]
question = "What should calc.py's add(a, b) function return? (It should return the arithmetic sum of a and b -- nothing else is asked of this run.)"
excursion = "declined: read -- the seed question already states its own answer; nothing off-repo is needed"
type = "fact"
''')


# [archive-aware-reads]
# Rationale: a *closed* root run is the success case this eval exists to
#   reach, and `cmd_close` (engine/cli.py) moves the whole work location to
#   `.agent-work/archive/<wid>/` in the top-level checkout and removes the
#   worktree in the same call, the moment `close` actually succeeds --
#   `tests/gitremote.py`'s own `read_archived` helper says outright that
#   `journal.root_for` cannot see an archived id afterward, because it is
#   simply not at either place that function looks. A first draft of this
#   eval read through `harness.state` and `harness.run_root` unconditionally
#   and would have raised on `None.get("closed")` the one time the drive
#   actually reached the finish line -- caught only by hand-driving the
#   real #63 proof run through the same `close`, never by the fast suite.
#   Every read below checks the archive first for exactly that reason.
# Rejected: asserting one step short of `closed` (e.g. "awaiting close") to
#   dodge the archive. That is the same shortcut `_FAKE_GH`'s own docstring
#   already rejected -- closing on the obligation board is the claim.
def work_location(workdir, wid):
    """Where `wid`'s own files actually are right now."""
    archived = pathlib.Path(workdir) / ".agent-work" / "archive" / wid
    return archived if archived.exists() else harness.run_root(workdir) / ".agent-work" / wid


def run_closed(workdir, wid):
    """True once `close` has archived this run -- the one signal that
    survives the sweep."""
    return (pathlib.Path(workdir) / ".agent-work" / "archive" / wid).exists()


def gate_children(workdir, wid):
    """Every gate this run itself dispatched (`run-a-gate` children, never a
    give-a-verdict panelist), read from the journal the same way `_mint_gates`
    stamps them -- so this counts gates that actually ran, not steps that
    merely named one."""
    base = work_location(workdir, wid)
    return sorted(p.parent.name for p in base.glob("g*/journal.toml"))


def execution_state(workdir, wid):
    path = work_location(workdir, wid) / "EXECUTION_STATE.toml"
    return boards.rows(path) if path.exists() else None


def test_the_cycle_turns_end_to_end_on_a_real_issue(workdir):
    """Open a run, seed one small ask, and drive a single light model
    through the whole thing by hand -- board, spec, its cold panel, the
    plan segment's own design-it-twice round and its panel, the one gate
    that plan projects, its adjudication, and the settle that follows.

    What is asserted, and why each is the actual claim and not a proxy for
    it:

    - a gate really ran (a `run-a-gate` child under this run, closed, with
      its own commit) -- the projection from plan to execute is a real
      dispatch, never a string typed into a form;
    - the execution-state board carries no row still `open` -- every
      obligation the spec made is disposed, not merely that the run
      stopped;
    - the run itself is `closed` -- and per ASSEMBLY.toml's own `execute`
      segment, `advance`'s only route to the terminal step is
      `commit; settle`, and `settle` only ever mints nothing (letting the
      run walk on to CLOSE.toml) when every obligation is disposed. A
      run seeded with obligations has no other path to closed, so closed
      plus a fully-disposed board is the causal claim, not a coincidence
      alongside it.
    """
    harness.spine(workdir, "open", "run-an-issue", "--id", "r1")
    seed_open(workdir, "r1")

    r = harness.drive(workdir, (
        "You are an agent working in this directory. Your work id is r1. "
        "Run `spine r1` to see where you are, and carry this run all the "
        "way through -- the understand board, the specification and its "
        "review panel, the plan segment and its own panel, the one gate "
        "the plan projects, that gate's own work and review, and the "
        "adjudication that follows it -- until `spine r1` itself reports "
        "the run closed. At every step read exactly what the room prints "
        "and do what it names: fill the response form it points at, then "
        "run the command it gives you to submit or close. Where it names "
        "a child run or a panelist, open it yourself with the exact "
        "command shown, carry that child all the way to its own close in "
        "this same session, and only then continue here -- you have no "
        "subagent to hand any of this to. Nobody will answer a question "
        "partway through, so resolve anything within your own reach "
        "yourself and record why, rather than stopping to ask. There is "
        "nothing wrong with the work at any point in this run -- a clean "
        "pass is the honest verdict wherever one is asked for. Do not "
        "stop until `spine r1` reports the run closed."),
        timeout=480)

    closed = run_closed(workdir, "r1")
    gates = gate_children(workdir, "r1")
    rows = execution_state(workdir, "r1")

    detail = (f"\n-- gates dispatched -- {gates}"
              f"\n-- execution-state board -- {rows}"
              f"\n-- run closed (archived): {closed}")

    # Rationale: mirrors the excursion eval's own split, but on `closed`
    #   rather than on whether a gate was ever minted -- measured directly:
    #   a real drive of this same prompt and tier reached g1's own review
    #   panelist (spec, its cold panel, the plan segment's own three-sibling
    #   round and its own second panel, the gate dispatched and its
    #   implement step submitted) and was still short of `closed` at the
    #   budget below.
    #   A run that has not reached `closed` yet says nothing about whether
    #   the cycle is sound -- everything observed up to the cut was correct
    #   -- so cut-off-and-not-closed is retried rather than failed; only a
    #   drive that finished on its own (or one that did close) is graded.
    # Rejected: gating retry on "no gate ever ran" instead. That measured
    #   nothing on the run above: a gate had already been dispatched,
    #   implemented and sent to review, and the assertions below would have
    #   failed on r1.g1 not being closed -- a true statement about the
    #   clock, reported as if it were a finding about the cycle.
    if not closed and harness.unfinished(r):
        stopped = harness.unfinished(r)
        pytest.fail(
            f"this eval measured nothing conclusive: {stopped}, and the run "
            f"had not reached closed yet. Rerun it.{detail}"
            f"{harness.evidence(workdir, 'r1', r)}")

    assert gates, (
        f"the plan segment never projected a gate -- the cycle did not "
        f"reach execute.{detail}{harness.evidence(workdir, 'r1', r)}")

    # Every gate in `gates` is guaranteed already closed the moment `closed`
    # is true: a dispatch step only completes once its child returns, and a
    # child returns only by closing (ASSEMBLY.toml's execute segment, and
    # `run`/`return` in the journal) -- so there is nothing left to check
    # gate by gate that `closed` below does not already cover.
    assert closed, (
        f"the drive finished on its own, short of the run closing -- a gate "
        f"ran, but the cycle did not reach its terminal step.{detail}"
        f"{harness.evidence(workdir, 'r1', r)}")

    assert rows, (
        f"the run closed with no execution-state board at all -- the "
        f"spec's obligations were never seeded onto it.{detail}")
    still_open = [row.get("id") for row in rows
                  if str(row.get("status", "open")).strip() == "open"]
    assert not still_open, (
        f"the run closed while an obligation was still open: {still_open} "
        f"-- closed happened some other way than every obligation being "
        f"disposed, which ASSEMBLY.toml's execute segment does not offer."
        f"{detail}")

    # A gate that actually did the work, not merely closed clean: the
    # engine's own commit, made on `advance` (ASSEMBLY.toml's execute
    # segment), is root evidence the diff landed -- the initial commit
    # from `init_checkout` plus at least one per gate. Read off the run's
    # own branch (named `r1`, same as the work id, per `_open_root_worktree`)
    # rather than `workdir`'s currently checked-out branch: `closed` is
    # already asserted true above, which means the worktree is gone and
    # `workdir` itself is back on whatever branch it started on, never `r1`.
    log = subprocess.run(["git", "log", "--oneline", "r1"], cwd=workdir,
                         capture_output=True, text=True, timeout=60)
    commits = [l for l in log.stdout.splitlines() if l.strip()]
    assert len(commits) > 1, (
        f"the run closed but no gate ever committed: {commits}"
        f"\n-- git log r1 stderr -- {log.stderr}{detail}")
