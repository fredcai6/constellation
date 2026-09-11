"""The send-back count is a journaled fact, not a guess from which form minted.

`rework_rounds` used to derive "another pass at the same artifact" from form
identity: a step-form mint restarted the count, a rework-form mint spent it.
That only works where a segment declares two forms, so it did nothing at the
two that declare one. At `run-a-gate`'s `work` the answer was right anyway --
every refill there really is another pass at the same diff. At
`run-an-issue`'s `understand` it was wrong, and issue96's run is where it
showed: round one was withdrawn whole by a principal's ruling, twice in an
hour, and the count read those replacements as repeats, so the outlet fired
having seen no second attempt at anything.

The verb already knows -- `rework` is another pass, `refill` is a fresh
artifact -- so the mint journals `sent_back` and the count reads it.
"""

import pathlib

import pytest

from engine import cli, run as runmod

from test_nesting import (
    _dispatch_and_close_plan,
    _dispatch_plan_critic,
    _fill_consolidate,
    _fill_open,
    _fill_spec,
    _response,
    _rule_impasse,
    _work_the_board,
)

ROOT = pathlib.Path(runmod.__file__).resolve().parent.parent
ASM = "run-an-issue"


def _open_to_the_spec_seam(wid="issue17"):
    cli.main(["open", ASM, "--issue", "17", "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    return wid


def _count(wid, seg):
    return runmod.rework_rounds(runmod.state(wid), runmod.load_assembly(ASM), seg)


# -- 1. the opening round was never sent back -------------------------------


def test_the_opening_round_is_round_zero(workdir, capsys):
    wid = _open_to_the_spec_seam()
    capsys.readouterr()
    assert _count(wid, "understand") == 0
    opening = next(s for s in runmod.state(wid)["steps"] if s["id"] == "understand-1")
    assert opening["sent_back"] == 0, (
        "the first cut carries no send-back count, so nothing downstream can "
        "read one off it")


# -- 2. the segment that declares one form now counts correctly -------------


def test_a_send_back_at_a_one_form_segment_counts(workdir, capsys):
    """`understand` declares a step-form and no rework-form. The old
    derivation counted every step-form mint alike here, which happened to be
    right for a rework and wrong for a replacement. The send-back lands on
    the impasse form first (`impasse-after = 0`); the round is ruled into
    being there, and that ruled round is the one the count reads."""
    wid = _open_to_the_spec_seam()
    _work_the_board(wid)
    _fill_consolidate(wid, "rework",
                      calls='[[calls]]\nfinding = "f"\ncall = "blocking"\n')
    cli.main([wid, "submit"])
    _rule_impasse(wid)
    capsys.readouterr()

    assert _count(wid, "understand") == 1
    rounds = runmod._rounds(runmod.state(wid), "understand")
    assert [r["sent_back"] for r in rounds] == [0, 1], (
        f"{[(r['id'], r['sent_back']) for r in rounds]}")


def test_the_count_is_carried_into_the_impasse_orders(workdir, capsys):
    """So the form can say how many rather than naming a number that goes
    stale the next time `impasse-after` moves -- which is how it last went
    stale, when the 2026-09-05 ruling took it from 2 to 1 and left five
    sentences saying "three"."""
    wid = _open_to_the_spec_seam()
    _work_the_board(wid)
    after = next(s for s in runmod.load_assembly(ASM)["segment"]
                 if s["id"] == "understand")["impasse-after"]
    for _ in range(after):
        _fill_consolidate(wid, "rework",
                          calls='[[calls]]\nfinding = "f"\ncall = "blocking"\n')
        cli.main([wid, "submit"])
        _fill_spec(wid)
        cli.main([wid, "submit"])
        _dispatch_plan_critic(wid)
    _fill_consolidate(wid, "rework",
                     calls='[[calls]]\nfinding = "f"\ncall = "blocking"\n')
    cli.main([wid, "submit"])
    capsys.readouterr()

    st = runmod.state(wid)
    assert st["current"]["form"] == "forms/IMPASSE.toml", st["current"].get("form")
    assert st["current"]["prefill"]["sent-back"] == str(after), (
        "the ruling form cannot say how many rounds it is ruling on: "
        f"{st['current']['prefill']}")


def test_a_restart_is_expressible_where_the_segment_declares_one_form(workdir, capsys):
    """The thing the old derivation could not say. It read a restart off a
    step-form mint, and at a one-form segment every mint is a step-form mint,
    so "start over" and "another pass" were the same journal entry.
    `understand` is such a segment, and issue96's run is where that cost
    something: a spec withdrawn whole by a ruling counted as a repeat."""
    wid = _open_to_the_spec_seam()
    _work_the_board(wid)
    _fill_consolidate(wid, "rework",
                      calls='[[calls]]\nfinding = "f"\ncall = "blocking"\n')
    cli.main([wid, "submit"])
    _rule_impasse(wid)
    capsys.readouterr()
    assert _count(wid, "understand") == 1

    asm = runmod.load_assembly(ASM)
    cli._mint_segment_round(wid, asm, "understand", restarts=True)
    assert _count(wid, "understand") == 0, (
        "a fresh artifact still counted as another pass at the old one -- the "
        "distinction a rework-form exists to make, at a segment that declares "
        "none")

    cli._mint_segment_round(wid, asm, "understand")
    assert _count(wid, "understand") == 1, "the fresh artifact's own first send-back"


# -- 3. no form in the tree names a count it cannot know --------------------


def test_no_impasse_form_hardcodes_a_number_of_rounds(workdir):
    """One file is shared by segments whose `impasse-after` need not agree,
    so naming a number in the prose is the coupling that went stale. The
    orders carry it instead."""
    for ref in ("assemblies/run-an-issue/forms/IMPASSE.toml",
                "assemblies/run-a-gate/forms/IMPASSE.toml"):
        text = (ROOT / ref).read_text().lower()
        for word in ("three", "fourth", "twice"):
            assert word not in text, (
                f"{ref} names a count in prose ({word!r}); the number is "
                "`impasse-after`'s and reaches the conductor as `sent-back` "
                "in the orders")
