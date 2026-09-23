"""Commitment 5's brief, in two halves: the wording `_dispatch_lines` now
shares between `render.brief` and `render.status`'s standalone branch, and
`_form_filler_brief`, the standalone room a form-step filler stands in --
built from the same `_room_kwargs` derivation `cmd_status` uses so the two
never drift. No caller of `_form_filler_brief` exists yet (gate 4's
horizon): this proves the contract alone.
"""

import pathlib

from engine import cli, journal, render, run as runmod, forms


def _mint_work_step(wid="v1", filler="implementer", prefill=None):
    """The shape `test_brief.py`'s own `_mint_work_step` builds -- a
    run-a-gate work-segment step standing directly on its real interior,
    with a synthetic `filler` free to name a role the fixture does not have
    to also stand up an assembly for."""
    journal.append(wid, "run", title="t", assembly="run-a-gate")
    journal.append(wid, "step", id="g1", segment="work",
                   form="skills/implementer/forms/IMPLEMENT.toml", filler=filler,
                   prefill=prefill or {}, anchor=False, terminal=False,
                   validates="", source="mint")


def _mint_board_step(wid="i1", board_text=None):
    """A step standing on a board-carrying segment ("understand"), with a
    real board file at the path the step's own board entry names -- the
    shape `_mint`'s own two board-seeding call sites leave behind
    (`engine/cli.py:2423`, `:2439`)."""
    journal.append(wid, "run", title="t", assembly="run-an-issue")
    journal.append(wid, "step", id="consolidate", segment="understand",
                   form="forms/CONSOLIDATE.toml", filler="conductor",
                   prefill={}, anchor=True, terminal=False, validates="board", source="open")
    path = journal.location(wid) / "UNDERSTAND.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(board_text or (
        'imperative = "reach common understanding"\n\n'
        '[[question]]\n'
        'id = "q1"\n'
        'status = "open"\n'
        'question = "what breaks?"\n'
    ))
    journal.append(wid, "board", segment="understand", path=str(path), rows=[])


def _mint_conductor_step(wid="c1", assembly="run-an-issue", segment="open", form="forms/OPEN.toml"):
    """A transition step whose raw `filler` is the bare `"conductor"`
    indirection -- `_role_tier`'s always-heavy case, and `runmod.hat`'s
    plain (non-board) case, which unwraps to the assembly's own
    `conductor` field."""
    journal.append(wid, "run", title="t", assembly=assembly)
    journal.append(wid, "step", id=segment, segment=segment,
                   form=form, filler="conductor",
                   prefill={}, anchor=True, terminal=False, validates="", source="open")


def _mint_returned_child_step(wid="r1", child=None):
    """A synthetic follow-on step whose own `child` field names an
    already-returned dispatch -- the shape `_room_kwargs` reads through
    `st["returns_by_child"]`, minted directly rather than by driving a
    whole gate through to its own route step."""
    child = child or f"{wid}.g1"
    journal.append(wid, "run", title="t", assembly="run-a-gate")
    journal.append(wid, "step", id="g1", segment="work", dispatches="run-a-gate",
                   child=child, anchor=False, terminal=False, source="mint")
    journal.append(wid, "return", step="g1", child=child,
                   fields={"result": "ok"},
                   summary={"checks": [{"exit": 0, "command": "true"}]})
    journal.append(wid, "step", id="select", segment="work",
                   form="forms/SELECT.toml", filler="conductor", child=child,
                   prefill={}, anchor=False, terminal=False, validates="", source="mint")


def _current(wid):
    st = runmod.state(wid)
    asm = runmod.load_assembly(st["assembly"])
    step = st["current"]
    form = cli._load_form(asm, step["form"], wid, step["id"])
    return st, asm, step, form


def _materialized(st, step, form, wid, root=None):
    dest = cli._response_path(st, step, root=root)
    if not dest.exists():
        forms.materialize(form, dest, work_id=wid,
                          submit=render.located(f"spine {wid} submit"))
    return dest


# -- render.brief: unchanged, now built from the shared `_dispatch_lines` ----


def test_brief_matches_dispatch_lines_construction_with_tree():
    role, tier, runner = "gate-conductor", "standard", "claude-sonnet-5"
    worktree, branch = "/tmp/some-tree", "issue100"
    text = render.brief("d1.g1", role, tier, runner,
                         "GATE_CLOSE.toml", worktree=worktree, branch=branch)

    expected = render._dispatch_lines(role, tier, runner, worktree, branch,
                                      written_at=render.posture(role))
    lines = text.splitlines()
    assert lines[0] == "  brief -- d1.g1"
    assert lines[1:1 + len(expected)] == expected
    assert not any("open it:" in l for l in lines)
    assert lines[-1] == (f"    finishing:   fill GATE_CLOSE.toml, then: "
                         f"{render.located('spine d1.g1 close')}")


