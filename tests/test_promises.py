"""Do the artifacts tell the truth about the engine?

Layer 2 puts the doctrine in forms, which only works if a form is true at the
moment it is read. Five times in one session an artifact promised something
the engine did not do -- a declared check nothing ran, a summary field nothing
produced, a status line asserting work that was still open, a menu of outcomes
nothing acted on, refusals offering escapes that did not work. Every one was
found by accident.

This is a test rather than a tool because it costs no machinery and runs on
every suite run. It is the standing cost of choosing to put doctrine in forms.
"""

import pathlib
import re
import sys
import tomllib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from engine import cli, forms  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENGINE_SRC = "\n".join(p.read_text() for p in sorted((ROOT / "engine").glob("*.py")))
ASSEMBLIES = sorted((ROOT / "assemblies").glob("*/ASSEMBLY.toml"))
FORMS = sorted(list((ROOT / "assemblies").rglob("forms/*.toml"))
               + list((ROOT / "skills").rglob("forms/*.toml")))

# Keys the engine reads structurally rather than by name -- an id is looked up,
# never branched on, so its absence from the source proves nothing.
STRUCTURAL = {"id", "assembly", "conductor", "segment", "transition", "field",
              "question", "imperative", "note", "item", "value", "status",
              "answer", "cluster", "after", "move", "type", "recommend",
              "option", "choice", "pros", "cons"}


def _keys(obj, out):
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.add(k)
            _keys(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _keys(v, out)


def test_every_assembly_key_is_read_by_the_engine():
    """A key an assembly declares and no engine file reads is a promise with
    nothing behind it -- `validates = "board"` sat unread while the form it
    belongs to told agents the engine was checking their work."""
    declared = set()
    for a in ASSEMBLIES:
        _keys(tomllib.load(open(a, "rb")), declared)
    unread = sorted(k for k in declared - STRUCTURAL
                    if f'"{k}"' not in ENGINE_SRC and f"'{k}'" not in ENGINE_SRC)
    assert not unread, f"declared in an assembly, read by nothing: {unread}"


def test_every_field_kind_is_one_the_engine_handles():
    """A form promising a kind the engine does not know produces a field that
    is silently treated as prose."""
    known = {"check", "evidence", "artifact", "decision", "plan"}
    for f in FORMS:
        for field in tomllib.load(open(f, "rb")).get("field", []):
            kind = field.get("kind", "evidence")
            assert kind in known, f"{f.name}: field {field['id']} has kind {kind!r}"
            assert f'"{kind}"' in ENGINE_SRC, f"{f.name}: nothing reads kind {kind!r}"


def test_summary_fields_named_in_form_prose_exist():
    """GATE_CLOSE and CLOSE tell the agent what the engine returns for them.
    Both promised a verdict for a long time before one existed."""
    built = set(re.findall(r'"([a-z_]+)":', _summary_source()))
    promised = {"verdict": ("verdict",), "cycles": ("cycle", "cycles"),
                "checks": ("check", "checks"), "amends": ("amend", "amends")}
    for f in FORMS:
        text = tomllib.load(open(f, "rb")).get("imperative", "") + f.read_text()
        for field, words in promised.items():
            if any(re.search(rf"\b{w}\b", text) for w in words):
                assert field in built, (
                    f"{f.name} speaks of {field!r}; the summary does not build it")


def _summary_source():
    src = (ROOT / "engine" / "cli.py").read_text()
    start = src.index("def _summary")
    return src[start:src.index("\ndef ", start + 1)]


def test_every_spine_command_the_engine_prints_uses_a_real_verb():
    """A refusal that names a command which does not do what it says is the
    same defect as one that names none: the agent types it and nothing
    happens. `submit it: spine {wid}` shipped once, and only re-rendered
    status."""
    verbs = {"submit", "note", "amend", "close", "status", "check"}
    src = (ROOT / "engine" / "cli.py").read_text() + (ROOT / "engine" / "render.py").read_text()

    # `spine open <assembly> ...` -- the assembly must be one that exists
    for name in re.findall(r"spine open ([a-z][a-z-]+)", src):
        assert (ROOT / "assemblies" / name / "ASSEMBLY.toml").exists(), \
            f"spine open names assembly {name!r}, which is not in assemblies/"

    # `spine <work-id> <verb>` -- the verb must be one main() dispatches
    for verb in re.findall(r"spine \{[\w\[\]'\".]+\} ([a-z]+)", src):
        assert verb in verbs, f"spine command uses {verb!r}"


def test_the_escape_a_refusal_offers_is_a_command_that_exists():
    """Every `spine ... <verb>` inside a refusal's escape text must name a verb
    main() dispatches, so the way out is real."""
    dispatched = set(re.findall(r'"(\w+)": cmd_', (ROOT / "engine" / "cli.py").read_text()))
    dispatched |= {"open", "status"}
    escapes = re.findall(r'escape=f?"([^"]*)"', (ROOT / "engine" / "cli.py").read_text())
    for esc in escapes:
        for verb in re.findall(r"spine \{?\w+[}\w.]*\}? (\w+)", esc):
            assert verb in dispatched, f"escape names verb {verb!r}: {esc}"


def test_every_form_a_run_can_reach_loads():
    """A form named by an assembly that does not parse is a step no agent can
    ever stand on."""
    for a in ASSEMBLIES:
        spec = tomllib.load(open(a, "rb"))
        spec["dir"] = a.parent
        for seg in spec["segment"]:
            refs = [seg.get("step-form"), seg.get("board"),
                    seg.get("transition", {}).get("form")]
            refs += [p["form"] for p in seg.get("transition", {}).get("panel", [])]
            for ref in filter(None, refs):
                path = ROOT / ref if ref.startswith("skills/") else a.parent / ref
                assert path.exists(), f"{a.parent.name}: {ref} does not exist"
                forms.load(path)  # raises if the form is malformed
