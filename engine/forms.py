"""Forms: load a step's form, materialize its response template, parse it back.

A form is a TOML file: one `imperative` string plus `[[field]]` entries (a
`plan` field nests `[[field.item]]` blocks). The response template is the
only way an agent answers a step -- it edits the file with ordinary tools;
`parse` reads it back with stdlib `tomllib`. `check` fields never reach the
template: the engine runs those commands itself at submit. A `proof` field
is filled like any other and run once at submit too, as a report the
conductor reads rather than a check the submit rides on
(`_trial_proofs`, engine/cli.py).
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
    # Rationale: a `mints = "board rows"` field reaching a board segment by
    #   being the one whose `interior` is `"board"` is unambiguous only while
    #   an assembly has one. `board` names which of several a field seeds
    #   (`engine/cli.py`'s `_board_segment`); carried through `_field` the same
    #   way `mints` itself is, so it survives from the raw TOML into what
    #   `_mint` reads at submit.
    if "board" in raw:
        out["board"] = raw["board"]
    if raw.get("record-only"):  # the producer's ledger -- the prefill guard reads this
        out["record-only"] = True
    # Rationale: a `plan` field the parent answers by accepting or contesting
    #   what its child claimed (GATE_TRANSITION.toml's `dispositions`, off
    #   GATE_CLOSE.toml's `claims`) names the returned field it opens already
    #   holding. Carried like `mints` and `board`, so `cli._drafts` reads it
    #   off the loaded form and `materialize` writes the blocks.
    if "drafted-by" in raw:
        out["drafted-by"] = raw["drafted-by"]
    if "item" in raw:
        out["item"] = [_field(it) for it in raw["item"]]
    return out


# [same-as]
# Rationale: three planner forms and the gate adjudication each restated the
#   same fields -- `call-tree` byte for byte, a gate's `proof` in four
#   wordings that had drifted apart (one form lost the rule that a later
#   gate's proof names its own tests; one said "the string you ran" where
#   the others said "to run"). A field worded once cannot drift. A field
#   that declares `same-as = "<form path>#<field id>"` takes that field
#   whole -- kind, note, items -- and keeps only what it writes itself.
# Rejected: "Same as PLAN.toml's `proof`" in the note. The agent filling the
#   form is not shown PLAN.toml, so the note pointed at text it could not see.
_ROOT = Path(__file__).resolve().parent.parent


def _same_as(raw: dict, seen=()) -> dict:
    """`raw` with its `same-as` source folded in beneath it; `raw` itself
    where it declares none. The path is relative to the engine root."""
    ref = raw.get("same-as")
    if not ref:
        return raw
    path, _, field_id = ref.partition("#")
    field_id = field_id or raw["id"]
    if ref in seen:
        raise ValueError(f"same-as loops back on {ref}")
    with open(_ROOT / path, "rb") as f:
        source = tomllib.load(f)
    found = next((x for x in source.get("field", []) if x["id"] == field_id), None)
    if found is None:
        raise ValueError(f"same-as names {ref}, and {path} has no field {field_id!r}")
    merged = {**_same_as(found, (*seen, ref)), **raw}
    merged.pop("same-as")
    return merged


def load(form_path) -> dict:
    with open(form_path, "rb") as f:
        raw = tomllib.load(f)
    return {
        "imperative": raw.get("imperative", ""),
        "fields": [_field(_same_as(f)) for f in raw.get("field", [])],
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
# A value may declare that it carries a reason -- `rejected: <reason>`. The
# suffix belongs to its alternative, so it does not end the enum:
# `satisfied | open: <reason> | deferred: <reason>` declares three values.
_REASON = r"(?::\s*<[^>|\n]*>)?"
_ALTERNATIVES = re.compile(rf"{_TOKEN}{_REASON}(?:\s*\|\s*{_TOKEN}{_REASON})+")
_REASONED = re.compile(r"^(.*?):\s*<[^>]*>$")


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
    silence of a note with no derived vocabulary, and the only failure mode
    of the derivation that is not loud.
    """
    return [_REASONED.sub(r"\1", alt) for alt in declared(note)]


def declared(note: str) -> list[str]:
    """The alternatives exactly as the note writes them, reason suffix
    included -- `["blocking", "accepted", "rejected: <reason>"]`. This is
    what a refusal prints, so the reader sees which values owe a reason."""
    if " | " not in note[:80]:
        return []
    found = _ALTERNATIVES.search(note)
    return [alt.strip() for alt in found.group(0).split("|")] if found else []


