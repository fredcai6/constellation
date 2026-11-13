"""A field worded once: `same-as` takes another form's field whole, and the
referring field keeps only what it writes itself."""
import pytest

from engine import forms

ROOT = forms._ROOT
PLAN = "skills/planner/forms/PLAN.toml"


def test_a_same_as_field_takes_the_source_fields_kind_note_and_items():
    plan = {f["id"]: f for f in forms.load(ROOT / PLAN)["fields"]}
    for name in ("REWORK", "REVIEW_PLAN"):
        form = {f["id"]: f for f in forms.load(ROOT / f"skills/planner/forms/{name}.toml")["fields"]}
        for fid in ("call-tree", "key-terms", "critical-questions", "gates"):
            assert form[fid] == plan[fid], f"{name}.{fid}"


def test_what_the_referring_field_writes_itself_wins(tmp_path):
    form = tmp_path / "F.toml"
    form.write_text(f'[[field]]\nid = "spec"\nsame-as = "{PLAN}#gates"\n'
                    'optional = true\nnote = "only for remint"\n')
    [field] = forms.load(form)["fields"]
    assert field["id"] == "spec" and field["optional"] is True
    assert field["note"] == "only for remint"
    assert field["kind"] == "plan"
    assert [it["id"] for it in field["item"]][:3] == ["purpose", "scope", "proof"]


def test_a_same_as_that_names_no_such_field_fails_loudly(tmp_path):
    form = tmp_path / "F.toml"
    form.write_text(f'[[field]]\nid = "x"\nsame-as = "{PLAN}#nope"\n')
    with pytest.raises(ValueError, match="has no field 'nope'"):
        forms.load(form)


def test_no_form_tells_its_reader_to_look_at_another_form():
    """The agent filling a form is shown that form alone."""
    import re
    for path in list(ROOT.glob("skills/*/forms/*.toml")) + list(ROOT.glob("assemblies/*/forms/*.toml")):
        form = forms.load(path)
        notes = [form["imperative"]] + [f["note"] for f in form["fields"]] + \
                [it["note"] for f in form["fields"] for it in f.get("item", [])]
        for note in notes:
            assert not re.search(r"[Ss]ame as \w+\.toml", note), f"{path.name}: {note[:80]}"
