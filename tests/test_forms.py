"""Tests for engine/forms.py: load, materialize, parse."""

import pathlib
import re
import tomllib

import pytest

from engine import boards, cli, forms

OPEN = "assemblies/run-an-issue/forms/OPEN.toml"
CONSOLIDATE = "assemblies/run-an-issue/forms/CONSOLIDATE.toml"
IMPLEMENT = "skills/implementer/forms/IMPLEMENT.toml"
GATE_TRANSITION = "assemblies/run-an-issue/forms/GATE_TRANSITION.toml"
GATE_CLOSE = "assemblies/run-a-gate/forms/GATE_CLOSE.toml"
REVIEW = "skills/reviewer/forms/REVIEW.toml"
GATE_IMPASSE = "assemblies/run-a-gate/forms/IMPASSE.toml"
UNDERSTAND = "skills/interrogator/forms/UNDERSTAND.toml"


def _ids(form):
    return [f["id"] for f in form["fields"]]


def _kinds(form):
    return {f["id"]: f["kind"] for f in form["fields"]}


# -- load() on the real forms ------------------------------------------------


def test_load_open():
    form = forms.load(OPEN)
    assert _ids(form) == ["issue", "authority", "questions"]
    kinds = _kinds(form)
    assert kinds["issue"] == "artifact"
    assert kinds["authority"] == "decision"
    assert kinds["questions"] == "plan"
    questions = next(f for f in form["fields"] if f["id"] == "questions")
    assert questions["mints"] == "board rows"
    assert [it["id"] for it in questions["item"]] == ["question", "excursion", "type"]
    assert form["imperative"].startswith("Confirm what this run is solving")


def test_load_consolidate():
    """Follow-up to ruling 3, 2026-09-03, and one look (2026-09-25):
    consolidate is the conductor's own route form now, the same shape
    PLAN_TO_EXECUTE.toml has -- `resolution` leads, every scalar it
    declares stands before its plan fields (`obligations`, `rungs`, then
    `calls`, all optional now that an incorporate, a rewrite or an up
    reaches this same form with nothing released to record). `rungs`
    is issue166's reservation transcription: the spec's own `rungs` field,
    carried here so `carries` can fold it into the run's prefill for the
    gate that actually lands the anchor to see -- `engine/cli.py`'s
    `_land_reserved_rungs`."""
    form = forms.load(CONSOLIDATE)
    assert _ids(form) == ["resolution", "orders", "spec", "key-terms", "settle",
                          "obligations", "rungs", "calls"]
    kinds = _kinds(form)
    assert kinds["spec"] == "artifact"
    assert kinds["key-terms"] == kinds["settle"] == "evidence"
    assert kinds["obligations"] == kinds["rungs"] == kinds["calls"] == "plan"
    assert kinds["resolution"] == "decision"
    assert forms.vocabulary(_note(CONSOLIDATE, "resolution")) == [
        "pass", "revise", "incorporate", "rewrite", "up"]
    obligations = next(f for f in form["fields"] if f["id"] == "obligations")
    assert obligations["mints"] == "board rows"
    assert obligations["board"] == "execution-state"
    assert obligations["optional"] is True
    assert [it["id"] for it in obligations["item"]] == ["obligation"]
    rungs = next(f for f in form["fields"] if f["id"] == "rungs")
    assert rungs["optional"] is True
    assert "mints" not in rungs
    assert [it["id"] for it in rungs["item"]] == ["anchor", "parents"]
    calls = next(f for f in form["fields"] if f["id"] == "calls")
    assert calls["optional"] is True
    assert "mints" not in calls
    assert [it["id"] for it in calls["item"]] == ["finding", "call"]


def test_load_implement():
    form = forms.load(IMPLEMENT)
    assert _ids(form) == ["change", "deviations", "proof"]
    assert _kinds(form)["proof"] == "check"
    assert _kinds(form)["change"] == "evidence"


