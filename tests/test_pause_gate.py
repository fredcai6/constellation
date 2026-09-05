"""`up` pauses a gate rather than ending its run (commitment 9), scoped to
run-a-gate's own two `up` rows: `work`'s own impasse ruling and `review`'s
own route form. An ask lands in the parent as a step it already stands on --
reordered ahead of the still-live dispatch/adjudicate pair that dispatched
this gate, never amend-closed -- and a marker stands in the child until the
parent's own answer resumes it as a fresh round.

Drives real `run-a-gate` end to end, the parent seeded directly in the shape
`_mint_gates` itself produces -- the same shortcut test_verdict_panels.py's
own single-gate scenarios already take, so this exercises the gate tier's
real mechanism without also driving the issue tier's understand/plan
machinery, which this gate does not touch.
"""

import pathlib
import shutil

import pytest

from engine import cli, journal, run as runmod

from test_nesting import _fill_open
from test_verdict_panels import _fill_implement, _fill_review, _fill_route, _open_panelist, _select
from test_verdict_route import _route_with_calls


def _fill(path, text):
    pathlib.Path(path).write_text(text)


def _seed_two_gates(pwid):
    """A parent holding two gate dispatch/adjudicate pairs -- `g1`, the one
    this file pauses, and `g2`, the sibling every assertion here holds
    untouched."""
    journal.append(pwid, "run", title="t", assembly="run-an-issue")
    for gid, purpose in (("g1", "fix the parser"), ("g2", "fix the linter")):
        child = f"{pwid}.{gid}"
        journal.append(pwid, "step", id=gid, segment="execute", dispatches="run-a-gate",
                       prefill={"purpose": purpose, "scope": "src/ only", "proof": "true"},
                       child=child, anchor=False, terminal=False, source="mint")
        journal.append(pwid, "step", id=f"{gid}-adjudicate", segment="execute",
                       form="forms/GATE_TRANSITION.toml", filler="conductor", child=child,
                       anchor=False, terminal=False, validates="", source="mint")


def _drive_to_up(pwid, gid):
    """One ordinary implement/select/review round, ruled `up` at route --
    the conductor's own word for "the spec, not the diff, is wrong"."""
    child = f"{pwid}.{gid}"
    cli.main(["open", "run-a-gate", "--parent", pwid, "--step", gid])
    _fill_implement(child)
    cli.main([child, "submit"])
    review = _select(child)
    panelist = _open_panelist(child, review)
    _fill_review(panelist, "pass")
    cli.main([panelist, "submit"])
    cli.main([panelist, "close"])
    _fill_route(child, "up")
    cli.main([child, "submit"])
    return child


def _drive_to_close(child):
    """The resumed round, driven all the way to a real close -- the same
    implement/select/review/route/close shape any ordinary gate takes."""
    _fill_implement(child)
    cli.main([child, "submit"])
    review = _select(child)
    panelist = _open_panelist(child, review)
    _fill_review(panelist, "pass")
    cli.main([panelist, "submit"])
    cli.main([panelist, "close"])
    _fill_route(child, "close")
    cli.main([child, "submit"])
    _fill(journal.location(child) / "GATE_CLOSE.toml", 'residue = "waived: none"\n')
    cli.main([child, "submit"])
    cli.main([child, "close"])


