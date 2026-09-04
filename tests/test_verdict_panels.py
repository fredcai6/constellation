"""The review transition dispatches its panel, collects verdicts, and acts.

Drives real `run-a-gate` and `give-a-verdict` assemblies -- not fixtures. A
panelist is a child run one level finer than a gate dispatch, opened through
the same `--parent`/`--step` mechanism with a `.pN` tag naming which panel
entry. These tests prove the four things the review transition promises:
status renders a copyable command per panelist; opening one prefills the
artifact and criteria; the merged verdict acts (pass releases, revise
refills with concatenated attributed findings); and a gate cannot reach
close without review having fired. The panel's vocabulary is `pass | revise`
-- there is no third word, so a reviewer who objects at the root writes that
as a revise finding, the same as any other; test_rework.py drives four of
them to the segment's own outlet.
"""

import pathlib

import pytest

from engine import cli, journal, run as runmod


def _fill(path, text):
    pathlib.Path(path).write_text(text)


def _fill_implement(wid):
    _fill(journal.location(wid) / "IMPLEMENT.toml",
         'change = "adjusted the bound"\ndeviations = "waived: none"\n')


def _fill_review(wid, verdict, findings="none: waived: clean"):
    _fill(journal.location(wid) / "REVIEW.toml", '''
verify = "read the diff line by line"
findings = "%s"
verdict = "%s"
''' % (findings, verdict))


def _fill_route(wid, resolution):
    """The conductor's own half of the review step: where the round the panel
    just judged goes next. `rework` refills `work` with the panel's findings;
    `close` releases the round and the gate walks on."""
    _fill(journal.location(wid) / "ROUTE.toml", 'resolution = "%s"\n' % resolution)


DEFAULT_LENS = "spec-fit: does the work fill the specification, whole and only"


def _select(wid, *criteria):
    """`work`'s own transition: name the lenses, submit, and the review step
    is minted -- panel and route form together. Every drive through this gate
    passes here, including the fresh round after a rework, which is the point
    of the beat: the readers are chosen again rather than inherited."""
    blocks = "".join('\n[[panelists]]\nworker = "reviewer"\nmodel = "standard"\n'
                     'criteria = "%s"\n' % c for c in (criteria or (DEFAULT_LENS,)))
    _fill(journal.location(wid) / "SELECT.toml", 'omitted = "waived: none"\n' + blocks)
    cli.main([wid, "submit"])
    return runmod.state(wid)["current"]["id"]


def _open_gate(gid="g1", *criteria):
    """A standalone run-a-gate, opened top-level the way test_robustness.py's
    hanging-check test does -- no run-an-issue plumbing needed to exercise
    the review beat -- and driven through implement and select, so the review
    step the rest of these tests stand on actually exists."""
    cli.main(["open", "run-a-gate", "--id", gid])
    _fill_implement(gid)
    cli.main([gid, "submit"])
    _select(gid, *criteria)
    return gid


def _review_step(gwid):
    """The id of the review step `select` minted -- generated per round now,
    not the fixed `review` a static declaration used to give it."""
    return next(s["id"] for s in runmod.state(gwid)["steps"]
                if s.get("form") == "forms/ROUTE.toml" and s.get("panel"))


def _pass_the_panel(gwid, step_id=None):
    """Drive the panel to a pass and dispose of the round on the review
    step's own conductor form, so the gate's next pending step is its
    ordinary close form."""
    wid = _open_panelist(gwid, step_id or _review_step(gwid))
    _fill_review(wid, "pass")
    cli.main([wid, "submit"])
    cli.main([wid, "close"])
    _fill_route(gwid, "close")
    cli.main([gwid, "submit"])


def _open_panelist(gwid, step_id, n=1):
    tag = f"{step_id}.p{n}"
    cli.main(["open", "give-a-verdict", "--parent", gwid, "--step", tag])
    return f"{gwid}.{tag}"


# -- status renders one command per panelist, and who has returned ----------


def test_status_renders_one_dispatch_command_per_panelist_with_progress(workdir, capsys):
    _open_gate()
    review = _review_step("g1")
    capsys.readouterr()

    cli.main(["g1"])
    out = capsys.readouterr().out
    assert f"spine open give-a-verdict --parent g1 --step {review}.p1" in out
    assert DEFAULT_LENS in out                     # the lens select just named
    assert "claude-sonnet-5" in out                 # tier resolved, same as a dispatch
    assert "not dispatched" in out

    panelist = _open_panelist("g1", review)
    _fill_review(panelist, "pass")
    cli.main([panelist, "submit"])
    cli.main([panelist, "close"])
    capsys.readouterr()


