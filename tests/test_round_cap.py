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

One look (ruling, 2026-09-25) changed what a send-back *is* on the plan and
understand seams: `impasse-after` and the impasse outlet are gone from both,
so the loop the cap exists to interrupt is no longer a chain of impasse
rulings (issue99's nineteen rounds) -- it is an `incorporate` (spent once
per artifact, refused a second time by `_check_one_look`) followed by a
chain of `rewrite`s, each judged by its own fresh panel
(`panel-rounds = "opening"` reads a rewrite's round too). `round-cap` is
what is left to bound that chain, and this file still exercises it exactly
that way -- five rounds sent back in a row with nothing released.

Reuses `test_nesting.py`/`test_review_yield.py`'s own plan-seam fixtures and
`test_pause_gate.py`'s own gate-review fixtures rather than hand-rolling a
journal -- the same mechanics those files already stand on.

Also exercises #177: a paused seam's answer mints a `resumed` round, and
`review_yield.seam_round_steps_since_release` restarts its own count there
-- the answer is the ruling the cap stopped to get, so it buys the seam a
fresh run of `round-cap` send-backs, not the single round the pre-#177 seam
had no way to buy more than.
"""

import pathlib

from engine import cli, review_yield, run as runmod

from test_nesting import (
    _dispatch_and_close_child, _dispatch_and_close_plan, _dispatch_plan_critic,
    _fill, _fill_consolidate, _fill_critic, _fill_open, _fill_plan,
    _fill_plan_rework, _fill_plan_to_execute, _response, _work_the_board,
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


def _dispatch_plan_critic_with_calls(wid, finding):
    """The cap round's own deciding form, ruled finding by finding rather
    than plain -- proves `_seam_findings_history`'s calls-narrowed branch
    (`_blocking_calls`, engine/cli.py) actually runs: without a `calls`
    table on some round's own done-entry, that branch never executes and a
    defect in it would pass every other test in this file. This round's own
    panel returns a `severe` finding and a `beyond` one, and the
    conductor's `[[calls]]` table calls each in kind, folding the severe
    one into `orders` -- a `rewrite`'s prefill is `orders` alone."""
    st = runmod.state(wid)
    step_id = st["current"]["id"]
    panel = next(s for s in st["steps"] if s["id"] == step_id).get("panel") or []
    for n in range(1, len(panel) + 1):
        cli.main(["open", "give-a-verdict", "--parent", wid, "--step", f"{step_id}.p{n}"])
        panelist = f"{wid}.{step_id}.p{n}"
        _fill_critic(panelist, "revise", f"{finding}\\n\\n{BEYOND_FINDING}")
        cli.main([panelist, "submit"])
        cli.main([panelist, "close"])
    body = ('orders = "%s -- replace it in kind"\n\n'
            '[[calls]]\nfinding = "%s"\ncall = "severe"\n\n'
            '[[calls]]\nfinding = "%s"\ncall = "beyond"\n\n') % (finding, finding, BEYOND_FINDING)
    _fill_plan_to_execute(wid, "rewrite", calls=body)
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
              'purpose-holds = "this gate\'s claim holds; re-ran its check"\n'
              'findings = "landed clean; more of the issue remains"\n'
              'plan-holds = "replan"\n')
        cli.main([wid, "submit"])  # refills plan for the next gate


def _drive_plan_seam_to_its_cap(wid="issue113c1"):
    """Five rounds at the plan-to-execute seam sent back in a row with none
    released -- one artifact, `incorporate`d once (a second incorporate on
    top of it is refused, `_check_one_look`), then four `rewrite`s, each
    judged by its own fresh panel (`panel-rounds = "opening"` reads a
    rewrite's round too). Read off the assembly, never pinned: the cap is
    `round-cap`, and the rounds before it are each sent back plain. The cap
    round's own deciding form carries a `[[calls]]` table narrowing it to
    one severe finding among two raised
    (`_dispatch_plan_critic_with_calls`) -- the only round here that does,
    so C1-findings below also proves `_seam_findings_history`'s
    calls-narrowed branch, not only its plain-join fallback every other
    round exercises."""
    cap = PLAN_SEG["round-cap"]
    _open_to_plan(wid)
    _dispatch_and_close_plan(wid)
    _dispatch_plan_critic(wid, verdict="revise", findings="gap: r1 needs another look",
                          resolution="incorporate")
    reworked = _fresh_plan_mint(wid)
    _dispatch_and_close_plan(wid, reworked["id"], _fill_plan_rework)
    _fill_plan_to_execute(wid, "rewrite",
        calls='orders = "gap: r2 needs another look -- replace it in kind"\n')
    cli.main([wid, "submit"])
    for n in range(3, cap):
        fresh = _fresh_plan_mint(wid)
        _dispatch_and_close_plan(wid, fresh["id"], _fill_plan)
        _dispatch_plan_critic(wid, verdict="revise",
                              findings=f"gap: r{n} needs another look",
                              resolution="rewrite")
    fresh = _fresh_plan_mint(wid)
    _dispatch_and_close_plan(wid, fresh["id"], _fill_plan)
    _dispatch_plan_critic_with_calls(wid, f"gap: r{cap} the scope creeps again")
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

    # -- the calls-narrowed branch: round 5's own `[[calls]]` table calls its
    # other finding `beyond`, not `severe`, so that finding is absent even
    # though the panel that raised it returned it -- proof
    # `_seam_findings_history` (engine/cli.py) actually reads a round's own
    # narrowed text for a round whose done-entry carries a table, not only
    # its plain-join fallback every other round here exercises ---------------
    assert BEYOND_FINDING not in findings, (
        "the ask carried a finding round 5's own calls table ruled beyond, not severe")


