"""#32's condition, checked the way it is now stated (plan.md, g4).

"No assembly's words appear in `engine/`" is lexical; what it stands for is
behavioural -- the engine does not branch on an assembly's identity and does
not embody an assembly's naming convention. A name-scan supports that claim,
it does not establish it: four were written for this plan and each went
blind to a category it did not anticipate -- a quoted-string grep that could
not see an f-string, a literal-dict AST walk that could not see a forwarded
prefill, a literal scan over functions holding no literal at all.

This file holds the two lexical checks anyway, because seven of the nine
symbols round 4 named happen to be caught by them incidentally, and because
a structural (AST) check and a raw-text (unquoted) check fail for different
reasons -- one is blind to a name mentioned only in a string, the other is
blind to nothing, including comments, which is why the source they scan
carries no dead name to trip on. Neither is the proof; `palette:validate`
driving a real run through the real engine is.

The nine-symbol list g1-g3's own scope named is already stale by the time
this gate runs: `_GATE_ADJUDICATION_FORM` (g2's own change log) was deleted
and the list never named it; `_MINTS` (g3's own change log: "Replaced ...
with `_BOARD_MINT` ... and a new `_mintable(asm)`") was less deleted than
split -- one literal survives on purpose (`_BOARD_MINT`, "board rows", the
one mint value that is the engine's own), the rest now derives. The list
below is re-measured against engine/ as it stands, not copied from the plan.
"""

import ast
import pathlib
import re
import tomllib

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENGINE_PATHS = sorted((ROOT / "engine").glob("*.py"))
ENGINE_SRC = "\n".join(p.read_text() for p in ENGINE_PATHS)

# Every one of these was, at some point in #32, a function or module-level
# constant in engine/cli.py that hand-read or hardcoded run-an-issue's or
# run-a-gate's own conventions -- the id-suffix pairing, the hardcoded
# adjudication form, the hardcoded `plan-holds`/`gate-spec` field names, the
# hardcoded `mints` enum. All nine are gone; `_GATE_ADJUDICATION_FORM` is the
# tenth name, real and deleted, that the plan's own list never carried.
DEAD_SYMBOLS = {
    "_impasse_segment",
    "_act_on_impasse",
    "_own_gate",
    "_pending_gates",
    "_check_outcome",
    "_act_on_outcome",
    "_close_gate",
    "_MINTS",
    "_GATE_ADJUDICATION_FORM",
}

# Assembly-held field names the engine used to hand-read by their literal
# string. Not "-adjudicate" (a cosmetic mint-time id label now, read by
# nothing -- kept, see the gate's close) and not "plan-holds"/"run-a-gate"/
# "run-an-issue" (each still appears, legitimately, in a comment citing the
# real case a mechanism was built for -- kept on the same grounds assembly
# names in comments always are). These two never had a legitimate reason to
# survive anywhere, comment or code, and re-measuring confirms they do not.
DEAD_STRINGS = {"gate-spec", "learned"}


def _defined_and_referenced_names(src):
    """Every identifier a module actually binds or reads: function and class
    names, every assignment target, and every `Name`/`Attribute` a body
    touches. `ast` sees none of this inside a comment -- a symbol's own
    history can still be told there (`# ... used to be handled by ...`)
    without that telling tripping the very check its absence is proving."""
    found = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.add(node.name)
        elif isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
    return found


def test_the_nine_symbols_round_4_named_are_structurally_gone():
    """AST-based, so a name mentioned only in a comment (explaining what a
    symbol used to be called) does not count as the symbol surviving, and a
    name reached only through an attribute or reassignment still does."""
    for path in ENGINE_PATHS:
        names = _defined_and_referenced_names(path.read_text())
        hit = names & DEAD_SYMBOLS
        assert not hit, f"{path.relative_to(ROOT)}: still defines or reads {hit}"


def test_the_dead_names_do_not_appear_even_as_raw_text():
    """A second technique, over the raw, unquoted text -- no AST, no
    tokenizing, nothing that could itself be blind to some future form one
    of these names might reappear in. `\\b` is enough: none of these names
    is a substring of a live identifier anywhere in engine/ today (verified
    below by the fact that this passes), so a word-boundary match is exact,
    not approximate."""
    for path in ENGINE_PATHS:
        text = path.read_text()
        for name in DEAD_SYMBOLS | DEAD_STRINGS:
            assert not re.search(rf"\b{re.escape(name)}\b", text), (
                f"{path.relative_to(ROOT)}: {name!r} still appears, "
                "quoted or not")