def test_a_multi_panelist_step_shows_each_returned_or_outstanding(workdir, capsys):
    """run-a-gate's own panel is one reviewer by default; a panel step can
    carry more, and status must account for each one individually."""
    journal.append("g2", "run", title="t", assembly="run-a-gate")
    journal.append("g2", "step", id="review", segment="work",
                   panel=[{"worker": "reviewer", "criteria": "c1"},
                          {"worker": "reviewer", "criteria": "c2", "model": "light"}])
    journal.append("g2", "return", step="review", child="g2.review.p1",
                   fields={"verdict": "pass", "findings": "none"})
    capsys.readouterr()

    cli.main(["g2"])
    out = capsys.readouterr().out
    assert "panelist p1 (returned)" in out
    assert "panelist p2 (not dispatched)" in out
    assert "claude-haiku-4-5-20251001" in out  # p2's own model override resolves


# -- opening a panelist prefills the artifact and criteria, ids differ ------


def test_open_panelist_prefills_artifact_and_criteria_with_a_distinct_work_id(workdir, capsys):
    """The artifact reaches the panelist across a segment boundary now: the
    review step is minted into its own segment, so the implement round it
    reads is carried onto that step's prefill at the mint rather than looked
    up among its segment's own earlier rounds."""
    _open_gate()
    review = _review_step("g1")
    capsys.readouterr()

    panelist = _open_panelist("g1", review)
    capsys.readouterr()

    assert panelist == f"g1.{review}.p1"
    assert journal.location(panelist) == pathlib.Path(".agent-work", "g1", review, "p1")
    pst = runmod.state(panelist)
    assert pst["parent"] == "g1" and pst["parent_step"] == review  # base id, not the tag
    assert pst["prefill"]["criteria"] == DEFAULT_LENS
    assert pst["prefill"]["change"] == "adjusted the bound"     # the implement step's output
    assert pst["prefill"]["deviations"] == "waived: none"


def test_several_panelists_on_one_step_get_different_work_ids(workdir, capsys):
    journal.append("g3", "run", title="t", assembly="run-a-gate")
    journal.append("g3", "step", id="review", segment="work",
                   panel=[{"worker": "reviewer", "criteria": "c1"},
                          {"worker": "reviewer", "criteria": "c2"}])
    capsys.readouterr()

    p1 = _open_panelist("g3", "review", 1)
    p2 = _open_panelist("g3", "review", 2)
    capsys.readouterr()

    assert p1 == "g3.review.p1" and p2 == "g3.review.p2"
    assert journal.exists(p1) and journal.exists(p2)
    assert runmod.state(p1)["prefill"]["criteria"] == "c1"
    assert runmod.state(p2)["prefill"]["criteria"] == "c2"


def test_opening_an_untagged_or_out_of_range_panel_step_refuses(workdir, capsys):
    _open_gate()
    review = _review_step("g1")
    capsys.readouterr()
    with pytest.raises(SystemExit):
        cli.main(["open", "give-a-verdict", "--parent", "g1", "--step", review])
    with pytest.raises(SystemExit):
        cli.main(["open", "give-a-verdict", "--parent", "g1", "--step", f"{review}.p2"])


# -- the transition acts: pass releases, revise refills ---------------------


def test_pass_holds_for_the_conductors_form_and_close_proceeds_to_close(workdir, capsys):
    """A pass is inert -- its declared verb is `release`, which mints
    nothing -- so it no longer walks the gate on by itself: the review step
    stays open on its own conductor form, and `close` there is what proceeds.
    One manual step where review used to auto-walk, and the same three steps
    either way: neither voice mints anything on a clean round."""
    _open_gate()
    review = _review_step("g1")
    panelist = _open_panelist("g1", review)
    _fill_review(panelist, "pass")
    cli.main([panelist, "submit"])
    capsys.readouterr()

    cli.main([panelist, "close"])
    capsys.readouterr()

    st = runmod.state("g1")
    assert st["current"]["id"] == review              # held, not released
    assert st["current"]["form"] == "forms/ROUTE.toml"

    _fill_route("g1", "close")
    cli.main(["g1", "submit"])
    capsys.readouterr()

    st = runmod.state("g1")
    assert st["current"]["id"] == "close"
    # select minted the review step and nothing else did: one round, one panel
    assert [s["id"] for s in st["steps"]] == ["work-1", "select", review, "close"]


