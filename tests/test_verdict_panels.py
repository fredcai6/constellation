"""The review transition dispatches its panel, collects verdicts, and acts.

Drives real `run-a-gate` and `give-a-verdict` assemblies -- not fixtures. A
panelist is a child run one level finer than a gate dispatch, opened through
the same `--parent`/`--step` mechanism with a `.pN` tag naming which panel
entry. These tests prove the four things the review transition promises:
status renders a copyable command per panelist; opening one prefills the
artifact and criteria; the merged verdict acts (pass releases, revise
refills with concatenated attributed findings, escalate releases and rides
the summary); and a gate cannot reach close without review having fired.
"""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from engine import cli, journal, run as runmod  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONSTELLATION_SESSION", "test-session")
    (tmp_path / "constellation.toml").write_text((REPO / "constellation.toml").read_text())
    return tmp_path


def _fill(path, text):
    pathlib.Path(path).write_text(text)


def _fill_implement(wid):
    _fill(journal.location(wid) / "IMPLEMENT.toml",
         'change = "adjusted the bound"\ndeviations = "waived: none"\n')


def _fill_review(wid, verdict, findings="none: waived: clean"):
    _fill(journal.location(wid) / "REVIEW.toml", '''
verify = "read the diff line by line"
findings = "%s"
vocabulary = "waived: consistent"
verdict = "%s"
''' % (findings, verdict))


def _open_gate(gid="g1"):
    """A standalone run-a-gate, opened top-level the way test_robustness.py's
    hanging-check test does -- no run-an-issue plumbing needed to exercise
    the review transition."""
    cli.main(["open", "run-a-gate", "--id", gid])
    _fill_implement(gid)
    cli.main([gid, "submit"])
    return gid


def _pass_the_panel(gwid, step_id="review"):
    """Drive the panel to a pass so the gate's next pending step is its
    ordinary close form."""
    wid = _open_panelist(gwid, step_id)
    _fill_review(wid, "pass")
    cli.main([wid, "submit"])
    cli.main([wid, "close"])


def _open_panelist(gwid, step_id, n=1):
    tag = f"{step_id}.p{n}"
    cli.main(["open", "give-a-verdict", "--parent", gwid, "--step", tag])
    return f"{gwid}.{tag}"


# -- status renders one command per panelist, and who has returned ----------


def test_status_renders_one_dispatch_command_per_panelist_with_progress(workdir, capsys):
    _open_gate()
    capsys.readouterr()

    cli.main(["g1"])
    out = capsys.readouterr().out
    assert "spine open give-a-verdict --parent g1 --step review.p1" in out
    assert "the gate spec, whole and only" in out  # the panelist's own criteria
    assert "claude-sonnet-5" in out                 # tier resolved, same as a dispatch
    assert "outstanding" in out

    panelist = _open_panelist("g1", "review")
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
    assert "panelist p2 (outstanding)" in out
    assert "claude-haiku-4-5-20251001" in out  # p2's own model override resolves


# -- opening a panelist prefills the artifact and criteria, ids differ ------


def test_open_panelist_prefills_artifact_and_criteria_with_a_distinct_work_id(workdir, capsys):
    _open_gate()
    capsys.readouterr()

    panelist = _open_panelist("g1", "review")
    capsys.readouterr()

    assert panelist == "g1.review.p1"
    assert journal.location(panelist) == pathlib.Path(".agent-work", "g1", "review", "p1")
    pst = runmod.state(panelist)
    assert pst["parent"] == "g1" and pst["parent_step"] == "review"  # base id, not the tag
    assert pst["prefill"]["criteria"] == "the gate spec, whole and only"
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
    capsys.readouterr()
    with pytest.raises(SystemExit):
        cli.main(["open", "give-a-verdict", "--parent", "g1", "--step", "review"])
    with pytest.raises(SystemExit):
        cli.main(["open", "give-a-verdict", "--parent", "g1", "--step", "review.p2"])


# -- the transition acts: pass releases, revise refills, escalate releases --


def test_pass_releases_and_the_gate_proceeds_to_close(workdir, capsys):
    _open_gate()
    panelist = _open_panelist("g1", "review")
    _fill_review(panelist, "pass")
    cli.main([panelist, "submit"])
    capsys.readouterr()

    cli.main([panelist, "close"])
    capsys.readouterr()

    st = runmod.state("g1")
    assert st["current"]["id"] == "close"           # released straight through
    assert [s["id"] for s in st["steps"]] == ["work-1", "review", "close"]  # nothing minted