def test_up_stands_the_ask_at_the_parent_and_resumes_to_a_real_close(workdir, capsys):
    _seed_two_gates("issue1")
    child = _drive_to_up("issue1", "g1")
    capsys.readouterr()

    # -- right after the pause fires: the parent's own pair for this gate is
    # still not-done and still present, and the ask is what it stands on --
    pst = runmod.state("issue1")
    assert "g1" not in pst["done"] and "g1-adjudicate" not in pst["done"]
    assert any(s["id"] == "g1" for s in pst["steps"])
    assert any(s["id"] == "g1-adjudicate" for s in pst["steps"])
    ask = pst["current"]
    assert ask["form"] == "skills/gate-conductor/forms/ASK.toml"
    assert ask["resumes"] == child
    assert ask["prefill"]["paused"] == child

    # the sibling pair is exactly as it was -- pause touches nothing it has
    # no business touching
    assert "g2" not in pst["done"] and "g2-adjudicate" not in pst["done"]

    # -- the child itself reads paused, not awaiting close ------------------
    cst = runmod.state(child)
    assert cst["open"] and not cst["awaiting_close"]
    assert runmod.paused(cst["current"])

    # (1) submit while paused refuses rather than raising -- `_current_form`'s
    # fallthrough is `step["form"]`, bracket access, and the marker has none
    with pytest.raises(SystemExit) as exc:
        cli.main([child, "submit"])
    assert "paused" in str(exc.value)

    # (2) close while paused offers neither of cmd_close's two wrong escapes
    with pytest.raises(SystemExit) as exc:
        cli.main([child, "close"])
    msg = str(exc.value)
    assert "fill its form and submit it" not in msg
    assert "open its child" not in msg

    # -- the parent answers, and the answer resumes the child ---------------
    answer = "narrow the scope to src/parser.c and drop the rest"
    _fill(journal.location("issue1") / "ASK.toml", 'answer = "%s"\n' % answer)
    cli.main(["issue1", "submit"])
    capsys.readouterr()

    cst = runmod.state(child)
    assert not runmod.paused(cst["current"])
    assert cst["current"]["form"] == "skills/implementer/forms/IMPLEMENT.toml"
    assert cst["current"]["prefill"] == {"answer": answer}

    # (3) driven all the way to an actual close: the parent's pair is still
    # the one the return lands on, and the gate still adjudicates -- the
    # exact defect a quietly-restored retirement would have caused
    _drive_to_close(child)
    capsys.readouterr()

    pst = runmod.state("issue1")
    # the return lands on the dispatch step itself (`state()["parent_step"]`,
    # stamped at open) -- the same site an ordinary, never-paused gate's
    # return always lands on. What pausing had to not break is that this
    # step is still the live one it was before the pause: not amend-closed,
    # and its adjudication still reachable right behind it.
    assert "g1" in pst["done"], "the return did not land on the live dispatch step"
    assert pst["returns_by_child"].get(child), "no return reached the parent"
    assert pst["current"]["id"] == "g1-adjudicate", "the adjudication step is not reachable"

    _fill(journal.location("issue1") / "GATE_TRANSITION.toml", '''
findings = "the narrowed scope landed cleanly"
plan-holds = "advance"
''')
    cli.main(["issue1", "submit"])
    capsys.readouterr()

    pst = runmod.state("issue1")
    assert "g1-adjudicate" in pst["done"], "the gate never adjudicated"

    # (5) the sibling pair, never touched by any of the above
    assert "g2" not in pst["done"] and "g2-adjudicate" not in pst["done"]
    sib = next(s for s in pst["steps"] if s["id"] == "g2")
    assert sib["prefill"]["purpose"] == "fix the linter"


def _drive_to_impasse(pwid, gid, rounds=3):
    """Two implement/review rounds, each revised and reworked, followed by a
    third revise that reaches `work`'s own `impasse-after` threshold
    (assemblies/run-a-gate/ASSEMBLY.toml, `impasse-after = 2` -- ruling,
    2026-09-02: at most three critic dispatches per artifact) and mints
    IMPASSE.toml in place of a fourth step-form round -- the same shape
    `test_rework.py`'s own `_drive_gate_to_impasse` drives, adapted to the
    `_seed_two_gates` parent instead of a full run-an-issue mint.

    `rounds` beyond three (issue113's own C2) rules each fresh IMPASSE
    `rework` to continue the loop before driving the next review round --
    `work` declares no `rework-form`, so its own `rework_rounds` never
    resets once tripped, and every round from the third on reaches this
    same outlet again unless `review`'s own round-cap intercepts first."""
    child = f"{pwid}.{gid}"
    cli.main(["open", "run-a-gate", "--parent", pwid, "--step", gid])
    for n in range(1, rounds + 1):
        if n > 3:
            _fill(journal.location(child) / "IMPASSE.toml",
                  f'ruling = "rework"\nwhy = "gap: untestable ({n - 1}) recurs"\n')
            cli.main([child, "submit"])
        _fill_implement(child)
        cli.main([child, "submit"])
        review = _select(child)
        panelist = _open_panelist(child, review)
        _fill_review(panelist, "revise", findings=f"gap: untestable ({n})")
        cli.main([panelist, "submit"])
        cli.main([panelist, "close"])
        _fill_route(child, "rework")
        cli.main([child, "submit"])
    return child


