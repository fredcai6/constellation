"""issue113: a run-level round-cap on `run-an-issue`'s understand and plan
seams, and `run-a-gate`'s review seam -- once `round-cap` rounds have landed
at a seam in this run, the next send-back pauses to an ask instead of
minting another round, naming the seam, the landed count, and every landed
round's own findings (spec.md's C1-C5).

Reuses `test_nesting.py`/`test_review_yield.py`'s own plan-seam fixtures and
`test_pause_gate.py`'s own gate-review fixtures rather than hand-rolling a
journal -- the same mechanics those files already stand on.
"""

import pathlib

from engine import cli, journal, run as runmod

from test_nesting import (
    _dispatch_and_close_child, _dispatch_and_close_plan, _dispatch_plan_critic,
    _fill, _fill_consolidate, _fill_critic, _fill_open, _fill_plan,
    _fill_plan_rework, _fill_plan_route_with_calls, _fill_plan_to_execute,
    _work_the_board,
)
from test_pause_gate import _drive_to_impasse, _seed_two_gates

ASK_FORM = "skills/gate-conductor/forms/ASK.toml"


def _fresh_plan_mint(wid):
    """The plan segment's own live, not-yet-decided round -- `source == mint`
    and `dispatches` both true, the same shape every plan round after the
    first takes, filtered to what is not already done since more than one
    such step can sit in the journal across several rounds."""
    st = runmod.state(wid)
    return next(s for s in st["steps"]
                if s["segment"] == "plan" and s.get("source") == "mint"
                and s["id"] not in st["done"] and s.get("dispatches"))


BEYOND_FINDING = "beyond: the migration angle is a separate piece of work"


def _dispatch_plan_critic_with_calls(wid, blocking_finding):
    """Round 5's own deciding form, ruled finding by finding rather than
    plain -- `_fill_plan_route_with_calls` (test_nesting.py), already in the
    tree for exactly this and unused from this file until now. Proves
    `_seam_findings_history`'s blocking-narrowed branch (`_blocking_calls`,
    engine/cli.py) actually runs: without a `calls` table on some round's
    own done-entry, that branch never executes and a defect in it would pass
    every other test in this file."""
    st = runmod.state(wid)
    step_id = st["current"]["id"]
    panel = next(s for s in st["steps"] if s["id"] == step_id)["panel"]
    for n in range(1, len(panel) + 1):
        cli.main(["open", "give-a-verdict", "--parent", wid, "--step", f"{step_id}.p{n}"])
        panelist = f"{wid}.{step_id}.p{n}"
        _fill_critic(panelist, "revise", f"{blocking_finding}\\n\\n{BEYOND_FINDING}")
        cli.main([panelist, "submit"])
        cli.main([panelist, "close"])
    _fill_plan_route_with_calls(wid, "rework",
        (blocking_finding, "blocking"), (BEYOND_FINDING, "beyond"))
    cli.main([wid, "submit"])


def _drive_plan_seam_to_its_cap(wid="issue113c1"):
    """Five landed rounds at the plan-to-execute seam, spread across two
    gates so the per-artifact `impasse-after` allowance (2) resets in
    between and never by itself reaches the cap (5): gate 1's own artifact
    is reworked once then released (2 landed rounds); gate 1 is dispatched,
    closed and replanned; gate 2's own fresh artifact is reworked twice more
    (rounds 3 and 4) before its own third rework -- round 5 -- lands at the
    cap and pauses instead of minting a sixth. Round 5's own deciding form
    carries a `[[calls]]` table narrowing it to one blocking finding among
    two raised (`_dispatch_plan_critic_with_calls`) -- the only round here
    that does, so C1-findings below also proves `_seam_findings_history`'s
    blocking-narrowed branch, not only its plain-join fallback every other
    round exercises."""
    cli.main(["open", "run-an-issue", "--id", wid, "--title", "round-cap"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])

    # -- gate 1's own plan artifact: round 1 reworked, round 2 released -----
    _dispatch_and_close_plan(wid)
    _dispatch_plan_critic(wid, verdict="revise",
                          findings="gap: r1 needs the loop bound checked")
    fresh = _fresh_plan_mint(wid)
    _dispatch_and_close_plan(wid, fresh["id"], _fill_plan_rework)
    _dispatch_plan_critic(wid, verdict="pass")
    _fill_plan_to_execute(wid, "pass")
    cli.main([wid, "submit"])  # releases, projects g1

    _dispatch_and_close_child(wid, "g1")
    _fill(journal.location(wid) / "GATE_TRANSITION.toml",
          'findings = "landed clean; more of the issue remains"\n'
          'plan-holds = "replan"\n')
    cli.main([wid, "submit"])  # refills plan for gate 2

    # -- gate 2's own plan artifact: rounds 3 and 4 reworked, round 5 at cap
    fresh = _fresh_plan_mint(wid)
    _dispatch_and_close_plan(wid, fresh["id"], fill_fn=lambda w: _fill_plan(
        w, purpose="gate 2 purpose", scope="gate 2 scope"))
    _dispatch_plan_critic(wid, verdict="revise",
                          findings="gap: r3 needs a fresh risk section")
    fresh = _fresh_plan_mint(wid)
    _dispatch_and_close_plan(wid, fresh["id"], _fill_plan_rework)
    _dispatch_plan_critic(wid, verdict="revise",
                          findings="gap: r4 still thin on proof")
    fresh = _fresh_plan_mint(wid)
    _dispatch_and_close_plan(wid, fresh["id"], _fill_plan_rework)
    _dispatch_plan_critic_with_calls(wid, "gap: r5 the scope creeps again")
    return wid


# -- C1: the plan seam stops at the cap and asks -----------------------------


