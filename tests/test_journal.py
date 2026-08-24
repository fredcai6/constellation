"""Tests for the journal: append-only TOML, fold-only state."""

import os
import re

import pytest

from engine import journal


@pytest.fixture(autouse=True)
def in_tmp_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CONSTELLATION_SESSION", raising=False)


def test_append_then_read_in_order():
    journal.append("issue17", "open", title="Fix the thing")
    journal.append("issue17", "note", body="looked around")

    entries = journal.read("issue17")

    assert [e["kind"] for e in entries] == ["open", "note"]
    assert entries[0]["title"] == "Fix the thing"
    assert entries[1]["body"] == "looked around"
    for e in entries:
        assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", e["at"])
        assert e["session"] == str(os.getpid())


def test_multiline_prose_round_trips_byte_exact():
    prose = 'He said "hi"\nthen wrote a """triple""" quote\nand a \\backslash\\ pair.'
    journal.append("issue17", "note", body=prose)

    entries = journal.read("issue17")

    assert entries[0]["body"] == prose


def test_child_id_nests_inside_parent_location():
    parent_loc = journal.location("issue17")
    child_loc = journal.location("issue17.g1")

    assert child_loc == parent_loc / "g1"

    journal.append("issue17.g1", "open", title="gate 1")

    assert journal.journal_path("issue17.g1") == parent_loc / "g1" / "journal.toml"
    assert journal.exists("issue17.g1")
    assert not journal.exists("issue17")


def test_interleaved_appenders_land_in_order_and_file_parses(monkeypatch):
    for i in range(6):
        monkeypatch.setenv("CONSTELLATION_SESSION", "alice" if i % 2 == 0 else "bob")
        journal.append("issue17", "note", seq=i)

    entries = journal.read("issue17")

    assert [e["seq"] for e in entries] == list(range(6))
    assert [e["session"] for e in entries] == ["alice", "bob"] * 3
    # file stays parseable (read() itself round-trips via tomllib; this just
    # confirms shape, since read() would have raised on a torn file)
    assert len(entries) == 6


def test_read_of_nonexistent_run_returns_empty_list():
    assert journal.read("issue-does-not-exist") == []


def test_caller_supplied_stamp_fields_are_not_clobbered():
    entry = journal.append("issue17", "note", at="1999-01-01T00:00:00Z", session="mine")

    assert entry["at"] == "1999-01-01T00:00:00Z"
    assert entry["session"] == "mine"

    entries = journal.read("issue17")
    assert entries[0]["at"] == "1999-01-01T00:00:00Z"
    assert entries[0]["session"] == "mine"
