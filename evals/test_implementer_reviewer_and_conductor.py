"""Issue 10 added self-location (a rendered brief a dispatched child can
actually run) and the first two skills (implementer, reviewer). These evals
drive each of the three roles that make a gate move -- an implementer closing
a gate from its orders alone, a reviewer grounding a verdict in a spec it was
just handed, and a conductor dispatching a child and adjudicating what comes
back -- and assert on the journal, never on transcript prose.

The lightest model is deliberate, same as the rest of this file's neighbor:
if a step needs a strong model to be followed, the instruction is at fault,
not the model.
"""

import os
import pathlib
import shutil

import pytest

from evals import harness

pytestmark = pytest.mark.agent


@pytest.fixture
def workdir(tmp_path):
    shutil.copy(harness.ROOT / "constellation.toml", tmp_path)
    return tmp_path


def _mint_gate_pair(workdir, wid, gid, purpose, scope, done, model=""):
    """A run-an-issue standing on exactly one execute-segment dispatch step
    and its adjudication companion -- the shape `_mint_gates` (engine/cli.py)
    produces from a real plan-to-execute round, built directly so this eval
    does not have to drive a whole understand/plan cycle just to reach a
    dispatch. Mirrors tests/test_brief.py's `_mint_dispatch_step`, plus the
    adjudicate companion a real gates-field mint always pairs it with."""
    cwd = os.getcwd()
    try:
        os.chdir(workdir)
        from engine import journal
        journal.append(wid, "run", title=purpose, assembly="run-an-issue",
                       conductor="commander")
        prefill = {"purpose": purpose, "scope": scope, "done": done}
        if model:
            prefill["model"] = model
        child = f"{wid}.{gid}"
        journal.append(wid, "step", id=gid, segment="execute", dispatches="run-a-gate",
                       prefill=prefill, child=child, anchor=False, terminal=False,
                       source="mint")
        journal.append(wid, "step", id=f"{gid}-adjudicate", segment="execute",
                       form="forms/GATE_TRANSITION.toml", filler="conductor", child=child,
                       anchor=False, terminal=False, validates="", source="mint")
    finally:
        os.chdir(cwd)


# -- 1. an implementer completing a gate from its orders alone ---------------


def test_an_implementer_completes_a_gate_from_its_orders_alone(workdir):
    """The implementer skill says "you conduct this gate -- nobody else
    pumps it between open and close": submit, dispatch the review panel the
    room names, act on its verdict, close. No engine or skill knowledge in
    the prompt -- only the work id and the outcome to reach."""
    harness.spine(workdir, "open", "run-a-gate", "--id", "g1")
    harness.prefill(workdir, "g1",
                    purpose="Create a file named result.txt containing exactly the text OK.",
                    scope="the workdir root only",
                    done="test -f result.txt && grep -qx OK result.txt")

    r = harness.drive(workdir, (
        "You are an agent working in this directory. Your work id is g1. "
        "Run `spine g1` to see your orders, and carry this gate all the way "
        "through: do the work, submit, and follow whatever the room tells "
        "you to do next -- all the way to close. Stop once `spine g1` shows "
        "the run closed."), timeout=300)

    st = harness.state(workdir, "g1")
    assert st["closed"], (
        f"the gate never closed on its own orders.{harness.evidence(workdir, 'g1', r)}")
    assert {"work-1", "review", "close"} <= st["done"].keys(), (
        f"a step along the way was skipped: {sorted(st['done'])}"
        f"{harness.evidence(workdir, 'g1', r)}")
    # root-verified: the engine's own check ran the real command and passed
    done_checks = [c for c in st["checks"] if "result.txt" in (c.get("command") or "")]
    # The check that let the gate close must have passed. An earlier failure
    # is the engine refusing and the agent recovering -- the loop working,
    # not a defect. Demanding none ever failed would fail a correct run.
    assert done_checks and done_checks[-1]["exit"] == 0, (
        f"the gate closed without its done check passing: {done_checks}")
    assert (pathlib.Path(workdir) / "result.txt").read_text().strip() == "OK"


