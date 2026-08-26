"""Issue 10 added self-location (a rendered brief a dispatched child can
actually run) and the first two skills (implementer, reviewer). These evals
drive each of the three roles that make a gate move -- an implementer closing
a gate from its orders alone, a reviewer grounding a verdict in a spec it was
just handed, and a conductor dispatching a child and adjudicating what comes
back -- and assert on the journal, never on transcript prose.

Issue 7 added a fourth, on the same implementer: whether the intent layer
gets authored while the code is being written. That one asserts on the
generator's own output rather than the journal, because the journal cannot
tell you what a comment says.

The lightest model is deliberate, same as the rest of this file's neighbor:
if a step needs a strong model to be followed, the instruction is at fault,
not the model.
"""

import json
import os
import pathlib
import shutil
import subprocess
import sys

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


# -- 4. an implementer authoring the intent layer as it works ----------------


@pytest.fixture
def checkout(tmp_path):
    """A workdir the code map can actually measure.

    The mappable corpus is `git ls-files` minus `.agent-work/`
    (tools/code_map/discovery.py), so where the work lands decides whether
    there is anything to read at all: a bare tmp_path is not a checkout and
    the generator refuses, a path under `.agent-work/` is excluded, and an
    untracked file is never listed. Each of those returns zero statements,
    which reads exactly like an implementer that authored nothing -- so this
    fixture makes the workdir a checkout, and `_intent_layer` stages it
    before it measures.

    No skill is copied in. What a dispatch hands an implementer is a path to
    the posture in the installed tree, not a copy in the tree it works in, so
    the bare workdir is the honest starting state -- and it is asserted rather
    than left to be noticed, because a stray `skills/` here would let the
    engine's own delivery go untested without anything failing.
    """
    shutil.copy(harness.ROOT / "constellation.toml", tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True, timeout=60)
    assert not (tmp_path / "skills").exists()
    return tmp_path


def _intent_layer(root):
    """Run the real generator over `root` and return what it read: the
    `ids.jsonl` text an anchor fills, and the tag statements. Both, because
    they are separate predicates -- correct tags extract and render while
    `ids.jsonl` stays empty, so either one alone passes on half a
    performance."""
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, timeout=60)
    subprocess.run([sys.executable, "-m", "tools.code_map", "build",
                    "--root", str(root)], cwd=harness.ROOT,
                   capture_output=True, text=True, timeout=300)
    ids = root / "map" / "ids.jsonl"
    store = root / ".code-map" / "statements.jsonl"
    lines = store.read_text().splitlines() if store.exists() else []
    tags = [json.loads(x) for x in lines if json.loads(x)["p"] == "tag"]
    return (ids.read_text() if ids.exists() else ""), tags


def test_an_implementer_authors_the_intent_layer_as_it_works(checkout):
    """v1 shipped this same reader and read nothing: 3 anchors and 11 tags
    against 4,473 holes in the factory repo, 0 anchors across 440 files
    downstream. The tooling was never the failure -- nobody kept the layer
    authored, and it survives only when it is written at the moment the code
    is. So the assertion is not that the grammar is teachable in the
    abstract: it is that a real light model, given a real gate and nothing
    but what `spine` tells it, leaves behind a map that has something in it.

    Nothing in the prompt mentions anchors, tags or the code map -- and since
    it no longer names the posture either, the engine's own delivery of it is
    now part of what this measures. If either the delivery or the guidance
    does not carry it, this fails, which is the whole point.
    """
    harness.spine(checkout, "open", "run-a-gate", "--id", "g1")
    harness.prefill(
        checkout, "g1",
        purpose="Add rate.py with a function retry_delay(attempt) giving the "
                "seconds to wait before retry attempt N: 1 second for attempt "
                "1, 2 for attempt 2, 4 for attempt 3, and 4 for every attempt "
                "after that. Three doublings and then a ceiling was chosen "
                "over unbounded doubling, which lets a dead host hold a "
                "caller forever.",
        scope="rate.py in the workdir root only",
        done="python3 -c \"import rate; assert [rate.retry_delay(n) for n in "
             "range(1, 6)] == [1, 2, 4, 4, 4]\"")

    r = harness.drive(checkout, (
        "You are an agent working in this directory. Your work id is g1. "
        "Run `spine g1` to see your orders, do the work, then fill "
        "and submit the form it names. Stop once the submit succeeds."),
        timeout=420)

    st = harness.state(checkout, "g1")
    assert "work-1" in st["done"], (
        f"the implement step was never submitted, so there is no work to "
        f"measure.{harness.evidence(checkout, 'g1', r)}")

    ids, tags = _intent_layer(checkout)
    # The corpus here is the one file the gate asked for, so an anchor or a
    # tag found at all was authored by the implementer during this run.
    assert ids.strip(), (
        f"the implementer left no anchor -- map/ids.jsonl is empty, which is "
        f"exactly what it reads on a repo where nobody authors one."
        f"{harness.evidence(checkout, 'g1', r)}")
    assert tags, (
        f"the implementer left no tag -- the anchor names the code but "
        f"nothing says why it is the way it is."
        f"{harness.evidence(checkout, 'g1', r)}")
