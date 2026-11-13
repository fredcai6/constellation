"""A dispatched child's brief says "fill the form, then close". `close`
makes that true: standing on its last step with the form filled, it hands
the form in and then closes."""
import pytest

from engine import cli, journal
from engine import run as runmod
from test_nesting import _fill, _response
from test_verdict_wiring import _to_the_spec_panel


def test_a_panelists_close_hands_in_its_filled_form_first(workdir, capsys):
    wid, step_id = _to_the_spec_panel(capsys)
    cli.main(["open", "give-a-verdict", "--parent", wid, "--step", f"{step_id}.p1"])
    critic = f"{wid}.{step_id}.p1"
    _fill(_response(critic), 'findings = "waived: clean"\nverdict = "pass"\n')

    assert cli.main([critic, "close"]) in (0, None)

    assert runmod.state(critic)["closed"]
    assert any(e.get("kind") == "submit" for e in journal.read(critic))


def test_a_close_on_an_unfilled_last_form_still_refuses(workdir, capsys):
    wid, step_id = _to_the_spec_panel(capsys)
    cli.main(["open", "give-a-verdict", "--parent", wid, "--step", f"{step_id}.p1"])
    critic = f"{wid}.{step_id}.p1"
    cli.main([critic])            # materialises the blank form
    with pytest.raises(SystemExit) as e:
        cli.main([critic, "close"])
    assert "not complete" in str(e.value)
    assert not runmod.state(critic)["closed"]
