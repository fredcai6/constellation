"""issue113: a run-level round-cap on `run-an-issue`'s understand and plan
seams, and `run-a-gate`'s review seam -- once a seam has sent back
`round-cap` rounds in a row with none released, the next send-back pauses
to an ask instead of minting another round, naming the seam, the count, and
the findings of every round counted (spec.md's C1-C5).

The count is the rounds landed since the seam last released one
(`review_yield.seam_round_steps_since_release`), never the seam's whole
history: a rolling-horizon run re-enters the plan seam once per gate by
design, and issue811's first run (2026-09-06) reached its sixth gate with no
send-back at all and was stopped by a cap counting every round since open.
Two fixtures here draw the line -- send-backs with no release reach the cap,
one released cut per gate never does.

Reuses `test_nesting.py`/`test_review_yield.py`'s own plan-seam fixtures and
`test_pause_gate.py`'s own gate-review fixtures rather than hand-rolling a
journal -- the same mechanics those files already stand on.
"""

import pathlib

from engine import cli, review_yield, run as runmod

from test_nesting import (
    _dispatch_and_close_child, _dispatch_and_close_plan, _dispatch_plan_critic,
    _fill, _fill_consolidate, _fill_critic, _fill_open, _fill_plan,
    _fill_plan_rework, _fill_plan_route_with_calls, _fill_plan_to_execute,
    _response, _work_the_board,
)
from test_pause_gate import _drive_to_impasse, _seed_two_gates

ASK_FORM = "skills/gate-conductor/forms/ASK.toml"
PLAN_SEG = next(s for s in runmod.load_assembly("run-an-issue")["segment"] if s["id"] == "plan")


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
    """The cap round's own deciding form, ruled finding by finding rather
    than plain -- `_fill_plan_route_with_calls` (test_nesting.py), already
    in the tree for exactly this. Proves `_seam_findings_history`'s
    blocking-narrowed branch (`_blocking_calls`, engine/cli.py) actually
    runs: without a `calls` table on some round's own done-entry, that
    branch never executes and a defect in it would pass every other test
    in this file."""
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


def _open_to_plan(wid):
    """A run-an-issue standing on its first plan round: opened, its board
    worked, its spec consolidated."""
    cli.main(["open", "run-an-issue", "--id", wid, "--title", "round-cap"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])


def _release_gates(wid, gates):
    """`gates` gates in a row, each the shape a rolling-horizon run takes by
    design: one cut, passed by the panel, released on PLAN_TO_EXECUTE (which
    projects the gate), the gate dispatched and closed, and the plan seam
    re-entered by a `replan` for the next cut. Every round lands and every
    round releases; nothing is ever sent back."""
    for gate in range(1, gates + 1):
        if gate == 1:
            _dispatch_and_close_plan(wid)
        else:
            fresh = _fresh_plan_mint(wid)
            _dispatch_and_close_plan(wid, fresh["id"], fill_fn=lambda w, g=gate: _fill_plan(
                w, purpose=f"gate {g} purpose", scope=f"gate {g} scope"))
        _dispatch_plan_critic(wid, verdict="pass")
        _fill_plan_to_execute(wid, "pass")
        cli.main([wid, "submit"])  # releases, projects this gate
        _dispatch_and_close_child(wid, f"g{gate}")
        _fill(_response(wid),
              'findings = "landed clean; more of the issue remains"\n'
              'plan-holds = "replan"\n')
        cli.main([wid, "submit"])  # refills plan for the next gate


def _send_back(wid, findings):
    """The current plan round sent back on `findings`: the panel revises, the
    conductor rules `rework` -- and where this artifact's own
    `impasse-after` is already spent, the impasse form that mints in place
    of a round is ruled `rework` too, so the loop keeps the same artifact.
    That ruling is the shape the cap exists to interrupt: issue99's
    nineteen rounds were impasse rulings sending the same plan back."""
    _dispatch_plan_critic(wid, verdict="revise", findings=findings)
    cur = runmod.state(wid)["current"]
    if cur["form"] == PLAN_SEG["impasse-form"]:
        _fill(_response(wid), 'ruling = "rework"\nwhy = "the same gap, one more pass"\n')
        cli.main([wid, "submit"])


def _drive_plan_seam_to_its_cap(wid="issue113c1"):
    """Five rounds at the plan-to-execute seam sent back in a row with none
    released -- one artifact, reworked past its own `impasse-after` and
    kept alive by impasse rulings of `rework`, the way issue99's plan seam
    ran. Read off the assembly, never pinned: the cap is `round-cap`, and
    the rounds before it are each sent back plain. The cap round's own
    deciding form carries a `[[calls]]` table narrowing it to one blocking
    finding among two raised (`_dispatch_plan_critic_with_calls`) -- the
    only round here that does, so C1-findings below also proves
    `_seam_findings_history`'s blocking-narrowed branch, not only its
    plain-join fallback every other round exercises."""
    _open_to_plan(wid)
    _dispatch_and_close_plan(wid)
    for n in range(1, PLAN_SEG["round-cap"]):
        _send_back(wid, f"gap: r{n} needs another look")
        fresh = _fresh_plan_mint(wid)
        _dispatch_and_close_plan(wid, fresh["id"], _fill_plan_rework)
    _dispatch_plan_critic_with_calls(wid, "gap: r5 the scope creeps again")
    return wid