def reasoned(note: str) -> list[str]:
    """The values a note declares with a reason -- `["rejected"]`."""
    return [m.group(1).strip() for m in map(_REASONED.match, declared(note)) if m]


def leading_word(value) -> str:
    """The word a submitted value selects -- `"converge -- Tommy: yes, go"`
    selects `converge`.

    One rule for every path. Two rules (the first word at one transition,
    the whole string at another) would make the same answer legal at one and
    refused at another, and a form
    asking for a value *and* a sentence (`logic | ui | measurement -- and the
    one line that put it there`) could not be answered as written. The word
    carries the decision; the rest carries the reason, and a reason should
    never have to be omitted to be understood.
    """
    words = str(value).split()
    return words[0].strip(".,;:-").lower() if words else ""


# [null-answers-do-not-travel]
# Rationale: `waived: <reason>` and `unknown: <reason>` are how a form says a
#   field has no value, and stored as the value, every later reader would
#   have to know the vocabulary to avoid acting on a non-answer,
#   and three readers did not: `_tier` read `waived: none` as a model tier
#   and dispatched `claude --model ""` until the start cap spent (three dead
#   children in one real run), `checks.budget_for` refused a proof whose
#   budget was waived instead of using the default, and `_gate_subject` wrote
#   a commit titled `g1: waived: none`. None of those is wrong about values;
#   each is right about a value and was handed a non-value.
# Rejected: teaching each reader the vocabulary. That is the same rule in N
#   places, and `_round_findings` already carries a fourth copy inline. The
#   engine already treats an absent optional field correctly everywhere --
#   `_tier`'s own `or seg.get("model", "")` is why an empty `model` has
#   always worked -- so a null that resolves to absent needs no reader to
#   change at all.
# Rejected: storing the reason alongside under a second key. The reason is
#   already in the journal, on the submit entry that answered the field; a
#   prefill is orders, and a reason a step was not ordered is not an order.
# Rejected: applying this to every prefill a run writes. Most of what a
#   prefill carries is not an order the engine reads -- it is an artifact a
#   later reader is handed, and there `waived: none` is an *answer*. A
#   reviewer told `deviations = "waived: none"` knows the implementer
#   declared none; hand it an absent key instead and it cannot tell that
#   from a field nobody filled. `tests/test_verdict_panels.py` and
#   `tests/test_planner_prefill.py` both pin that, and both go red when
#   this is applied broadly. So it belongs only where a spec becomes
#   orders the engine itself acts on -- `_mint_gates` -- and nowhere that
#   merely carries one agent's answer to the next.
NULL_WORDS = ("waived", "unknown")


def without_nulls(fields):
    """`fields` with every null answer dropped, so a non-value never travels
    as orders. What is left is what was actually declared -- and a reader
    asking for a key that is not there already has the behaviour a waived
    field asks for, which is its own default."""
    return {k: v for k, v in (fields or {}).items()
            if not (isinstance(v, str) and leading_word(v) in NULL_WORDS)}


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


# [command-slot-is-literal]
# Rationale: a planner who writes an awk clause, `RS="\n## "`, into a
#   `"""` slot has TOML read the two characters as a newline: the value is
#   exactly what TOML meant and not what the planner typed, and the gate's
#   own check dies on it after the work is built. A command is text for a
#   shell, and a basic string puts a second escape language in front of it.
#   A literal string has none, so a command slot is minted as one and what is
#   typed into it is what runs.
# Rejected: a note asking planners to double their backslashes. It is one
#   more thing to read on every cut, and the slot still decodes what it holds.
# See: #182
COMMAND_KINDS = ("proof", "check")


def _slot(field_id: str, short: bool, kind: str = "") -> str:
    if kind in COMMAND_KINDS:
        return f"{field_id} = '''\n'''"
    return f'{field_id} = ""' if short else f'{field_id} = """\n"""'


# [escapes-refused]
# Rationale: the two escapes are offered per field, not once per form, because
#   `cli._check_vocabulary` refuses both on a `decision` field whose note
#   declares its values -- a `waived:` verdict is no word that field's own
#   vocabulary declares, so `verdict_fold` resolves it to a refusal naming
#   that voice, which holds the round open at its seam and names it at the
#   room. The refusal here is correct, and it is the template that was wrong
#   to promise a way out its own submit rejects.
# Rejected: dropping the two lines from the header for every form. A form is a
#   mix -- one field with a vocabulary beside four of prose -- and the four
#   still take the escapes; a per-form answer is wrong for one side or the
#   other whichever way it goes.
# See: engine/cli.py `_check_vocabulary`
ESCAPES_REFUSED = "# One of those values -- this field refuses waived: and unknown:."


