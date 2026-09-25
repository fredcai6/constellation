"""#122: the engine runs a plan's `proof` once, where it is written.

Three critics passed issue116's plan; none ran its `proof`, which was prose
naming a palette entry, and the gate had built its whole diff before the
first submit died on an apostrophe. Now the planner's own submit runs each
`kind = "proof"` field once, through the same resolution the gate's check
will use (`_resolve_command`, the palette, the shell), against the run's
tree as it stands, bounded by the smaller of the gate's `budget` and the
handback -- and journals a `check` entry the conductor's route room renders
as a reading. Nothing is refused: a secretary reports, the conductor rules.

Three readings matter. A real check fails on an empty diff, so a nonzero
exit the command itself produced is the healthy one. Exit 0 is the reading
PLAN.toml's own note already names -- a proof that passes on an empty diff
proves nothing. And a string that never became a command -- the shell could
not parse it, could not find it, or the palette has no such entry -- is
#122's defect, read where the cut can still be sent back.

#163: the trial used to run in the caller's own foreground, killed at
`min(budget, HANDBACK)` -- so a proof that was right but slow (this repo's
own fast suite, 168s against a 90s handback) never got a real reading, only
a fourth, useless one: "no result after 90s". Now it starts detached at the
cut (`checkrun.hand_in_trial`) and the caller waits no longer than the
handback; a proof that lands within it journals its reading exactly as
before, and one that does not keeps running, its check-started already
left behind for the route form to find once it does.
"""

import time

from engine import checks, cli, journal, render, run as runmod

from test_nesting import (
    _dispatch_plan_critic,
    _fill,
    _fill_consolidate,
    _fill_open,
    _response,
    _work_the_board,
    _write_plan_artifact,
)


def _to_the_first_cut(wid="issue17"):
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    cli.main(["open", "cut-a-gate", "--parent", wid, "--step", "plan-1"])
    return f"{wid}.plan-1"


def _cut(child, proof, budget=""):
    loc = journal.location(child)
    _write_plan_artifact(loc / "plan.md")
    _fill(_response(child), '''
plan = "%s/plan.md"
purpose = "fix the parser"
scope = "src/parser.c only"
proof = """%s"""
%shorizon = "waived: none yet"
key-terms = "waived: none"
''' % (loc, proof, f'budget = "{budget}"\n' if budget else ""))


def _checks(wid):
    return [e for e in journal.read(wid) if e.get("kind") == "check"]


def _route_room(wid, capsys):
    """The conductor's PLAN_TO_EXECUTE room, once the opening cut's panel has
    returned and the form is what stands there."""
    _dispatch_plan_critic(wid)
    capsys.readouterr()
    cli.main([wid])
    return capsys.readouterr().out


# -- the trial itself ---------------------------------------------------------


def test_the_planners_submit_runs_the_proof_once_and_journals_a_check(workdir, capsys):
    child = _to_the_first_cut()
    _cut(child, "exit 3")
    capsys.readouterr()

    cli.main([child, "submit"])
    out = capsys.readouterr().out

    ran = _checks(child)
    assert len(ran) == 1
    assert ran[0]["step"] == "cut" and ran[0]["field"] == "proof"
    assert ran[0]["command"] == "exit 3" and ran[0]["exit"] == 3
    assert "resolved, exit 3" in out            # the planner is told too
    assert "cut" in runmod.state(child)["done"]  # and nothing was refused


def test_a_palette_proof_resolves_through_the_palette_like_the_gates_own_check(workdir, capsys):
    child = _to_the_first_cut()
    _cut(child, "palette:test --version")
    capsys.readouterr()

    cli.main([child, "submit"])

    [ran] = _checks(child)
    assert ran["command"].startswith("python3 -m pytest -q --version")
    assert ran["exit"] == 0


def test_a_waived_proof_is_not_run(workdir, capsys):
    child = _to_the_first_cut()
    _cut(child, "waived: nothing here is testable yet")
    cli.main([child, "submit"])
    assert _checks(child) == []


# -- the three readings, in the room the conductor routes from ---------------


def test_a_real_check_that_fails_before_the_work_reads_as_resolved(workdir, capsys):
    child = _to_the_first_cut()
    _cut(child, "exit 1")
    cli.main([child, "submit"])
    cli.main([child, "close"])

    out = _route_room("issue17", capsys)
    assert "the proof, run once at the cut" in out
    assert "`exit 1`" in out
    assert "resolved, exit 1" in out
    assert "returns from issue17.plan-1" in out   # the cut itself is in the room
    assert "fix the parser" in out


