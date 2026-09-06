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

from test_nesting import (
    _dispatch_and_close_plan,
    _fill,
    _fill_consolidate,
    _response,
)
from test_rework import (
    _dispatch_rework_round,
    _drive_to_revise,
    _drive_understand_to_impasse,
    _dispatch_plan_critic,
    _plan_impasse_after,
    _round,
)
from test_select_mint import _drive_gate_through


def test_two_rounds_at_one_seam_resolve_to_different_paths(workdir, capsys):
    """Round one's own plan-to-execute round already disposed of itself with
    `resolution = "rework"` by the time `_drive_to_revise` returns -- that
    step is `done`, not `current`, but its response path is still
    resolvable. Round two's rework mints a fresh plan-to-execute step, and
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
    with `resolution = "rework"`; the room round two materializes must not
    still be holding that word."""
    wid = _drive_to_revise()
    _dispatch_rework_round(wid)
    _dispatch_plan_critic(wid, verdict="pass")  # releases the panel, leaves the route form open
    capsys.readouterr()

    st = runmod.state(wid)
    assert st["current"]["form"] == "forms/PLAN_TO_EXECUTE.toml"

    cli.main([wid])  # the room materializes round two's blank form
    capsys.readouterr()
    body = cli._response_path(st, st["current"]).read_text()
    assert 'resolution = "rework"' not in body, (
        "round two's room opened round one's filled route form:\n" + body)


def test_understand_and_plan_impasses_share_a_form_but_not_a_path(workdir, capsys):
    """`understand` and `plan` both declare `forms/IMPASSE.toml`, so under
    the old naming they shared one live path -- a consolidate ruling left
    behind at `understand`'s impasse is what `plan`'s own impasse would
    have opened, sequentially, in the same run's own work location."""
    wid = _drive_understand_to_impasse("issue84")
    capsys.readouterr()
    st = runmod.state(wid)
    assert st["current"]["form"] == "forms/IMPASSE.toml"
    understand_path = cli._response_path(st, st["current"])

    _fill(_response(wid),
          'ruling = "advance"\nwhy = "both rounds landed on the wording"\n')
    cli.main([wid, "submit"])  # mints CONSOLIDATE alone, over the live revise
    capsys.readouterr()

    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    _dispatch_and_close_plan(wid)
    _dispatch_plan_critic(wid, verdict="revise", findings="gap: gate 1 is untestable")
    for n in range(1, _plan_impasse_after() + 1):
        _round(wid, f"gap: the proof still passes on an empty diff ({n})")
    capsys.readouterr()

    st2 = runmod.state(wid)
    assert st2["current"]["form"] == "forms/IMPASSE.toml", (
        "this test no longer stands on the impasse form: "
        f"{st2['current'].get('form')}")
    plan_path = cli._response_path(st2, st2["current"])

    assert understand_path != plan_path


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
