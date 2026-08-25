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


def test_every_panel_names_a_form_the_panelist_actually_fills():
    """A panel declares the form its panelist fills. The engine opened every
    panelist under one assembly whose form was fixed, so a critic panel
    declaring CRITIC.toml was handed REVIEW.toml and the key went unread."""
    src = (ROOT / "engine" / "cli.py").read_text()
    assert 'panelist["form"]' in src or "panelist.get(\"form\")" in src, \
        "nothing reads a panel's declared form"
    for a in ASSEMBLIES:
        for seg in tomllib.load(open(a, "rb"))["segment"]:
            for p in seg.get("transition", {}).get("panel", []):
                assert (ROOT / p["form"]).exists(), f"{a.parent.name}: {p['form']}"


def test_the_status_values_the_template_teaches_are_ones_the_engine_reads():
    """A response template tells the agent which statuses a field accepts.
    Each must be one something actually acts on -- a status nobody reads is
    the same defect as a form promising a check nobody runs."""
    header = (ROOT / "engine" / "forms.py").read_text()
    taught = set(re.findall(r"#   (\w+):", header))
    src = ENGINE_SRC
    for status in taught:
        assert f'"{status}:"' in src or f"{status}:" in src, \
            f"the template teaches {status!r}; nothing in the engine reads it"
    assert "working" in taught  # the one that gates a submit


SKILL_BUDGETS = {"commander": 1500, "implementer": 800}


def test_commander_and_implementer_skills_exist_inside_budget():
    """Layer 3 gives exactly two roles a SKILL.md -- commander and
    implementer, the only postures with no form of their own to carry them.
    Each budget is set in the spec and enforced with `wc -w`, forms not
    included: a skill is corpus words, not machinery, but it still answers
    to the number the spec gave it."""
    for name, budget in SKILL_BUDGETS.items():
        path = ROOT / "skills" / name / "SKILL.md"
        assert path.exists(), f"skills/{name}/SKILL.md does not exist"
        words = len(path.read_text().split())
        assert words <= budget, (
            f"skills/{name}/SKILL.md is {words} words, over its {budget}-word budget")


def test_no_skill_exists_for_a_role_the_roster_does_not_list():
    """interrogator and reviewer get no SKILL.md: their forms already carry
    their whole posture, and a skill repeating its form is corpus words with
    no work in them. That call was made with evidence and stands until a
    later decision reopens it with its own evidence -- not by a SKILL.md
    quietly appearing for a role never meant to have one, or for a name the
    roster does not even recognize."""
    roster = set(re.findall(r"^\| `([a-z-]+)` \|", (ROOT / "docs" / "V2_DESIGN.md").read_text(),
                            re.M))
    assert roster, "could not read the roster from the spec"
    for skill_md in sorted((ROOT / "skills").glob("*/SKILL.md")):
        name = skill_md.parent.name
        assert name in roster, (
            f"skills/{name}/SKILL.md exists for a role the roster does not list")


def test_every_role_an_assembly_names_is_one_the_design_declares():
    """An assembly naming a role the roster does not have is a promise with
    nobody behind it. `gate-executor` outlived its own removal in four files
    because this suite checked assembly *keys* and never their values, and the
    edit that dropped it silently failed to match in every file but the spec.
    """
    roster = set(re.findall(r"^\| `([a-z-]+)` \|", (ROOT / "docs" / "V2_DESIGN.md").read_text(),
                            re.M))
    assert roster, "could not read the roster from the spec"
    for a in ASSEMBLIES:
        spec = tomllib.load(open(a, "rb"))
        named = {spec.get("conductor", "")}
        for seg in spec["segment"]:
            named |= {seg.get("worker", ""), seg["transition"].get("filler", "")}
            named |= {p.get("worker", "") for p in seg["transition"].get("panel", [])}
        # `filler = "conductor"` is an indirection, not a role: it means
        # whoever conducts this assembly. Resolve it before checking.
        named = {spec.get("conductor", "") if r == "conductor" else r for r in named}
        for role in named - {""}:
            assert role in roster, (
                f"{a.parent.name} names role {role!r}, which the spec's roster does not list")