def test_up_from_impasse_carries_why_into_the_ask(workdir, capsys):
    """scope's other `up` row -- `work`'s own impasse ruling, reached once
    review has sent the same diff back `impasse-after` times, never through
    `review`'s route form -- maps IMPASSE.toml's own `why` field into the
    ask's `findings` key when `_pause_gate` finds no `calls` table
    (cli.py:1204-1205). Nothing existing drives this half: every
    `_drive_gate_to_impasse` caller in test_rework.py rules advance, rework
    or filler, never `up`."""
    _seed_two_gates("issue4")
    child = _drive_to_impasse("issue4", "g1")
    capsys.readouterr()

    why = "the spec asks for something no proof can check"
    _fill(journal.location(child) / "IMPASSE.toml",
          'ruling = "up"\nwhy = "%s"\n' % why)
    cli.main([child, "submit"])
    capsys.readouterr()

    pst = runmod.state("issue4")
    ask = pst["current"]
    assert ask["form"] == "skills/gate-conductor/forms/ASK.toml"
    assert ask["resumes"] == child
    assert ask["prefill"].get("findings") == why


def test_up_with_calls_carries_findings_into_the_ask(workdir, capsys):
    """scope names the review's own `calls` table (or `why`'s fallback) as
    the content `_pause_gate` maps into the ask's own `findings` key
    (cli.py:1199-1205) -- commitment 9's own text. `_drive_to_up` only ever
    routes `up` through `_fill_route`, which fills no `calls` table at all,
    so nothing bound proves this mapping survives; the ask that scenario
    mints carries no `findings` key whatsoever. Driven here instead through
    `test_verdict_route.py`'s own `_route_with_calls` helper -- already in
    the tree, unused until now -- with one `[[calls]]` block, so the ask
    landing at the parent has something to carry."""
    _seed_two_gates("issue2")
    child = "issue2.g1"
    cli.main(["open", "run-a-gate", "--parent", "issue2", "--step", "g1"])
    _fill_implement(child)
    cli.main([child, "submit"])
    review = _select(child)
    panelist = _open_panelist(child, review)
    _fill_review(panelist, "pass")
    cli.main([panelist, "submit"])
    cli.main([panelist, "close"])
    _route_with_calls(child, "up", ("gap: the parser drops the trailing token", "blocking"))
    cli.main([child, "submit"])
    capsys.readouterr()

    pst = runmod.state("issue2")
    ask = pst["current"]
    assert ask["form"] == "skills/gate-conductor/forms/ASK.toml"
    assert ask["resumes"] == child
    assert "gap: the parser drops the trailing token" in ask["prefill"].get("findings", "")


def test_resuming_a_child_whose_journal_is_gone_notes_rather_than_fabricates_one(
        workdir, capsys):
    """(4) `journal.append`'s own `mkdir(parents=True, exist_ok=True)`
    (journal.py:119) means an unguarded resume would fabricate a phantom
    journal for a child swept to the archive or removed by hand. The guard
    is `journal.exists` checked before anything is written into the child --
    proved here by removing the child's own journal outright."""
    _seed_two_gates("issue3")
    child = _drive_to_up("issue3", "g1")
    capsys.readouterr()
    shutil.rmtree(journal.location(child))
    assert not journal.exists(child)

    _fill(journal.location("issue3") / "ASK.toml", 'answer = "too late -- already gone"\n')
    cli.main(["issue3", "submit"])  # must not raise, and must not fabricate a journal
    capsys.readouterr()

    assert not journal.exists(child), "a phantom journal was fabricated for a gone child"
    notes = [e for e in journal.read("issue3") if e.get("kind") == "note"]
    assert any(child in n.get("text", "") for n in notes), "no note recorded the missing child"


