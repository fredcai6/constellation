"""Forms: load a step's form, materialize its response template, parse it back.

A form is a TOML file: one `imperative` string plus `[[field]]` entries (a
`plan` field nests `[[field.item]]` blocks). The response template is the
only way an agent answers a step -- it edits the file with ordinary tools;
`parse` reads it back with stdlib `tomllib`. `check` fields never reach the
template: the engine runs those commands itself at submit.
"""

import textwrap
import tomllib
from pathlib import Path

_WIDTH = 70  # comment content width; "# " prefix brings lines to ~72 cols


def _field(raw: dict) -> dict:
    out = {
        "id": raw["id"],
        "kind": raw.get("kind", "evidence"),
        "note": raw.get("note", ""),
        "optional": raw.get("optional", False),
    }
    if "mints" in raw:
        out["mints"] = raw["mints"]
    if raw.get("record-only"):  # the producer's ledger -- the prefill guard reads this
        out["record-only"] = True
    if "item" in raw:
        out["item"] = [_field(it) for it in raw["item"]]
    return out


def load(form_path) -> dict:
    with open(form_path, "rb") as f:
        raw = tomllib.load(f)
    return {
        "imperative": raw.get("imperative", ""),
        "fields": [_field(f) for f in raw.get("field", [])],
    }


def _comment(note: str, optional: bool) -> str:
    """Wrap a note into '# '-prefixed lines, an optional marker appended."""
    if optional:
        note = note + " Optional -- may be left blank."
    lines = []
    for para in note.split("\n\n"):  # blank line = paragraph break; a
        collapsed = " ".join(para.split())  # single newline is just wrap
        lines.extend(textwrap.wrap(collapsed, width=_WIDTH) or [""])
    return "\n".join(f"# {line}" for line in lines)


def _is_short(field: dict) -> bool:
    """Short `id = ""` slot vs multi-line prose slot -- judgment call: short
    when the note itself reads as an enum, or the field is a brief
    decision/artifact (typically one word or one path); else multi-line,
    since prose is the common case."""
    if " | " in field["note"][:80]:
        return True
    return field["kind"] in ("decision", "artifact") and len(field["note"]) < 120


def _slot(field_id: str, short: bool) -> str:
    return f'{field_id} = ""' if short else f'{field_id} = """\n"""'


def materialize(form: dict, dest_path, work_id=None, submit=None) -> None:
    dest_path = Path(dest_path)
    work_id = work_id or dest_path.parent.name
    submit = submit or f"spine {work_id} submit"
    lines = [f"# {dest_path} -- fill the values, then: {submit}",
             "#",
             "# Any field also takes a status instead of an answer:",
             "#   working: <what is left>   still in hand; submit will say so",
             "#   waived: <reason>          does not apply here",
             "#   unknown: <reason>         could not determine",
             ""]
    for field in form["fields"]:
        if field["kind"] == "check":
            continue
        lines.append(_comment(field["note"], field["optional"]))
        if field["kind"] == "plan":
            lines.append("# Repeat this block per item; delete the example if none apply.")
            lines.append(f'[[{field["id"]}]]')
            for item in field.get("item", []):
                lines.append(_comment(item["note"], item["optional"]))
                lines.append(_slot(item["id"], True))
        else:
            lines.append(_slot(field["id"], _is_short(field)))
        lines.append("")
    dest_path.write_text("\n".join(lines).rstrip() + "\n")


def _clean(v):
    """Strip a string's leading/trailing blank lines; recurse into lists/dicts."""
    if isinstance(v, str):
        rows = v.split("\n")
        while rows and rows[0].strip() == "":
            rows.pop(0)
        while rows and rows[-1].strip() == "":
            rows.pop()
        return "\n".join(rows)
    if isinstance(v, list):
        return [_clean(x) for x in v]
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    return v


def _is_blank(v) -> bool:
    return v == "" or (isinstance(v, str) and v.strip() == "") or v == []


def _parse_impl(dest_path) -> dict:
    with open(dest_path, "rb") as f:
        raw = tomllib.load(f)
    cleaned = {k: _clean(v) for k, v in raw.items()}
    return {k: v for k, v in cleaned.items() if not _is_blank(v)}


def parse(dest_path):
    """Read a filled response form. A file the agent broke while filling it is
    a refusal naming the line, never a traceback -- the agent is mid-edit and
    needs to know where to look."""
    try:
        return _parse_impl(dest_path)
    except tomllib.TOMLDecodeError as e:
        raise SystemExit(f"{Path(dest_path).name}: not valid TOML -- {e}\n"
                         "  fix the file and submit again; nothing was recorded")


def in_hand(dest_path):
    """Fields the agent marked `working:` -- what is still open on this form.

    A status nobody renders is a status nobody sets, so this is what makes the
    marker worth writing: it shows up in `status` and in the rail's nudge.
    """
    try:
        filled = parse(dest_path)
    except SystemExit:
        return {}
    return {k: str(v).strip()[len("working:"):].strip()
            for k, v in filled.items() if str(v).strip().startswith("working:")}
