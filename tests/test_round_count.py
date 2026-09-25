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

from engine import cli, run as runmod

from test_nesting import _fill_open, _work_the_board

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
    right for a rework and wrong for a replacement. One look (2026-09-25)
    removed the impasse form this test used to drive the send-back through
    (`understand` no longer declares `impasse-after` at all, and an
    `incorporate` there refills the step-form directly, ASSEMBLY.toml) --
    `_mint_segment_round` is where `sent_back` is actually stamped, so this
    drives it there directly rather than through a submit."""
    wid = _open_to_the_spec_seam()
    _work_the_board(wid)
    capsys.readouterr()

    asm = runmod.load_assembly(ASM)
    assert _count(wid, "understand") == 0
    cli._mint_segment_round(wid, asm, "understand")

    assert _count(wid, "understand") == 1
    rounds = runmod._rounds(runmod.state(wid), "understand")
    assert [r["sent_back"] for r in rounds] == [0, 1], (
        f"{[(r['id'], r['sent_back']) for r in rounds]}")


def test_a_restart_is_expressible_where_the_segment_declares_one_form(workdir, capsys):
    """The thing the old derivation could not say. It read a restart off a
    step-form mint, and at a one-form segment every mint is a step-form mint,
    so "start over" and "another pass" were the same journal entry.
    `understand` is such a segment, and issue96's run is where that cost
    something: a spec withdrawn whole by a ruling counted as a repeat. One
    look (2026-09-25) removed the impasse form this test used to drive the
    first send-back through; `restarts` on `_mint_segment_round` is the
    mechanism under test, driven directly."""
    wid = _open_to_the_spec_seam()
    _work_the_board(wid)
    capsys.readouterr()

    asm = runmod.load_assembly(ASM)
    cli._mint_segment_round(wid, asm, "understand")
    assert _count(wid, "understand") == 1

    cli._mint_segment_round(wid, asm, "understand", restarts=True)
    assert _count(wid, "understand") == 0, (
        "a fresh artifact still counted as another pass at the old one -- the "
        "distinction a rework-form exists to make, at a segment that declares "
        "none")

    cli._mint_segment_round(wid, asm, "understand")
    assert _count(wid, "understand") == 1, "the fresh artifact's own first send-back"
