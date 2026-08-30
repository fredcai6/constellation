"""The record hands back what it recorded, in two places.

Triage notes -- the one kind of note that names an issue candidate -- reach
the room, so the conductor fills CLOSE.toml from what was said rather than
memory, and reach `_summary()`, so a parent adjudicating a return sees them
too. And every structured value the summary can carry (`checks`, `cycles`,
`amends`, `triage`) prints as lines a conductor can act on: a bare `[]` or a
Python repr is not something a root-verify can type.
"""

import pathlib
import re

import pytest

from engine import cli, journal, render, run as runmod
from gitremote import init_checkout
from test_nesting import (
    _dispatch_and_close_child, _dispatch_review, _fill_gate_close,
    _fill_gate_transition, _fill_implement, _mint_first_gate,
)

REPO = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONSTELLATION_SESSION", "test-session")
    (tmp_path / "constellation.toml").write_text((REPO / "constellation.toml").read_text())
    init_checkout(tmp_path)
    return tmp_path


# -- render helpers: structured summary values become typeable lines ---------


def test_render_helpers_format_entries_and_stay_empty_lists_when_bare():
    assert render.checks([{"command": "pytest -q", "exit": 0, "output": ""}]) == \
        ["exit 0 pytest -q"]
    assert render.cycles([{"segment": "work", "count": 2}]) == ["work x2"]
    assert render.triage([{"text": "a"}, {"text": "b"}]) == ["a", "b"]
    assert render.checks([]) == []
    assert render.cycles([]) == []
    assert render.triage([]) == []


# -- _summary carries triage notes, and only the triage kind -----------------


def test_summary_triage_carries_only_the_triage_kind(workdir):
    cli.main(["open", "run-a-gate", "--id", "g1"])
    cli.main(["g1", "note", "triage", "extract the validator into its own module"])
    cli.main(["g1", "note", "observation", "the fixture is flaky"])
    cli.main(["g1", "note", "decision", "keep the legacy format"])

    summary = cli._summary(runmod.state("g1"))
    assert summary["triage"] == [{"text": "extract the validator into its own module"}]


# -- the room: the agent filling a close form sees what was noted ------------


def test_room_shows_triage_notes_and_no_other_kind(workdir, capsys):
    cli.main(["open", "run-a-gate", "--id", "g1"])
    capsys.readouterr()
    cli.main(["g1", "note", "triage", "split the parser module"])
    cli.main(["g1", "note", "decision", "keep the legacy format"])
    capsys.readouterr()

    cli.main(["g1"])
    out = capsys.readouterr().out
    assert "triage noted" in out
    assert "split the parser module" in out
    assert "keep the legacy format" not in out


def test_room_wraps_a_long_triage_note_to_width(workdir, capsys):
    """A real triage note runs on well past a terminal's width -- issue11's
    two live notes hit 249 and 410 characters. Unwrapped, the note reads as
    one ragged line beside every other block, which does wrap. The property
    that matters is the width itself, not today's exact break points."""
    cli.main(["open", "run-a-gate", "--id", "g1"])
    capsys.readouterr()
    long_note = " ".join(f"word{i}" for i in range(80))
    cli.main(["g1", "note", "triage", long_note])
    capsys.readouterr()

    cli.main(["g1"])
    lines = capsys.readouterr().out.splitlines()
    start = lines.index("  triage noted") + 1
    block = []
    for line in lines[start:]:
        if line == "":
            break
        block.append(line)

    assert block
    assert max(len(line) for line in block) <= render.WIDTH


def test_room_omits_the_triage_block_when_none_noted(workdir, capsys):
    cli.main(["open", "run-a-gate", "--id", "g1"])
    capsys.readouterr()

    cli.main(["g1"])
    out = capsys.readouterr().out
    assert "triage noted" not in out


def test_close_toml_room_shows_the_runs_own_triage_notes(workdir, capsys):
    """The literal case the gate spec names: the conductor filling
    run-an-issue's CLOSE.toml works from the record, not memory."""
    _mint_first_gate()
    _dispatch_and_close_child("issue17", "g1")
    from test_nesting import _replan_to_next_gate
    _replan_to_next_gate("issue17", "g1-adjudicate")  # sequential: cuts "g2"
    _dispatch_and_close_child("issue17", "g2")
    _fill_gate_transition("issue17")
    cli.main(["issue17", "submit"])
    cli.main(["issue17", "note", "triage", "consider extracting the loader"])
    capsys.readouterr()

    cli.main(["issue17"])
    out = capsys.readouterr().out
    assert "triage noted" in out
    assert "consider extracting the loader" in out


# -- the returns block: every structured field renders, none inherits str() --


def _dispatch_and_close_child_noting_triage(parent_wid, step_id, note_text):
    cli.main(["open", "run-a-gate", "--parent", parent_wid, "--step", step_id])
    child_wid = f"{parent_wid}.{step_id}"
    _fill_implement(child_wid, step_id)
    cli.main([child_wid, "submit"])
    _dispatch_review(child_wid)
    cli.main([child_wid, "note", "triage", note_text])
    _fill_gate_close(child_wid)
    cli.main([child_wid, "submit"])
    cli.main([child_wid, "close"])
    return child_wid


def test_returns_block_renders_checks_cycles_amends_triage_as_lines(workdir, capsys):
    _mint_first_gate()
    capsys.readouterr()
    _dispatch_and_close_child_noting_triage("issue17", "g1", "split the validator")
    capsys.readouterr()

    cli.main(["issue17"])
    out = capsys.readouterr().out

    assert re.search(r"checks\s+exit 0\s+true", out)  # the re-run itself, typeable
    assert re.search(r"cycles\s+none", out)            # no rework: none, never []
    assert re.search(r"amends\s+none", out)             # no amends: none, never []
    assert "split the validator" in out                 # the triage note's text
    assert "{'command'" not in out and "{'text'" not in out  # never a python repr
    assert "[]" not in out


def test_returns_block_renders_cycles_when_rework_happened(workdir, capsys):
    _mint_first_gate()
    capsys.readouterr()
    _dispatch_and_close_child("issue17", "g1", cycles=2)
    capsys.readouterr()

    cli.main(["issue17"])
    out = capsys.readouterr().out
    assert re.search(r"cycles\s+work x2", out)


# -- a form field of the same name overrides the summary's structured value --


def test_a_close_forms_own_triage_field_overrides_the_summarys_note_list(workdir, capsys):
    """CLOSE.toml has a `triage` field the conductor answers in prose --
    routed candidates, not raw notes. When it lands beside the summary's own
    `triage` list under the same key, the form's answer must survive and the
    raw list must never leak through, whether as prose or as a Python repr."""
    journal.append("p1", "run", title="t", assembly="run-an-issue")
    journal.append("p1", "step", id="g1", segment="execute", dispatches="run-a-gate")
    journal.append("p1", "step", id="execute", segment="execute", form="forms/CLOSE.toml",
                   filler="conductor", anchor=True, terminal=True, validates="",
                   child="p1.gate1")
    journal.append("p1", "return", step="g1", child="p1.gate1",
                   summary={"triage": [{"text": "noticed mid-run"}], "checks": [],
                            "cycles": [], "amends": [], "verdict": "", "model": "",
                            "steps_completed": 3},
                   fields={"disposition": "merged", "triage": "waived: none noted",
                           "residue": "waived: none"})
    capsys.readouterr()

    cli.main(["p1"])
    out = capsys.readouterr().out
    assert "waived: none noted" in out
    assert "noticed mid-run" not in out
    assert "{'text'" not in out