def test_brief_matches_dispatch_lines_construction_without_tree():
    role, tier, runner = "reviewer", "standard", "claude-sonnet-5"
    text = render.brief("g9.review.p1", role, tier, runner, "REVIEW.toml")

    expected = render._dispatch_lines(role, tier, runner, "", "",
                                      written_at=render.posture(role))
    lines = text.splitlines()
    assert lines[1:1 + len(expected)] == expected
    assert not any(l.strip().startswith("tree ") for l in lines)


# -- render.status: an ordinary room is unaffected ---------------------------


def test_status_ordinary_room_keeps_legal_moves_and_prints_no_dispatch_lines(workdir, capsys):
    _mint_work_step("v1")
    capsys.readouterr()

    cli.main(["v1"])
    out = capsys.readouterr().out

    assert "also legal:" in out
    assert not any(l.strip().startswith(("tier ", "runner ", "tree ")) for l in out.splitlines())


# -- render.status's standalone branch matches render.brief's own lines -----


def _dispatch_block(text):
    return [l for l in text.splitlines()
            if l.strip().startswith(("role ", "tier ", "runner ", "tree "))]


def test_status_standalone_dispatch_lines_match_brief_given_same_values(workdir):
    _mint_work_step("v1", filler="implementer")
    st, asm, step, form = _current("v1")
    dest = _materialized(st, step, form, "v1")
    kwargs = cli._room_kwargs("v1", st, asm, step, form, dest)

    tier, runner, worktree, branch = "standard", "claude-sonnet-5", "/tmp/tree", "issue100"
    status_out = render.status(st, form, dest, tier=tier, runner=runner,
                                worktree=worktree, branch=branch, **kwargs)
    brief_out = render.brief("v1.g1", kwargs["role"], tier, runner, "",
                              worktree=worktree, branch=branch)

    assert _dispatch_block(status_out) == _dispatch_block(brief_out)
    assert "role         implementer" in status_out
    assert "also legal:" not in status_out
    assert "note ..." not in status_out and "amend ..." not in status_out


def test_status_standalone_role_line_prints_once_for_a_role_with_a_posture(workdir):
    _mint_work_step("v1", filler="implementer")
    st, asm, step, form = _current("v1")
    dest = _materialized(st, step, form, "v1")
    kwargs = cli._room_kwargs("v1", st, asm, step, form, dest)

    out = render.status(st, form, dest, tier="standard", runner="claude-sonnet-5",
                        worktree="/tmp/tree", **kwargs)

    assert "role         implementer" in out
    assert out.count("SKILL.md") == 1, "the posture must print once, not twice"


def test_status_standalone_role_line_prints_for_a_role_with_no_posture(workdir):
    _mint_work_step("v1", filler="ghostwriter")
    st, asm, step, form = _current("v1")
    dest = _materialized(st, step, form, "v1")
    kwargs = cli._room_kwargs("v1", st, asm, step, form, dest)

    out = render.status(st, form, dest, tier="standard", runner="claude-sonnet-5",
                        worktree="/tmp/tree", **kwargs)

    assert "role         ghostwriter" in out, "the role line must still print"
    assert "SKILL.md" not in out


# -- cmd_status: regression across prefill, board, and a returned child -----


def test_cmd_status_still_renders_prefill(workdir, capsys):
    _mint_work_step("v1", prefill={"purpose": "fix the parser"})
    capsys.readouterr()

    cli.main(["v1"])
    out = capsys.readouterr().out
    assert "your orders" in out
    assert "fix the parser" in out


def test_cmd_status_still_renders_board_content(workdir, capsys):
    _mint_board_step("i1")
    capsys.readouterr()

    cli.main(["i1"])
    out = capsys.readouterr().out
    assert "the board:" in out
    assert "UNDERSTAND.toml" in out
    assert "q1" in out


def test_cmd_status_still_renders_a_returned_childs_fields(workdir, capsys):
    _mint_returned_child_step("r1")
    capsys.readouterr()

    cli.main(["r1"])
    out = capsys.readouterr().out
    assert "returns" in out
    assert "result" in out and "ok" in out