# -- C1: the plan seam stops at the cap and asks -----------------------------


def test_round_cap_pauses_the_plan_seam_after_five_send_backs_with_no_release(workdir, capsys):
    wid = _drive_plan_seam_to_its_cap()
    capsys.readouterr()

    pst = runmod.state(wid)
    ask = pst["current"]
    assert ask["form"] == ASK_FORM, "the fifth send-back minted a round instead of an ask"
    assert ask["resumes"] == wid  # a root run, no parent to reach: self-mint
    assert ask["filler"] == runmod.PRINCIPAL  # the issue tier's ask is the human's, never the run's own

    # -- C3: the room names the seam and the count --------------------------
    reason = ask["prefill"]["ask"]
    assert "plan-to-execute" in reason
    assert "5" in reason

    # -- C1-findings: every one of the five counted rounds' own findings, not
    # only the one that tripped the cap -- the sent-back rounds each carry
    # "r<n> needs another look", the cap round its own text ------------------
    findings = ask["prefill"].get("findings", "")
    sent_back = [n for n in range(1, 5) if f"r{n} needs another look" in findings]
    assert sent_back and sent_back[0] == 1, "round 1's own findings missing from the ask"
    assert "r5 the scope creeps again" in findings

    # -- oldest first: `_seam_findings_history`'s own contract, not only that
    # every round's text is present but that it lands in landed order --------
    positions = [findings.index(f"r{n} needs another look") for n in sent_back]
    positions.append(findings.index("r5 the scope creeps again"))
    assert positions == sorted(positions), (
        "the ask's findings landed out of round order (oldest first)")

    # -- the blocking-narrowed branch: round 5's own `[[calls]]` table ruled
    # its other finding `beyond`, so that finding is absent even though the
    # panel that raised it returned it -- proof `_seam_findings_history`
    # (engine/cli.py) actually reads `_blocking_calls`'s narrowed text for a
    # round whose done-entry carries a table, not only its plain-join
    # fallback every other round here exercises ---------------------------
    assert BEYOND_FINDING not in findings, (
        "the ask carried a finding round 5's own calls table ruled beyond, not blocking")


# -- a release starts the count over: one cut per gate never reaches it -----


def test_round_cap_never_fires_on_a_plan_seam_released_once_per_gate(workdir, capsys):
    """issue811's shape: six gates, each cut once and released, is six plan
    rounds landed -- past the old count's cap -- with nothing sent back.
    The seventh gate's cut, the run's first send-back, mints a rework round
    and no ask. The yield still reads every round (`seam_rounds`); only the
    cap's own count is cut at the last release."""
    wid = "issue811"
    _open_to_plan(wid)
    _release_gates(wid, 6)
    fresh = _fresh_plan_mint(wid)
    _dispatch_and_close_plan(wid, fresh["id"], fill_fn=lambda w: _fill_plan(
        w, purpose="gate 7 purpose", scope="gate 7 scope"))
    _dispatch_plan_critic(wid, verdict="revise",
                          findings="gap: r7 the run's first send-back")
    capsys.readouterr()

    st = runmod.state(wid)
    cur = st["current"]
    assert cur["form"] != ASK_FORM, "the cap fired on structure, not on churn"
    assert not runmod.paused(cur)
    assert cur["segment"] == "plan" and cur.get("dispatches"), "no rework round was minted"
    assert cur["form"] == PLAN_SEG["rework-form"]

    asm = runmod.load_assembly("run-an-issue")
    assert len(review_yield.seam_rounds(st, PLAN_SEG, asm)) == 7
    since = review_yield.seam_round_steps_since_release(st, PLAN_SEG, asm)
    assert len(since) == 1, "the six released rounds still counted against the cap"
    assert since[0]["id"] in st["done"]  # gate 7's own round, the one just sent back


# -- C4: an answer buys one round, and the next send-back asks again --------


def test_round_cap_answer_buys_one_round_then_asks_again(workdir, capsys):
    wid = _drive_plan_seam_to_its_cap()
    capsys.readouterr()

    answer = "narrow both gates to src/parser.c and drop the rest"
    _fill(_response(wid), 'answer = "%s"\n' % answer)
    cli.main([wid, "submit"])
    capsys.readouterr()

    cst = runmod.state(wid)
    assert not runmod.paused(cst["current"])
    assert cst["current"]["segment"] == "plan"
    assert cst["current"]["form"] == "skills/planner/forms/PLAN.toml"
    assert cst["current"]["prefill"] == {"answer": answer}

    # the answer buys exactly one round: draft it, land it with a revise --
    # the sixth send-back with still nothing released, one past the cap
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


def test_round_cap_pauses_a_gates_review_seam_at_five_send_backs(workdir, capsys):
    """`run-a-gate`'s review seam sends back with `does = "rework work"`, so
    the segment the cap is declared on (`review`) and the segment whose own
    `impasse-after` is spent (`work`) are two different segments -- proof
    that the cap counts against the seam's own segment, never the rework's
    target, and outranks the per-artifact outlet where both would otherwise
    fire on the same round (spec.md's "The ordering, corrected"). Five
    reviews, five `rework`s, nothing released: the count is the gate's whole
    history here because nothing ever cut it. The ask lands in the parent
    under the `conductor` filler: a gate's ask is its parent's conductor's
    to answer, and only an ask with no parent run to reach is the
    principal's."""
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
    assert ask["filler"] == "conductor"
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
