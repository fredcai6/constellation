"""Every call in the route forms' vocabulary says where the finding goes.

Run-an-issue's two one-look seams (`understand`, `plan`) share one
vocabulary now (ruling, 2026-09-25): `writer` rides into the incorporate
round the writer takes or rejects on its own judgement, `severe` is the call
that forces a `rewrite`, and `rejected: <reason>` is the record that it was
called and never becomes work here. Run-a-gate's own ROUTE.toml keeps its
older vocabulary unchanged -- its review seam still gets more than one look
-- but a finding has two destinations now, never a third (ruling,
2026-09-25, docs/PURPOSE.md): `beyond` is gone from every route form's
vocabulary, and what it named -- real, but not this seam's to answer -- is
a `rejected: <reason>` like any other.

And a call outside the vocabulary refuses. `_check_vocabulary` reaches a
form's own fields and stops there, so the one value the engine acts on from
inside a `kind = "plan"` row was never checked: `_blocking_calls` used to
compare against the literal `"blocking"`, so a typo read as not-blocking and
dropped its finding from the round's orders in silence; `_check_calls` is
what closes that now, read off each item's own declared vocabulary -- which
is also what refuses `beyond` outright: the word simply is not one of them.
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

CALL_BLOCK = '[[calls]]\nfinding = "f"\ncall = "writre"\n'

BEYOND_BLOCK = '[[calls]]\nfinding = "f"\ncall = "beyond"\n'


ONE_LOOK_FORMS = ("assemblies/run-an-issue/forms/PLAN_TO_EXECUTE.toml",
                  "assemblies/run-an-issue/forms/CONSOLIDATE.toml")

GATE_ROUTE_FORM = "assemblies/run-a-gate/forms/ROUTE.toml"


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


# -- 1. the vocabulary is declared, identically, and as a decision ----------


def test_the_two_one_look_forms_declare_the_same_call_vocabulary(workdir):
    """Read off the forms rather than a list written here: the engine derives
    what it enforces from the item's own note, so a form that reworded its
    calls must not leave this test asserting the old words."""
    seen = {}
    for ref in ONE_LOOK_FORMS:
        form = formsmod.load(ROOT / ref)
        calls = next(f for f in form["fields"] if f["id"] == "calls")
        item = next(i for i in calls["item"] if i["id"] == "call")
        assert formsmod.enforced_vocabulary(item), (
            f"{ref}: the call item declares no vocabulary the engine may "
            "enforce -- it needs kind = \"decision\"")
        seen[ref] = tuple(formsmod.enforced_vocabulary(item))
    assert len(set(seen.values())) == 1, f"the seams disagree on the vocabulary: {seen}"
    assert set(w.split(":")[0].strip() for w in next(iter(seen.values()))) == {
        "writer", "severe", "rejected"}


def test_run_a_gates_route_form_keeps_its_own_older_call_vocabulary(workdir):
    """Run-a-gate's review seam still gets more than one look, so ROUTE.toml
    is deliberately not folded into the one-look forms' shared vocabulary
    above -- the ruling that shrank understand and plan to one look left it
    alone. Its own vocabulary lost `beyond` the same way theirs did."""
    form = formsmod.load(ROOT / GATE_ROUTE_FORM)
    calls = next(f for f in form["fields"] if f["id"] == "calls")
    item = next(i for i in calls["item"] if i["id"] == "call")
    vocab = formsmod.enforced_vocabulary(item)
    assert set(w.split(":")[0].strip() for w in vocab) == {
        "blocking", "accepted", "rejected"}


# -- 2. a call outside the vocabulary refuses -------------------------------


def test_an_unknown_call_word_refuses_rather_than_reading_as_not_writer(workdir, capsys):
    """The silent default this closes: `_blocking_calls` used to test the
    literal word `"blocking"`, so anything else was quietly non-blocking and
    its finding never reached the round's orders. `_check_calls` refuses
    before the submit lands now, read off the item's own declared
    vocabulary -- so this fires the same way whether or not the resolution
    itself (`incorporate`) is one this round could legally take."""
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    _fill_open("issue17")
    cli.main(["issue17", "submit"])
    _work_the_board("issue17")
    _fill_consolidate("issue17", "incorporate",
                      calls=CALL_BLOCK)
    capsys.readouterr()

    with pytest.raises(SystemExit) as e:
        cli.main(["issue17", "submit"])
    said = str(e.value)
    assert "writre" in said and "writer" in said, said


def test_a_beyond_call_is_refused_at_submit(workdir, capsys):
    """The third destination is gone from the vocabulary, not merely
    discouraged: `beyond` is no longer a word any route form declares, so
    `_check_calls` refuses it exactly as it refuses any other undeclared
    word -- there is nothing left to carry it anywhere."""
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    _fill_open("issue17")
    cli.main(["issue17", "submit"])
    _work_the_board("issue17")
    _fill_consolidate("issue17", "incorporate", calls=BEYOND_BLOCK)
    capsys.readouterr()

    with pytest.raises(SystemExit) as e:
        cli.main(["issue17", "submit"])
    said = str(e.value)
    assert "beyond" in said and "not a call this step can act on" in said, said


# -- 3. rejected carries nothing forward; writer rides into the next round --


def test_a_rejected_call_carries_nothing_into_the_incorporate_round(workdir, capsys):
    """Only the `writer` calls ride into the incorporate round -- a
    `rejected` call is a record on this round's own `calls` table and
    nothing more; it never becomes a fresh round's prefill."""
    wid = _at_the_plan_route()
    route_step = runmod.state(wid)["current"]["id"]
    _fill_plan_route_with_calls(
        wid, "incorporate",
        ("the retry budget is unbounded", "writer"),
        ("the name could be sharper", "rejected: not this plan's to answer"))
    cli.main([wid, "submit"])
    capsys.readouterr()

    prefill = runmod.state(wid)["current"]["prefill"]["findings"]
    assert "retry budget" in prefill
    assert "could be sharper" not in prefill, (
        f"a rejected finding arrived as the round's own findings: {prefill}")

    calls = runmod.state(wid)["done"][route_step]["fields"]["calls"]
    rejected = next(c for c in calls if "sharper" in c["finding"])
    assert rejected["call"] == "rejected: not this plan's to answer"
