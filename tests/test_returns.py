"""Returns accumulate per step: a panel of N is satisfied only once N
panelists have each returned; a step with no panel still completes on one.
"""


from engine import journal, run as runmod


def _fixture(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONSTELLATION_SESSION", "test-session")


def test_single_child_dispatch_step_still_completes_on_one_return(tmp_path, monkeypatch):
    _fixture(tmp_path, monkeypatch)
    journal.append("issue1", "run", title="t")
    journal.append("issue1", "step", id="g1", segment="execute")  # no panel

    st = runmod.state("issue1")
    assert st["current"]["id"] == "g1"
    assert "g1" not in st["done"]

    journal.append("issue1", "return", step="g1", child="issue1.g1", fields={"x": "y"})
    st = runmod.state("issue1")

    assert "g1" in st["done"]
    assert st["done"]["g1"]["kind"] == "return"
    assert st["current"] is None
    assert st["returns_by_child"]["issue1.g1"]["fields"] == {"x": "y"}


def test_panel_step_stays_current_between_returns_and_completes_on_the_last(tmp_path, monkeypatch):
    _fixture(tmp_path, monkeypatch)
    journal.append("issue2", "run", title="t")
    journal.append("issue2", "step", id="review", segment="work",
                   panel=[{"worker": "reviewer"}, {"worker": "reviewer"}])

    journal.append("issue2", "return", step="review", child="issue2.review.p1",
                   fields={"verdict": "pass"})
    st = runmod.state("issue2")

    # one of two: the step is still current, its outstanding count is visible
    # to a caller as len(panel) - len(returns) -- no separate bookkeeping needed
    assert "review" not in st["done"]
    assert st["current"]["id"] == "review"
    assert [r["child"] for r in st["returns"]["review"]] == ["issue2.review.p1"]
    step = next(s for s in st["steps"] if s["id"] == "review")
    assert len(step["panel"]) - len(st["returns"]["review"]) == 1  # one outstanding

    journal.append("issue2", "return", step="review", child="issue2.review.p2",
                   fields={"verdict": "revise"})
    st = runmod.state("issue2")

    # two of two: done, both returns kept in arrival order and attributable
    assert "review" in st["done"]
    assert st["done"]["review"]["child"] == "issue2.review.p2"
    assert [r["child"] for r in st["returns"]["review"]] == \
        ["issue2.review.p1", "issue2.review.p2"]
    assert st["returns"]["review"][0]["fields"]["verdict"] == "pass"
    assert st["returns"]["review"][1]["fields"]["verdict"] == "revise"
    assert st["current"] is None

    # returns_by_child still resolves each panelist's own return individually
    assert st["returns_by_child"]["issue2.review.p1"]["fields"]["verdict"] == "pass"
    assert st["returns_by_child"]["issue2.review.p2"]["fields"]["verdict"] == "revise"


def test_a_later_step_stays_blocked_by_an_unfinished_panel(tmp_path, monkeypatch):
    """A panel step with returns outstanding must not let a following step
    read as current -- the fold's ordering, not just its per-step done-ness."""
    _fixture(tmp_path, monkeypatch)
    journal.append("issue3", "run", title="t")
    journal.append("issue3", "step", id="review", segment="work",
                   panel=[{"worker": "reviewer"}, {"worker": "reviewer"}, {"worker": "reviewer"}])
    journal.append("issue3", "step", id="close", segment="close")

    journal.append("issue3", "return", step="review", child="issue3.review.p1", fields={})
    journal.append("issue3", "return", step="review", child="issue3.review.p2", fields={})
    st = runmod.state("issue3")

    assert st["current"]["id"] == "review"  # two of three: still not done

    journal.append("issue3", "return", step="review", child="issue3.review.p3", fields={})
    st = runmod.state("issue3")

    assert st["current"]["id"] == "close"  # three of three: review clears