def test_rework_refills_with_every_panelists_findings_concatenated_and_attributed(workdir, capsys):
    """*What* refills is unchanged -- every panelist's findings, verbatim,
    concatenated and attributed -- but *who* says so is not: the revise
    holds the step open, and the conductor's own `rework` is what mints the
    round the findings ride into."""
    journal.append("g4", "run", title="t", assembly="run-a-gate")
    journal.append("g4", "step", id="work-1", segment="work", form="skills/implementer/forms/IMPLEMENT.toml",
                   filler="implementer", anchor=False, terminal=False, validates="", source="open")
    # the route form rides on the step beside the panel -- the real
    # two-voices shape `select`'s own mint writes; only the panel is
    # overridden here, to exercise attribution across more panelists than
    # run-a-gate's own SELECT.toml documents as defaults
    journal.append("g4", "step", id="review", segment="review",
                   form="forms/ROUTE.toml", source="mint",
                   panel=[{"worker": "reviewer", "criteria": "c1"},
                          {"worker": "reviewer", "criteria": "c2"}])
    _fill_implement("g4")
    cli.main(["g4", "submit"])
    capsys.readouterr()

    p1 = _open_panelist("g4", "review", 1)
    _fill_review(p1, "revise", "gap: the loop bound is still off by one")
    cli.main([p1, "submit"])
    p2 = _open_panelist("g4", "review", 2)
    _fill_review(p2, "pass", "beyond: could also fix the sibling parser")
    cli.main([p2, "submit"])
    capsys.readouterr()

    cli.main([p1, "close"])
    cli.main([p2, "close"])
    capsys.readouterr()

    st = runmod.state("g4")
    assert st["current"]["id"] == "review"   # the revise minted nothing on its own
    _fill_route("g4", "rework")
    cli.main(["g4", "submit"])
    capsys.readouterr()

    st = runmod.state("g4")
    fresh = next(s for s in st["steps"] if s["segment"] == "work" and s.get("source") == "mint")
    assert fresh["form"] == "skills/implementer/forms/IMPLEMENT.toml"
    findings = fresh["prefill"]["findings"]
    assert "off by one" in findings and "sibling parser" in findings  # both, verbatim
    assert findings.index("off by one") != findings.index("sibling parser")  # not merged into one line
    assert "[p1]" in findings and "[p2]" in findings                 # attributed

    # a fresh `select` exists too -- work's transition re-fires for the new
    # round, and it carries no panel: the next round's readers are chosen on
    # that form rather than copied off the round just judged. Nothing else in
    # the run carries a panel until select is submitted again.
    fresh_select = next(s for s in st["steps"]
                        if s["segment"] == "work" and s.get("form") == "forms/SELECT.toml")
    assert not fresh_select.get("panel")
    assert [s["id"] for s in st["steps"] if s.get("panel")] == ["review"]
    assert st["current"]["id"] == fresh["id"]                # work resumes, not close


def test_a_gates_impasse_verdict_rides_the_summary_up(workdir, capsys):
    """There is still no third verdict word: a root objection is a revise
    finding like any other, so the only way this gate's review ever ends
    without a final pass is the loop -- three revises the conductor sends
    back through the transition's own form, the third reaching the impasse
    (`impasse-after = 2`, ruling 2026-09-02: at most three critic dispatches
    per artifact), `advance` walking the gate on to its own close over the
    live revise (`up` now pauses rather than closing, so it cannot drive
    this scenario to a return any more -- see test_pause_gate.py for that
    path instead). The count is spent on the form's own `rework` now, which
    is the path the mint moved onto; `_summary` still stamps the panel's own
    last merged verdict onto the return, not the conductor's ruling on it,
    so the parent adjudicating sees what the panel actually said."""
    journal.append("issue9", "run", title="t", assembly="run-an-issue")
    journal.append("issue9", "step", id="g5", segment="execute", dispatches="run-a-gate",
                   prefill={"purpose": "p"}, child="issue9.g5", source="mint")
    cli.main(["open", "run-a-gate", "--parent", "issue9", "--step", "g5"])
    child = "issue9.g5"
    for n in range(3):
        _fill_implement(child)
        cli.main([child, "submit"])
        panel_id = _select(child)          # a fresh panel every round, chosen here
        panelist = _open_panelist(child, panel_id)
        _fill_review(panelist, "revise", f"gap: still off by one ({n})")
        cli.main([panelist, "submit"])
        cli.main([panelist, "close"])
        _fill_route(child, "rework")
        cli.main([child, "submit"])
    capsys.readouterr()

    st = runmod.state(child)
    assert st["current"]["form"] == "forms/IMPASSE.toml"
    _fill(journal.location(child) / "IMPASSE.toml",
          'ruling = "advance"\nwhy = "the diff stands as it is over the live revise"\n')
    cli.main([child, "submit"])
    _fill_route(child, "close")
    cli.main([child, "submit"])
    _fill(journal.location(child) / "GATE_CLOSE.toml",
          'commit = "refuse-or-name-the-escape @ 0000000"\nresidue = "waived: none"\n')
    cli.main([child, "submit"])
    cli.main([child, "close"])
    capsys.readouterr()

    ret = next(e for e in journal.read("issue9") if e["kind"] == "return")
    assert ret["summary"]["verdict"] == "revise"  # the panel's own word, not the ruling


