"""Reserved rungs: issue166. `SPEC.toml` used to write `map/parents.jsonl`'s
row at spec time, before any code carried the anchor -- dangling it for the
whole run and turning the fast suite red for anyone who followed the
instruction (`test_code_map_parents.py`'s own clean-tree pin). Now the spec
only reserves the anchor id and its parent, as structured data
(`SPEC.toml`'s own `rungs` field); consolidate's `carries` folds it into the
run's prefill; and the engine writes the row itself, mechanically, at the
gate that actually lands the anchor -- `engine/cli.py`'s `_land_reserved_rungs`,
called from `_commit_gate` right after the diff is staged and before the
commit, so the pointer and its target land in one commit.

Both tests drive a real `run-an-issue` through a real `run-a-gate` end to
end -- not the assembly's own field declarations -- the way
`test_gate_commit.py` and `test_nesting.py` already do.
"""

import json
import pathlib
import subprocess

from engine import cli, journal, run as runmod
from test_nesting import (
    _fill, _response, _fill_open, _fill_implement, _dispatch_and_close_child,
    _dispatch_and_close_plan, _dispatch_plan_critic, _fill_plan_to_execute,
    _fill_gate_transition, _dispatch_review, _fill_gate_close,
)

PARENT = "make-mechanical-things-mechanical"  # a real root claim, standards/approach.md


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)


def _work_the_board_reserving(wid, anchor, parents):
    """`test_nesting._work_the_board` plus a `rungs` reservation on the real
    `SPEC.toml` -- the spec-writer's own field, not consolidate's mirror of
    it."""
    board = pathlib.Path(f".agent-work/{wid}/UNDERSTAND.toml")
    board.write_text(board.read_text().replace(
        'status = "open"',
        'status = "answered"\nanswer = "settled."'))
    loc = pathlib.Path(f".agent-work/{wid}")
    (loc / "spec.md").write_text("1. Land the reserved anchor.\n")
    _fill(_response(wid), 'spec = "%s/spec.md"\n\n'
          '[[rungs]]\nanchor = "%s"\nparents = "%s"\n' % (loc, anchor, parents))
    cli.main([wid, "submit"])
    _dispatch_plan_critic(wid)


def _fill_consolidate_reserving(wid, anchor, parents):
    """CONSOLIDATE.toml's own release, transcribing the same reservation
    into its own `rungs` field -- verbatim, the way `obligations` already
    transcribes the spec's obligation list."""
    _fill(_response(wid), (
        'resolution = "pass"\n\n'
        'spec = ".agent-work/%s/spec.md"\n'
        'key-terms = "waived: none"\n'
        'settle = "waived: none"\n\n'
        '[[rungs]]\nanchor = "%s"\nparents = "%s"\n'
    ) % (wid, anchor, parents))


