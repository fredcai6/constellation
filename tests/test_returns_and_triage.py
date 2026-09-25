"""The record hands back what it recorded, and never crashes on what it used
to record.

A finding now has two destinations, never a third (ruling, 2026-09-25,
docs/PURPOSE.md): done, or dropped with its reason recorded where a later
run can find it. `triage` is gone as a note kind, as a CLOSE.toml field, and
as the plumbing (`_beyond_calls`) that once carried a `beyond` call there --
`cmd_note` refuses the word outright now, the same way any other undeclared
word refuses. But an *old* journal that already holds a `triage` note or a
`beyond` call is data, not a submission: nothing here re-submits it, so
nothing refuses it, and this file pins that a room, a summary, and the new
prior-drops reader (`engine/drops.py`) all read straight past it rather than
raising.

Every structured value the summary can carry (`checks`, `cycles`, `amends`)
still prints as lines a conductor can act on: a bare `[]` or a Python repr
is not something a root-verify can type.
"""

import re
import shutil

import pytest

from engine import cli, drops as dropsmod, journal, render, run as runmod
from test_nesting import _dispatch_and_close_child, _mint_first_gate

# -- render helpers: structured summary values become typeable lines ---------


def test_render_helpers_format_entries_and_stay_empty_lists_when_bare():
    assert render.checks([{"command": "pytest -q", "exit": 0, "output": ""}]) == \
        ["exit 0 pytest -q"]
    assert render.cycles([{"segment": "work", "count": 2}]) == ["work x2"]
    assert render.checks([]) == []
    assert render.cycles([]) == []


def test_returns_block_renders_checks_cycles_amends_as_lines(workdir, capsys):
    _mint_first_gate()
    capsys.readouterr()
    _dispatch_and_close_child("issue17", "g1")
    capsys.readouterr()

    cli.main(["issue17"])
    out = capsys.readouterr().out

    assert re.search(r"checks\s+exit 0\s+true", out)  # the re-run itself, typeable
    assert re.search(r"cycles\s+none", out)            # no rework: none, never []
    assert re.search(r"amends\s+none", out)             # no amends: none, never []
    assert "{'command'" not in out                      # never a python repr
    assert "[]" not in out


def test_returns_block_renders_cycles_when_rework_happened(workdir, capsys):
    _mint_first_gate()
    capsys.readouterr()
    _dispatch_and_close_child("issue17", "g1", cycles=2)
    capsys.readouterr()

    cli.main(["issue17"])
    out = capsys.readouterr().out
    assert re.search(r"cycles\s+work x2", out)


# -- the word is gone from the vocabulary, not merely unwritten --------------


def test_note_triage_refuses_the_word_is_no_longer_a_kind(workdir, capsys):
    cli.main(["open", "run-a-gate", "--id", "g1"])
    capsys.readouterr()

    with pytest.raises(SystemExit) as e:
        cli.main(["g1", "note", "triage", "extract the validator into its own module"])
    said = str(e.value)
    assert "triage" in said and "blocked" in said  # names the kinds that remain


# -- old data outlives the mechanism: it is read, never resubmitted ---------


def test_a_journal_carrying_an_old_triage_note_still_summarizes_and_renders(workdir, capsys):
    """A run whose journal already holds a `triage` note -- written before
    this ruling -- is data, not a submission: `_summary` and the room built
    off it must read straight past a kind_detail the record no longer
    defines, never raise on it."""
    cli.main(["open", "run-a-gate", "--id", "g1"])
    capsys.readouterr()
    journal.append("g1", "note", id="n0001", kind_detail="triage",
                   text="an old candidate, noted before the ruling", about="", step="do")

    summary = cli._summary(runmod.state("g1"))
    assert "triage" not in summary

    cli.main(["g1"])
    out = capsys.readouterr().out
    assert "an old candidate" not in out  # inert data, not re-surfaced


def test_the_drops_reader_skips_an_old_beyond_call_in_an_archived_journal(workdir):
    """A `calls` table journaled before this ruling may still hold a
    `beyond` row -- the word this ruling retired. `dropsmod.rejected_calls`
    reads every archived `submit` entry's `calls` table looking only for
    `rejected`; an old `beyond` row is simply not one, never a parse
    failure -- it is data, not something this reader is asked to act on."""
    journal.append("issue9", "run", title="t", assembly="run-an-issue")
    journal.append("issue9", "submit", step="route",
                   fields={"resolution": "close",
                           "calls": [{"finding": "an old finding", "call": "beyond"},
                                     {"finding": "engine/cli.py names a real gap",
                                      "call": "rejected: not this gate's to answer"}]})
    archive = workdir / ".agent-work" / "archive"
    archive.mkdir(parents=True)
    shutil.move(str(workdir / ".agent-work" / "issue9"), str(archive / "issue9"))

    drops = dropsmod.rejected_calls(str(workdir))
    assert len(drops) == 1
    assert drops[0]["run"] == "issue9"
    assert drops[0]["files"] == {"engine/cli.py"}