# ============================================================================
# `up` the bare command (issue84.g1): `spine <wid> up "<reason>"`, dispatched
# beside `status`/`submit`/`note`/`amend`/`close`/`trace` -- as opposed to
# `up` the outcome *value*, which the tests above still drive through
# ROUTE.toml / IMPASSE.toml exactly as before. Both resolve to the same
# `_pause_gate`; what differs is how the target segment is found (a
# backward scan over the assembly's own declared order, `_up_target`, for
# the bare verb; a hand-named `tseg` in ASSEMBLY.toml's `does = "pause"` /
# `"pause work"` rows for the outcome value) and who does the amend-close
# of `state(wid)["current"]` (`cmd_up` itself; the outcome path needs none,
# since the deciding submit that reached `does = "pause"` is already
# journaled by the time `_perform` runs it).
# ============================================================================


def test_bare_up_at_the_route_position_resolves_to_work_and_pauses_in_one_call(
        workdir, capsys):
    """Standing on ROUTE.toml -- the two-voices step in `review`, panel
    already passed, conductor's own form not yet submitted -- `up` the bare
    command pauses without that form ever being filled: no ROUTE.toml
    submit happens on this path at all. `review` itself declares no
    step-form (anchor-only, `route-form` only), so the backward scan steps
    past it to `work`, the segment `run-a-gate` declares immediately
    before it."""
    _seed_two_gates("issue10")
    child = "issue10.g1"
    cli.main(["open", "run-a-gate", "--parent", "issue10", "--step", "g1"])
    _fill_implement(child)
    cli.main([child, "submit"])
    review = _select(child)
    panelist = _open_panelist(child, review)
    _fill_review(panelist, "pass")
    cli.main([panelist, "submit"])
    cli.main([panelist, "close"])
    capsys.readouterr()

    # standing on ROUTE.toml, not yet submitted -- the route step is what
    # `_current_form` resolves to but this call never touches its form
    pre = runmod.state(child)["current"]
    assert pre["form"] == "forms/ROUTE.toml" and pre["segment"] == "review"
    route_path = journal.location(child) / "ROUTE.toml"
    assert not route_path.exists() or "resolution" not in route_path.read_text()

    cli.main([child, "up", "the spec never says what src/ means here"])
    capsys.readouterr()

    cst = runmod.state(child)
    marker = cst["current"]
    assert runmod.paused(marker) and marker["paused"] == "work"
    assert marker["segment"] == "work"
    # ROUTE.toml was never submitted to get here
    assert pre["id"] not in cst["done"]

    pst = runmod.state("issue10")
    ask = pst["current"]
    assert ask["form"] == "skills/gate-conductor/forms/ASK.toml"
    assert ask["resumes"] == child
    assert ask["prefill"]["ask"] == "the spec never says what src/ means here"
    assert "g1" not in pst["done"] and "g1-adjudicate" not in pst["done"]

    # -- one full resume round trip: the answer becomes a fresh IMPLEMENT
    # round in `work`, and the drive to a real close still lands the return
    # on the live dispatch/adjudicate pair, `g2` untouched throughout -----
    answer = "narrow src/ to src/parser.c only"
    _fill(journal.location("issue10") / "ASK.toml", 'answer = "%s"\n' % answer)
    cli.main(["issue10", "submit"])
    capsys.readouterr()

    cst = runmod.state(child)
    assert not runmod.paused(cst["current"])
    assert cst["current"]["segment"] == "work"
    assert cst["current"]["form"] == "skills/implementer/forms/IMPLEMENT.toml"
    assert cst["current"]["prefill"] == {"answer": answer}

    _drive_to_close(child)
    capsys.readouterr()

    pst = runmod.state("issue10")
    assert "g1" in pst["done"]
    assert pst["current"]["id"] == "g1-adjudicate"
    assert "g2" not in pst["done"] and "g2-adjudicate" not in pst["done"]