# -- a release starts the count over: one cut per gate never reaches it -----


def test_round_cap_never_fires_on_a_plan_seam_released_once_per_gate(workdir, capsys):
    """issue811's shape: six gates, each cut once and released, is six plan
    rounds landed -- past the old count's cap -- with nothing sent back.
    The seventh gate's cut, the run's first send-back, is an `incorporate`
    (a spec or a cut still gets its one pass), which mints a writer round
    and no ask. The yield still reads every round (`seam_rounds`); only the
    cap's own count is cut at the last release."""
    wid = "issue811"
    _open_to_plan(wid)
    _release_gates(wid, 6)
    fresh = _fresh_plan_mint(wid)
    _dispatch_and_close_plan(wid, fresh["id"], fill_fn=lambda w: _fill_plan(
        w, purpose="gate 7 purpose", scope="gate 7 scope"))
    _dispatch_plan_critic(wid, verdict="revise",
                          findings="gap: r7 the run's first send-back",
                          resolution="incorporate")
    capsys.readouterr()

    st = runmod.state(wid)
    cur = st["current"]
    assert cur["form"] != ASK_FORM, "the cap fired on structure, not on churn"
    assert not runmod.paused(cur)
    assert cur["segment"] == "plan" and cur.get("dispatches"), "no writer round was minted"
    assert cur["form"] == PLAN_SEG["rework-form"]

    asm = runmod.load_assembly("run-an-issue")
    assert len(review_yield.seam_rounds(st, PLAN_SEG, asm)) == 7
    since = review_yield.seam_round_steps_since_release(st, PLAN_SEG, asm)
    assert len(since) == 1, "the six released rounds still counted against the cap"
    assert since[0]["id"] in st["done"]  # gate 7's own round, the one just sent back


# -- C4: an answer buys one round, and the next send-back asks again --------


def test_round_cap_answer_restarts_the_count_then_asks_again_after_a_full_cap(workdir, capsys):
    """#177: the round a paused seam's answer opens is stamped `resumed`,
    and `review_yield.seam_round_steps_since_release` restarts its count
    there -- the answer is the ruling the cap stopped to get, so it buys the
    seam a fresh run of `round-cap` send-backs, not one. Before #177 this
    seam had no way to buy more than a single round back; this is the new
    behaviour, not a port of the old one-round test."""
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

    resumed_step = next(s for s in runmod.state(wid)["steps"]
                        if s["segment"] == "plan" and s.get("resumed"))
    assert resumed_step.get("resumed") is True

    cap = PLAN_SEG["round-cap"]
    # round one after the resume: the resumed transition mints no panel of
    # its own (`panel-rounds = "opening"`), so this send-back is the
    # conductor's alone, same shape every panel-less round after the
    # opening cut takes
    _dispatch_and_close_plan(wid, cst["current"]["id"], fill_fn=lambda w: _fill_plan(
        w, purpose="gate 2 purpose, narrowed", scope="src/parser.c only"))
    _fill_plan_to_execute(wid, "rewrite",
        calls='orders = "gap: r6 still too broad -- replace it in kind"\n')
    cli.main([wid, "submit"])
    capsys.readouterr()

    # the count restarted at the resumed round: it takes `cap` more
    # send-backs, not one, to reach the ask a second time
    for n in range(2, cap):
        fresh = _fresh_plan_mint(wid)
        _dispatch_and_close_plan(wid, fresh["id"], _fill_plan)
        _dispatch_plan_critic(wid, verdict="revise",
                              findings=f"gap: round {n} since the resume, still too broad",
                              resolution="rewrite")
        capsys.readouterr()
        assert not runmod.paused(runmod.state(wid)["current"]), (
            f"the cap fired after only {n} rounds since the resume, not {cap}")

    fresh = _fresh_plan_mint(wid)
    _dispatch_and_close_plan(wid, fresh["id"], _fill_plan)
    _dispatch_plan_critic(wid, verdict="revise",
                          findings="gap: the same gap, still, since the resume",
                          resolution="rewrite")
    capsys.readouterr()

    pst = runmod.state(wid)
    ask = pst["current"]
    assert ask["form"] == ASK_FORM, "round-cap did not fire a second time after the resume"
    assert ask["resumes"] == wid
    assert "the same gap, still, since the resume" in ask["prefill"].get("findings", "")


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
    principal's.

    Unchanged by one look (2026-09-25): run-a-gate's own `work` segment and
    its `review`/ROUTE.toml still keep `impasse-after` and `rework` -- only
    run-an-issue's `understand` and `plan` seams lost them."""
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