def test_load_gate_transition():
    form = forms.load(GATE_TRANSITION)
    assert _ids(form) == ["purpose-holds", "findings", "plan-holds", "dispositions",
                          "gate-spec"]
    kinds = _kinds(form)
    # `plan-holds` is a decision because the engine acts on its value, and that
    # kind is what makes its note's alternatives enforced -- see
    # forms.enforced_vocabulary. `purpose-holds` and `findings` are prose the
    # engine only records: the wide question is shaped by the field, never
    # checked by the engine. `dispositions` is a plan field like `gate-spec`
    # -- the engine mints its rows onto the execution-state board rather than
    # acting on the field itself, so it carries no enforced vocabulary either
    # (#56); it opens holding the gate's own `claims`, for the conductor to
    # accept or contest.
    assert kinds["purpose-holds"] == "evidence"
    assert kinds["findings"] == "evidence"
    assert kinds["plan-holds"] == "decision"
    assert kinds["dispositions"] == "plan"
    assert kinds["gate-spec"] == "plan"
    dispositions = next(f for f in form["fields"] if f["id"] == "dispositions")
    assert dispositions["drafted-by"] == "claims"
    assert [it["id"] for it in dispositions["item"]] == ["obligation", "disposition", "root"]
    spec = next(f for f in form["fields"] if f["id"] == "gate-spec")
    assert spec["optional"] is True
    assert [it["id"] for it in spec["item"]] == ["purpose", "scope", "proof",
                                                 "budget", "model"]


def test_load_gate_close():
    form = forms.load(GATE_CLOSE)
    # `residue` first: a scalar after a `[[claims]]` block would parse into
    # the last claim's own table (test_reachable_briefs pins the rule).
    assert _ids(form) == ["residue", "claims"]
    claims = next(f for f in form["fields"] if f["id"] == "claims")
    # The gate's claims return up; nothing is minted at the gate tier, so the
    # field carries no `mints` -- the parent's `dispositions` does that.
    assert claims["kind"] == "plan"
    assert claims["optional"] is True
    assert "mints" not in claims
    assert [it["id"] for it in claims["item"]] == ["obligation", "disposition", "root"]


def test_load_defaults_kind_and_note_and_optional():
    # every field carries the documented defaults when absent from the TOML
    form = forms.load(CONSOLIDATE)
    for field in form["fields"]:
        assert isinstance(field["note"], str) and field["note"]
    # `resolution` is the one field this form declares `optional` explicitly
    # false: everything else that reaches this seam does so through the
    # route form's own resolution word, and it is the one answer no round
    # -- release, rework, or up -- ever leaves out.
    field = next(f for f in form["fields"] if f["id"] == "resolution")
    assert field["kind"] == "decision"
    assert field["optional"] is False


# -- vocabulary(): the values a note declares ---------------------------------


def _note(path, field_id):
    return next(f for f in forms.load(path)["fields"] if f["id"] == field_id)["note"]


def test_a_field_note_declares_the_values_the_engine_will_accept():
    """A transition's alternatives are written once, in the note the agent
    reads. `vocabulary` is how the engine reads the same string, so the enum
    an agent is told and the enum the engine enforces cannot drift."""
    assert forms.vocabulary(_note(REVIEW, "verdict")) == ["pass", "revise"]
    assert forms.vocabulary(_note(GATE_IMPASSE, "ruling")) == ["advance", "rework", "up"]
    # a placeholder alternative survives whole: the argument is another
    # check's question, and the note is what the refusal quotes back
    assert forms.vocabulary(_note(GATE_TRANSITION, "plan-holds")) == [
        "advance", "remint", "drop <gate-id>", "replan"]

    # prose declares nothing, and neither does an enum that has been reworded
    # out of the note's opening -- the one failure mode of this that is silent
    assert forms.vocabulary(_note(GATE_TRANSITION, "findings")) == []
    assert forms.vocabulary("Say which way this goes. " * 3 + "advance | rework | up.") == []

    # and it is the same fact the response template already chose its slot on
    assert forms.vocabulary("light | standard | heavy. Omit for the default.") == [
        "light", "standard", "heavy"]