def test_a_verdict_outside_the_vocabulary_refuses_at_the_panelists_submit(workdir, capsys):
    """The verdict is checked where it is written, not where it is merged.
    That is what makes `merged_verdict`'s fall-through to `pass` sound: a
    value nothing can act on never becomes a return for it to read."""
    _open_gate()
    review = _review_step("g1")
    panelist = _open_panelist("g1", review)
    _fill_review(panelist, "looks good to me")
    capsys.readouterr()

    with pytest.raises(SystemExit) as e:
        cli.main([panelist, "submit"])
    msg = str(e.value)
    assert "verdict" in msg and "pass | revise" in msg

    st = runmod.state(panelist)
    assert not st["done"]                            # the panelist did not advance
    assert review not in runmod.state("g1")["done"]  # and nothing returned to the gate

    # one edit is the whole way out of it
    _fill_review(panelist, "revise", findings="gap: the bound is still off")
    cli.main([panelist, "submit"])
    assert runmod.state(panelist)["done"]


# -- a gate cannot reach close without its review transition firing ---------


def test_a_gate_cannot_reach_close_without_review_having_fired(workdir, capsys):
    """The failure this whole gate exists to close: a suite (or a run) that
    never drives review would let a gate close in silence. `close` must
    refuse loudly while review is outstanding, and the worklist must not
    offer `close` as reachable until review completes."""
    _open_gate()
    review = _review_step("g1")
    capsys.readouterr()

    st = runmod.state("g1")
    assert st["current"]["id"] == review  # not close -- work-1 and select did not release it

    # Asserting only that the step id appears is what let a wrong escape
    # survive here once: the message named the right step and offered a
    # fill-or-waive way out that a panel step has no way to use.
    with pytest.raises(SystemExit) as e:
        cli.main(["g1", "close"])
    msg = str(e.value)
    assert review in msg
    assert "panelists complete it" in msg      # the escape that fits this kind
    assert f"amend close {review}" in msg      # and the one that always exists
    assert "waived:" not in msg                # never the one that cannot work

    with pytest.raises(SystemExit) as e:
        cli.main(["g1", "submit"])  # a panel step is never itself submitted
    assert "outstanding" in str(e.value)
    assert "waived:" not in str(e.value)


def test_the_panel_step_refusal_offers_an_escape_that_fits(workdir, capsys):
    """Submitting a panel step is a category error, not an unfilled field. The
    generic fill-or-waive escape does not apply -- there is no form."""
    _open_gate("gt")
    capsys.readouterr()

    with pytest.raises(SystemExit) as e:
        cli.main(["gt", "submit"])
    msg = str(e.value)
    assert "outstanding" in msg
    assert "waived:" not in msg


def test_every_close_refusal_escape_is_a_command_that_runs(workdir, capsys):
    """An escape that names the wrong command is the same defect as one that
    names none: the agent types what it was told and nothing happens. Each
    kind of pending step gets the command that actually moves it."""
    _open_gate()
    capsys.readouterr()

    with pytest.raises(SystemExit) as e:      # pending panel step
        cli.main(["g1", "close"])
    assert "panelists complete it" in str(e.value)

    _pass_the_panel("g1")                      # now the pending step is a form
    capsys.readouterr()
    with pytest.raises(SystemExit) as e:
        cli.main(["g1", "close"])
    msg = str(e.value)
    assert "spine g1 submit" in msg            # the verb, not a bare status call
    assert "amend close" in msg
    assert "waived:" not in msg


def test_a_returned_amend_still_names_what_was_amended(workdir):
    """render.amends calls itself the whole enforcement of the freeze: the tier
    above reads it and accepts or contests. Rendered from a child's return it
    dropped the verb and the step id, so the tier above could see that
    something was amended but never what."""
    from engine import render
    _open_gate()
    review = _review_step("g1")
    cli.main(["g1", "amend", "close", review, "--reason", "no panel needed"])

    st = runmod.state("g1")
    direct = render.amends(st["amends"])
    returned = render.amends(cli._summary(st)["amends"])
    assert direct == returned          # the tier above sees what the run sees
    assert f"close {review}" in returned[0]