def test_bare_up_against_run_an_issues_execute_segment_resolves_to_plan(workdir, capsys):
    """`_seed_two_gates`'s parent stands current on `g1`, the dispatch step
    in `execute` -- a segment with no `step-form` of its own. The backward
    scan steps past it to `plan` (declares `step-form`), skipping
    `execution-state` along the way for the same reason -- no `step-form`
    there either. This parent has no parent of its own, so the ask
    self-mints into its own journal rather than crashing for lack of
    anywhere else to stand."""
    _seed_two_gates("issue11")
    pst = runmod.state("issue11")
    assert pst["current"]["id"] == "g1" and pst["current"]["segment"] == "execute"

    cli.main(["issue11", "up", "the plan never says how g1 and g2 divide the file"])
    capsys.readouterr()

    pst = runmod.state("issue11")
    marker = next(s for s in pst["steps"] if runmod.paused(s))
    assert marker["paused"] == "plan" and marker["segment"] == "plan"
    ask = pst["current"]
    assert ask["form"] == "skills/gate-conductor/forms/ASK.toml"
    assert ask["resumes"] == "issue11"  # self-mint: no parent above this run
    assert ask["prefill"]["ask"] == "the plan never says how g1 and g2 divide the file"
    # the amend-close retired the dispatch step it was ruled at -- g1 itself,
    # not the sibling pair, which stays exactly as `_seed_two_gates` left it
    assert not any(s["id"] == "g1" for s in pst["steps"])
    assert any(s["id"] == "g2" for s in pst["steps"])
    assert any(s["id"] == "g2-adjudicate" for s in pst["steps"])


def _seed_bare_understand(wid):
    """A fresh `run-an-issue` run, journaled directly rather than through
    `cmd_open`, standing on `understand`'s own step-form round -- the shape
    `skeleton()` mints at `open` for that segment, minus the board `_mint`
    seeds alongside it (unneeded here: nothing in this test submits
    anything, only rules `up` against the standing step)."""
    journal.append(wid, "run", title="t", assembly="run-an-issue")
    journal.append(wid, "step", id="understand-1", segment="understand",
                   form="skills/spec-writer/forms/SPEC.toml", filler="spec-writer",
                   anchor=False, terminal=False, validates="", source="open")


def test_bare_up_against_understand_matches_at_the_first_position_no_walk(workdir, capsys):
    """`understand` is `interior = "board"`, not `"steps"` -- exactly the
    shape a stopping rule that also checked `interior == "steps"` would
    refuse over, wrongly continuing back to `open` (which has no
    `step-form` at all) and refusing there instead. Checking `step-form`
    alone matches `understand` at the very first position the scan checks,
    with no backward walk needed."""
    _seed_bare_understand("issue12")
    pre = runmod.state("issue12")["current"]
    assert pre["id"] == "understand-1" and pre["segment"] == "understand"

    cli.main(["issue12", "up", "the spec can't settle what 'done' means here"])
    capsys.readouterr()

    pst = runmod.state("issue12")
    marker = next(s for s in pst["steps"] if runmod.paused(s))
    assert marker["paused"] == "understand" and marker["segment"] == "understand"
    ask = pst["current"]
    assert ask["form"] == "skills/gate-conductor/forms/ASK.toml"
    assert ask["resumes"] == "issue12"
    assert "understand-1" not in [s["id"] for s in pst["steps"]]  # amend-closed


def test_bare_up_with_no_parent_at_all_mints_a_readable_ask_not_a_silent_note(
        workdir, capsys):
    """A root run ruling `up` -- (1) of the three previously-silent
    branches. `_pause_gate`'s reachable-parent check finds no `parent` on
    the run at all, so the ask self-mints into this run's own journal
    instead of only a `note` nobody but a trace command would read.

    Ruled from `select` rather than straight off `open`: `work`'s own
    transition (`select`) mints alongside `work-1` at open (`skeleton()`),
    so pausing before `work-1` is even submitted would leave that live
    sibling sitting ahead of the newly-minted ask in journal-append order
    within the same segment -- an ordering artifact this test does not
    exist to exercise. Submitting the implement round first retires
    `work-1` the ordinary way, leaving `select` as the segment's one live
    step for `up` to retire in turn."""
    cli.main(["open", "run-a-gate", "--id", "g20"])
    _fill_implement("g20")
    cli.main(["g20", "submit"])
    capsys.readouterr()
    pre = runmod.state("g20")["current"]
    assert pre["id"] == "select" and pre["segment"] == "work"  # a root run, no parent

    cli.main(["g20", "up", "the purpose itself is unclear from here"])
    capsys.readouterr()

    st = runmod.state("g20")
    assert st["open"] and not st["awaiting_close"], "the run was left standing on a lost cause"
    ask = st["current"]
    assert ask["form"] == "skills/gate-conductor/forms/ASK.toml"
    assert ask["resumes"] == "g20"
    assert ask["prefill"]["ask"] == "the purpose itself is unclear from here"
    notes = [e for e in journal.read("g20") if e.get("kind") == "note"]
    assert notes == [], "the old silent note is gone, not merely joined by the ask"


