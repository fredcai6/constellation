"""A response form is named for the step that fills it, not for the form
(#118).

`_response_path` used to be `pathlib.Path(step["form"]).stem + ".toml"` --
right exactly while a form is filled once per run. At a seam it is not:
round two used to open round one's own filled form, and two live fillers
could be handed the same path. Naming by step as well as by form makes both
impossible by construction: this file proves the property, not the
mechanism `engine/cli.py`'s own `[response-path-by-step]` rationale block
already argues for.
"""

from engine import cli, run as runmod

from test_nesting import _fill_spec, _response
from test_rework import (
    _dispatch_rework_round,
    _drive_to_revise,
    _drive_understand_to_revise,
    _dispatch_plan_critic,
)
from test_select_mint import _drive_gate_through


def test_two_rounds_at_one_seam_resolve_to_different_paths(workdir, capsys):
    """Round one's own plan-to-execute round already disposed of itself with
    `resolution = "incorporate"` by the time `_drive_to_revise` returns --
    that step is `done`, not `current`, but its response path is still
    resolvable. The planner's pass mints a fresh plan-to-execute step, and
    the two must not name the same file."""
    wid = _drive_to_revise()
    st = runmod.state(wid)
    round_one = next(s for s in st["steps"]
                     if s.get("form") == "forms/PLAN_TO_EXECUTE.toml" and s["id"] in st["done"])
    round_one_path = cli._response_path(st, round_one)

    _dispatch_rework_round(wid)
    st2 = runmod.state(wid)
    assert st2["current"]["form"] == "forms/PLAN_TO_EXECUTE.toml", (
        "this test no longer stands on the route form: "
        f"{st2['current'].get('form')}")
    round_two_path = cli._response_path(st2, st2["current"])

    assert round_one_path != round_two_path


def test_round_two_at_a_seam_renders_a_blank_route_form(workdir, capsys):
    """#118's own measurement, as a test: round one disposed of its round
    with `resolution = "incorporate"`; the room round two materializes must
    not still be holding that word."""
    wid = _drive_to_revise()
    _dispatch_rework_round(wid)
    _dispatch_plan_critic(wid, verdict="pass")  # no panel on round two: a no-op, the form stands
    capsys.readouterr()

    st = runmod.state(wid)
    assert st["current"]["form"] == "forms/PLAN_TO_EXECUTE.toml"

    cli.main([wid])  # the room materializes round two's blank form
    capsys.readouterr()
    body = cli._response_path(st, st["current"]).read_text()
    assert 'resolution = "incorporate"' not in body, (
        "round two's room opened round one's filled route form:\n" + body)


def test_two_consolidate_rounds_resolve_to_different_paths(workdir, capsys):
    """The understand seam's own counterpart: the opening consolidate round
    and the one the spec-writer's pass mints stand on the same form, and
    must not share a live path -- the first is filled, the second is the
    conductor's next word on the returned spec."""
    wid = _drive_understand_to_revise("issue84")
    capsys.readouterr()
    st = runmod.state(wid)
    round_one = next(s for s in st["steps"]
                     if s.get("form") == "forms/CONSOLIDATE.toml" and s["id"] in st["done"])
    round_one_path = cli._response_path(st, round_one)

    _fill_spec(wid)
    cli.main([wid, "submit"])
    capsys.readouterr()
    st2 = runmod.state(wid)
    assert st2["current"]["form"] == "forms/CONSOLIDATE.toml", (
        "this test no longer stands on the route form: "
        f"{st2['current'].get('form')}")

    assert cli._response_path(st2, st2["current"]) != round_one_path


def test_a_respawned_filler_adopts_its_step_but_a_fresh_one_does_not(workdir, capsys):
    """A filler re-spawned on the step already current gets the same path
    back and picks up the in-progress form (adopted); a filler spawned on
    the fresh round a revise mints gets a fresh path, carrying none of the
    abandoned filler's work (new work). Two independent `_response` reads
    stand in for two separate processes, since nothing about resolving the
    path depends on which process asks."""
    gid = _drive_gate_through("g1", 1)  # one revise round landed; a fresh implement round is current
    capsys.readouterr()

    round_two_path = _response(gid)
    round_two_path.write_text('change = "still tracing the EOF branch"\n')

    respawned = _response(gid)  # a second filler, spawned fresh on the same step
    assert respawned == round_two_path
    assert respawned.read_text() == 'change = "still tracing the EOF branch"\n', (
        "a re-spawned filler on the same step did not adopt the work in progress")

    # round one's own implement round, before the revise -- a fresh step,
    # and it must neither share round two's path nor carry its content
    st = runmod.state(gid)
    round_one = next(s for s in st["steps"]
                     if s.get("form") == "skills/implementer/forms/IMPLEMENT.toml"
                     and s["id"] in st["done"])
    round_one_path = cli._response_path(st, round_one)
    assert round_one_path != round_two_path, (
        "round one's own implement round shares round two's live path")