# -- materialize() ------------------------------------------------------------


def test_materialize_implement_omits_check_field(tmp_path):
    form = forms.load(IMPLEMENT)
    dest = tmp_path / "IMPLEMENT.toml"
    forms.materialize(form, dest)
    text = dest.read_text()
    assert "proof" not in text
    assert "change" in text
    assert "deviations" in text


@pytest.mark.parametrize("path, table", [
    ("skills/planner/forms/PLAN.toml", None),
    ("skills/planner/forms/REWORK.toml", None),
    (GATE_TRANSITION, "gate-spec"),
])
def test_a_command_typed_into_a_minted_proof_slot_reads_back_as_typed(tmp_path, path, table):
    """#182: an awk clause typed into the proof slot came back from TOML with
    its backslash-n turned into a newline. The slot a command is typed into
    holds it byte for byte."""
    command = r"""awk 'BEGIN{RS="\n## "} /ok/ {f=1} END{exit !f}' LOG.md && test "$(grep -c 'a\.b' f)" -ge 2"""
    dest = tmp_path / "FORM.toml"
    forms.materialize(forms.load(path), dest)
    slot = "\nproof = '''\n'''"
    text = dest.read_text()
    assert slot in text
    raw = tomllib.loads(text.replace(slot, f"\nproof = '''\n{command}\n'''", 1))
    got = raw["proof"] if table is None else raw[table][0]["proof"]
    assert got.strip() == command


def test_materialize_header_names_work_id_and_submit_command(tmp_path):
    form = forms.load(IMPLEMENT)
    dest = tmp_path / "issue17" / "IMPLEMENT.toml"
    dest.parent.mkdir()
    forms.materialize(form, dest, work_id="issue17", submit="spine issue17 submit")
    first_line = dest.read_text().splitlines()[0]
    assert first_line.startswith("#")
    assert "issue17" in first_line
    assert "spine issue17 submit" in first_line


def test_materialize_header_defaults_work_id_from_parent_dir(tmp_path):
    form = forms.load(IMPLEMENT)
    dest = tmp_path / "issue42.g1" / "IMPLEMENT.toml"
    dest.parent.mkdir()
    forms.materialize(form, dest)
    first_line = dest.read_text().splitlines()[0]
    assert "issue42.g1" in first_line
    assert "spine issue42.g1 submit" in first_line


def test_materialize_writes_drafted_blocks_in_place_of_the_example(tmp_path):
    """A plan field handed `drafts` opens holding the child's returned blocks,
    one per row and every declared item present -- a key the child never
    returned is an empty slot -- while every other plan field keeps its
    blank example. The answer starts as the claim: leaving a block accepts
    it, changing its word contests it."""
    form = forms.load(GATE_TRANSITION)
    dest = tmp_path / "GATE_TRANSITION.toml"
    forms.materialize(form, dest, drafts={"dispositions": [
        {"obligation": "o1", "disposition": "satisfied", "root": "tests/test_x.py passes"},
        {"obligation": "o2", "disposition": "deferred: the next gate's"}]})
    text = dest.read_text()
    with open(dest, "rb") as f:
        parsed = tomllib.load(f)
    assert [b["obligation"] for b in parsed["dispositions"]] == ["o1", "o2"]
    assert parsed["dispositions"][0]["root"] == "tests/test_x.py passes"
    assert parsed["dispositions"][1]["root"] == ""
    assert text.count("Repeat this block per item") == 1  # gate-spec's example alone
    assert "Written from the return's `claims`" in text


@pytest.mark.parametrize("path", [OPEN, CONSOLIDATE, IMPLEMENT, GATE_TRANSITION, GATE_CLOSE])
def test_materialize_output_always_parses(tmp_path, path):
    form = forms.load(path)
    dest = tmp_path / "OUT.toml"
    forms.materialize(form, dest)
    with open(dest, "rb") as f:
        tomllib.load(f)  # must not raise