GLOSSARY = ROOT / "standards" / "glossary.md"
HEADWORD = re.compile(r"^- \*\*([^*]+)\*\*", re.MULTILINE)

# Every term this migration makes load-bearing: the outcome mechanism itself,
# its two engine-read keys, and every verb g1 and g2 taught `_perform`.
# `release` needs no verb word and is still a verb every row can name.
# `step-form`/`rework-form` have no entries of their own, and the adjudication
# form is read the same structural way -- this gate's call is to match that
# precedent rather than break it, so it is deliberately not in this set.
LOAD_BEARING_TERMS = {
    "outcome", "decides", "release", "refill", "rework", "skip", "remint", "close",
    "transition",  # dual-sense, on the same grounds as `anchor` -- the noun already had it
}


def test_every_load_bearing_term_has_a_glossary_headword():
    """Round 4 found the promise `standards/glossary.md` makes is unchecked:
    neither the fast suite nor the evals open the file, and the only test
    that touches it (`tests/test_install.py`) asserts it exists, not that it
    says anything. A glossary entry with no check is a promise nothing keeps."""
    headwords = set(HEADWORD.findall(GLOSSARY.read_text()))
    missing = LOAD_BEARING_TERMS - headwords
    assert not missing, f"no glossary headword for {missing}"


# Two more corpus promises nothing checks, and both are about the same thing:
# a form sentence that describes a delivery the engine does not make. A reader
# has no way to catch either by running anything -- the run still completes,
# and the writer it misdirects is a fresh context that never sees the corpus
# it was misdirected by. So they are checked here, lexically, on the same
# grounds as everything above.

RUN_AN_ISSUE_FORMS = ROOT / "assemblies" / "run-an-issue" / "forms"
PLAN_FORM = RUN_AN_ISSUE_FORMS / "PLAN.toml"
OPEN_FORM = RUN_AN_ISSUE_FORMS / "OPEN.toml"
SENTENCE = re.compile(r"(?<=\.)\s+")


def _note(form, field_id):
    fields = tomllib.load(open(form, "rb")).get("field", [])
    return next(f for f in fields if f["id"] == field_id)["note"]


def test_the_plan_imperative_names_the_critics_real_inputs():
    """A panelist's prefill is the run's prefill plus the producing step's
    fields plus its criteria, and the run's prefill is fed by the one
    transition marked `carries` -- the consolidate. The critic therefore holds
    a statement of the problem and the plan, never the issue, which
    `skills/critic/forms/CRITIC.toml` states in its own header.

    The word is `spec`. What run-an-issue hands a critic is the consolidate's
    output and what explore-an-idea hands one is SPEC.toml's artifact; both
    play the same part, and a critic told the name of the document that
    produced it learns nothing it can act on. Scoped to the sentence that names
    the critic's inputs: the imperative's first sentence says "how this issue
    gets solved" and is legal."""
    imperative = tomllib.load(open(PLAN_FORM, "rb"))["imperative"]
    named = [s for s in SENTENCE.split(imperative) if "critic" in s]
    assert len(named) == 1, f"expected one sentence naming the critic, got {named}"
    # That sentence carries the implementer's bar too, in its own clause ending
    # "from its spec alone" -- so a bare `"spec" in sentence` passes on wording
    # that never mentions the critic's spec at all. Cut at the implementer.
    sentence = " ".join(named[0].split())
    clause, _, rest = sentence.partition("implementer")
    assert rest, f"expected the implementer's clause to follow the critic's: {sentence!r}"
    assert "spec" in clause, f"does not name the spec: {clause!r}"
    assert "issue" not in clause, f"promises the critic the issue: {clause!r}"


def test_the_open_forms_issue_note_offers_no_tracker_branch():
    """The field is `kind = "artifact"` and the corpus has no reader for a
    tracker reference: nothing fetches one, so a run that answers with one
    leaves every later reader holding a string. The note names the file."""
    note = " ".join(_note(OPEN_FORM, "issue").split())
    assert "tracker" not in note, f"still offers a tracker reference: {note!r}"
    assert "file in the work location" in note, f"does not name the file: {note!r}"
