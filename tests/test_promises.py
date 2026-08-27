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

import ast
import inspect
import pathlib
import re
import tempfile
import tomllib

from engine import cli, forms, run as runmod

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


# Where the engine writes a step's prefill by name, and which form the step it
# mints stands on -- named by the assembly key that holds it, since the form
# itself is the assembly's choice and not the engine's. The keys come off the
# source, so a key added to one of these sites joins the sweep below without
# anyone remembering to; the sites are pinned so that a new one fails loudly
# instead of going unswept. `_mint_segment_round` falls back to the segment's
# step-form when its caller names no rework form, so both roles receive it.
MINT_TARGETS = {
    ("_open_child", None): ("panel",),                 # a panelist's dispatch
    ("_act_on_outcome", None): ("step-form",),         # a replan's fresh round
    ("_act_on_verdicts", "outlet"): ("impasse-form",),
    ("_act_on_verdicts", 'seg.get("rework-form", "")'): ("rework-form", "step-form"),
}

# A form that receives a minted key its own prose never names, and the file
# that teaches its reader instead -- checked, not waived: the key must appear
# there. `None` is not an exception but a gap this sweep records rather than
# hides.
PREFILL_NAMED_ELSEWHERE = {
    # The implementer's posture, read on every gate, is where the revise round
    # and the findings it carries are described; the form is filled on a first
    # pass too, and does not speak of rounds at all.
    ("skills/implementer/forms/IMPLEMENT.toml", "findings"):
        "skills/implementer/SKILL.md",
    # A replan mints PLAN.toml carrying the adjudication's `learned` under the
    # key `findings`. The form's prose names the consolidate's keys and calls
    # itself a first cut, so this arrival is unnamed. Outside the scope of the
    # gate that added this sweep (issue30.g1-a07af) and raised there as a note,
    # recorded here rather than narrowed away.
    ("assemblies/run-an-issue/forms/PLAN.toml", "findings"): None,
}


def _prefill_mints():
    """Every prefill dict the engine builds with literal keys: {(the function
    that mints it, the source of the `form` it names): keys}."""
    found = {}
    for path in sorted((ROOT / "engine").glob("*.py")):
        src = path.read_text()
        for fn in ast.walk(ast.parse(src)):
            if not isinstance(fn, ast.FunctionDef):
                continue
            for node in ast.walk(fn):
                if isinstance(node, ast.Call):
                    kw = {k.arg: k.value for k in node.keywords}
                    value, form = kw.get("prefill"), kw.get("form")
                elif isinstance(node, ast.Assign) and any(
                        isinstance(t, ast.Name) and t.id == "prefill"
                        for t in node.targets):
                    value, form = node.value, None
                else:
                    continue
                if not isinstance(value, ast.Dict):
                    continue  # a forwarded or comprehended prefill mints no name
                keys = {k.value for k in value.keys if isinstance(k, ast.Constant)}
                if keys:
                    site = (fn.name, form if form is None
                            else ast.get_source_segment(src, form))
                    found.setdefault(site, set()).update(keys)
    return found


def _forms_in_role(role):
    """Every form any assembly puts in one role -- `step-form`, `rework-form`,
    `impasse-form`, or `panel`."""
    paths = set()
    for a in ASSEMBLIES:
        for seg in tomllib.load(open(a, "rb"))["segment"]:
            refs = ([p["form"] for p in seg.get("transition", {}).get("panel", [])]
                    if role == "panel" else [seg.get(role)])
            for ref in filter(None, refs):
                paths.add(ROOT / ref if ref.startswith("skills/") else a.parent / ref)
    return sorted(paths)


def test_every_prefill_key_the_engine_mints_is_named_by_the_form_that_receives_it():
    """Prefill is the orders a step opens with -- `render.status` prints it
    above the fields. A key the engine mints and the receiving form never
    mentions is the menu-of-outcomes defect run backwards: the reader is handed
    a value and taught nothing about it. `arrival` shipped that way into
    run-a-gate's IMPASSE, accurate and unexplained.

    Only keys the engine writes by name are swept. A gate spec's keys are the
    plan's, copied whole, and a panelist's artifact fields are the producing
    form's -- neither is a name this engine chose, so neither is a name it can
    be held to."""
    mints = _prefill_mints()
    assert set(mints) == set(MINT_TARGETS), (
        "a prefill mint this sweep does not know about: "
        f"{sorted(set(mints) ^ set(MINT_TARGETS))}")
    for site, keys in mints.items():
        for role in MINT_TARGETS[site]:
            for path in _forms_in_role(role):
                text, rel = path.read_text(), str(path.relative_to(ROOT))
                for key in sorted(keys):
                    if re.search(rf"\b{re.escape(key)}\b", text):
                        continue
                    assert (rel, key) in PREFILL_NAMED_ELSEWHERE, (
                        f"{rel} is minted with prefill {key!r} by {site[0]} and "
                        "names it nowhere")
                    elsewhere = PREFILL_NAMED_ELSEWHERE[(rel, key)]
                    assert elsewhere is None or key in (ROOT / elsewhere).read_text(), (
                        f"{rel}: {key!r} is said to be named by {elsewhere}, and is not")


