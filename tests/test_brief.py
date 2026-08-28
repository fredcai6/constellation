"""Self-location, and the brief a dispatch step renders.

Two things, proven separately. First: every command the engine prints
resolves to something a dispatched child -- no shell of its own, nothing on
PATH -- can actually run, proven deterministically with PATH stripped
entirely, no model involved. Second: a dispatch step and a panel step each
render one brief gathering the child id, its role, where that role is
written, the resolved tier and runner, a runnable open command, and what
finishing means -- proven for a gate dispatch (role: the dispatched
assembly's own conductor) and for a panelist (role: its own `worker`, which
need not match the assembly's).

Third: wherever a role is announced -- a dispatch brief, a panelist brief,
or the room an agent stands in -- the rendered line names the file the
posture is written in and says to read it. A role with no SKILL.md gets no
line, because naming a file that is not there is this defect inverted.
"""

import pathlib
import subprocess

import pytest

from engine import cli, journal, render

REPO = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONSTELLATION_SESSION", "test-session")
    (tmp_path / "constellation.toml").write_text((REPO / "constellation.toml").read_text())
    return tmp_path


def _mint_dispatch_step(wid="d1", child="d1.g1"):
    """The shape `_mint_gates` produces -- a run-an-issue standing on one
    execute-segment dispatch step -- built directly so the test does not
    need to drive a whole plan just to reach it."""
    journal.append(wid, "run", title="fix the parser", assembly="run-an-issue")
    journal.append(wid, "step", id="g1", segment="execute", dispatches="run-a-gate",
                   prefill={"purpose": "fix the parser", "scope": "src/parser.c",
                            "proof": "true"},
                   child=child, anchor=False, terminal=False, source="mint")


def _mint_panel_step(wid="g9", worker="reviewer"):
    """A review panel step with one entry -- the shape a gate's own review
    transition mints, built directly so a synthetic `worker` can be given
    without also standing up a whole gate."""
    journal.append(wid, "run", title="t", assembly="run-a-gate")
    journal.append(wid, "step", id="review", segment="work",
                   panel=[{"worker": worker, "criteria": "the gate spec, whole and only"}])


def _mint_work_step(wid="v1", filler="implementer"):
    """A work-segment step standing on run-a-gate's real interior, built
    directly so a synthetic `filler` can be given without the assembly's own
    conductor (`implementer`, `reviewer` -- both written) getting in the
    way."""
    journal.append(wid, "run", title="t", assembly="run-a-gate")
    journal.append(wid, "step", id="g1", segment="work",
                   form="skills/implementer/forms/IMPLEMENT.toml", filler=filler,
                   prefill={}, anchor=False, terminal=False, validates="", source="mint")


# -- self-location: deterministic, no model ----------------------------------


def test_spine_cmd_resolves_to_the_real_spine_file():
    path = pathlib.Path(render.spine_cmd())
    assert path.is_file() and path.name == "spine"


def test_located_swaps_the_bare_word_for_the_resolved_path():
    out = render.located("fill it, then: spine g1 submit")
    assert out == f"fill it, then: {render.spine_cmd()} g1 submit"
    # only the standalone word -- never a substring collision
    assert render.located("give-a-verdict") == "give-a-verdict"


def test_self_located_command_runs_with_path_stripped_entirely(tmp_path):
    """The scenario a dispatched child is actually in: nothing on PATH at
    all. A bare `spine` would fail with 'command not found'; the resolved
    path must not."""
    cmd = render.located("spine")
    assert cmd != "spine"
    r = subprocess.run([cmd], capture_output=True, text=True, env={},
                       cwd=tmp_path, timeout=20)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "no open runs" in r.stdout


# -- the brief: every ingredient, together ------------------------------------


