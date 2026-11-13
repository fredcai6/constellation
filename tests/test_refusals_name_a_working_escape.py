"""A refusal's second line is the move that gets past it. There is no
default: eleven refusals once inherited "fill it, or answer waived:" where
that was irrelevant or itself refused."""
import pytest

from engine import cli, forms, render


def test_a_refusal_with_no_escape_prints_none():
    assert render.refusal("reason", "amend needs --reason") == "reason: amend needs --reason"


def test_amend_without_a_reason_prints_the_amend_syntax(bare_workdir):
    with pytest.raises(SystemExit) as e:
        cli.main(["x1", "amend", "close", "work-1"])
    text = str(e.value)
    assert "waived:" not in text
    assert "amend close <step-id> --reason" in text


def test_a_block_list_given_a_single_value_is_not_offered_waived():
    form = {"fields": [{"id": "gates", "kind": "plan", "optional": False}]}
    with pytest.raises(SystemExit) as e:
        cli._check_plan({}, form, {"gates": "waived: none"})
    text = str(e.value)
    assert "does not take waived: or unknown:" in text
    assert "or answer  waived" not in text
    assert 'note blocked "<why gates is empty>"' in text


def test_an_optional_block_list_is_told_it_can_be_left_out():
    form = {"fields": [{"id": "calls", "kind": "plan", "optional": True}]}
    with pytest.raises(SystemExit) as e:
        cli._check_plan({}, form, {"calls": "waived: none"})
    assert "delete the field" in str(e.value)


NOTE = "blocking | accepted | rejected: <reason>"


def test_a_vocabulary_keeps_the_values_after_one_that_carries_a_reason():
    note = "satisfied | open: <reason> | deferred: <reason>\n\nmore"
    assert forms.vocabulary(note) == ["satisfied", "open", "deferred"]
    assert forms.reasoned(note) == ["open", "deferred"]
    assert forms.declared(NOTE) == ["blocking", "accepted", "rejected: <reason>"]


def _calls(call):
    form = {"fields": [{"id": "calls", "kind": "plan", "item": [
        {"id": "call", "kind": "decision", "note": NOTE}]}]}
    cli._check_calls(form, {"calls": [{"finding": "f", "call": call}]})


def test_a_call_that_owes_a_reason_refuses_without_one():
    with pytest.raises(SystemExit) as e:
        _calls("rejected")
    assert "'rejected' needs its reason" in str(e.value)
    assert "rejected: <reason>" in str(e.value)
    _calls("rejected: outside this gate's scope")
    _calls("accepted")


def test_an_unknown_call_is_shown_which_values_owe_a_reason():
    with pytest.raises(SystemExit) as e:
        _calls("maybe")
    assert "one of: blocking | accepted | rejected: <reason>" in str(e.value)


def test_a_field_the_run_acts_on_refuses_a_null_answer():
    from engine import run as runmod
    asm = runmod.load_assembly("run-a-gate")
    step = next(s for s in runmod.skeleton(asm) if s.get("id") == "review")
    with pytest.raises(SystemExit) as e:
        cli._outcome(asm, step, {"resolution": "waived: not sure"}, {"steps": [], "done": []})
    assert "is not a decision" in str(e.value)
    assert "rework" in str(e.value)
