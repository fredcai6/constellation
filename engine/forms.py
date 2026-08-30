"""Forms: load a step's form, materialize its response template, parse it back.

A form is a TOML file: one `imperative` string plus `[[field]]` entries (a
`plan` field nests `[[field.item]]` blocks). The response template is the
only way an agent answers a step -- it edits the file with ordinary tools;
`parse` reads it back with stdlib `tomllib`. `check` fields never reach the
template: the engine runs those commands itself at submit.
"""

import re
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
    # Rationale: a `mints = "board rows"` field used to reach the only board
    #   segment an assembly ever had, found by being the one whose `interior`
    #   is `"board"` -- unambiguous while true. `board` names which of
    #   several a field seeds, the moment run-an-issue holds two
    #   (`engine/cli.py`'s `_board_segment`); carried through `_field` here
    #   the same way `mints` itself already is, so it survives from the raw
    #   TOML into what `_mint` reads at submit.
    if "board" in raw:
        out["board"] = raw["board"]
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


# One alternative is a run of ordinary words ending in a non-space: `|`
# separates them, and the sentence punctuation after the last one ends the
# enum. Ending each on a non-space is what lets the run reach its last
# alternative -- a token that swallowed its own trailing space would leave
# `\s*\|` with nothing to match and stop the enum a term early.
_TOKEN = r"[^|\n.;,:\u2014]*[^\s|\n.;,:\u2014]"
_ALTERNATIVES = re.compile(rf"{_TOKEN}(?:\s*\|\s*{_TOKEN})+")


# [field-vocabulary]
# Rationale: the values a field accepts are already written once -- in the note
#   the agent reads. Deriving them from that note is what makes the enum an
#   agent is told and the enum the engine enforces one string, so a reworded
#   note cannot leave the engine enforcing the old list.
# Rejected: a `values = [...]` key beside the note. A second copy of the same
#   list is a second place for it to go stale, and the note stays the thing the
#   agent actually reads -- so the copy the engine trusted could be the wrong
#   one.
def vocabulary(note: str) -> list[str]:
    """The alternatives a note declares -- `["pass", "revise"]` --
    or `[]` for a note that declares none.

    The enum has to open the note to count. A note reworded so its ` | ` falls
    past the first 80 characters yields `[]` and validates nothing: the same
    silence that stood before this derivation existed, and the only failure
    mode of it that is not loud.
    """
    if " | " not in note[:80]:
        return []
    found = _ALTERNATIVES.search(note)
    return [alt.strip() for alt in found.group(0).split("|")] if found else []


def leading_word(value) -> str:
    """The word a submitted value selects -- `"converge -- Tommy: yes, go"`
    selects `converge`.

    One rule, because there were two. The declared-outcomes path matched the
    first word while the gate path matched the whole string, so the same
    answer was legal at one transition and refused at another, and a form
    asking for a value *and* a sentence (`logic | ui | measurement -- and the
    one line that put it there`) could not be answered as written. The word
    carries the decision; the rest carries the reason, and a reason should
    never have to be omitted to be understood.
    """
    words = str(value).split()
    return words[0].strip(".,;:-").lower() if words else ""


def enforced_vocabulary(field: dict) -> list[str]:
    """The values the engine will accept for a field -- `[]` where it accepts
    anything.

    Two conditions, and the second is the one that took a second pass to get
    right. A note's alternatives say *what* the values are; `kind = "decision"`
    says the engine acts on them, and only then is the note load-bearing.
    Deriving enforcement from the punctuation alone made an ordinary prose
    note -- `Name the risk | the mitigation | who owns it` -- into an enum
    nothing declared and no one could see, and a field kind is a thing a form
    author chooses on purpose.
    """
    return vocabulary(field["note"]) if field["kind"] == "decision" else []


def _is_short(field: dict) -> bool:
    """Short `id = ""` slot vs multi-line prose slot: two rules, then a proxy.

    A field whose note lists its values takes one of them. That is keyed off
    `enforced_vocabulary` rather than the note alone, so a ` | ` in ordinary
    prose means nothing here either -- one rule for what the punctuation does,
    not one for the slot and another for the check.

    An `artifact` field takes a path: `cli._measure_artifacts` reads its value
    with `Path(...).read_text()`, so one line is the only shape it was ever
    going to be, however long the note explaining it runs. Reading the note's
    length here instead gave run-an-issue PLAN.toml's `plan` a prose block and
    PLAN_TO_EXECUTE.toml's `plan` a line for the same document.

    The proxy is the last case, and it is a proxy: a `decision` note under 120
    characters is read as a one-word answer and one over it as prose, which
    guesses the answer's length from the note's. It holds across a 44-character
    gap -- explore-an-idea CLOSE.toml's `confirmed` takes a line at 76, its
    OPEN.toml's `authority` takes a block at 121 -- so there is no room to
    raise the number, and a decision note that crosses it changes the minted
    slot with nothing at the note to say so. Declaring the shape in the form
    would end that."""
    if enforced_vocabulary(field) or field["kind"] == "artifact":
        return True
    return field["kind"] == "decision" and len(field["note"]) < 120


def _slot(field_id: str, short: bool) -> str:
    return f'{field_id} = ""' if short else f'{field_id} = """\n"""'


# [escapes-refused]
# Rationale: the two escapes are offered per field, not once per form, because
#   `cli._check_vocabulary` refuses both on a `decision` field whose note
#   declares its values -- a `waived:` verdict would fall through `merged_verdict` to
#   `pass`, so the refusal is correct and it is the template that was wrong to
#   promise a way out its own submit rejects.
# Rejected: dropping the two lines from the header for every form. A form is a
#   mix -- one field with a vocabulary beside four of prose -- and the four
#   still take the escapes; a per-form answer is wrong for one side or the
#   other whichever way it goes.
# See: engine/cli.py `_check_vocabulary`
ESCAPES_REFUSED = "# One of those values -- this field refuses waived: and unknown:."


def materialize(form: dict, dest_path, work_id=None, submit=None) -> None:
    dest_path = Path(dest_path)
    work_id = work_id or dest_path.parent.name
    submit = submit or f"spine {work_id} submit"
    shown = [f for f in form["fields"] if f["kind"] != "check"]
    lines = [f"# {dest_path} -- fill the values, then: {submit}",
             "#",
             "# Any field also takes a status instead of an answer:",
             "#   working: <what is left>   still in hand; submit will say so"]
    # The escapes are named at all only while some field still accepts them.
    if any(not enforced_vocabulary(f) for f in shown):
        lines += ["#   waived: <reason>          does not apply here",
                  "#   unknown: <reason>         could not determine"]
    lines.append("")
    for field in shown:
        lines.append(_comment(field["note"], field["optional"]))
        if field["kind"] == "plan":
            lines.append("# Repeat this block per item; delete the example if none apply.")
            lines.append(f'[[{field["id"]}]]')
            for item in field.get("item", []):
                lines.append(_comment(item["note"], item["optional"]))
                lines.append(_slot(item["id"], True))
        else:
            if enforced_vocabulary(field):
                lines.append(ESCAPES_REFUSED)
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