# -- _form_filler_brief: the same room cmd_status prints, plus the four -----


def _shared_body(text):
    """Every line up to whichever comes first: the dispatch block
    (`_form_filler_brief`'s own addition) or the posture/response-form tail
    -- the part of the room neither caller's own roots or additions touch.

    The board's own path line is normalized before comparing: it is the one
    other line commitment 5 deliberately makes the two callers disagree on
    -- `cmd_status` trusts whatever the board's stored entry says, unresolved,
    while `_form_filler_brief` re-resolves it absolute against its own root.
    Everything else on that line, and every other line, must still agree.
    """
    lines = text.splitlines()
    out = []
    for l in lines:
        if l.startswith("    role ") or l.startswith("  your posture:") \
                or l.startswith("  your response form:"):
            break
        if l.startswith("  the board:"):
            l = "  the board:          <path>"
        out.append(l)
    return out


def test_form_filler_brief_matches_cmd_status_body_for_a_board_step(workdir, capsys):
    _mint_board_step("i1")
    capsys.readouterr()

    cli.main(["i1"])
    status_out = capsys.readouterr().out

    st, asm, step, form = _current("i1")
    filler_out = cli._form_filler_brief("i1", st, asm, step, form)

    assert _shared_body(status_out) == _shared_body(filler_out)


def test_form_filler_brief_matches_cmd_status_body_for_prefill_and_in_hand(workdir, capsys):
    _mint_work_step("v1", prefill={"purpose": "fix the parser"})
    st, asm, step, form = _current("v1")
    dest = _materialized(st, step, form, "v1")
    # something already in hand on the response form
    dest.write_text(dest.read_text() + '\n[in_hand]\nchange = "working: half done"\n')
    capsys.readouterr()

    cli.main(["v1"])
    status_out = capsys.readouterr().out

    st2, asm2, step2, form2 = _current("v1")
    filler_out = cli._form_filler_brief("v1", st2, asm2, step2, form2)

    assert _shared_body(status_out) == _shared_body(filler_out)


# -- _form_filler_brief: tier/runner/tree off the step's own raw filler -----


def test_form_filler_brief_reports_tier_runner_tree_for_an_implementer_step(workdir):
    _mint_work_step("v1", filler="implementer")
    st, asm, step, form = _current("v1")

    out = cli._form_filler_brief("v1", st, asm, step, form)

    expected_tier = cli._role_tier("implementer")
    expected_runner = cli._runner(expected_tier)
    expected_worktree, expected_branch = cli._tree_info("v1", st)

    assert f"    tier         {expected_tier}" in out
    assert f"    runner       {expected_runner}" in out
    assert expected_worktree in out
    if expected_branch:
        assert expected_branch in out


# -- _form_filler_brief: the bare "conductor" indirection -------------------


def test_form_filler_brief_on_a_conductor_step_resolves_heavy_tier_and_matching_posture(
        workdir, capsys):
    _mint_conductor_step("c1", assembly="run-an-issue")
    st, asm, step, form = _current("c1")

    filler_out = cli._form_filler_brief("c1", st, asm, step, form)
    assert "    tier         heavy" in filler_out
    assert "    role         issue-conductor" in filler_out

    capsys.readouterr()
    cli.main(["c1"])
    status_out = capsys.readouterr().out

    expected_posture = render.posture("issue-conductor")
    assert expected_posture in filler_out
    assert expected_posture in status_out


def test_form_filler_brief_on_a_gate_conductor_step_resolves_heavy_tier_and_matching_posture(
        workdir, capsys):
    _mint_conductor_step("g1", assembly="run-a-gate", segment="select", form="forms/SELECT.toml")
    st, asm, step, form = _current("g1")

    filler_out = cli._form_filler_brief("g1", st, asm, step, form)
    assert "    tier         heavy" in filler_out
    assert "    role         gate-conductor" in filler_out

    capsys.readouterr()
    cli.main(["g1"])
    status_out = capsys.readouterr().out

    expected_posture = render.posture("gate-conductor")
    assert expected_posture in filler_out
    assert expected_posture in status_out


# -- _form_filler_brief: absolute paths, correct even off a stale root ------


def test_form_filler_brief_response_path_is_absolute_and_exists(workdir):
    _mint_work_step("v1", filler="implementer")
    st, asm, step, form = _current("v1")

    out = cli._form_filler_brief("v1", st, asm, step, form)
    line = next(l for l in out.splitlines() if "your response form:" in l)
    path = pathlib.Path(line.split("your response form:", 1)[1].strip())

    assert path.is_absolute()
    assert path.exists()


