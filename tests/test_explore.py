"""explore-an-idea, driven: the ideas board seeds under its own row name,
an excursion returns under its row, and the outcomes the assembly declares
are the only ones a submit can take."""

import io
import contextlib
import pathlib

import pytest

from engine import cli
from engine import run as runmod


def _spine(*args):
    buf = io.StringIO()
    code = 0
    try:
        with contextlib.redirect_stdout(buf):
            cli.main(list(args))
    except SystemExit as e:
        code = e.code
    return buf.getvalue(), code


def _fill(wid, name, text):
    pathlib.Path(f".agent-work/{wid.replace('.', '/')}/{name}").write_text(text)


def _current(wid):
    return runmod.state(wid)["current"]


@pytest.fixture
def explore(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONSTELLATION_SESSION", "test")
    out, _ = _spine("open", "explore-an-idea", "--title", "memory graph")
    wid = out.split()[1]
    _fill(wid, "OPEN.toml", 'idea = "x"\nauthority = "Tommy"\n'
                            '[[seeds]]\nidea = "the itch"\n[[seeds]]\nidea = "for whom"\n')
    _spine(wid, "submit")
    return wid


def test_id_kind_is_the_assemblys_last_word(explore):
    assert explore.startswith("idea")


def test_ideas_board_seeds_under_its_own_row_name(explore):
    board = pathlib.Path(f".agent-work/{explore}/IDEAS.toml").read_text()
    assert "[[idea]]" in board and "[[question]]" not in board.split("--- the board ---")[1]
    assert 'id = "i1"' in board and 'status = "live"' in board


def test_status_renders_the_board_without_validating_it(explore):
    out, _ = _spine(explore)
    assert "the tree" in out and "i1" in out and "the itch" in out
    assert "your posture:" in out and "skills/explorer/SKILL.md" in out


def test_excursion_returns_under_its_row_and_completes_nothing(explore):
    out, _ = _spine("open", "find-prior-art", "--parent", explore, "--row", "i1")
    child = out.split()[1]
    assert child == f"{explore}.i1"
    assert runmod.state(child)["prefill"] == {"idea": "the itch"}
    _fill(child, "PRIOR_ART.toml", 'findings = "f"\nsearched = "s"\nverdict = "v"\nregenerate = "r"\n')
    _spine(child, "submit")
    _spine(child, "close")
    st = runmod.state(explore)
    assert st["current"]["form"] == "forms/CYCLE.toml", "a row's return completed the transition"
    assert "i1" in st["row_returns"]
    out, _ = _spine(explore)
    assert "excursion returned to row i1" in out and "verdict" in out


def test_a_second_excursion_off_one_row_gets_its_own_id(explore):
    a, _ = _spine("open", "find-prior-art", "--parent", explore, "--row", "i1")
    b, _ = _spine("open", "draw-a-picture", "--parent", explore, "--row", "i1")
    assert a.split()[1] != b.split()[1]


def test_an_excursion_from_no_such_row_is_refused(explore):
    out, code = _spine("open", "find-prior-art", "--parent", explore, "--row", "i9")
    assert code and "no board row" in str(code)


def test_an_undeclared_outcome_is_refused_naming_the_declared_ones(explore):
    _fill(explore, "CYCLE.toml", 'consolidation = "c"\ndecision = "maybe"\n')
    _, code = _spine(explore, "submit")
    assert "cycle, converge, shelve" in str(code)
    assert _current(explore)["id"] == "explore", "the refusal advanced the run"


def test_cycle_refills_the_transition_with_the_board_untouched(explore):
    before = pathlib.Path(f".agent-work/{explore}/IDEAS.toml").read_text()
    _fill(explore, "CYCLE.toml", 'consolidation = "c"\ndecision = "cycle"\nflavor = "compare"\n')
    _spine(explore, "submit")
    cur = _current(explore)
    assert cur["segment"] == "explore" and cur["form"] == "forms/CYCLE.toml"
    assert cur["prefill"]["flavor"] == "compare"
    assert pathlib.Path(f".agent-work/{explore}/IDEAS.toml").read_text() == before


def test_converge_releases_to_spec_and_the_word_may_carry_prose(explore):
    _fill(explore, "CYCLE.toml", 'consolidation = "c"\ndecision = "converge -- Tommy: yes, go"\n')
    _spine(explore, "submit")
    assert _current(explore)["form"] == "forms/SPEC.toml"


def test_shelve_skips_spec_loudly(explore):
    _fill(explore, "CYCLE.toml", 'consolidation = "c"\ndecision = "shelve"\n')
    _spine(explore, "submit")
    st = runmod.state(explore)
    assert st["current"]["form"] == "forms/CLOSE.toml"
    assert any(a["anchor"] for a in st["amends"]), "skipping an anchored transition was silent"


def _to_rework(explore):
    _fill(explore, "CYCLE.toml", 'consolidation = "c"\ndecision = "converge"\n')
    _spine(explore, "submit")
    _fill(explore, "SPEC.toml", 'spec = "SPEC.md"\nrivals = "waived: none"\nkey-terms = "waived: none"\n')
    _spine(explore, "submit")
    panel = _current(explore)["id"]
    # Three cold readers, one per criterion; one revise among them refills.
    for n, verdict in enumerate(("revise", "pass", "pass"), start=1):
        out, _ = _spine("open", "give-a-verdict", "--parent", explore, "--step", f"{panel}.p{n}")
        critic = out.split()[1]
        _fill(critic, "CRITIC.toml", f'findings = "gap: no point"\nvocabulary = "waived: ok"\nverdict = "{verdict}"\n')
        _spine(critic, "submit")
        _spine(critic, "close")
    assert _current(explore)["form"] == "forms/REWORK.toml"


def test_re_explore_goes_back_to_the_board_and_a_fresh_spec_waits(explore):
    _to_rework(explore)
    _fill(explore, "REWORK.toml", 'spec = "SPEC.md"\ndispositions = "F1 re-explore"\nnext = "re-explore"\n')
    _spine(explore, "submit")
    st = runmod.state(explore)
    assert st["current"]["segment"] == "explore"
    pending = [s for s in st["steps"] if s["id"] not in st["done"]]
    assert [s["segment"] for s in pending] == ["explore", "spec", "spec", "close"]
    assert pending[1]["form"] == "forms/SPEC.toml", "the fresh round is a first cut, not a rework"
    _fill(explore, "CYCLE.toml", 'consolidation = "c"\ndecision = "converge"\n')
    _spine(explore, "submit")
    assert _current(explore)["form"] == "forms/SPEC.toml"


def test_resubmit_releases_to_the_panel(explore):
    _to_rework(explore)
    _fill(explore, "REWORK.toml", 'spec = "SPEC.md"\ndispositions = "F1 edit"\nnext = "resubmit"\n')
    _spine(explore, "submit")
    assert _current(explore).get("panel"), "resubmit did not land on the panel"


def test_amend_add_transition_takes_the_panel_the_assembly_declares_today(explore):
    """A run copies its skeleton at open; when the template later grows a
    panelist, `amend add --transition` is how the live run catches up."""
    _fill(explore, "CYCLE.toml", 'consolidation = "c"\ndecision = "converge"\n')
    _spine(explore, "submit")
    _spine(explore, "amend", "close", "spec", "--reason", "re-minting with today's panel")
    _spine(explore, "amend", "add", "--segment", "spec", "--transition", "--reason", "today's panel")
    st = runmod.state(explore)
    fresh = [s for s in st["steps"] if s["segment"] == "spec" and s.get("panel")]
    assert len(fresh) == 1 and len(fresh[0]["panel"]) == 3
    assert fresh[0]["anchor"] and st["amends"][-1]["anchor"], "the anchored transition was re-minted quietly"