# -- 2. a reviewer returning a grounded verdict -------------------------------


def test_a_reviewer_returns_a_grounded_verdict(workdir):
    """The artifact under review openly admits it did not do what the spec
    asked -- no validation was added, only a rename -- so the one grounded
    verdict is `revise`. A reviewer that passes it anyway has not grounded
    the verdict in the spec at all."""
    harness.spine(workdir, "open", "run-a-gate", "--id", "g2")
    harness.prefill(workdir, "g2",
                    purpose="Add input validation to `parse_line` so it rejects empty "
                            "strings.",
                    scope="src/parser.py only", done="true")
    (pathlib.Path(workdir) / ".agent-work/g2/IMPLEMENT.toml").write_text(
        'change = "Renamed parse_line to parseLine for style consistency. No '
        'validation logic was added."\n'
        'deviations = "waived: none"\n')
    harness.spine(workdir, "g2", "submit")  # done check "true" fires the review anchor
    harness.spine(workdir, "open", "give-a-verdict", "--parent", "g2", "--step", "review.p1")

    r = harness.drive(workdir, (
        "You are an agent working in this directory. Your work id is "
        "g2.review.p1. Run `spine g2.review.p1` to see your orders and "
        "criteria. Do exactly what it tells you, all the way through to "
        "close."), timeout=180)

    child = harness.state(workdir, "g2.review.p1")
    assert child["closed"], (
        f"the verdict never closed -- it did not return."
        f"{harness.evidence(workdir, 'g2', r)}")
    fields = child["done"].get("verdict", {}).get("fields", {})
    assert fields.get("verdict", "").strip().lower().startswith("revise"), (
        f"an ungrounded verdict on work that admits it skipped the spec: {fields}")

    # the verdict actually returned to the gate that dispatched it
    parent = harness.state(workdir, "g2")
    assert "review" in parent["done"], "the verdict never landed back on the gate"
    ret = parent["returns"]["review"][0]
    assert ret["fields"].get("verdict", "").strip().lower().startswith("revise")


# -- 3. a conductor dispatching a child and adjudicating its return ----------


def test_a_conductor_dispatches_a_child_and_adjudicates_its_return(workdir):
    """The prompt is exactly what `spine d1` prints for a dispatch step --
    the brief a real conductor hands its harness, not prose describing one.
    The agent must open the child it names, carry it to its own close, and
    then adjudicate the return using nothing but what the room says next."""
    wid = "d1"
    _mint_gate_pair(workdir, wid, "g1",
                    purpose="Create a file named done.txt containing exactly the text ok.",
                    scope="the workdir root only",
                    done="test -f done.txt && grep -qx ok done.txt")

    brief = harness.spine(workdir, wid).stdout

    r = harness.drive(workdir, (
        f"You are an agent working in this directory. Your work id is {wid}. "
        f"Below is exactly what `spine {wid}` just printed:\n\n{brief}\n\n"
        "Follow it: open the child it names, carry that child all the way "
        "through to its own close, and once it has returned here, "
        "adjudicate it -- fill and submit whatever this run then asks for. "
        "Use only what each command's output tells you along the way."),
        timeout=480)

    st = harness.state(workdir, wid)
    assert st["done"].get("g1", {}).get("kind") == "return", (
        f"the dispatch step never completed -- the child did not return."
        f"{harness.evidence(workdir, wid, r)}")
    assert "g1-adjudicate" in st["done"], (
        f"the child returned but was never adjudicated."
        f"{harness.evidence(workdir, wid, r)}")
    fields = st["done"]["g1-adjudicate"]["fields"]
    assert fields.get("plan-holds", "").strip().lower().startswith("advance"), (
        f"adjudication did not land on a real decision: {fields}")

    child_st = harness.state(workdir, "d1.g1")
    assert child_st["closed"], "the dispatched gate itself never closed"
    assert (pathlib.Path(workdir) / "done.txt").read_text().strip() == "ok"
