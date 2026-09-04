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

STALE_PHRASES = ("writes per gate at plan-to-execute", "consolidate output")


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


def test_glossary_names_no_deleted_mechanism():
    """Truth: the phrasing this wave deletes does not survive inside an
    entry that still resolves by name alone."""
    text = GLOSSARY.read_text()
    present = [p for p in STALE_PHRASES if p in text]
    assert not present, f"stale mechanism phrasing still present: {present}"