def test_materialize_notes_are_wrapped_and_optional_marked(tmp_path):
    form = {
        "imperative": "x",
        "fields": [
            {
                "id": "extra",
                "kind": "evidence",
                "note": "A short note that should still show up as optional in its comment.",
                "optional": True,
            }
        ],
    }
    dest = tmp_path / "OUT.toml"
    forms.materialize(form, dest)
    text = dest.read_text()
    assert "Optional" in text
    # skip the header line: it names a path + command, exempt from wrapping
    for line in text.splitlines()[1:]:
        if line.startswith("#"):
            assert len(line) <= 80


# -- round-trip: materialize, fill, parse -------------------------------------


def test_prose_with_quotes_and_triple_quote_round_trips(tmp_path):
    form = forms.load(CONSOLIDATE)
    dest = tmp_path / "CONSOLIDATE.toml"
    forms.materialize(form, dest)
    text = dest.read_text()

    tricky = 'He said "hello" and used a \\"\\"\\" escape-looking bit,\nplus a literal """ triple quote.\nSecond line here.'
    from engine import tomlw

    filled = text.replace('key-terms = """\n"""', "key-terms = " + tomlw._multiline(tricky))
    dest.write_text(filled)

    result = forms.parse(dest)
    assert result["key-terms"] == tricky


def test_blank_slots_omitted_and_waived_kept(tmp_path):
    form = forms.load(CONSOLIDATE)
    dest = tmp_path / "CONSOLIDATE.toml"
    forms.materialize(form, dest)
    text = dest.read_text()
    text = text.replace('key-terms = """\n"""', 'key-terms = """\nwaived: none\n"""')
    dest.write_text(text)

    result = forms.parse(dest)
    assert "spec" not in result  # left blank
    assert "settle" not in result  # left blank
    assert "resolution" not in result  # left blank
    assert result["key-terms"] == "waived: none"


def test_plan_field_round_trips_two_blocks(tmp_path):
    form = forms.load(OPEN)
    dest = tmp_path / "OPEN.toml"
    forms.materialize(form, dest, work_id="issue17", submit="spine issue17 submit")
    text = dest.read_text()

    # fill the single example block, then append a second block after it
    assert '[[questions]]' in text
    text = text.replace('question = ""', 'question = "Does the CLI validate the token?"', 1)
    text = text.replace('type = ""', 'type = "fact"', 1)
    text += '\n[[questions]]\nquestion = "Who owns the retry budget?"\ntype = "decision"\n'
    text = text.replace('issue = ""', 'issue = "issue17"')
    text = text.replace('authority = """\n"""', 'authority = """\nwaived: derived from parent\n"""')
    dest.write_text(text)

    result = forms.parse(dest)
    # the first block came from the template, so it carries the blank
    # `excursion` slot; the hand-appended second block does not.
    assert result["questions"] == [
        {"question": "Does the CLI validate the token?", "excursion": "",
         "type": "fact"},
        {"question": "Who owns the retry budget?", "type": "decision"},
    ]
    assert result["issue"] == "issue17"
    assert result["authority"] == "waived: derived from parent"


def test_parse_ignores_form_definition_reads_file_directly(tmp_path):
    # parse()'s signature takes only dest_path -- confirm it needs no form arg
    dest = tmp_path / "OUT.toml"
    dest.write_text('a = "x"\nb = ""\nc = []\n')
    assert forms.parse(dest) == {"a": "x"}


# -- the excursion column: its own named field on every understand row -------