def _open_and_reserve(wid, issue, anchor, parents=PARENT):
    cli.main(["open", "run-an-issue", "--issue", issue, "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board_reserving(wid, anchor, parents)
    _fill_consolidate_reserving(wid, anchor, parents)
    cli.main([wid, "submit"])


def _drive_to_first_gate(wid):
    _dispatch_and_close_plan(wid)
    _dispatch_plan_critic(wid)
    _fill_plan_to_execute(wid)
    cli.main([wid, "submit"])


# -- the reservation reaches the gates: consolidate's carries fold ----------


def test_the_reservation_rides_the_runs_own_prefill_off_a_real_consolidate_release(
        workdir, capsys):
    wid = "issue166"
    _open_and_reserve(wid, "166", "rung-reaches-prefill")
    capsys.readouterr()

    assert runmod.state(wid)["prefill"]["rungs"] == [
        {"anchor": "rung-reaches-prefill", "parents": PARENT}]


# -- driven for real: reservation -> gate lands the anchor -> row appears ---


def test_a_reserved_anchor_that_lands_gets_its_row_in_the_same_commit_as_the_anchor(
        workdir, capsys):
    wid = "issue166"
    _open_and_reserve(wid, "166", "gate-lands-its-own-rung")
    _drive_to_first_gate(wid)
    capsys.readouterr()

    worktree = workdir / ".worktrees" / wid
    parents_path = worktree / "map" / "parents.jsonl"
    before = parents_path.read_text() if parents_path.exists() else ""
    assert "gate-lands-its-own-rung" not in before  # nothing written until the gate lands it

    cli.main(["open", "run-a-gate", "--parent", wid, "--step", "g1"])
    child_wid = f"{wid}.g1"
    pathlib.Path("new_thing.py").write_text(
        "# [gate-lands-its-own-rung]\ndef land_it():\n    pass\n")
    _fill_implement(child_wid, "g1")
    cli.main([child_wid, "submit"])
    _dispatch_review(child_wid)
    _fill_gate_close(child_wid)
    cli.main([child_wid, "submit"])
    cli.main([child_wid, "close"])
    capsys.readouterr()

    _fill_gate_transition(wid)
    cli.main([wid, "submit"])
    capsys.readouterr()

    rows = [json.loads(line) for line in parents_path.read_text().splitlines() if line.strip()]
    row = next(r for r in rows if r["id"] == "gate-lands-its-own-rung")
    assert row["parents"] == [PARENT]

    # same commit as the anchor, not a separate one
    stat = _git(worktree, "show", "--stat", "HEAD").stdout
    assert "new_thing.py" in stat
    assert "map/parents.jsonl" in stat


def test_landing_the_anchor_a_second_time_leaves_the_existing_row_alone(workdir, capsys):
    """`_land_reserved_rungs` skips an anchor that already has a row -- a
    second gate that also carries the same reservation (e.g. a rework)
    never overwrites what a prior gate authored, and never refuses either."""
    wid = "issue166"
    _open_and_reserve(wid, "166", "gate-lands-its-own-rung")
    _drive_to_first_gate(wid)
    capsys.readouterr()

    worktree = workdir / ".worktrees" / wid
    parents_path = worktree / "map" / "parents.jsonl"

    cli.main(["open", "run-a-gate", "--parent", wid, "--step", "g1"])
    child_wid = f"{wid}.g1"
    pathlib.Path("new_thing.py").write_text(
        "# [gate-lands-its-own-rung]\ndef land_it():\n    pass\n")
    _fill_implement(child_wid, "g1")
    cli.main([child_wid, "submit"])
    _dispatch_review(child_wid)
    _fill_gate_close(child_wid)
    cli.main([child_wid, "submit"])
    cli.main([child_wid, "close"])
    _fill_gate_transition(wid)
    cli.main([wid, "submit"])
    capsys.readouterr()

    first = parents_path.read_text()
    assert first.count("gate-lands-its-own-rung") == 1

    # a second, unrelated file also carrying the same anchor text lands
    # later in the tree (e.g. a stray comment) -- the engine must not
    # duplicate or touch the row that is already there
    cli._land_reserved_rungs(wid, worktree)
    assert parents_path.read_text() == first


# -- the honest negative: an unlanded reservation writes nothing, refuses nothing --


def test_a_reservation_whose_anchor_never_lands_writes_no_row_and_nothing_refuses(
        workdir, capsys):
    wid = "issue167"
    _open_and_reserve(wid, "167", "never-lands")
    _drive_to_first_gate(wid)
    capsys.readouterr()

    worktree = workdir / ".worktrees" / wid

    # the ordinary case: the implementer's diff never touches tracked files
    # at all (everything it wrote stayed in .agent-work, gitignored), so the
    # reserved anchor never actually lands in the tree
    _dispatch_and_close_child(wid, "g1")
    capsys.readouterr()

    _fill_gate_transition(wid)
    cli.main([wid, "submit"])  # must not raise -- nothing refuses on an unlanded reservation
    capsys.readouterr()

    parents_path = worktree / "map" / "parents.jsonl"
    text = parents_path.read_text() if parents_path.exists() else ""
    assert "never-lands" not in text
    assert runmod.state(wid)["current"]["form"] == "forms/CLOSE.toml"


def test_a_reservation_whose_anchor_lands_in_a_different_gate_than_the_first_still_writes_nothing_early(
        workdir, capsys):
    """The reservation rides every later gate's prefill (it is on the run's
    own prefill, not the dispatch step's), so a gate that does not land the
    anchor still carries it and still writes nothing -- only the gate that
    actually lands the marker in a tracked file ever produces the row."""
    wid = "issue168"
    _open_and_reserve(wid, "168", "lands-on-gate-two")
    _drive_to_first_gate(wid)
    capsys.readouterr()

    worktree = workdir / ".worktrees" / wid
    parents_path = worktree / "map" / "parents.jsonl"

    # gate 1 never touches the anchor
    _dispatch_and_close_child(wid, "g1")
    _fill_gate_transition(wid)
    cli.main([wid, "submit"])
    capsys.readouterr()

    text = parents_path.read_text() if parents_path.exists() else ""
    assert "lands-on-gate-two" not in text
    assert runmod.state(wid)["current"]["form"] == "forms/CLOSE.toml"


# -- the field itself: structured data, not prose, and optional -------------


def test_spec_and_consolidate_both_declare_an_optional_rungs_field_with_anchor_and_parents():
    from engine import forms
    asm = runmod.load_assembly("run-an-issue")
    for ref in ("skills/spec-writer/forms/SPEC.toml", "forms/CONSOLIDATE.toml"):
        form = forms.load(runmod.resolve_form(asm, ref))
        field = next(f for f in form["fields"] if f["id"] == "rungs")
        assert field["kind"] == "plan"
        assert field["optional"] is True
        item_ids = {it["id"] for it in field["item"]}
        assert item_ids == {"anchor", "parents"}


def test_consolidates_carries_now_names_rungs_so_it_reaches_later_dispatches():
    asm = runmod.load_assembly("run-an-issue")
    understand = next(s for s in asm["segment"] if s["id"] == "understand")
    assert understand["transition"]["carries"] == [
        "spec", "key-terms", "settle", "obligations", "rungs"]
