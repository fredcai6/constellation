"""`_role_tier`'s own contract.

`render.brief` calls this to fill in a form step's tier. Each of the
function's promises gets its own test rather than one sweep.

See: #100
"""

import pathlib

import pytest

from engine import cli, run as runmod


def test_an_unlisted_conductor_runs_standard_under_every_assembly(bare_workdir):
    """Heavy needs the owner's authorization, so the bare indirection never
    reaches it by default, whichever assembly's conductor it stands for."""
    pathlib.Path("constellation.toml").write_text(
        '[models]\nstandard = "s"\nheavy = "h"\n[roles]\nplanner = "standard"\n')
    assert runmod.load_assembly("run-an-issue")["conductor"] == "issue-conductor"
    assert runmod.load_assembly("run-a-gate")["conductor"] == "gate-conductor"

    assert cli._role_tier("conductor") == "standard"


def test_a_repository_can_authorize_a_heavy_conductor(bare_workdir):
    """The one way to heavy is the owner writing it down."""
    pathlib.Path("constellation.toml").write_text(
        '[roles]\nconductor = "heavy"\nplanner = "standard"\n')

    assert cli._role_tier("conductor") == "heavy"


def test_planner_resolves_to_standard(bare_workdir):
    pathlib.Path("constellation.toml").write_text(
        '[roles]\nplanner = "standard"\nimplementer = "standard"\n')

    assert cli._role_tier("planner") == "standard"


def test_implementer_resolves_to_standard(bare_workdir):
    pathlib.Path("constellation.toml").write_text(
        '[roles]\nplanner = "standard"\nimplementer = "standard"\n')

    assert cli._role_tier("implementer") == "standard"


def test_an_unmapped_role_refuses_and_names_the_missing_role(bare_workdir):
    """A `filler` that is neither the bare `"conductor"` indirection nor
    present in `[roles]` is a refusal naming the missing role -- never a
    spawn under an empty or default runner. No real caller supplies a role
    like this, so a synthetic name is enough to prove the refusal
    shape."""
    pathlib.Path("constellation.toml").write_text(
        '[roles]\nplanner = "standard"\nimplementer = "standard"\n')

    with pytest.raises(SystemExit) as e:
        cli._role_tier("stargazer")

    said = str(e.value)
    assert "stargazer" in said
    assert "planner" in said and "implementer" in said, (
        "the refusal does not name the entries that exist")


def test_an_unmapped_role_with_no_roles_table_still_refuses(bare_workdir):
    """No `[roles]` table at all is the same refusal, not a crash on a
    missing key and not a silent default runner."""
    pathlib.Path("constellation.toml").write_text('[models]\nstandard = "x"\n')

    with pytest.raises(SystemExit) as e:
        cli._role_tier("stargazer")

    said = str(e.value)
    assert "stargazer" in said
    assert "[roles]" in said
