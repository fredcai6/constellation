"""Completeness and truth for #38's four delivery terms, and the glossary
entries this wave leaves stale.

`posture`, `brief`, `role` and `delivery` are in live use across the engine
(`engine/render.py`'s `posture`/`brief`, `engine/run.py`'s `role_of`/`hat`),
the tests, and `standards/skill.md`'s "one posture" -- with no glossary
entry at all, so `standards/prose.md`'s rule 2 ("one name for one thing...
the source of truth") has nothing to check the words against.

`gate spec` and `spec` once described mechanisms this wave deletes -- a
conductor writing the gate spec at plan-to-execute, and run-an-issue's
consolidate emitting the spec directly. A stale entry satisfies mere
completeness (the headword is still there) while still teaching the
deleted mechanism, which is this gate's own defect class arriving inside
its own check -- so the second assertion checks the phrasing, not presence.

Both pin DESIRED behaviour: the first fails until the four entries exist,
and the second is a tripwire against the deleted phrasing creeping back in.

#80's gate 4 (obligation 13) rides the same seam: `verdict panel`'s own
entry described a fixed `pass | revise` vocabulary and "the merged verdict",
both stale now that `verdict_fold` reads each panelist's own form and folds
to `clean`/`refused`/`quiet` rather than a bare merge of a hardcoded pair.
`clean`, `refused`, `quiet` and `unreadable` are the four load-bearing names
that primitive introduced and used across more than one file with no
headword of their own until this gate.
"""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
GLOSSARY = ROOT / "standards" / "glossary.md"
HEADWORD = re.compile(r"^- \*\*([^*]+)\*\*", re.MULTILINE)

DELIVERY_TERMS = {"posture", "brief", "role", "delivery"}

# #55's own key-terms field: `dispatch`'s changed meaning and the new
# `liveness` entry this gate writes, plus `impasse` and `projection` (#94),
# riding along on the same seam under epic #55's ride-along rule.
FOUR_STATE_TERMS = {"dispatch", "liveness", "impasse", "projection"}

# #80's gate 4: verdict_fold's own per-voice/panel outcome kinds, plus the
# record word a refusal prints -- live in engine/run.py and engine/cli.py,
# never named by a glossary headword before this gate.
VERDICT_FOLD_TERMS = {"clean", "refused", "quiet", "unreadable"}

STALE_PHRASES = (
    "writes per gate at plan-to-execute", "consolidate output",
    # #80's gate 4: the fixed pair and the deleted merge function
    # `verdict panel`'s own entry used to describe.
    "is `pass | revise`, never a third word", "The merged verdict",
    # issue119: manual-conductor mode is deleted, not documented -- the
    # dispatch entry's own sentence describing a human starting a child by
    # hand.
    "leaves starting the child to the reader, who copies that same brief",
)


def test_delivery_terms_resolve_to_a_glossary_entry():
    """Completeness: every term #38's forms lean on -- the four delivery
    terms this gate owns -- resolves to a glossary headword."""
    headwords = set(HEADWORD.findall(GLOSSARY.read_text()))
    missing = DELIVERY_TERMS - headwords
    assert not missing, f"no glossary headword for {missing}"


def test_four_state_terms_resolve_to_a_glossary_entry():
    """Completeness: `dispatch`'s changed meaning, the new `liveness` entry,
    and the two ride-along terms (`impasse`, `projection`) each resolve to a
    glossary headword."""
    headwords = set(HEADWORD.findall(GLOSSARY.read_text()))
    missing = FOUR_STATE_TERMS - headwords
    assert not missing, f"no glossary headword for {missing}"


def test_verdict_fold_terms_resolve_to_a_glossary_entry():
    """Completeness: `verdict_fold`'s three per-voice/panel outcome kinds
    and the record word a refusal prints each resolve to a glossary
    headword."""
    headwords = set(HEADWORD.findall(GLOSSARY.read_text()))
    missing = VERDICT_FOLD_TERMS - headwords
    assert not missing, f"no glossary headword for {missing}"


def test_glossary_names_no_deleted_mechanism():
    """Truth: the phrasing this wave deletes does not survive inside an
    entry that still resolves by name alone."""
    text = GLOSSARY.read_text()
    present = [p for p in STALE_PHRASES if p in text]
    assert not present, f"stale mechanism phrasing still present: {present}"