def test_dispatch_brief_carries_every_ingredient(workdir, capsys):
    _mint_dispatch_step()
    capsys.readouterr()

    cli.main(["d1"])
    out = capsys.readouterr().out

    assert "d1.g1" in out                                    # the child id
    assert "role         implementer" in out                 # see role test below
    assert "tier         standard" in out
    assert "runner       claude-sonnet-5" in out              # the resolved runner
    assert "finishing:" in out and "GATE_CLOSE.toml" in out   # what finishing means

    line = next(l for l in out.splitlines() if "open it:" in l)
    open_cmd = line.split("open it:", 1)[1].strip()
    parts = open_cmd.split()
    assert pathlib.Path(parts[0]).is_file()                  # self-located, not bare
    assert parts[1:] == ["open", "run-a-gate", "--parent", "d1", "--step", "g1"]


def test_panel_brief_carries_every_ingredient(workdir, capsys):
    _mint_panel_step(worker="reviewer")
    capsys.readouterr()

    cli.main(["g9"])
    out = capsys.readouterr().out

    assert "g9.review.p1" in out                             # the child id
    assert "role         reviewer" in out
    assert "tier         standard" in out
    assert "runner       claude-sonnet-5" in out
    assert "finishing:" in out and "REVIEW.toml" in out
    assert "outstanding" in out

    line = next(l for l in out.splitlines() if "open it:" in l)
    open_cmd = line.split("open it:", 1)[1].strip()
    parts = open_cmd.split()
    assert pathlib.Path(parts[0]).is_file()
    assert parts[1:] == ["open", "give-a-verdict", "--parent", "g9", "--step", "review.p1"]


def test_the_dispatch_briefs_open_command_runs_with_path_stripped(workdir, capsys):
    """Not just well-formed -- actually runnable by whoever has nothing but
    what the brief handed them."""
    _mint_dispatch_step()
    capsys.readouterr()

    cli.main(["d1"])
    out = capsys.readouterr().out
    line = next(l for l in out.splitlines() if "open it:" in l)
    parts = line.split("open it:", 1)[1].strip().split()

    r = subprocess.run(parts, capture_output=True, text=True, env={},
                       cwd=workdir, timeout=20)
    assert r.returncode == 0, r.stdout + r.stderr
    assert journal.exists("d1.g1")


# -- role resolution: a dispatch vs. a panelist -------------------------------


def test_gate_dispatch_role_is_the_dispatched_assemblys_conductor(workdir, capsys):
    """run-a-gate's own conductor is `implementer` -- the brief must name
    that, not the dispatching run-an-issue's own conductor (`commander`)."""
    _mint_dispatch_step()
    capsys.readouterr()

    cli.main(["d1"])
    out = capsys.readouterr().out
    assert "role         implementer" in out
    assert "role         commander" not in out


def test_panelist_role_is_its_own_worker_not_the_assemblys_conductor(workdir, capsys):
    """give-a-verdict's own conductor is `reviewer`; a panel entry can name a
    different worker (a focused panelist), and the brief must show that
    entry's own role rather than the assembly's -- the reconciliation this
    issue's plan notes was already made, proven by giving the two different
    values and checking which one renders."""
    _mint_panel_step(worker="implementer")
    capsys.readouterr()

    cli.main(["g9"])
    out = capsys.readouterr().out
    assert "role         implementer" in out
    assert "role         reviewer" not in out


def test_a_panelist_brief_names_the_form_that_panelist_will_actually_get(workdir, capsys):
    """A panel entry may name its own form, and _open_child honours it. A brief
    quoting the assembly's default would name a file the agent is never handed
    -- the brief lying about the step it just told you to open. run-an-issue's
    critic panel overrides to CRITIC.toml, and no fixture exercised that."""
    cli.main(["open", "run-an-issue", "--id", "i1", "--title", "t"])
    journal.append("i1", "step", id="plan", segment="plan",
                   form="forms/PLAN_TO_EXECUTE.toml", filler="conductor",
                   panel=[{"form": "skills/critic/forms/CRITIC.toml",
                           "worker": "reviewer", "criteria": "c"}],
                   anchor=True, source="open")
    journal.append("i1", "submit", step="open", fields={})
    journal.append("i1", "submit", step="understand", fields={})
    journal.append("i1", "submit", step="plan-1", fields={})
    capsys.readouterr()

    cli.main(["i1"])
    out = capsys.readouterr().out
    assert "CRITIC.toml" in out, "the brief quoted the assembly default, not the override"
    assert "REVIEW.toml" not in out

    # and the file it names is the one actually materialized
    cli.main(["open", "give-a-verdict", "--parent", "i1", "--step", "plan.p1"])
    loc = journal.location("i1.plan.p1")
    assert (loc / "CRITIC.toml").exists()
    assert not (loc / "REVIEW.toml").exists()


