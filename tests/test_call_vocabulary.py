"""Every call in the route forms' vocabulary says where the finding goes.

`blocking` rides into the next round, `beyond` leaves as a triage note that
reaches the close form, `rejected` and `accepted` go nowhere -- the first
owing a reason and the second owing nothing. Three of those four were true
before this; `beyond` was carried by asking the conductor to remember, at
close, what it had called several rounds earlier and retype it, which is the
transcription bug `[gate-projection]` already refused once.

And a call outside the vocabulary refuses. `_check_vocabulary` reaches a
form's own fields and stops there, so the one value the engine acts on from
inside a `kind = "plan"` row was never checked: `_blocking_calls` compares
against the literal `"blocking"`, so a typo read as not-blocking and dropped
its finding from the round's orders in silence.
"""

import pathlib

import pytest

from engine import cli, forms as formsmod, run as runmod

from test_nesting import (
    _dispatch_and_close_plan,
    _dispatch_plan_critic,
    _fill_consolidate,
    _fill_open,
    _fill_plan_route_with_calls,
    _work_the_board,
)

ROOT = pathlib.Path(runmod.__file__).resolve().parent.parent

CALL_BLOCK = '[[calls]]\nfinding = "f"\ncall = "blockign"\n'


ROUTE_FORMS = ("assemblies/run-an-issue/forms/PLAN_TO_EXECUTE.toml",
               "assemblies/run-an-issue/forms/CONSOLIDATE.toml",
               "assemblies/run-a-gate/forms/ROUTE.toml")


def _at_the_plan_route(wid="issue17", findings="F1: the retry budget is unbounded"):
    """Open a real run-an-issue and drive it to the plan seam's route form,
    the panel having returned `findings` -- a `pass` verdict so the panel does
    not dispose of its own round, leaving the form for the caller to rule on."""
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    _dispatch_and_close_plan(wid)
    _dispatch_plan_critic(wid, verdict="pass", findings=findings)
    return wid


def _triage(wid):
    return [n.get("text", "") for n in runmod.state(wid)["notes"]
            if n.get("kind_detail") == "triage"]


# -- 1. the vocabulary is declared, identically, and as a decision ----------


def test_every_route_form_declares_the_same_call_vocabulary(workdir):
    """Read off the forms rather than a list written here: the engine derives
    what it enforces from the item's own note, so a form that reworded its
    calls must not leave this test asserting the old words."""
    seen = {}
    for ref in ROUTE_FORMS:
        form = formsmod.load(ROOT / ref)
        calls = next(f for f in form["fields"] if f["id"] == "calls")
        item = next(i for i in calls["item"] if i["id"] == "call")
        assert formsmod.enforced_vocabulary(item), (
            f"{ref}: the call item declares no vocabulary the engine may "
            "enforce -- it needs kind = \"decision\"")
        seen[ref] = tuple(formsmod.enforced_vocabulary(item))
    assert len(set(seen.values())) == 1, f"the seams disagree on the vocabulary: {seen}"
    assert set(w.split(":")[0].strip() for w in next(iter(seen.values()))) == {
        "blocking", "accepted", "beyond", "rejected"}


# -- 2. a call outside the vocabulary refuses -------------------------------


def test_an_unknown_call_word_refuses_rather_than_reading_as_not_blocking(workdir, capsys):
    """The silent default this closes: `_blocking_calls` tests the literal
    word, so anything else was quietly non-blocking and its finding never
    reached the round's orders."""
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    _fill_open("issue17")
    cli.main(["issue17", "submit"])
    _work_the_board("issue17")
    _fill_consolidate("issue17", "rework",
                      calls=CALL_BLOCK)
    capsys.readouterr()

    with pytest.raises(SystemExit) as e:
        cli.main(["issue17", "submit"])
    said = str(e.value)
    assert "blockign" in said and "blocking" in said, said


# -- 3. beyond leaves as a triage note; accepted and rejected leave nothing --


def test_a_beyond_call_journals_a_triage_note(workdir, capsys):
    wid = _at_the_plan_route()
    capsys.readouterr()
    assert _triage(wid) == [], "nothing has been called beyond yet"

    _fill_plan_route_with_calls(
        wid, "rework",
        ("the retry budget is unbounded", "blocking"),
        ("the log format is inconsistent repo-wide", "beyond"),
        ("the name could be sharper", "accepted"),
        ("it double-frees", "rejected: line 40 frees once"))
    cli.main([wid, "submit"])
    capsys.readouterr()

    assert _triage(wid) == ["the log format is inconsistent repo-wide"], (
        "only the beyond call is a triage candidate; accepted and rejected "
        f"go nowhere, and blocking goes to the next round -- got {_triage(wid)}")


def test_the_triage_note_reaches_the_record_the_close_form_is_filled_from(workdir, capsys):
    """CLOSE.toml's own header promises the engine appends "the run's triage
    notes -- the candidates raised", and `_summary` is the record that writes
    them: the conductor fills the field from that, not from memory of a
    call it made several rounds earlier."""
    wid = _at_the_plan_route()
    _fill_plan_route_with_calls(wid, "rework",
                               ("the log format is inconsistent", "beyond"))
    cli.main([wid, "submit"])
    capsys.readouterr()

    raised = [t["text"] for t in cli._summary(runmod.state(wid))["triage"]]
    assert raised == ["the log format is inconsistent"], raised


def test_an_accepted_call_carries_nothing_into_the_next_round(workdir, capsys):
    """The rubber stamp: the round stands, nothing moves. A rework carries the
    blocking blocks alone, so an accepted finding must not arrive as orders."""
    wid = _at_the_plan_route()
    _fill_plan_route_with_calls(
        wid, "rework",
        ("the retry budget is unbounded", "blocking"),
        ("the name could be sharper", "accepted"))
    cli.main([wid, "submit"])
    capsys.readouterr()

    prefill = runmod.state(wid)["current"]["prefill"]["findings"]
    assert "retry budget" in prefill
    assert "could be sharper" not in prefill, (
        f"an accepted finding arrived as the round's orders: {prefill}")
    assert _triage(wid) == [], "an accepted finding is not a triage candidate"