# [column-notes]
# Rationale: a board template's doctrine lives in TOML comments, which
#   tomllib discards -- so a note is only pinnable by reading the file as
#   text. Scoping a note to its own column (indented continuations only,
#   ended by a blank line or an unindented comment) is what lets these
#   tests assert a boundary between two columns rather than substring-
#   matching the whole file, where `artifact` and `excursion` both appear.
# Rejected: matching against the whole file's text -- it cannot tell "the
#   excursion note names artifact" from "artifact is mentioned somewhere",
#   which is exactly the claim these tests exist to make.
def _column_notes(path):
    """The inline `# ...` note attached to each `name = ...` line of a board
    template, continuation lines folded in. A blank line or an unindented
    comment ends a note, which is what keeps the file's standalone doctrine
    blocks from bleeding into the column above them."""
    notes, current = {}, None
    for line in pathlib.Path(path).read_text().splitlines():
        head, sep, comment = line.partition("#")
        if not line.strip() or (not head.strip() and not line.startswith((" ", "\t"))):
            current = None
        elif re.match(r"^\w[\w-]* = ", line):
            current = line.split(" = ")[0]
            notes[current] = comment.strip()
        elif current and sep and not head.strip():
            notes[current] += " " + comment.strip()
    return notes


def test_seeded_row_carries_excursion(tmp_path):
    """The column reaches a seeded row through the mint alone, no engine change:
    OPEN's `questions` field offers the item, a blank value survives parse
    (only top-level blanks are dropped), and `_seed_board` writes it onto the
    row. Blank on the board beats present-only in the commented header -- the
    header is what 63 rows read past."""
    questions = next(f for f in forms.load(OPEN)["fields"] if f["id"] == "questions")
    assert "excursion" in [it["id"] for it in questions["item"]]

    dest = tmp_path / "UNDERSTAND.toml"
    cli._seed_board(pathlib.Path(UNDERSTAND), dest,
                    [{"question": "Who owns the retry budget?", "excursion": "",
                      "type": "fact"}])
    row = boards.rows(dest)[0]
    assert row["excursion"] == ""
    assert "excursion" in dest.read_text().split("# --- the board ---")[1]


def test_a_row_is_labelled_by_its_boards_own_column_in_any_order(tmp_path):
    """#47, #86: a row's label was its first string, so a column above the
    real one -- a flat `recommend`, a `verdict` a plan listed first --
    labelled the row everywhere it rendered. The label is the column the
    board names its array after, wherever it sits in the row."""
    board = tmp_path / "UNDERSTAND.toml"
    board.write_text('''[[question]]
id = "q1"
recommend = "an offered draft"
excursion = "prior-art: what the ecosystem does with retries"
question = "Who owns the retry budget?"
type = "decision"
status = "open"
''')
    assert boards.column(board) == "question"
    assert boards.label(boards.rows(board)[0], boards.column(board)) == "Who owns the retry budget?"

    ideas = tmp_path / "IDEAS.toml"
    cli._seed_board(pathlib.Path("skills/explorer/forms/IDEAS.toml"), ideas,
                    [{"verdict": "a verdict listed first", "idea": "the real idea"}])
    assert boards.label(boards.rows(ideas)[0], boards.column(ideas)) == "the real idea"


def test_move_note_drops_excursions():
    """`move` offers only what is settled without leaving the board. Offering
    the three excursion moves in both columns is the shape that let a row pick
    one of six in-place options and pick an excursion zero times in twelve
    runs."""
    move = _column_notes(UNDERSTAND)["move"]
    for offered in ("prior-art", "prototype", "picture"):
        assert offered not in move
    for kept in ("read", "trace", "reproduce", "evidence-loop", "ask", "mirror"):
        assert kept in move


def test_artifact_defers_to_excursion():
    """One job, one column. `excursion` owns the brief and the child run and
    its returns; `artifact` keeps grounding evidence of every other kind. Both
    notes state the boundary, so neither reader has to infer it."""
    notes = _column_notes(UNDERSTAND)

    assert "returns stamp back here" in notes["excursion"]
    assert "returns stamp back here" not in notes["artifact"]
    assert "artifact" in notes["excursion"]
    assert "excursion" in notes["artifact"]

    # the brief the column exists to carry, and the decline that is never blank
    for briefed in ("prior-art", "prototype", "picture", "budget", "stop conditions"):
        assert briefed in notes["excursion"]
    assert "never a blank" in notes["excursion"]