def test_a_proof_that_passes_on_an_empty_diff_reads_as_proving_nothing(workdir, capsys):
    child = _to_the_first_cut()
    _cut(child, "true")
    cli.main([child, "submit"])
    cli.main([child, "close"])

    out = _route_room("issue17", capsys)
    assert "passes with no work in the tree (exit 0)" in out
    assert "proves nothing" in out


def test_a_proof_that_passes_on_a_tree_carrying_work_reads_as_its_measure(workdir, capsys):
    """#181: a proof field is trialled wherever a form carries one -- at a
    gate's adjudication, at a rework cut -- and there the tree already holds
    work. The reading says what the trial measured, and "proves nothing"
    belongs to a tree with no work in it."""
    child = _to_the_first_cut()
    (journal.root_for(child) / "landed.txt").write_text("work\n")
    _cut(child, "true")
    cli.main([child, "submit"])
    cli.main([child, "close"])

    out = _route_room("issue17", capsys)
    assert "passes (exit 0) against 1 path changed since the cut" in out
    assert "no work in the tree" not in out


def test_a_prose_proof_reads_as_not_resolving(workdir, capsys):
    """issue116's own string: a description naming the palette entry, which
    `/bin/sh` reads as an unterminated quote."""
    child = _to_the_first_cut()
    _cut(child, "constellation.toml's `test` entry: python3 -m pytest -q")
    cli.main([child, "submit"])
    cli.main([child, "close"])

    [ran] = _checks(child)
    assert ran["exit"] == 2 and "Syntax error" in ran["output"]
    out = _route_room("issue17", capsys)
    assert "did not resolve (exit 2)" in out
    assert "Syntax error" in out


def test_a_palette_name_with_no_entry_reads_as_not_resolving(workdir, capsys):
    child = _to_the_first_cut()
    _cut(child, "palette:nonesuch")
    capsys.readouterr()
    cli.main([child, "submit"])                 # reported, never refused
    cli.main([child, "close"])

    [ran] = _checks(child)
    assert ran["exit"] == 127
    assert "no entry named 'nonesuch'" in ran["output"]
    out = _route_room("issue17", capsys)
    assert "did not resolve (exit 127)" in out
    assert "nonesuch" in out


def test_a_command_the_shell_cannot_find_reads_as_not_resolving(workdir, capsys):
    child = _to_the_first_cut()
    _cut(child, "no-such-command-anywhere --flag")
    cli.main([child, "submit"])
    [ran] = _checks(child)
    assert ran["exit"] == 127
    assert render.proof_readings([ran])[0].startswith("`no-such-command-anywhere --flag`\n"
                                                    "did not resolve (exit 127)")


# -- the bound ----------------------------------------------------------------


def test_a_proof_past_its_budget_is_reported_not_awaited(workdir, capsys, monkeypatch):
    """The planner's `budget` is the bound, capped at the handback so a slow
    proof never strands the planner's turn (#72); what is journaled is the
    same shape the gate's own runner writes for an overrun."""
    monkeypatch.setattr(checks, "HANDBACK", 30)
    child = _to_the_first_cut()
    _cut(child, "sleep 20", budget="1")
    capsys.readouterr()

    began = time.time()
    cli.main([child, "submit"])
    held = time.time() - began
    assert held < 10, f"held the caller for {held:.1f}s"

    [ran] = _checks(child)
    assert ran["exit"] == -1 and ran["output"] == "no result after 1s"
    cli.main([child, "close"])
    out = _route_room("issue17", capsys)
    assert "did not finish -- no result after 1s; not awaited at the cut" in out


def test_a_proof_that_printed_before_it_was_killed_is_reported_not_raised(workdir):
    """The overrun path's whole job is to hand back what the proof printed.
    `TimeoutExpired` carries those streams as raw `bytes` -- `text=True`
    decodes what `run` returns, not what the exception holds -- so the tail
    has to be decoded here or reporting the overrun raises instead.

    Pinned separately from the `sleep`-only overrun tests on purpose: a proof
    that prints nothing hands back empty `bytes`, which are falsy, so those
    tests pass whether or not this decode exists."""
    code, output = checks._run("echo carried; sleep 5", ".", 1)
    assert code is None                      # it did outrun the budget
    assert output == "carried\n"             # ... and said what it managed to say

    silent, nothing = checks._run("sleep 5", ".", 1)
    assert (silent, nothing) == (None, "")   # a proof that printed nothing still reports