# -- where the role is written ------------------------------------------------


def _posture_line(out):
    """The one rendered line naming a posture, or None. Both places that say
    it share `render.posture`'s wording, so one reader finds either."""
    return next((l for l in out.splitlines() if "SKILL.md" in l), None)


def _posture_text(line):
    """The substring `render.posture` actually returns -- the path and its
    imperative -- with the label before it stripped off. A brief and a room
    prefix that substring with different labels ("  your posture:" vs the
    room's own column), so comparing whole lines would fail on the label,
    not the posture."""
    idx = line.index(next(w for w in line.split() if w.endswith("SKILL.md")))
    return line[idx:]


def _assert_delivered(line, role):
    """What a posture line has to be to be worth anything: an absolute path,
    under the install root rather than the cwd the child happens to be in, to
    a file that is actually there -- and an instruction to read it."""
    assert line, "no rendered line names a posture"
    path = pathlib.Path(next(w for w in line.split() if w.endswith("SKILL.md")))
    assert path.is_absolute(), f"{path} is not absolute"
    assert path == REPO / "skills" / role / "SKILL.md", f"{path} is not under the install root"
    assert path.is_file(), f"{path} does not exist"
    assert "read it" in line, f"the line names a file but never says to read it: {line}"


def test_dispatch_brief_names_where_the_dispatched_role_is_written(workdir, capsys):
    """The defect in this issue's title: the child was told `implementer` and
    never told where `implementer` is written."""
    _mint_dispatch_step()
    capsys.readouterr()

    cli.main(["d1"])
    _assert_delivered(_posture_line(capsys.readouterr().out), "implementer")


def test_panelist_brief_names_where_its_own_role_is_written(workdir, capsys):
    """A panelist's role is its own `worker`, so the posture follows the
    worker and not give-a-verdict's conductor."""
    _mint_panel_step(worker="implementer")
    capsys.readouterr()

    cli.main(["g9"])
    _assert_delivered(_posture_line(capsys.readouterr().out), "implementer")


def test_panelist_brief_names_no_file_for_a_role_that_has_no_skill(workdir, capsys):
    """A panelist worker with no SKILL.md gets no posture line: naming one
    anyway would be this issue's own defect inverted -- a path to nothing.
    Proven against a fixture role rather than a rostered one with no
    directory today: pinning to a real role re-arms the staleness trap this
    test used to be, where a later SKILL.md for that role flips it green for
    the wrong reason instead of failing loudly."""
    _mint_panel_step(worker="ghostwriter")
    capsys.readouterr()

    cli.main(["g9"])
    out = capsys.readouterr().out
    assert "role         ghostwriter" in out
    assert _posture_line(out) is None, "the brief named a posture that does not exist"


def test_the_room_names_where_the_filler_of_this_step_is_written(workdir, capsys):
    """The second place a role is announced: the form step an agent is
    standing on. run-a-gate's work interior is filled by `implementer`."""
    cli.main(["open", "run-a-gate", "--id", "g1"])
    capsys.readouterr()

    cli.main(["g1"])
    out = capsys.readouterr().out
    _assert_delivered(_posture_line(out), "implementer")
    assert "your response form:" in out, "the posture displaced the form it sits beside"


def test_conductor_resolves_through_the_assembly_not_a_skills_conductor(workdir, capsys):
    """`filler = "conductor"` is an indirection, not a role. run-an-issue's
    open step declares it, and the assembly's conductor is `commander`."""
    cli.main(["open", "run-an-issue", "--id", "i1", "--title", "t"])
    capsys.readouterr()

    cli.main(["i1"])
    out = capsys.readouterr().out
    _assert_delivered(_posture_line(out), "commander")
    assert "skills/conductor" not in out


