"""`_role_tier`'s own contract, proven with no caller yet in the tree.

A later gate wires `render.brief` to call this to fill in a form step's
tier; wiring a real spawn is later still. Until then this is the only place
the function's promises are checked at all, so each bullet in issue100.g2's
own scope gets its own test rather than one sweep.
"""

import pathlib

import pytest

from engine import cli, run as runmod


def test_conductor_resolves_to_heavy_under_run_an_issue(bare_workdir):
    """The bare `"conductor"` indirection is reserved to heavy tier
    structurally -- checked before anything unwraps it to a concrete
    assembly's own conductor value. `run-an-issue`'s own `conductor` field
    is `"issue-conductor"`, named here only to show what this function
    deliberately never reads."""
    asm = runmod.load_assembly("run-an-issue")
    assert asm["conductor"] == "issue-conductor"

    assert cli._role_tier("conductor") == "heavy"


def test_conductor_resolves_to_heavy_under_run_a_gate_too(bare_workdir):
    """A second assembly, a different concrete conductor
    (`"gate-conductor"`) -- proving the reservation needs no second table
    entry and does not depend on which assembly's own conductor is asked,
    since `_role_tier` never reads `asm["conductor"]` at all."""
    asm = runmod.load_assembly("run-a-gate")
    assert asm["conductor"] == "gate-conductor"

    assert cli._role_tier("conductor") == "heavy"


def test_conductor_stays_heavy_even_with_a_conflicting_roles_entry(bare_workdir):
    """The `"conductor"` check has to run *before* the `[roles]` lookup, not
    merely need no entry there -- so a `[roles]` table that does carry a
    `conductor` key, mapped to something other than `"heavy"`, still resolves
    to `"heavy"`. A table-first variant (`roles.get(filler, ...)` before the
    equality check) would return `"standard"` here instead."""
    pathlib.Path("constellation.toml").write_text(
        '[roles]\nconductor = "standard"\nplanner = "standard"\n'
        'implementer = "standard"\n')

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
    like this yet, so a synthetic name is enough to prove the refusal
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