def test_form_filler_brief_board_path_ignores_a_stale_stored_directory(workdir):
    """The board's own stored path may have been minted against some other
    cwd entirely (`_board_path`'s whole reason to exist) -- `_form_filler_
    brief` must still land on the real, absolute path under this run's own
    tree, trusting the stored string only for its filename."""
    journal.append("i1", "run", title="t", assembly="run-an-issue")
    journal.append("i1", "step", id="consolidate", segment="understand",
                   form="forms/CONSOLIDATE.toml", filler="conductor",
                   prefill={}, anchor=True, terminal=False, validates="board", source="open")
    real_board = journal.location("i1") / "UNDERSTAND.toml"
    real_board.parent.mkdir(parents=True, exist_ok=True)
    real_board.write_text('imperative = "x"\n\n[[question]]\nid = "q1"\n'
                          'status = "open"\nquestion = "?"\n')
    stale = str(pathlib.Path("some-other-cwd-that-never-existed") / ".agent-work" / "i1"
               / "UNDERSTAND.toml")
    journal.append("i1", "board", segment="understand", path=stale, rows=[])

    st, asm, step, form = _current("i1")
    out = cli._form_filler_brief("i1", st, asm, step, form)

    assert "some-other-cwd-that-never-existed" not in out
    assert "the board:" in out
    assert str(real_board.resolve()) in out


# -- _form_filler_brief: correct even when the run lives in a nested tree ---


def test_form_filler_brief_resolves_absolute_paths_for_a_run_nested_in_a_worktree(workdir):
    """A run whose `.agent-work` lives inside a sibling worktree (ruling 8's
    own shape) rather than directly under this checkout -- `_tree_info`'s
    own `journal.root_for` finds it there, and `_form_filler_brief`'s paths
    must follow, not fall back to this checkout's own root."""
    wt = workdir / ".worktrees" / "nested"
    (wt / ".agent-work" / "n1").mkdir(parents=True)
    _mint_work_step("n1", filler="implementer")

    st, asm, step, form = _current("n1")
    out = cli._form_filler_brief("n1", st, asm, step, form)

    worktree, _branch = cli._tree_info("n1", st)
    assert worktree == str(wt.resolve())

    line = next(l for l in out.splitlines() if "your response form:" in l)
    path = pathlib.Path(line.split("your response form:", 1)[1].strip())
    assert path.is_absolute()
    assert str(wt.resolve()) in str(path)
    assert path.exists()


# -- the room says what the form already holds (#26) -------------------------


def _room(wid):
    """The room text `cmd_status` renders, built the way the file's other
    tests build it: mint, materialize, then render off `_room_kwargs`."""
    st, asm, step, form = _current(wid)
    dest = _materialized(st, step, form, wid)
    return dest, render.status(st, form, str(dest),
                               **cli._room_kwargs(wid, st, asm, step, form, dest))


def test_a_form_that_already_carries_answers_says_so(workdir):
    """#26: a stopped agent's response form is adopted by whoever stands on
    the step next -- deliberate (`_response_path`), and silent until now, so
    a panelist read a complete critique of a superseded artifact as its own
    blank form."""
    _mint_work_step()
    dest, _ = _room("v1")
    dest.write_text('change = "the diff"\ndeviations = "waived: none"\n',
                    encoding="utf-8")

    _, text = _room("v1")

    assert "already answered on this form: change, deviations" in text
    assert "read it before you add to it" in text


def test_a_form_carrying_only_working_markers_says_nothing(workdir):
    """The filter is the subtle half: `parse` keeps a `working:` value, and
    `in_hand` is what reports those. Reporting them twice, in two vocabularies,
    would say the step is further along than it is."""
    _mint_work_step()
    dest, _ = _room("v1")
    dest.write_text('change = "working: still reading"\n', encoding="utf-8")

    _, text = _room("v1")

    assert "already answered on this form" not in text
    assert "still in hand on this form" in text


def test_a_form_not_yet_materialized_carries_no_answers(workdir):
    """The absent-file case reaches the same empty answer as an unfilled one,
    so the room says nothing either way."""
    _mint_work_step()
    st, asm, step, form = _current("v1")
    dest = cli._response_path(st, step)

    assert not dest.exists()
    assert cli._room_kwargs("v1", st, asm, step, form, dest)["answered"] == []