def test_dropping_review_is_loud_in_the_parents_adjudication_view(workdir):
    """A gate that reaches close without review has graded its own work. The
    freeze is visibility, not refusal: amending review away stays one
    journaled step, and the tier above must see that it happened."""
    from engine import render
    _open_gate()
    review = _review_step("g1")
    cli.main(["g1", "amend", "close", review, "--reason", "in a hurry"])

    st = runmod.state("g1")
    amend = st["amends"][0]
    assert amend["anchor"] is True             # the mint copied the flag off the declaration

    line = render.amends(cli._summary(st)["amends"])[0]
    assert line.startswith("ANCHOR ")          # flagged where the parent reads it
    assert f"close {review}" in line and "in a hurry" in line


# -- a dispatched panelist can rule up mid-verdict, and resumes correctly ---


def test_a_dispatched_reviewer_asks_mid_verdict_resumes_once_and_the_verdict_survives(
        workdir, capsys):
    cli.main(["open", "run-a-gate", "--id", "gpx"])
    _fill_implement("gpx")
    cli.main(["gpx", "submit"])
    review = _select("gpx")
    panelist = _open_panelist("gpx", review)
    capsys.readouterr()

    cli.main([panelist, "up", "the diff touches a file the spec never named -- in scope?"])
    capsys.readouterr()

    gate_state = runmod.state("gpx")
    review_step = next(s for s in gate_state["steps"] if s["id"] == review)
    assert runmod.panel_outstanding(gate_state, review_step)
    assert not gate_state["returns"].get(review, [])
    ask = next(s for s in gate_state["steps"]
               if s.get("form") == "skills/gate-conductor/forms/ASK.toml")
    assert ask["segment"] == review_step["segment"]

    panelist_state = runmod.state(panelist)
    assert panelist_state["open"], "up must pause the reviewer's own run, not close it"

    (journal.location("gpx") / "ASK.toml").write_text(
        'answer = "yes -- the touched file is in scope, note it in the diff summary"\n')
    cli.main(["gpx", "submit"])
    capsys.readouterr()

    resumed = runmod.state(panelist)
    not_done = [s for s in resumed["steps"] if s["id"] not in resumed["done"]]
    assert len(not_done) == 1, (
        f"resume must mint exactly one fresh round, not {len(not_done)}: {not_done}")
    assert not_done[0]["form"] == "skills/reviewer/forms/REVIEW.toml"
    assert not_done[0]["terminal"], "the resumed round must be the segment's terminal step"

    _fill_review(panelist, "revise",
                 findings="gap: the touched file needs its own line in the diff summary")
    cli.main([panelist, "submit"])
    cli.main([panelist, "close"])

    gate_state = runmod.state("gpx")
    ret = gate_state["returns_by_child"].get(panelist)
    assert ret, "no return reached the parent"
    assert ret["fields"]["verdict"] == "revise", (
        "the panelist's actual ruling must reach the parent, not fall through empty: "
        f"{ret['fields']}")


def test_a_critic_panelist_asks_mid_verdict_and_resumes_into_its_own_form(workdir, capsys):
    journal.append("gcz", "run", title="t", assembly="run-a-gate")
    journal.append("gcz", "step", id="review", segment="work",
                   panel=[{"form": "skills/critic/forms/CRITIC.toml", "worker": "critic",
                           "criteria": "testability"}])
    capsys.readouterr()

    panelist = _open_panelist("gcz", "review")
    st = runmod.state(panelist)
    assert st["current"]["form"] == "skills/critic/forms/CRITIC.toml"
    assert st["current"]["filler"] == "critic"

    cli.main([panelist, "up", "is this in scope for the plan under review?"])
    capsys.readouterr()

    (journal.location("gcz") / "ASK.toml").write_text('answer = "yes, it is in scope"\n')
    cli.main(["gcz", "submit"])
    capsys.readouterr()

    resumed = runmod.state(panelist)
    not_done = [s for s in resumed["steps"] if s["id"] not in resumed["done"]]
    assert len(not_done) == 1, (
        f"resume must mint exactly one fresh round, not {len(not_done)}: {not_done}")
    assert not_done[0]["form"] == "skills/critic/forms/CRITIC.toml", (
        "a critic-role panelist must resume into its own panel-entry form, "
        f"not {not_done[0].get('form')}")
    assert not_done[0]["filler"] == "critic"
    assert not_done[0]["terminal"]