def test_bare_up_with_parents_journal_gone_mints_a_readable_ask_not_a_silent_note(
        workdir, capsys):
    """(2) of the three: the parent named at open existed once, but its
    journal is gone by the time `up` is ruled. Only the parent's own
    `journal.toml` is removed, not its whole directory -- the child nests
    inside the parent's own work location (`_open_child`'s own doctrine),
    so `shutil.rmtree`ing the parent's directory would collaterally take
    the child down with it, which is the other (already-covered) test."""
    _seed_two_gates("issue13")
    child = "issue13.g1"
    cli.main(["open", "run-a-gate", "--parent", "issue13", "--step", "g1"])
    _fill_implement(child)
    cli.main([child, "submit"])  # retires work-1 so `select` is the segment's one live step
    capsys.readouterr()
    (journal.location("issue13") / "journal.toml").unlink()
    assert not journal.exists("issue13")
    assert journal.exists(child)

    cli.main([child, "up", "the parent that dispatched this is gone"])
    capsys.readouterr()

    st = runmod.state(child)
    assert st["open"] and not st["awaiting_close"]
    ask = st["current"]
    assert ask["form"] == "skills/gate-conductor/forms/ASK.toml"
    assert ask["resumes"] == child
    assert ask["prefill"]["ask"] == "the parent that dispatched this is gone"
    notes = [e for e in journal.read(child) if e.get("kind") == "note"]
    assert notes == []


def test_bare_up_with_parent_no_longer_holding_the_dispatch_step_mints_a_readable_ask(
        workdir, capsys):
    """(3) of the three: the parent's journal is fine, but it no longer
    holds the step that dispatched this run -- amended away in the
    meantime, the same as a reorder past it would leave it."""
    _seed_two_gates("issue14")
    child = "issue14.g1"
    cli.main(["open", "run-a-gate", "--parent", "issue14", "--step", "g1"])
    _fill_implement(child)
    cli.main([child, "submit"])  # retires work-1 so `select` is the segment's one live step
    cli.main(["issue14", "amend", "close", "g1", "--reason", "reassigned to a human"])
    capsys.readouterr()
    pst = runmod.state("issue14")
    assert not any(s["id"] == "g1" for s in pst["steps"])

    cli.main([child, "up", "the dispatch step I was opened against is gone"])
    capsys.readouterr()

    st = runmod.state(child)
    assert st["open"] and not st["awaiting_close"]
    ask = st["current"]
    assert ask["form"] == "skills/gate-conductor/forms/ASK.toml"
    assert ask["resumes"] == child
    assert ask["prefill"]["ask"] == "the dispatch step I was opened against is gone"
    notes = [e for e in journal.read(child) if e.get("kind") == "note"]
    assert notes == []


def test_bare_up_refuses_when_no_segment_at_or_before_current_has_a_step_form(
        workdir, capsys):
    """Ruled at `open`, before `understand` (the first segment carrying a
    step-form) ever mints -- no segment at or before `open` qualifies, so
    the verb refuses by name rather than pausing nowhere. Nothing is
    journaled: a refusal here must not strand the run on a marker with no
    segment behind it to answer into."""
    journal.append("issue15", "run", title="t", assembly="run-an-issue")
    journal.append("issue15", "step", id="open", segment="open", form="forms/OPEN.toml",
                   filler="conductor", anchor=True, terminal=False, validates="",
                   source="open")
    before = journal.read("issue15")

    with pytest.raises(SystemExit) as exc:
        cli.main(["issue15", "up", "too early to say anything yet"])
    msg = str(exc.value)
    assert "open" in msg
    assert "declares a step-form" in msg  # the actual refusal text `cmd_up` raises
    assert journal.location("issue15") is not None  # still a real run, not wedged open

    after = journal.read("issue15")
    assert after == before, "a refusal must journal nothing that could strand the run"


