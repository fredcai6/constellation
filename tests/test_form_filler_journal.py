"""Commitment 7's record, and commitment 5's board path -- proven with no
caller anywhere in the tree yet.

`_response_path` already resolved location-independently (`root=None`
default, unchanged); this gate gives it a `root` keyword so a standalone
brief built for a filler whose process starts somewhere else can resolve
it against that tree instead. `_board_path` is the identical idiom applied
to a segment's board entry, which a prior round left frozen against
whatever cwd minted it. `_form_filler_records`/`_form_filler_start_counts`
are the read half of the `form-filler-started` record -- the same
`{key: record}` / `{key: count}` shapes `_dispatch_records` and
`_dispatch_start_counts` already give per child, here keyed by step
instead, since a form-step filler is addressed by the step it fills.
"""

import pathlib

from engine import cli, journal, run as runmod


def _mint_response_step(wid="v1", filler="implementer"):
    """A work-segment step standing on run-a-gate's real interior -- the
    same shape `test_brief.py`'s own `_mint_work_step` builds, reused here
    so `_response_path`'s own `step["form"]` reference is real."""
    journal.append(wid, "run", title="t", assembly="run-a-gate")
    journal.append(wid, "step", id="g1", segment="work",
                   form="skills/implementer/forms/IMPLEMENT.toml", filler=filler,
                   prefill={}, anchor=False, terminal=False, validates="", source="mint")


def _mint_board_step(wid="i1", stored_path=None):
    """A step standing on a board-carrying segment ("understand"), with a
    real `board` journal entry -- the shape `_mint`'s own two board-seeding
    call sites leave behind (`engine/cli.py:2423`, `:2439`)."""
    journal.append(wid, "run", title="t", assembly="run-an-issue")
    journal.append(wid, "step", id="consolidate", segment="understand",
                   form="forms/CONSOLIDATE.toml", filler="conductor",
                   prefill={}, anchor=True, terminal=False, validates="board", source="open")
    path = stored_path or str(journal.location(wid) / "UNDERSTAND.toml")
    journal.append(wid, "board", segment="understand", path=path, rows=[])


# -- _response_path: unchanged default, new `root` -----------------------


def test_response_path_with_no_root_resolves_exactly_as_today(bare_workdir):
    _mint_response_step("v1")
    st = runmod.state("v1")
    step = next(s for s in st["steps"] if s["id"] == "g1")

    assert cli._response_path(st, step) == journal.location("v1") / "IMPLEMENT.g1.toml"


def test_response_path_with_root_resolves_against_that_root(bare_workdir, tmp_path):
    _mint_response_step("v1")
    st = runmod.state("v1")
    step = next(s for s in st["steps"] if s["id"] == "g1")

    other = tmp_path / "elsewhere"
    got = cli._response_path(st, step, root=other)

    assert got == journal.location("v1", other) / "IMPLEMENT.g1.toml"
    assert got != cli._response_path(st, step)
    assert str(other) in str(got)


# -- _board_path: mirrors _response_path, filename only -------------------


def test_board_path_with_no_root_matches_todays_direct_read(bare_workdir):
    _mint_board_step("i1")
    st = runmod.state("i1")
    step = next(s for s in st["steps"] if s["id"] == "consolidate")

    stored = st["boards"]["understand"]
    assert cli._board_path("i1", st, step) == pathlib.Path(stored)


def test_board_path_with_root_resolves_against_that_root_using_only_the_filename(
        bare_workdir, tmp_path):
    """The stored string is trusted only for its filename -- a board minted
    under one directory name and re-resolved against a different root must
    not carry that original directory along with it."""
    weird_dir = tmp_path / "some-other-cwd" / ".agent-work" / "i1"
    _mint_board_step("i1", stored_path=str(weird_dir / "UNDERSTAND.toml"))
    st = runmod.state("i1")
    step = next(s for s in st["steps"] if s["id"] == "consolidate")

    other = tmp_path / "the-real-tree"
    got = cli._board_path("i1", st, step, root=other)

    assert got == journal.location("i1", other) / "UNDERSTAND.toml"
    assert "some-other-cwd" not in str(got)


def test_board_path_is_none_when_the_segment_carries_no_board(bare_workdir):
    _mint_response_step("v1")  # run-a-gate's work segment: no board at all
    st = runmod.state("v1")
    step = next(s for s in st["steps"] if s["id"] == "g1")

    assert cli._board_path("v1", st, step) is None
    assert cli._board_path("v1", st, step, root=pathlib.Path("/tmp")) is None


# -- _form_filler_records / _form_filler_start_counts ----------------------


def test_form_filler_records_empty_journal_is_empty(bare_workdir):
    _mint_response_step("v1")
    assert cli._form_filler_records("v1") == {}
    assert cli._form_filler_start_counts("v1") == {}


def test_form_filler_records_one_entry(bare_workdir):
    _mint_response_step("v1")
    journal.append("v1", "form-filler-started", step="g1", pid=123, log="dispatch.g1.log")

    records = cli._form_filler_records("v1")
    assert set(records) == {"g1"}
    assert records["g1"]["pid"] == 123
    assert cli._form_filler_start_counts("v1") == {"g1": 1}


def test_form_filler_records_several_steps_and_repeat_starts_on_one_step(bare_workdir):
    """Two different steps, and a second start on one of them -- `records`
    keeps the latest per step, `start_counts` keeps the total, the same
    split `_dispatch_records`/`_dispatch_start_counts` already draw."""
    _mint_response_step("v1")
    journal.append("v1", "form-filler-started", step="g1", pid=111, log="a.log")
    journal.append("v1", "form-filler-started", step="g2", pid=222, log="b.log")
    journal.append("v1", "form-filler-started", step="g1", pid=333, log="a2.log")

    records = cli._form_filler_records("v1")
    assert set(records) == {"g1", "g2"}
    assert records["g1"]["pid"] == 333, "the latest record for a repeated step, not the first"
    assert records["g2"]["pid"] == 222

    counts = cli._form_filler_start_counts("v1")
    assert counts == {"g1": 2, "g2": 1}
