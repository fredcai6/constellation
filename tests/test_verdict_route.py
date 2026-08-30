"""#56: `_act_on_verdicts` no longer special-cases the raw word. Since g3
dropped `escalate` from the tree, `run-a-gate`'s review and
`explore-an-idea`'s spec were the last transitions whose routing lived in a
hardcoded `if verdict != "revise": return` rather than in a declared
`[[segment.transition.outcome]]` table -- the exact mechanism a two-voices
step (run-an-issue's plan-to-execute) already used. This file proves the
merged verdict now resolves the same way there too: `pass` performs the
declared `release` (a no-op -- nothing mints, the run advances by its own
step order), `revise` performs the declared `rework` (a fresh round, exactly
as before), and no routing branch in the engine still compares the word
itself.

Drives the real `run-a-gate` assembly, not a fixture -- `test_verdict_panels.py`
already does, and its fixtures are reused here rather than re-declared.
"""

import inspect
import pathlib

from engine import cli, run as runmod
from test_verdict_panels import (  # noqa: F401
    _fill_review, _open_gate, _open_panelist, workdir,
)

REPO = pathlib.Path(__file__).resolve().parent.parent


# -- the wiring: `_decided_here` picks the transition's own `verdict` -------


def test_run_a_gates_review_declares_verdict_disjoint_from_ruling():
    """`_decided_here` on the review panel step must pick the transition's
    own `verdict` -- the panel's merged word, never typed by a conductor --
    not `ruling`, the `work` segment's own field (IMPASSE.toml's). The two
    have to stay disjoint for a deciding step to resolve to exactly one
    outcome table. `_outcome` then resolves both of `verdict`'s legal values
    against the rows the assembly actually declares."""
    asm = runmod.load_assembly("run-a-gate")
    step = {"segment": "work", "panel": [{"form": "skills/reviewer/forms/REVIEW.toml"}]}

    field = cli._decided_here(asm, step)
    assert field == "verdict"
    assert field != "ruling"  # the segment's own decides -- IMPASSE.toml's, not this

    seg, does = cli._outcome(asm, step, {"verdict": "revise"}, {"steps": []})
    assert seg["id"] == "work" and does == "rework"

    seg, does = cli._outcome(asm, step, {"verdict": "pass"}, {"steps": []})
    assert seg["id"] == "work" and does == "release"


# -- end to end: pass releases, revise reworks, both through the table -----


def test_a_pass_resolves_through_the_outcome_table_and_releases(workdir, capsys):
    """Pass's declared verb is `release`, which `_perform` matches nothing
    for -- a deliberate no-op, not an absence of routing. The gate advances
    to close by its own step order (all three steps were minted at open),
    never by a mint this call makes."""
    _open_gate()
    panelist = _open_panelist("g1", "review")
    _fill_review(panelist, "pass")
    cli.main([panelist, "submit"])
    capsys.readouterr()
    cli.main([panelist, "close"])
    capsys.readouterr()

    st = runmod.state("g1")
    assert st["current"]["id"] == "close"
    assert [s["id"] for s in st["steps"]] == ["work-1", "review", "close"]


def test_a_revise_resolves_through_the_outcome_table_and_reworks(workdir, capsys):
    """Revise's declared verb is `rework`: a fresh implement round, minted
    with the panel's own findings as prefill -- the same shape the old
    hardcoded fallback produced, now reached through `_outcome`/`_perform`
    instead of a branch on the word."""
    _open_gate()
    panelist = _open_panelist("g1", "review")
    _fill_review(panelist, "revise", findings="gap: the bound is still off")
    cli.main([panelist, "submit"])
    capsys.readouterr()
    cli.main([panelist, "close"])
    capsys.readouterr()

    st = runmod.state("g1")
    fresh = next(s for s in st["steps"] if s["segment"] == "work" and s.get("source") == "mint")
    assert fresh["form"] == "skills/implementer/forms/IMPLEMENT.toml"
    assert "gap: the bound is still off" in fresh["prefill"]["findings"]
    assert st["current"]["id"] == fresh["id"]


# -- the vocabulary comparison itself is gone from the routing branches -----


def test_only_the_display_line_still_compares_the_word_verdict():
    """Pinned, not silently tolerated: exactly one line in `engine/cli.py`
    still writes `verdict ==` or `verdict !=`, and it is `_returned_verdict`
    (line ~578) deciding whether a status render *shows* the merged word to
    a reader -- not where a run goes. That comparison is current and
    intended, named here on purpose so a future reader does not mistake the
    survivor for a leftover of the branch this gate removed: the gate spec
    for #56 explicitly leaves `_returned_verdict` alone, since rewriting it
    to satisfy a bare grep would spend clarity to move a number and answer
    a question about display, not about routing. Asserting the count (one),
    not the absence (zero), is what pins it as deliberate."""
    src = (REPO / "engine" / "cli.py").read_text()
    hits = [(n, line) for n, line in enumerate(src.splitlines(), start=1)
           if "verdict ==" in line or "verdict !=" in line]
    assert len(hits) == 1, f"expected exactly one surviving comparison, found: {hits}"
    n, line = hits[0]
    assert 'verdict == "pass"' in line

    fn_lines = inspect.getsource(cli._returned_verdict).splitlines()
    assert any('verdict == "pass"' in l for l in fn_lines), \
        "the surviving comparison is not inside _returned_verdict"