def test_revise_refills_with_every_panelists_findings_concatenated_and_attributed(workdir, capsys):
    journal.append("g4", "run", title="t", assembly="run-a-gate")
    journal.append("g4", "step", id="work-1", segment="work", form="skills/implementer/forms/IMPLEMENT.toml",
                   filler="implementer", anchor=False, terminal=False, validates="", source="open")
    journal.append("g4", "step", id="review", segment="work",
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
    fresh = next(s for s in st["steps"] if s["segment"] == "work" and s.get("source") == "mint")
    assert fresh["form"] == "skills/implementer/forms/IMPLEMENT.toml"
    findings = fresh["prefill"]["findings"]
    assert "off by one" in findings and "sibling parser" in findings  # both, verbatim
    assert findings.index("off by one") != findings.index("sibling parser")  # not merged into one line
    assert "[p1]" in findings and "[p2]" in findings                 # attributed

    # a fresh review step exists too -- the panel re-fires for the new round
    fresh_review = next(s for s in st["steps"]
                        if s.get("panel") and s["id"] not in ("review",))
    assert fresh_review["panel"] == st["steps"][1]["panel"]  # same panel config carried forward
    assert st["current"]["id"] == fresh["id"]                # work resumes, not close


def test_escalate_releases_like_pass_and_the_verdict_rides_the_summary(workdir, capsys):
    journal.append("issue9", "run", title="t", assembly="run-an-issue")
    journal.append("issue9", "step", id="g5", segment="execute", dispatches="run-a-gate",
                   prefill={"purpose": "p"}, child="issue9.g5", source="mint")
    cli.main(["open", "run-a-gate", "--parent", "issue9", "--step", "g5"])
    _fill_implement("issue9.g5")
    cli.main(["issue9.g5", "submit"])
    panelist = _open_panelist("issue9.g5", "review")
    _fill_review(panelist, "escalate", "gap: the spec asks for the wrong file entirely")
    cli.main([panelist, "submit"])
    cli.main([panelist, "close"])
    capsys.readouterr()

    st = runmod.state("issue9.g5")
    assert st["current"]["id"] == "close"  # released, exactly like pass
    _fill(journal.location("issue9.g5") / "GATE_CLOSE.toml", 'residue = "waived: none"\n')
    cli.main(["issue9.g5", "submit"])
    cli.main(["issue9.g5", "close"])
    capsys.readouterr()

    ret = next(e for e in journal.read("issue9") if e["kind"] == "return")
    assert ret["summary"]["verdict"] == "escalate"  # stamped up for the parent to adjudicate


# -- a gate cannot reach close without its review transition firing ---------


def test_a_gate_cannot_reach_close_without_review_having_fired(workdir, capsys):
    """The failure this whole gate exists to close: a suite (or a run) that
    never drives review would let a gate close in silence. `close` must
    refuse loudly while review is outstanding, and the worklist must not
    offer `close` as reachable until review completes."""
    _open_gate()
    capsys.readouterr()

    st = runmod.state("g1")
    assert st["current"]["id"] == "review"  # not close -- work-1 alone did not release it

    # Asserting only that "review" appears is what let a wrong escape survive
    # here once: the message named the right step and offered a fill-or-waive
    # way out that a panel step has no way to use.
    with pytest.raises(SystemExit) as e:
        cli.main(["g1", "close"])
    msg = str(e.value)
    assert "review" in msg
    assert "panelists complete it" in msg      # the escape that fits this kind
    assert "amend close review" in msg         # and the one that always exists
    assert "waived:" not in msg                # never the one that cannot work

    with pytest.raises(SystemExit) as e:
        cli.main(["g1", "submit"])  # a panel step is never itself submitted
    assert "outstanding" in str(e.value)
    assert "waived:" not in str(e.value)


def test_the_panel_step_refusal_offers_an_escape_that_fits(workdir, capsys):
    """Submitting a panel step is a category error, not an unfilled field. The
    generic fill-or-waive escape does not apply -- there is no form."""
    cli.main(["open", "run-a-gate", "--id", "gt"])
    pathlib.Path(".agent-work/gt/IMPLEMENT.toml").write_text(
        'change = "c"\ndeviations = "waived: none"\n')
    cli.main(["gt", "submit"])
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