def test_a_proof_that_outlives_the_handback_does_not_block_the_submit(
        workdir, capsys, monkeypatch):
    """#163: this repo's own fast suite takes 168s against a 90s handback,
    and every one of its `[commands]` entries includes it -- so a proof
    that is right but slow must not be killed and misread as a fourth
    reading. The trial starts detached at the cut (`checkrun.hand_in_trial`)
    -- the submit returns inside the handback, refusing nothing and
    blocking on nothing -- and the real reading is not lost: it lands once
    the detached trial actually finishes, and reaches the conductor's route
    form from there, not from the planner's own submit."""
    monkeypatch.setattr(checks, "HANDBACK", 1)
    child = _to_the_first_cut()
    _cut(child, "sleep 2 && exit 5", budget="600")
    capsys.readouterr()

    began = time.time()
    cli.main([child, "submit"])                     # never blocks past the handback
    held = time.time() - began
    assert held < 10, f"held the caller for {held:.1f}s"
    assert _checks(child) == []                      # nothing landed yet -- still running
    assert "cut" in runmod.state(child)["done"]       # the submit itself was not held for it

    cli.main([child, "close"])
    out = _route_room("issue17", capsys)
    assert "has not finished yet" in out
    assert f"spine {child} wait" in out

    deadline = time.time() + 10
    while not _checks(child) and time.time() < deadline:
        time.sleep(0.2)
    [ran] = _checks(child)                            # the real reading, not lost
    assert ran["exit"] == 5

    capsys.readouterr()
    cli.main(["issue17"])
    out = capsys.readouterr().out
    assert "resolved, exit 5" in out                  # ... and it reaches the route form
    assert "has not finished yet" not in out


def test_a_proof_that_fails_fast_refuses_nothing_and_reaches_the_route_form(
        workdir, capsys, monkeypatch):
    """Every proof goes through the same detached trial now, not only a
    slow one -- a fast, failing proof must land exactly as promptly and as
    unrefused as it always did (`[trial-proofs]`: nothing here is ever a
    wall the planner meets)."""
    monkeypatch.setattr(checks, "HANDBACK", 30)
    child = _to_the_first_cut()
    _cut(child, "exit 7")
    capsys.readouterr()

    began = time.time()
    cli.main([child, "submit"])                       # never raises
    held = time.time() - began
    assert held < 10, f"held the caller for {held:.1f}s"
    assert "cut" in runmod.state(child)["done"]

    [ran] = _checks(child)
    assert ran["exit"] == 7
    cli.main([child, "close"])

    out = _route_room("issue17", capsys)
    assert "resolved, exit 7" in out
    assert "has not finished yet" not in out


def test_a_malformed_budget_is_read_as_none_and_refuses_nothing(workdir, capsys):
    child = _to_the_first_cut()
    _cut(child, "exit 4", budget="15m")
    cli.main([child, "submit"])
    [ran] = _checks(child)
    assert ran["exit"] == 4
    assert "cut" in runmod.state(child)["done"]


# -- once, at the cut ---------------------------------------------------------


def test_the_route_forms_own_submit_does_not_run_the_proof_again(workdir, capsys):
    child = _to_the_first_cut()
    _cut(child, "exit 1")
    cli.main([child, "submit"])
    cli.main([child, "close"])
    _dispatch_plan_critic("issue17")
    _write_plan_artifact(journal.location("issue17") / "plan.md")
    _fill(_response("issue17"), 'resolution = "pass"\nplan = "%s/plan.md"\n'
          % journal.location("issue17"))
    cli.main(["issue17", "submit"])
    capsys.readouterr()

    assert _checks("issue17") == []                # the parent ran nothing
    assert len(_checks(child)) == 1                # the cut ran it once
    # and the gate the round projected carries the proof, unchanged, as its own
    g1 = next(s for s in runmod.state("issue17")["steps"] if s["id"] == "g1")
    assert g1["prefill"]["proof"] == "exit 1"


def test_the_reading_reaches_the_close_summary_apart_from_the_gates_own_checks(workdir, capsys):
    """The child's close summary carries its trial up under `proof_trials`,
    and `checks` -- the gate's own runs, read as exit codes -- holds none of
    it (#181: a gate's real pass read as "passes on an empty diff")."""
    child = _to_the_first_cut()
    _cut(child, "exit 1")
    cli.main([child, "submit"])
    cli.main([child, "close"])
    capsys.readouterr()

    ret = runmod.state("issue17")["returns_by_child"][child]
    assert ret["summary"]["proof_trials"] == [{"command": "exit 1", "exit": 1, "output": "", "changed": 0}]
    assert ret["summary"]["checks"] == []