def test_a_field_with_a_vocabulary_does_not_advertise_an_escape_it_refuses():
    """`waived:` and `unknown:` are refused on any field whose note declares a
    vocabulary -- `merged_verdict` would read a waived verdict as a `pass` --
    so a template offering them there hands the agent a way out its own submit
    rejects. The offer is per field, not per form: one enum field beside four
    of prose leaves the four still taking the escapes, and only a form with
    nothing but enum fields drops the offer entirely."""
    assert all(e in forms.ESCAPES_REFUSED for e in ("waived:", "unknown:")), \
        "the line a vocabulary field gets no longer names what it refuses"
    for f in FORMS + [None]:
        # The last pass is a form of nothing but enum fields -- no assembly has
        # one today, and the header has to be right the day one does.
        form = (forms.load(f) if f else
                {"imperative": "", "fields": [{"id": "verdict", "kind": "decision",
                                               "note": "pass | revise | escalate.",
                                               "optional": False}]})
        dest = pathlib.Path(tempfile.mkdtemp()) / "RESPONSE.toml"
        forms.materialize(form, dest, work_id="issue1")
        header, *blocks = dest.read_text().split("\n\n")
        shown = [x for x in form["fields"] if x["kind"] != "check"]
        assert len(blocks) == len(shown), f"{dest}: a field per block"
        for field, block in zip(shown, blocks):
            offered = field["kind"] != "plan" and any(
                e in header for e in ("waived:", "unknown:"))
            if forms.vocabulary(field["note"]):
                assert forms.ESCAPES_REFUSED in block, (
                    f"{f}: {field['id']} declares a vocabulary and is not told "
                    "the escapes are refused on it")
                assert offered == any(not forms.vocabulary(x["note"]) for x in shown), (
                    f"{f}: the header offers an escape no field on it accepts")
            else:
                assert forms.ESCAPES_REFUSED not in block
                assert offered or field["kind"] == "plan", (
                    f"{f}: {field['id']} accepts the escapes and is offered neither")


# The enum each transition accepts, as its form teaches it, and the act that
# performs it. Pinned here because the derivation reads prose: a note reworded
# so its ` | ` leaves the opening line yields no vocabulary and enforces
# nothing, and that is the one way this can fail quietly.
VOCABULARIES = [
    ("assemblies/run-an-issue/forms/IMPASSE.toml", "ruling",
     ["advance", "rework", "up"], cli._act_on_impasse),
    ("assemblies/run-a-gate/forms/IMPASSE.toml", "ruling",
     ["advance", "rework", "up"], cli._act_on_impasse),
    ("assemblies/run-an-issue/forms/GATE_TRANSITION.toml", "plan-holds",
     ["advance", "remint", "drop <gate-id>", "replan"], cli._act_on_outcome),
    ("skills/reviewer/forms/CRITIC.toml", "verdict",
     ["pass", "revise", "escalate"], runmod.merged_verdict),
    ("skills/reviewer/forms/REVIEW.toml", "verdict",
     ["pass", "revise", "escalate"], runmod.merged_verdict),
]


def test_every_vocabulary_the_engine_enforces_is_the_one_the_form_teaches():
    """The engine refuses a value outside the alternatives a field's note
    declares, so those alternatives are load-bearing twice over: every field
    that had one must still yield one, and every value in it must be one the
    act downstream actually performs. An alternative nothing performs is the
    menu-of-outcomes defect again -- offered to the agent, acted on by
    nothing."""
    swept = {}
    for f in FORMS:
        for field in forms.load(f)["fields"]:
            vocab = forms.vocabulary(field["note"])
            if vocab:
                swept[(str(f.relative_to(ROOT)), field["id"])] = vocab

    expected = {(path, fid): vocab for path, fid, vocab, _ in VOCABULARIES}
    assert swept == expected, "a note was reworded out of the enum the engine enforces"

    for path, fid, vocab, act in VOCABULARIES:
        src = inspect.getsource(act)
        for alt in vocab:
            head = alt.split("<")[0].strip()
            assert re.search(rf"\b{re.escape(head)}\b", src), \
                f"{path}: {fid} offers {alt!r}; {act.__name__} does nothing with it"


SKILL_BUDGETS = {"commander": 1500, "implementer": 800}


def test_commander_and_implementer_skills_exist_inside_budget():
    """Layer 3 gives exactly two roles a SKILL.md -- commander and
    implementer, the only postures with no form of their own to carry them.
    Each budget is set in the spec and enforced with `wc -w`, FORMS INCLUDED
    (V2_DESIGN.md, "Draft per-skill word budgets, forms included"): what a
    role costs is everything its agent reads to hold that posture, and its
    own forms are read every time it is filled. This test used to count the
    SKILL.md alone and say so in this docstring, which left one budget with
    two live definitions and a skill free to spend the difference by moving
    words into a form."""
    for name, budget in SKILL_BUDGETS.items():
        skill = ROOT / "skills" / name / "SKILL.md"
        assert skill.exists(), f"skills/{name}/SKILL.md does not exist"
        parts = [skill] + sorted((ROOT / "skills" / name / "forms").glob("*.toml"))
        counts = {p.name: len(p.read_text().split()) for p in parts}
        assert sum(counts.values()) <= budget, (
            f"skills/{name} is {sum(counts.values())} words, over its "
            f"{budget}-word budget: {counts}")


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