def _drafted(field: dict, rows: list) -> list[str]:
    """A plan field's blocks written from what the child returned, one per
    row, every declared item present -- a key the child did not return is an
    empty slot, never a missing one. The answer starts as the claim: leaving
    a block accepts it, changing its word contests it."""
    from engine import tomlw
    lines = [f"# Written from the return's `{field.get('drafted-by', '')}`, one block "
             "per claim as the child made it. Leave a block to accept; change its "
             "word to contest; delete it to leave the row open."]
    for row in rows:
        block = {it["id"]: row.get(it["id"], "") for it in field.get("item", [])}
        lines.append(tomlw.table(field["id"], block).rstrip())
        lines.append("")
    return lines[:-1]


def materialize(form: dict, dest_path, work_id=None, submit=None, drafts=None) -> None:
    """Write the response template. `drafts` is `{field id: rows}` for the
    plan fields that open already holding a child's returned blocks
    (`cli._drafts`); every other plan field gets its blank example."""
    dest_path = Path(dest_path)
    work_id = work_id or dest_path.parent.name
    submit = submit or f"spine {work_id} submit"
    drafts = drafts or {}
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
        if field["kind"] == "plan" and drafts.get(field["id"]):
            lines.extend(_drafted(field, drafts[field["id"]]))
        elif field["kind"] == "plan":
            lines.append("# Repeat this block per item. A block list takes blocks only, never"
                         " waived: or unknown:." + (
                             " Delete the example if none apply." if field["optional"]
                             else " It needs at least one block."))
            lines.append(f'[[{field["id"]}]]')
            for item in field.get("item", []):
                lines.append(_comment(item["note"], item["optional"]))
                lines.append(_slot(item["id"], True, item.get("kind", "")))
        else:
            if enforced_vocabulary(field):
                lines.append(ESCAPES_REFUSED)
            lines.append(_slot(field["id"], _is_short(field), field["kind"]))
        lines.append("")
    dest_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _clean(v):
    """Strip a string's leading/trailing blank lines; recurse into lists/dicts.
    A repeated block with every field blank is the form's own example left
    standing, so it is no block: a remint from one (story_time issue57) would
    never see the `remint` refusal that names a missing spec."""
    if isinstance(v, str):
        rows = v.split("\n")
        while rows and rows[0].strip() == "":
            rows.pop(0)
        while rows and rows[-1].strip() == "":
            rows.pop()
        return "\n".join(rows)
    if isinstance(v, list):
        cleaned = [_clean(x) for x in v]
        return [x for x in cleaned
                if not (isinstance(x, dict) and all(_is_blank(y) for y in x.values()))]
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


def answered(filled):
    """Field ids this form already carries an answer for -- anything filled
    that is not a `working:` marker. Takes what `parse` returned, so the room
    reads the file once for this and `in_hand` both.

    A form is materialized once and adopted by whoever stands on the step
    next, which is deliberate (`_response_path`, engine/cli.py: a filler
    restarted on the same step picks up its own in-progress form). The room
    said nothing about it, so an agent that inherited a stopped agent's work
    read a complete answer as its own blank form. This is what the room
    reports instead of guessing who wrote what, which it cannot know.

    See: #26
    """
    return [k for k, v in filled.items()
            if not str(v).strip().startswith("working:")]


def filled_or_empty(dest_path):
    """What `parse` returned, or `{}` for a file that is absent or that the
    agent broke while filling it -- a form nobody can read carries no answers
    to report, and the refusal that says so belongs to `submit`, not here."""
    if not dest_path.exists():
        return {}
    try:
        return parse(dest_path)
    except SystemExit:
        return {}


def in_hand(filled):
    """Fields the agent marked `working:` -- what is still open on this form.

    A status nobody renders is a status nobody sets, so this is what makes the
    marker worth writing: it shows up in `status` and in the rail's nudge.
    """
    return {k: str(v).strip()[len("working:"):].strip()
            for k, v in filled.items() if str(v).strip().startswith("working:")}
