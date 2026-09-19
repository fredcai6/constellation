"""explore-an-idea, driven: the ideas board seeds under its own row name,
an excursion returns under its row, and the outcomes the assembly declares
are the only ones a submit can take."""

import io
import contextlib
import pathlib

import pytest

from engine import cli
from engine import run as runmod
from gitremote import init_checkout
from test_nesting import _response


def _spine(*args):
    buf = io.StringIO()
    code = 0
    try:
        with contextlib.redirect_stdout(buf):
            cli.main(list(args))
    except SystemExit as e:
        code = e.code
    return buf.getvalue(), code


def _fill(path, text):
    path.write_text(text)


def _write_spec_md(wid):
    """The real file `spec = "SPEC.md"` must point at: #45's
    `_check_artifact` refuses a value that is not a readable path.
    `journal.root_for` resolves an id with no worktree of its own to the
    top-level cwd, so a bare filename like this fixture's own `SPEC.md`
    lands there, not under the work location -- same as the engine sees
    it."""
    pathlib.Path("SPEC.md").write_text("1. the spec.\n")


def _current(wid):
    return runmod.state(wid)["current"]


@pytest.fixture
def explore(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONSTELLATION_SESSION", "test")
    init_checkout(tmp_path)
    out, _ = _spine("open", "explore-an-idea", "--title", "memory graph")
    wid = out.split()[1]
    _fill(_response(wid), 'idea = "x"\nauthority = "Tommy"\n'
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
    _fill(_response(child), 'findings = "f"\nsearched = "s"\nverdict = "v"\nregenerate = "r"\n')
    _spine(child, "submit")
    _spine(child, "close")
    st = runmod.state(explore)
    assert st["current"]["form"] == "forms/CYCLE.toml", "a row's return completed the transition"
    assert "i1" in st["row_returns"]
    out, _ = _spine(explore)
    assert "excursion returned to row i1" in out and "verdict" in out


def test_an_excursions_form_is_its_workers_not_its_principals(explore):
    """A conductor opens an excursion precisely so it does NOT spend its own
    context answering the row -- the excursion skill is written to the agent
    doing the looking ("You are a child run opened from a board row"), not to
    the one who sent it. So the room must not tell that reader the form is its
    principal's, and `drive` must be willing to start a filler on it.

    `terminal` alone used to decide this, which let the close-form rule shadow
    a worker the assembly names outright: find-prior-art's one step is both its
    terminal and its work, and declares `filler = "excursion"`. The room said
    "none -- this form is the run's principal's to fill" and nothing would
    start anyone on it."""
    out, _ = _spine("open", "find-prior-art", "--parent", explore, "--row", "i1")
    child = out.split()[1]

    step = runmod.state(child)["current"]
    assert step["terminal"] and step["filler"] == "excursion"
    assert not runmod.principal_fills(step)

    room, _ = _spine(child)
    assert "principal's to fill" not in room
    assert "skills/excursion/SKILL.md" in room


def test_a_close_form_is_still_its_principals_to_fill(explore):
    """The other half, and the reason the predicate reads `filler` rather than
    dropping `terminal`: a real close form leaves `filler` at the `conductor`
    default, and stays the principal's. `drive` starts nobody there."""
    step = {"terminal": True, "filler": "conductor"}
    assert runmod.principal_fills(step)
    assert runmod.principal_fills({"terminal": False, "filler": "principal"})
    assert not runmod.principal_fills({"terminal": False, "filler": "spec-writer"})


def test_a_second_excursion_off_one_row_gets_its_own_id(explore):
    a, _ = _spine("open", "find-prior-art", "--parent", explore, "--row", "i1")
    b, _ = _spine("open", "draw-a-picture", "--parent", explore, "--row", "i1")
    assert a.split()[1] != b.split()[1]


def test_usage_names_the_row_form(explore):
    """USAGE documents both ways a child is opened, not just the step form.

    The step form was there and the row form was not, so the whole of
    `--row` -- the only way an excursion is ever opened -- was undocumented
    in the one place an agent looks when it does not know a verb."""
    assert "--parent <id> --row <row-id>" in cli.USAGE
    assert "excursion" in cli.USAGE
    for word in ("the row is the brief", "completes no step"):
        assert word in cli.USAGE, f"the gloss does not say {word!r}"
    out, _ = _spine("--help")
    assert "--row <row-id>" in out, "--help does not print the row form"


def test_an_excursion_from_no_such_row_is_refused(explore):
    out, code = _spine("open", "find-prior-art", "--parent", explore, "--row", "i9")
    assert code and "no board row" in str(code)


def test_an_undeclared_outcome_is_refused_naming_the_declared_ones(explore):
    _fill(_response(explore), 'consolidation = "c"\ndecision = "maybe"\n')
    _, code = _spine(explore, "submit")
    assert "cycle | converge | shelve" in str(code)
    assert _current(explore)["id"] == "explore", "the refusal advanced the run"


def test_cycle_refills_the_transition_with_the_board_untouched(explore):
    before = pathlib.Path(f".agent-work/{explore}/IDEAS.toml").read_text()
    _fill(_response(explore), 'consolidation = "c"\ndecision = "cycle"\nflavor = "compare"\n')
    _spine(explore, "submit")
    cur = _current(explore)
    assert cur["segment"] == "explore" and cur["form"] == "forms/CYCLE.toml"
    assert cur["prefill"]["flavor"] == "compare"
    assert pathlib.Path(f".agent-work/{explore}/IDEAS.toml").read_text() == before


def test_converge_releases_to_spec_and_the_word_may_carry_prose(explore):
    _fill(_response(explore), 'consolidation = "c"\ndecision = "converge -- Tommy: yes, go"\n')
    _spine(explore, "submit")
    assert _current(explore)["form"] == "forms/SPEC.toml"


def test_shelve_skips_spec_loudly(explore):
    _fill(_response(explore), 'consolidation = "c"\ndecision = "shelve"\n')
    _spine(explore, "submit")
    st = runmod.state(explore)
    assert st["current"]["form"] == "forms/CLOSE.toml"
    assert any(a["anchor"] for a in st["amends"]), "skipping an anchored transition was silent"


def _to_rework(explore):
    _fill(_response(explore), 'consolidation = "c"\ndecision = "converge"\n')
    _spine(explore, "submit")
    _write_spec_md(explore)
    _fill(_response(explore), 'spec = "SPEC.md"\nrivals = "waived: none"\nkey-terms = "waived: none"\n')
    _spine(explore, "submit")
    panel = _current(explore)["id"]
    # Three fresh-context readers, one per criterion; one revise among them refills.
    for n, verdict in enumerate(("revise", "pass", "pass"), start=1):
        out, _ = _spine("open", "give-a-verdict", "--parent", explore, "--step", f"{panel}.p{n}")
        critic = out.split()[1]
        _fill(_response(critic), f'findings = "gap: no point"\nverdict = "{verdict}"\n')
        _spine(critic, "submit")
        _spine(critic, "close")
    assert _current(explore)["form"] == "forms/REWORK.toml"
    # The critics' own findings ride into that round verbatim -- this caller
    # submits no `calls` table, so `_blocking_calls` reads `None` and the
    # carry-everything behaviour is untouched. Same shape
    # `test_rework.py::test_revise_mints_rework_form_with_findings_as_prefill`
    # and `test_spec_review.py` already assert; without it this file only ever
    # checked which form came next.
    assert "gap: no point" in _current(explore)["prefill"]["findings"]


def test_re_explore_goes_back_to_the_board_and_a_fresh_spec_waits(explore):
    _to_rework(explore)
    _write_spec_md(explore)
    _fill(_response(explore), 'spec = "SPEC.md"\ndispositions = "F1 re-explore"\nnext = "re-explore"\n')
    _spine(explore, "submit")
    st = runmod.state(explore)
    assert st["current"]["segment"] == "explore"
    pending = [s for s in st["steps"] if s["id"] not in st["done"]]
    assert [s["segment"] for s in pending] == ["explore", "spec", "spec", "close"]
    assert pending[1]["form"] == "forms/SPEC.toml", "the fresh round is a first cut, not a rework"
    _fill(_response(explore), 'consolidation = "c"\ndecision = "converge"\n')
    _spine(explore, "submit")
    assert _current(explore)["form"] == "forms/SPEC.toml"


def test_resubmit_releases_to_the_panel(explore):
    _to_rework(explore)
    _write_spec_md(explore)
    _fill(_response(explore), 'spec = "SPEC.md"\ndispositions = "F1 edit"\nnext = "resubmit"\n')
    _spine(explore, "submit")
    assert _current(explore).get("panel"), "resubmit did not land on the panel"


def test_amend_add_transition_takes_the_panel_the_assembly_declares_today(explore):
    """A run copies its skeleton at open; when the template later grows a
    panelist, `amend add --transition` is how the live run catches up."""
    _fill(_response(explore), 'consolidation = "c"\ndecision = "converge"\n')
    _spine(explore, "submit")
    _spine(explore, "amend", "close", "spec", "--reason", "re-minting with today's panel")
    _spine(explore, "amend", "add", "--segment", "spec", "--transition", "--reason", "today's panel")
    st = runmod.state(explore)
    fresh = [s for s in st["steps"] if s["segment"] == "spec" and s.get("panel")]
    assert len(fresh) == 1 and len(fresh[0]["panel"]) == 3
    assert fresh[0]["anchor"] and st["amends"][-1]["anchor"], "the anchored transition was re-minted quietly"


def test_round_cap_undeclared_never_pauses_the_spec_seam(explore):
    """issue113's C5: `spec` is the one seam left declaring no `round-cap` at
    all (spec.md's out-of-scope list), and it already has no impasse outlet
    of its own -- "every disposition here is the human's" (ASSEMBLY.toml).
    Driven seven rounds deep, well past the five that stop `understand`,
    `plan` and `review`, nothing here pauses: an undeclared cap changes
    nothing about how a run resolves."""
    _to_rework(explore)  # round 1, landed
    for n in range(2, 8):  # rounds 2..7, six more landed rounds
        _write_spec_md(explore)
        _fill(_response(explore), 'spec = "SPEC.md"\ndispositions = "F1 edit"\nnext = "resubmit"\n')
        _spine(explore, "submit")
        panel = _current(explore)["id"]
        assert _current(explore).get("panel"), f"round {n} did not reach a fresh panel"
        for p, verdict in enumerate(("revise", "pass", "pass"), start=1):
            out, _ = _spine("open", "give-a-verdict", "--parent", explore,
                            "--step", f"{panel}.p{p}")
            critic = out.split()[1]
            _fill(_response(critic), f'findings = "gap: round {n}"\nverdict = "{verdict}"\n')
            _spine(critic, "submit")
            _spine(critic, "close")
        assert _current(explore)["form"] == "forms/REWORK.toml", (
            f"round {n} did not land a fresh REWORK round")

    st = runmod.state(explore)
    assert not runmod.paused(st["current"]), "an undeclared round-cap paused the run anyway"
    assert not any(s.get("form") == "skills/gate-conductor/forms/ASK.toml" for s in st["steps"])
