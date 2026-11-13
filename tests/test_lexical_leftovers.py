"""#32's condition, checked as behaviour.

"No assembly's words appear in `engine/`" is lexical; what it stands for is
behavioural -- the engine does not branch on an assembly's identity and does
not embody an assembly's naming convention. A name-scan supports that claim,
it does not establish it: each name-scan goes blind to a category it did
not anticipate -- a quoted-string grep that could
not see an f-string, a literal-dict AST walk that could not see a forwarded
prefill, a literal scan over functions holding no literal at all.

This file holds the two lexical checks anyway, because most of the listed
symbols happen to be caught by them incidentally, and because
a structural (AST) check and a raw-text (unquoted) check fail for different
reasons -- one is blind to a name mentioned only in a string, the other is
blind to nothing, including comments, which is why the source they scan
carries no dead name to trip on. Neither is the proof; `palette:validate`
driving a real run through the real engine is.

The symbol list is measured against engine/ as it stands:
`_GATE_ADJUDICATION_FORM` is deleted and listed; `_MINTS` is split -- one
literal survives on purpose (`_BOARD_MINT`, "board rows", the one mint value
that is the engine's own), the rest derives.

See: #32
"""

import ast
import pathlib
import re
import tomllib

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENGINE_PATHS = sorted((ROOT / "engine").glob("*.py"))
ENGINE_SRC = "\n".join(p.read_text() for p in ENGINE_PATHS)

# Every one of these names a function or module-level constant that would
# hand-read or hardcode run-an-issue's or run-a-gate's own conventions -- the
# id-suffix pairing, the hardcoded adjudication form, the hardcoded
# `plan-holds`/`gate-spec` field names, the hardcoded `mints` enum. None may
# reappear in engine/ (See: #32).
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

# Assembly-held field names the engine must not hand-read by their literal
# string. Not "-adjudicate" (a cosmetic mint-time id label, read by
# nothing) and not "plan-holds"/"run-a-gate"/
# "run-an-issue" (each still appears, legitimately, in a comment citing the
# real case a mechanism was built for -- kept on the same grounds assembly
# names in comments always are). These two never had a legitimate reason to
# survive anywhere, comment or code.
DEAD_STRINGS = {"gate-spec", "learned"}


def _defined_and_referenced_names(src):
    """Every identifier a module actually binds or reads: function and class
    names, every assignment target, and every `Name`/`Attribute` a body
    touches. `ast` sees none of this inside a comment, so a comment may
    still name a symbol without tripping the check its absence is proving."""
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
    """AST-based, so a name mentioned only in a comment does not count as the symbol surviving, and a
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

# Every load-bearing term: the outcome mechanism itself, its two
# engine-read keys, and every verb `_perform` knows.
# `release` needs no verb word and is still a verb every row can name.
# `step-form`/`rework-form` have no entries of their own, and the adjudication
# form is read the same structural way, so it is deliberately not in this set.
LOAD_BEARING_TERMS = {
    "outcome", "decides", "release", "refill", "rework", "skip", "remint", "close",
    "transition",  # dual-sense, on the same grounds as `anchor` -- the noun already had it
}


def test_every_load_bearing_term_has_a_glossary_headword():
    """The promise `standards/glossary.md` makes needs a check: neither the
    fast suite nor the evals would otherwise open the file, and the only
    other test that touches it (`tests/test_install.py`) asserts it exists,
    not that it says anything. A glossary entry with no check is a promise
    nothing keeps."""
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
PLAN_FORM = ROOT / "skills" / "planner" / "forms" / "PLAN.toml"
OPEN_FORM = RUN_AN_ISSUE_FORMS / "OPEN.toml"
SENTENCE = re.compile(r"(?<=\.)\s+")


def _note(form, field_id):
    fields = tomllib.load(open(form, "rb")).get("field", [])
    return next(f for f in fields if f["id"] == field_id)["note"]


# PLAN.toml's imperative does not name the critic or the implementer's "from
# the gate spec alone" bar (a planner reads the code map, not a promise about
# what a fresh-context reader gets), so no test scopes itself to that sentence.


def test_the_open_forms_issue_note_offers_no_tracker_branch():
    """The field is `kind = "artifact"` and the corpus has no reader for a
    tracker reference: nothing fetches one, so a run that answers with one
    leaves every later reader holding a string. The note names the file."""
    note = " ".join(_note(OPEN_FORM, "issue").split())
    assert "tracker" not in note, f"still offers a tracker reference: {note!r}"
    assert "file in the work location" in note, f"does not name the file: {note!r}"