def test_round_cap_pauses_the_plan_seam_after_five_landed_rounds(workdir, capsys):
    wid = _drive_plan_seam_to_its_cap()
    capsys.readouterr()

    pst = runmod.state(wid)
    ask = pst["current"]
    assert ask["form"] == ASK_FORM, "the sixth send-back minted a round instead of an ask"
    assert ask["resumes"] == wid  # a root run, no parent to reach: self-mint

    # -- C3: the room names the seam and the landed count -------------------
    reason = ask["prefill"]["ask"]
    assert "plan-to-execute" in reason
    assert "5" in reason

    # -- C1-findings: every one of the five landed rounds' own findings, not
    # only the one that tripped the cap --------------------------------------
    findings = ask["prefill"].get("findings", "")
    for text in ("r1 needs the loop bound checked", "r3 needs a fresh risk section",
                 "r4 still thin on proof", "r5 the scope creeps again"):
        assert text in findings, f"{text!r} missing from the ask's own findings"

    # -- oldest first: `_seam_findings_history`'s own contract, not only that
    # every round's text is present but that it lands in landed order --------
    assert (findings.index("r1 needs the loop bound checked")
            < findings.index("r3 needs a fresh risk section")
            < findings.index("r4 still thin on proof")
            < findings.index("r5 the scope creeps again")), (
        "the ask's findings landed out of round order (oldest first)")

    # -- the blocking-narrowed branch: round 5's own `[[calls]]` table ruled
    # its other finding `beyond`, so that finding is absent even though the
    # panel that raised it returned it -- proof `_seam_findings_history`
    # (engine/cli.py) actually reads `_blocking_calls`'s narrowed text for a
    # round whose done-entry carries a table, not only its plain-join
    # fallback every other round here exercises ---------------------------
    assert BEYOND_FINDING not in findings, (
        "the ask carried a finding round 5's own calls table ruled beyond, not blocking")


# -- C4: an answer buys one round, and the next send-back asks again --------


def test_round_cap_answer_buys_one_round_then_asks_again(workdir, capsys):
    wid = _drive_plan_seam_to_its_cap()
    capsys.readouterr()

    answer = "narrow both gates to src/parser.c and drop the rest"
    _fill(journal.location(wid) / "ASK.toml", 'answer = "%s"\n' % answer)
    cli.main([wid, "submit"])
    capsys.readouterr()

    cst = runmod.state(wid)
    assert not runmod.paused(cst["current"])
    assert cst["current"]["segment"] == "plan"
    assert cst["current"]["form"] == "skills/planner/forms/PLAN.toml"
    assert cst["current"]["prefill"] == {"answer": answer}

    # the answer buys exactly one round: draft it, land it with a revise --
    # the seventh round overall, sixth since the cap already caught the fifth
    _dispatch_and_close_plan(wid, cst["current"]["id"], fill_fn=lambda w: _fill_plan(
        w, purpose="gate 2 purpose, narrowed", scope="src/parser.c only"))
    _dispatch_plan_critic(wid, verdict="revise",
                          findings="gap: r6 still too broad")
    capsys.readouterr()

    pst = runmod.state(wid)
    ask = pst["current"]
    assert ask["form"] == ASK_FORM, "the send-back past the cap minted a round, not a second ask"
    assert ask["resumes"] == wid
    assert "r6 still too broad" in ask["prefill"].get("findings", "")


# -- C2: the same stop holds at a gate's own review seam ---------------------


def test_round_cap_pauses_a_gates_review_seam_at_five_landed_rounds(workdir, capsys):
    """`run-a-gate`'s review seam sends back with `does = "rework work"`, so
    the segment the cap is declared on (`review`) and the segment whose own
    `impasse-after` is spent (`work`) are two different segments -- proof
    that the cap counts against the seam's own segment, never the rework's
    target, and outranks the per-artifact outlet where both would otherwise
    fire on the same round (spec.md's "The ordering, corrected")."""
    _seed_two_gates("issue113c2")
    child = _drive_to_impasse("issue113c2", "g1", rounds=5)
    capsys.readouterr()

    # round five's send-back pauses -- not a third IMPASSE.toml mint
    cst = runmod.state(child)
    assert runmod.paused(cst["current"]), (
        "review's fifth send-back minted a third impasse instead of pausing")

    pst = runmod.state("issue113c2")
    ask = pst["current"]
    assert ask["form"] == ASK_FORM
    assert ask["resumes"] == child
    reason = ask["prefill"]["ask"]
    assert "review" in reason and "5" in reason

    findings = ask["prefill"].get("findings", "")
    for n in (1, 2, 3, 4, 5):
        assert f"untestable ({n})" in findings, f"round {n}'s own findings are missing"

    # -- oldest first, per `_seam_findings_history`'s own contract ----------
    positions = [findings.index(f"untestable ({n})") for n in (1, 2, 3, 4, 5)]
    assert positions == sorted(positions), (
        "the ask's findings landed out of round order (oldest first)")

    # the sibling gate is untouched throughout
    assert "g2" not in pst["done"] and "g2-adjudicate" not in pst["done"]


# -- C5: undeclared, the cap changes nothing ---------------------------------


def test_round_cap_is_declared_at_exactly_three_sites_in_assemblies():
    root = pathlib.Path(__file__).resolve().parent.parent / "assemblies"
    sites = [f"{p.relative_to(root)}:{n}"
             for p in sorted(root.glob("**/ASSEMBLY.toml"))
             for n, line in enumerate(p.read_text().splitlines(), start=1)
             if line.strip().startswith("round-cap")]
    assert len(sites) == 3, sites
    assert all("run-an-issue" in s or "run-a-gate" in s for s in sites)
