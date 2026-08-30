"""A gate id names one gate, closed or not.

`_mint_gates` numbers a fresh pair by suffixing on collision -- until #56,
against live ids only. `amend close` (the mechanism `drop` and `remint`
both use) drops a step out of the *folded* worklist so the run can move on,
but the raw journal still holds it. A mint that reads only the folded view
sees the freed id as available again, and hands it to a second, unrelated
spec: on #7 the journal came to read step -> amend close -> step for one
id, `g2`, naming two different gates. `trace`, `drop <gate-id>` and a later
`amend close` all address an ambiguous name once that happens.

Both tests below pin DESIRED behaviour: the fixed `_mint_gates` reads ids
from the raw journal, not the fold, so a closed id stays spent.
"""

import pathlib

import pytest

from engine import cli, journal, run as runmod
from gitremote import init_checkout
from test_nesting import (_dispatch_and_close_child, _fill_gate_transition_drop,
                          _mint_n_gates, _replan_to_next_gate)

REPO = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONSTELLATION_SESSION", "test-session")
    (tmp_path / "constellation.toml").write_text((REPO / "constellation.toml").read_text())
    init_checkout(tmp_path)
    return tmp_path


def test_mint_gates_does_not_reissue_an_amend_closed_id(workdir):
    """Direct at the changed unit, no plan/critic machinery: mint a gate,
    amend-close it the way `drop` does, then mint again with no explicit id
    -- the same "default to g1" a remint always asks for. The folded view
    shows the slot as empty; the raw journal does not."""
    wid = "solo"
    seg = {"id": "execute", "dispatches": "run-a-gate",
           "adjudication-form": "forms/GATE_TRANSITION.toml"}
    cli._mint_gates(wid, seg, [{"purpose": "first spec", "scope": "s1", "proof": "true"}])
    journal.append(wid, "amend", action="close", segment="execute", step="g1",
                   reason="drop g1", anchor=False)
    journal.append(wid, "amend", action="close", segment="execute", step="g1-adjudicate",
                   reason="drop g1", anchor=False)

    # the fold is exactly what makes the id look free
    assert "g1" not in {s["id"] for s in runmod.state(wid)["steps"]}

    cli._mint_gates(wid, seg, [{"purpose": "second, unrelated spec", "scope": "s2",
                               "proof": "true"}])

    step_entries = [e for e in journal.read(wid) if e["kind"] == "step"]
    ids = [e["id"] for e in step_entries]
    assert ids.count("g1") == 1, ids             # the closed id was not reissued
    assert len(ids) == len(set(ids)), ids         # no id names two steps, live or closed
    fresh = next(e for e in step_entries if e["id"] not in ("g1", "g1-adjudicate"))
    assert fresh["prefill"]["purpose"] == "second, unrelated spec"
    assert fresh["id"] != "g1" and fresh["id"].startswith("g1-a")


def test_a_dropped_gate_does_not_donate_its_id_to_a_later_plan_round(workdir, capsys):
    """The real #7/#56 story, end to end: g3 is minted, then dropped before
    it ever dispatches. A later plan round projects a fresh gate that lands
    at the position the folded view now counts as next -- the same position
    g3 held. DESIRED behaviour: the new gate is not named "g3"; that name
    is already spent, and the journal never carries two step entries under
    it."""
    _mint_n_gates(3)
    capsys.readouterr()
    _dispatch_and_close_child("issue17", "g1")
    capsys.readouterr()

    _fill_gate_transition_drop("issue17", "g3")
    cli.main(["issue17", "submit"])
    capsys.readouterr()
    dropped = {a["step"] for a in journal.read("issue17") if a["kind"] == "amend"}
    assert dropped == {"g3", "g3-adjudicate"}

    _dispatch_and_close_child("issue17", "g2")
    capsys.readouterr()
    _replan_to_next_gate("issue17", "g2", purpose="reused-id probe", scope="probe scope")
    capsys.readouterr()

    st = runmod.state("issue17")
    new_gates = [s for s in st["steps"] if s.get("dispatches") == "run-a-gate"
                and s["id"] not in ("g1", "g2")]
    assert len(new_gates) == 1
    new_gate = new_gates[0]
    assert new_gate["id"] != "g3"                            # the freed-looking id stayed spent
    assert new_gate["prefill"]["purpose"] == "reused-id probe"

    step_ids = [e["id"] for e in journal.read("issue17") if e["kind"] == "step"]
    assert len(step_ids) == len(set(step_ids)), step_ids     # no id named twice