# ============================================================================
# The self-mint ordering defect (issue84.g2): a step-form segment's own
# transition mints alongside its round-one interior step (`skeleton()`) --
# `run-a-gate`'s `work-1`/`select`, `run-an-issue`'s `understand-1`/its own
# consolidate. Ruling a bare `up` before that round-one step ever submits
# leaves the transition sitting there untouched, and at plain append order
# it would still precede the freshly self-minted ask in `_ordered`'s own
# within-segment order -- `state()["current"]` would resolve to the stale
# sibling, not the ask. `_pause_gate` now reorders the ask (and its marker)
# ahead of it. Every other test above rules `up` after that round-one step
# has already submitted (or from a synthetic single-step journal with no
# sibling at all), so none of them exercise this -- these two do.
# ============================================================================


def test_bare_up_outranks_its_untouched_open_minted_sibling_in_run_a_gate(workdir, capsys):
    """Drives the sibling-ordering fix end to end, through a real resume --
    not only the pause moment. A first draft of this fix (issue84.g2's own
    review found) reordered the ask and its marker ahead of `select`, but
    `_resume_paused_child`'s own `_mint_segment_round` call plain-appends
    the fresh round behind whatever already stands in the segment, so once
    the marker closes the untouched `select` -- only ever leapfrogged, never
    itself reordered -- resurfaced ahead of the fresh round the same way.
    This test fails against that first draft and passes against the fix
    that also carries `select`'s id forward on the marker (`sibling`) so
    the fresh round gets reordered ahead of it too."""
    child_open = ["open", "run-a-gate", "--id", "gzp"]
    cli.main(child_open)
    capsys.readouterr()
    pre = runmod.state("gzp")
    assert pre["current"]["id"] == "work-1"
    assert any(s["id"] == "select" for s in pre["steps"]), "select never minted at open"

    cli.main(["gzp", "up", "the purpose itself is unclear before any round lands"])
    capsys.readouterr()

    st = runmod.state("gzp")
    cur = st["current"]
    assert cur["form"] == "skills/gate-conductor/forms/ASK.toml", (
        "self-mint landed behind its own untouched sibling -- current is %r" % (cur,))
    # `select` is still there, not-done, waiting for the resumed round -- the
    # fix reorders past it, and never closes or drops it
    select = next(s for s in st["steps"] if s["id"] == "select")
    assert "select" not in st["done"]
    assert select["segment"] == "work"

    # -- the actual resume: answer the ask, and the fresh round must be
    # what `current` resolves to next, not the untouched `select` it was
    # reordered ahead of at the pause moment ------------------------------
    _fill(journal.location("gzp") / "ASK.toml", 'answer = "narrow the purpose"\n')
    cli.main(["gzp", "submit"])
    capsys.readouterr()

    resumed = runmod.state("gzp")["current"]
    assert resumed["form"] == "skills/implementer/forms/IMPLEMENT.toml", (
        "resume landed behind the stale sibling instead of the fresh round -- "
        "current is %r" % (resumed,))
    assert resumed["id"] != "work-1"


