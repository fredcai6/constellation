"""Tests for engine/forms.py: load, materialize, parse."""

import tomllib

import pytest

from engine import forms

OPEN = "assemblies/run-an-issue/forms/OPEN.toml"
CONSOLIDATE = "assemblies/run-an-issue/forms/CONSOLIDATE.toml"
IMPLEMENT = "skills/implementer/forms/IMPLEMENT.toml"
GATE_TRANSITION = "assemblies/run-an-issue/forms/GATE_TRANSITION.toml"


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
    assert [it["id"] for it in questions["item"]] == ["question", "type"]
    assert form["imperative"].startswith("Confirm what this run is solving")


def test_load_consolidate():
    form = forms.load(CONSOLIDATE)
    assert _ids(form) == ["learnings", "key-terms", "settle"]
    assert set(_kinds(form).values()) == {"evidence"}


def test_load_implement():
    form = forms.load(IMPLEMENT)
    assert _ids(form) == ["change", "deviations", "done"]
    assert _kinds(form)["done"] == "check"
    assert _kinds(form)["change"] == "evidence"


def test_load_gate_transition():
    form = forms.load(GATE_TRANSITION)
    assert _ids(form) == ["learned", "plan-holds"]
    assert set(_kinds(form).values()) == {"evidence"}


def test_load_defaults_kind_and_note_and_optional():
    # every field carries the documented defaults when absent from the TOML
    form = forms.load(CONSOLIDATE)
    for field in form["fields"]:
        assert field["kind"] == "evidence"
        assert isinstance(field["note"], str) and field["note"]
        assert field["optional"] is False


# -- materialize() ------------------------------------------------------------


def test_materialize_implement_omits_check_field(tmp_path):
    form = forms.load(IMPLEMENT)
    dest = tmp_path / "IMPLEMENT.toml"
    forms.materialize(form, dest)
    text = dest.read_text()
    assert "done" not in text
    assert "change" in text
    assert "deviations" in text


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


@pytest.mark.parametrize("path", [OPEN, CONSOLIDATE, IMPLEMENT, GATE_TRANSITION])
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

    filled = text.replace('learnings = """\n"""', "learnings = " + tomlw._multiline(tricky))
    dest.write_text(filled)

    result = forms.parse(dest)
    assert result["learnings"] == tricky


def test_blank_slots_omitted_and_waived_kept(tmp_path):
    form = forms.load(CONSOLIDATE)
    dest = tmp_path / "CONSOLIDATE.toml"
    forms.materialize(form, dest)
    text = dest.read_text()
    text = text.replace('key-terms = """\n"""', 'key-terms = """\nwaived: none\n"""')
    dest.write_text(text)

    result = forms.parse(dest)
    assert "learnings" not in result  # left blank
    assert "settle" not in result  # left blank
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
    assert result["questions"] == [
        {"question": "Does the CLI validate the token?", "type": "fact"},
        {"question": "Who owns the retry budget?", "type": "decision"},
    ]
    assert result["issue"] == "issue17"
    assert result["authority"] == "waived: derived from parent"


def test_parse_ignores_form_definition_reads_file_directly(tmp_path):
    # parse()'s signature takes only dest_path -- confirm it needs no form arg
    dest = tmp_path / "OUT.toml"
    dest.write_text('a = "x"\nb = ""\nc = []\n')
    assert forms.parse(dest) == {"a": "x"}