def test_the_room_names_no_file_for_a_filler_that_has_no_skill(workdir, capsys):
    """The room a filler with no SKILL.md stands in: silence, not a path to
    nothing. Proven against a fixture role, the same way the panelist case
    above is -- every rostered role either has a directory today or is one
    decision away from getting one, and pinning to a real one re-arms the
    staleness trap this test used to be."""
    _mint_work_step(filler="ghostwriter")
    capsys.readouterr()

    cli.main(["v1"])
    out = capsys.readouterr().out
    assert "your response form:" in out
    assert _posture_line(out) is None, "the room named a posture that does not exist"


# -- the stamp: a panelist's room matches its brief ---------------------------
#
# engine/cli.py's `_open_child` stamps a dispatched panelist's step with the
# panel entry's own `worker` (the comment above that line explains why:
# without it, the child keeps give-a-verdict's literal `reviewer` filler no
# matter which worker the panel entry names). The three tests below guard
# that stamp landing and staying landed.


def test_a_critic_panelists_room_names_the_critics_posture(workdir, capsys):
    """The defect this gate exists to correct: a critic panel entry's
    dispatched child must stand in a room naming `skills/critic/SKILL.md`,
    not give-a-verdict's own conductor (`reviewer`)."""
    _mint_panel_step(worker="critic")
    capsys.readouterr()

    cli.main(["open", "give-a-verdict", "--parent", "g9", "--step", "review.p1"])
    capsys.readouterr()

    cli.main(["g9.review.p1"])
    out = capsys.readouterr().out
    _assert_delivered(_posture_line(out), "critic")


def test_the_brief_and_the_room_name_the_same_posture_for_the_same_child(workdir, capsys):
    """The invariant the stamp buys and no other test states: the panel
    step's brief renders the posture from the panel entry's `worker`, and
    the panelist's own room -- once opened -- renders it from the child's
    stamped `filler`. Those two answers cannot diverge, or a child is told
    one thing on dispatch and stands somewhere else once it opens."""
    _mint_panel_step(worker="critic")
    capsys.readouterr()

    cli.main(["g9"])
    brief_line = _posture_line(capsys.readouterr().out)
    _assert_delivered(brief_line, "critic")

    cli.main(["open", "give-a-verdict", "--parent", "g9", "--step", "review.p1"])
    capsys.readouterr()

    cli.main(["g9.review.p1"])
    room_line = _posture_line(capsys.readouterr().out)
    _assert_delivered(room_line, "critic")

    assert _posture_text(brief_line) == _posture_text(room_line)


def test_a_reviewer_panelist_is_unmoved_by_a_neighboring_critic(workdir, capsys):
    """The stamp must not have moved every panelist to whatever the last
    entry said. Proven with a critic entry ahead of the reviewer entry in
    the same panel, both opened: a stamp that quietly defaulted every child
    to give-a-verdict's literal `reviewer` filler (what a no-op does) is
    caught here by the critic entry, even though the reviewer entry alone --
    already give-a-verdict's own default -- could never tell the two trees
    apart."""
    journal.append("g9", "run", title="t", assembly="run-a-gate")
    journal.append("g9", "step", id="review", segment="work",
                   panel=[{"worker": "critic", "criteria": "c"},
                          {"worker": "reviewer", "criteria": "c"}])
    capsys.readouterr()

    cli.main(["open", "give-a-verdict", "--parent", "g9", "--step", "review.p1"])
    capsys.readouterr()
    cli.main(["g9.review.p1"])
    _assert_delivered(_posture_line(capsys.readouterr().out), "critic")

    cli.main(["open", "give-a-verdict", "--parent", "g9", "--step", "review.p2"])
    capsys.readouterr()
    cli.main(["g9.review.p2"])
    _assert_delivered(_posture_line(capsys.readouterr().out), "reviewer")