def test_bare_up_outranks_its_untouched_open_minted_sibling_in_run_an_issue(workdir, capsys):
    """Same shape as the `run-a-gate` test above, for `understand`'s own
    consolidate sibling, driven through a real resume."""
    cli.main(["open", "run-an-issue", "--id", "iss1"])
    _fill_open("iss1")
    cli.main(["iss1", "submit"])
    capsys.readouterr()
    pre = runmod.state("iss1")
    assert pre["current"]["id"] == "understand-1"
    consolidate = next(s for s in pre["steps"] if s["segment"] == "understand"
                       and s["id"] != "understand-1")
    assert consolidate["id"] not in pre["done"], "consolidate never minted untouched at open"

    cli.main(["iss1", "up", "the spec can't settle what 'done' means before any round lands"])
    capsys.readouterr()

    st = runmod.state("iss1")
    cur = st["current"]
    assert cur["form"] == "skills/gate-conductor/forms/ASK.toml", (
        "self-mint landed behind its own untouched sibling -- current is %r" % (cur,))
    assert consolidate["id"] not in st["done"]

    _fill(journal.location("iss1") / "ASK.toml", 'answer = "define done as EOF handling"\n')
    cli.main(["iss1", "submit"])
    capsys.readouterr()

    resumed = runmod.state("iss1")["current"]
    assert resumed["form"] == "skills/spec-writer/forms/SPEC.toml", (
        "resume landed behind the stale consolidate sibling instead of the "
        "fresh spec round -- current is %r" % (resumed,))
    assert resumed["id"] != "understand-1"


def test_bare_up_at_work_1_with_a_reachable_parent_also_outranks_the_sibling(
        workdir, capsys):
    """The sibling-ordering defect is not self-mint-only: the marker
    `_pause_gate` mints always lands in the *child's own* journal, whether
    or not the ask itself goes to a reachable parent. Ruled at a dispatched
    gate's own `work-1`, before `select` is ever touched, the child's own
    `select` sibling would otherwise still precede the marker -- so the
    child's own `cmd_status` would show `select`'s ordinary prompt instead
    of `paused`, even though the parent correctly stands on the ask.
    Driven end to end, through the parent answering and the child resuming."""
    _seed_two_gates("issue20")
    child = "issue20.g1"
    cli.main(["open", "run-a-gate", "--parent", "issue20", "--step", "g1"])
    capsys.readouterr()
    pre = runmod.state(child)
    assert pre["current"]["id"] == "work-1"

    cli.main([child, "up", "ruled at work-1 directly, with a reachable parent"])
    capsys.readouterr()

    cst = runmod.state(child)
    assert runmod.paused(cst["current"]), (
        "the child's own current is not the marker -- the untouched sibling "
        "outranked it: %r" % (cst["current"],))

    pst = runmod.state("issue20")
    ask = pst["current"]
    assert ask["form"] == "skills/gate-conductor/forms/ASK.toml"
    assert ask["resumes"] == child

    _fill(journal.location("issue20") / "ASK.toml",
          'answer = "narrow the scope to src/parser.c"\n')
    cli.main(["issue20", "submit"])
    capsys.readouterr()

    resumed = runmod.state(child)["current"]
    assert resumed["form"] == "skills/implementer/forms/IMPLEMENT.toml", (
        "resume landed behind the stale sibling instead of the fresh round -- "
        "current is %r" % (resumed,))


# ============================================================================
# The ask's own prefill (commitment 7, issue84.g2): keyed under `"paused"`,
# not the literal word `"gate"` -- true of a gate's own reachable-parent
# ask no less than a root run's self-minted one -- and `attempted` never
# renders blank for want of a `scope`/`purpose` to read.
# ============================================================================


def test_pause_prefill_names_what_actually_paused_when_reachable(workdir, capsys):
    _seed_two_gates("ppf1")
    child = _drive_to_up("ppf1", "g1")
    capsys.readouterr()

    prefill = runmod.state("ppf1")["current"]["prefill"]
    assert "gate" not in prefill, (
        "prefill still keys the paused child under the literal word 'gate' -- %r" % (prefill,))
    assert prefill.get("paused") == child
    assert prefill.get("attempted"), "attempted must not render blank when scope/purpose were dispatched"


def test_pause_prefill_names_what_actually_paused_at_a_root_self_mint(workdir, capsys):
    cli.main(["open", "run-a-gate", "--id", "ppf2"])
    capsys.readouterr()
    cli.main(["ppf2", "up", "the purpose itself is unclear before any round lands"])
    capsys.readouterr()

    prefill = runmod.state("ppf2")["current"]["prefill"]
    assert "gate" not in prefill, (
        "root self-mint still keys the paused id under the literal word 'gate' -- %r" % (prefill,))
    assert prefill.get("paused") == "ppf2"
    assert prefill.get("attempted"), "attempted must not render blank at a root self-mint"
