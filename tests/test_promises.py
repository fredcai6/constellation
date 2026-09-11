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
import subprocess
import tempfile
import tomllib

from engine import cli, forms, journal, run as runmod

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


# [read-not-merely-present]
# Rationale: this check is named for a class -- declared and unwired -- and a
#   substring sweep of the engine source cannot see that class at all. A key
#   the engine only ever *writes* satisfies `'"k}" in ENGINE_SRC'`, so
#   `filler` was declared in all three assemblies, written at five sites,
#   read by no production code, and passed this test for the engine's whole
#   life. The reader it did have was a test asserting a value the test itself
#   had written.
# Rejected: keeping the substring sweep and listing known-write-only keys
#   beside it. That is the same defect with a maintenance burden: the list
#   would be written once, by someone who already knew, and the next
#   write-only key would pass exactly as `filler` did.
_READING_CALLS = {"get", "pop", "setdefault"}


def _keys_read_by(source: str) -> set:
    """String constants the source actually *reads* a mapping by: `x["k"]`,
    `x.get("k")`, `"k" in x`. A dict literal's own key and a subscript being
    assigned to are writes, and are what this must not count."""
    tree = ast.parse(source)
    written = set()
    for node in ast.walk(tree):
        # `d["k"] = v` -- the subscript is a target, not a read
        targets = (node.targets if isinstance(node, ast.Assign) else
                   [node.target] if isinstance(node, (ast.AugAssign, ast.AnnAssign)) else [])
        for t in targets:
            if isinstance(t, ast.Subscript) and isinstance(t.slice, ast.Constant):
                written.add(id(t))
    read = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and id(node) not in written:
            if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
                read.add(node.slice.value)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in _READING_CALLS and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    read.add(first.value)
        elif isinstance(node, ast.Compare):
            ops = {type(o) for o in node.ops}
            if (ops & {ast.In, ast.NotIn}) and isinstance(node.left, ast.Constant):
                if isinstance(node.left.value, str):
                    read.add(node.left.value)
    return read


ENGINE_READS = _keys_read_by(ENGINE_SRC)


def test_every_assembly_key_is_read_by_the_engine():
    """A key an assembly declares and no engine file reads is a promise with
    nothing behind it -- `validates = "board"` sat unread while the form it
    belongs to told agents the engine was checking their work.

    Read, not merely present: see [read-not-merely-present]."""
    declared = set()
    for a in ASSEMBLIES:
        _keys(tomllib.load(open(a, "rb")), declared)
    unread = sorted(declared - STRUCTURAL - ENGINE_READS)
    assert not unread, f"declared in an assembly, read by nothing: {unread}"


def test_the_unwired_key_check_fails_on_a_key_that_is_only_written():
    """The check on the check -- #32's standard, and the one that matters
    most here, since this instrument was blind to its own class for the
    engine's whole life. A key written and never read must not pass."""
    written_only = "\n".join((
        'def f(step):',
        '    entry = {"quezacotl": step.id}',
        '    journal.append(wid, "step", **entry)',
        '    return {"quezacotl": 1}',
    ))
    assert "quezacotl" not in _keys_read_by(written_only)
    # and the substring sweep this replaced would have passed it
    assert '"quezacotl"' in written_only

    read_too = written_only + "\n\ndef g(e):\n    return e[\"quezacotl\"]\n"
    assert "quezacotl" in _keys_read_by(read_too)


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
    verbs = {"submit", "note", "amend", "close", "status", "check", "wait"}
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
            refs = [seg.get("step-form"), seg.get("board"), seg.get("route-form"),
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


def test_a_panel_entrys_form_lives_under_its_own_workers_skill():
    """A panel entry names both a `form` and a `worker`; the two are one
    claim -- this panelist, this posture -- made in two fields that nothing
    ties together. The prior check only asks whether `form` exists on disk,
    which a half-migrated entry still satisfies: move the form and leave the
    worker behind (or the reverse) and the file is still there, just under
    the wrong skill. That is exactly how a critic panel ended up handed
    REVIEW.toml -- docs/DERIVED_IS_CODE.md:20."""
    for a in ASSEMBLIES:
        for seg in tomllib.load(open(a, "rb"))["segment"]:
            for p in seg.get("transition", {}).get("panel", []):
                form, worker = p["form"], p["worker"]
                expected = f"skills/{worker}/forms/"
                assert form.startswith(expected), (
                    f"{a.parent.name}: panel form {form!r} does not live "
                    f"under {expected!r} for worker {worker!r}")


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
# instead of going unswept.
MINT_TARGETS = {
    ("_open_child", None): ("panel",),                 # a panelist's dispatch
    # a replan's fresh round now goes through `_perform`'s generic `refill`
    # verb (`_mint_segment_round(wid, asm, tseg["id"], prefill=fields)`) --
    # `fields` is forwarded whole, not a literal dict this sweep can see, so
    # there is no site left here for gate adjudication's replan to name.
    # The outlet moved onto `_perform`'s own `rework` verb, where both voices
    # that can decide a rework reach it: the panel's merged verdict resolving
    # to `rework`, and a conductor form submitting on the step that panel
    # returned to. `_act_on_verdicts` no longer mints anything itself.
    ("_perform", "outlet"): ("impasse-form",),
    # An ordinary revise (no impasse loop) resolves through the same
    # declared-outcome table a two-voices step already used -- `_perform`'s
    # `rework` verb, whose prefill is either the deciding step's own
    # (forwarded, not a literal this sweep can see) or `_panel_judged_rework`'s
    # findings, built there rather than as a literal dict at the mint.
}

# A form that receives a minted key its own prose never names, and the file
# that teaches its reader instead -- checked, not waived: the key must appear
# there. Every entry names a real document; a key nothing teaches is a defect
# in the form, not a row to add here.
PREFILL_NAMED_ELSEWHERE = {
    # The implementer's posture, read on every gate, is where the revise round
    # and the findings it carries are described; the form is filled on a first
    # pass too, and does not speak of rounds at all.
    ("skills/implementer/forms/IMPLEMENT.toml", "findings"):
        "skills/implementer/SKILL.md",
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


def _forms_in_role(role, segment=None):
    """Every form any assembly puts in one role -- `step-form`, `rework-form`,
    `impasse-form`, or `panel`.

    `segment` narrows to segments of that name, for a mint that names the
    segment it targets rather than deriving it. Narrowing, never waiving: a
    form reached by no path to the mint cannot be handed its keys, and holding
    it to them reports a defect that cannot occur.
    """
    paths = set()
    for a in ASSEMBLIES:
        for seg in tomllib.load(open(a, "rb"))["segment"]:
            if segment and seg["id"] != segment:
                continue
            if role == "panel":
                refs = [p["form"] for p in seg.get("transition", {}).get("panel", [])]
            elif "|" in role:
                refs = [next((seg[k] for k in role.split("|") if seg.get(k)), None)]
            else:
                refs = [seg.get(role)]
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
            role, seg_name = role if isinstance(role, tuple) else (role, None)
            for path in _forms_in_role(role, seg_name):
                text, rel = path.read_text(), str(path.relative_to(ROOT))
                for key in sorted(keys):
                    if re.search(rf"\b{re.escape(key)}\b", text):
                        continue
                    assert (rel, key) in PREFILL_NAMED_ELSEWHERE, (
                        f"{rel} is minted with prefill {key!r} by {site[0]} and "
                        "names it nowhere")
                    elsewhere = PREFILL_NAMED_ELSEWHERE[(rel, key)]
                    assert key in (ROOT / elsewhere).read_text(), (
                        f"{rel}: {key!r} is said to be named by {elsewhere}, and is not")


def test_a_field_with_a_vocabulary_does_not_advertise_an_escape_it_refuses():
    """`waived:` and `unknown:` are refused on a decision field whose note declares a
    vocabulary -- `verdict_fold` reads a waived verdict as a refusal, not a
    ruling --
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
            if forms.enforced_vocabulary(field):
                assert forms.ESCAPES_REFUSED in block, (
                    f"{f}: {field['id']} declares a vocabulary and is not told "
                    "the escapes are refused on it")
                assert offered == any(not forms.enforced_vocabulary(x) for x in shown), (
                    f"{f}: the header offers an escape no field on it accepts")
            else:
                assert forms.ESCAPES_REFUSED not in block
                assert offered or field["kind"] == "plan", (
                    f"{f}: {field['id']} accepts the escapes and is offered neither")


# A third mode for the sweep below. The first two say a reader names the
# vocabulary's words in its own source, or that no engine branch reads them
# at all. Neither fits a reader that takes the words from the field's own
# note: `_voice_outcome` (engine/run.py) resolves every panelist's return
# against `forms.enforced_vocabulary(field)`, critic and reviewer alike, and
# asserting the two literal words appear in its source would be asserting
# exactly the hardcoding this issue removed. So the claim held here is the
# generic call, and its converse -- that the words themselves are *not* in
# that source.
BY_THE_FIELDS_OWN_NOTE = (runmod._voice_outcome, "enforced_vocabulary")

# The enum each transition accepts, as its form teaches it, and the act that
# performs it. Pinned here because the derivation reads prose: a note reworded
# so its ` | ` leaves the opening line yields no vocabulary and enforces
# nothing, and that is the one way this can fail quietly.
VOCABULARIES = [
    # GATE_TRANSITION's `plan-holds` used to be a row here, back when
    # `_act_on_outcome` hand-read it. It now declares `decides`, so it is
    # `_outcome`'s field like any other -- excluded from `swept` below and
    # covered instead by `test_a_declared_outcome_and_its_field_note_are_the_same_list`.
    ("skills/critic/forms/CRITIC.toml", "verdict",
     ["pass", "revise"], BY_THE_FIELDS_OWN_NOTE),
    ("skills/reviewer/forms/REVIEW.toml", "verdict",
     ["pass", "revise"], BY_THE_FIELDS_OWN_NOTE),
    # These two the engine enforces and no engine code reads: the value is
    # carried in prefill and the reader is the agent on the other side. Saying
    # so is the point -- a string here instead of a function is a claim that
    # nothing branches on it, and the sweep below holds it to that.
    ("assemblies/explore-an-idea/forms/CYCLE.toml", "flavor",
     ["shotgun", "compare", "refine"],
     "carried to the next explore round; no engine branch reads it"),
    ("skills/excursion/forms/PROTOTYPE.toml", "branch",
     ["logic", "ui", "measurement"],
     "recorded for the dispatcher; no engine branch reads it"),
]


def _direct_taught(asm, seg, spec, fid):
    """The vocabulary a real, submittable form of this assembly's own teaches
    for `fid` -- `None` where none of `spec`'s (or its segment's, as a
    fallback) `form`/`step-form`/`rework-form`/`impasse-form`/
    `adjudication-form`/`route-form` keys reach a field of that name. A
    panel-only transition's own keys are all empty, so it always resolves to
    `None` here -- its decided field is never a form any submit in this
    assembly carries; `_panel_taught` below is its own, separate teacher.

    `route-form` is the minted case: run-a-gate's `review` names the form its
    conductor half stands on there rather than on its transition, because
    `select` is what mints the step and a static `form` key would have `open`
    mint it instead. The form is as real and as submittable as any other."""
    return next(
        (forms.vocabulary(fl["note"])
         for key in ("form", "step-form", "rework-form", "impasse-form",
                    "adjudication-form", "route-form")
         for src in (spec.get(key), seg.get(key)) if src
         for fl in forms.load(runmod.resolve_form(asm, src))["fields"]
         if fl["id"] == fid), None)


def test_every_vocabulary_the_engine_enforces_is_the_one_the_form_teaches():
    """The engine refuses a value outside the alternatives a field's note
    declares, so those alternatives are load-bearing twice over: every field
    that had one must still yield one, and every value in it must be one the
    act downstream actually performs. An alternative nothing performs is the
    menu-of-outcomes defect again -- offered to the agent, acted on by
    nothing.

    `decided` is scoped to fields a real form of the deciding assembly
    itself teaches (`_direct_taught`), not merely to a field id some
    `decides` names -- a panel-only transition's decided field (`verdict`,
    the panel's own merged word, never a submitted field) shares a name
    with the panelist forms' own `verdict`, and that field is still
    `_check_vocabulary`'s to enforce, on a wholly different submit, in a
    wholly different assembly. Scoping by name alone would exclude it from
    this sweep for a reason that never applies to it."""
    decided = {fid for name in runmod.assemblies()
               for asm in [runmod.load_assembly(name)]
               for seg in asm["segment"]
               for spec in (seg, seg.get("transition", {}))
               if (fid := spec.get("decides")) and _direct_taught(asm, seg, spec, fid)}
    swept = {}
    for f in FORMS:
        for field in forms.load(f)["fields"]:
            vocab = forms.enforced_vocabulary(field)
            # a field the assembly declares outcomes for is `_outcome`'s, not
            # `_check_vocabulary`'s -- covered by the test below instead
            if vocab and field["id"] not in decided:
                swept[(str(f.relative_to(ROOT)), field["id"])] = vocab

    expected = {(path, fid): vocab for path, fid, vocab, _ in VOCABULARIES}
    assert swept == expected, "a note was reworded out of the enum the engine enforces"

    engine_src = "".join((ROOT / "engine" / f).read_text()
                         for f in ("cli.py", "run.py", "forms.py", "render.py"))
    for path, fid, vocab, act in VOCABULARIES:
        if isinstance(act, tuple):
            # the claim is that the reader takes the words from the field's
            # own note; hold both halves of it
            fn, generic_call = act
            src = inspect.getsource(fn)
            assert f"{generic_call}(" in src, \
                f"{path}: {fid} is recorded as read through {generic_call}, and " \
                f"{fn.__name__} does not call it"
            for alt in vocab:
                head = alt.split("<")[0].strip()
                assert not re.search(rf'["\']{re.escape(head)}["\']', src), \
                    f"{path}: {fid} is recorded as read from the field's own note, " \
                    f"but {fn.__name__} names {head!r} itself"
            continue
        if isinstance(act, str):
            # the claim is that nothing branches on it; hold the claim
            for alt in vocab:
                assert not re.search(rf'["\']{re.escape(alt)}["\']', engine_src), \
                    f"{path}: {fid} is recorded as read by no engine branch, but " \
                    f"{alt!r} appears in the engine -- update the entry or the claim"
            continue
        src = inspect.getsource(act)
        for alt in vocab:
            head = alt.split("<")[0].strip()
            assert re.search(rf"\b{re.escape(head)}\b", src), \
                f"{path}: {fid} offers {alt!r}; {act.__name__} does nothing with it"


def test_a_declared_outcome_and_its_field_note_are_the_same_list():
    """The other half of the same promise, for the fields `_outcome` owns.

    An assembly names the values it acts on in `[[outcome]]` rows; the form's
    note names the values it tells the agent. Nothing made those one string,
    so they can drift -- the agent offered a word the assembly cannot perform,
    or a row nobody is told about. Both are the menu-of-outcomes defect, from
    opposite ends.

    A third check rides along: every `does` verb an outcome row names is one
    `_perform` actually acts on -- `release`, the field's own default, is the
    documented no-op and needs no branch to back it. This is the coverage
    `VOCABULARIES` used to carry for the impasse's `ruling` field, back when
    `_act_on_impasse` hand-read it; now that ruling is a `decides` field like
    any other, the same proof belongs on the generic actor.

    A panel-only transition submits no form of its own, so `_direct_taught`
    always misses it -- `_act_on_verdicts` synthesizes the decided field from
    `verdict_fold`, never from a step this assembly minted. What teaches
    the agent there is the panel's own form instead: every panelist declares
    a field of the same name (the vote `verdict_fold` folds), so the panel
    is checked in `_direct_taught`'s place, requiring every panelist agree.
    """
    perform_src = inspect.getsource(cli._perform)
    checked = verbs_checked = 0
    for name in runmod.assemblies():
        asm = runmod.load_assembly(name)
        for seg in asm["segment"]:
            for spec in (seg, seg.get("transition", {})):
                fid = spec.get("decides")
                if not fid:
                    continue
                declared = [o["value"] for o in spec.get("outcome", [])]
                taught = _direct_taught(asm, seg, spec, fid)
                if taught is None and spec.get("panel"):
                    panel_taught = [forms.vocabulary(fl["note"])
                                    for p in spec["panel"]
                                    for fl in forms.load(runmod.resolve_form(asm, p["form"]))["fields"]
                                    if fl["id"] == fid]
                    assert panel_taught and all(t == panel_taught[0] for t in panel_taught), (
                        f"{name}/{seg['id']}: decides {fid!r}, and the panel's own "
                        f"forms do not all teach the same vocabulary for it: {panel_taught}")
                    taught = panel_taught[0]
                assert taught is not None, \
                    f"{name}/{seg['id']}: decides {fid!r}, and no form it reaches has that field"
                assert declared == taught, (
                    f"{name}/{seg['id']}: the assembly acts on {declared} and the "
                    f"form teaches {taught}")
                checked += 1
                for o in spec.get("outcome", []):
                    for verb in filter(None, (v.strip() for v in
                                              o.get("does", "release").split(";"))):
                        word = verb.split(" ", 1)[0]
                        verbs_checked += 1
                        if word == "release":
                            continue
                        assert re.search(rf'\b{re.escape(word)}\b', perform_src), (
                            f"{name}/{seg['id']}: outcome {o['value']!r} does {word!r}; "
                            f"_perform does nothing with it")
    assert checked, "no assembly declares an outcome -- this test swept nothing"
    assert verbs_checked, "no outcome named a verb -- this test swept nothing"


def _panel_verdict_taught(asm, panel):
    """The vocabulary every voice in `panel` teaches for the literal field
    id `"verdict"` -- `_voice_outcome`'s own hardcoded key
    (`engine/run.py`'s `f.get("id") == "verdict"`), never `decides`, which
    coincides with it only by chance at explore-an-idea's spec seam. Each
    entry resolves its own form the way the runtime does
    (`runmod._panelist_form_ref`): the entry's own `form` where it names
    one, and otherwise `give-a-verdict`'s terminal form -- the shape a
    `[[panelists]]` block from `SELECT.toml` has, which is what an entry
    naming no form of its own (`{}`) mimics.

    `None` where no voice's form declares a `verdict` field at all --
    design-it-twice's rival-planner panel (shelved, #96) was this case, and
    has nothing to check."""
    vocabs = []
    for entry in panel:
        pasm, ref = runmod._panelist_form_ref(asm, entry)
        fields = forms.load(runmod.resolve_form(pasm, ref))["fields"]
        field = next((f for f in fields if f["id"] == "verdict"), None)
        vocabs.append(forms.vocabulary(field["note"]) if field else None)
    if all(v is None for v in vocabs):
        return None
    assert vocabs and all(v == vocabs[0] for v in vocabs), (
        f"panel voices teach different verdict vocabularies: {vocabs}")
    return vocabs[0]


def test_the_panels_own_vocabulary_never_drifts_from_the_table_it_answers():
    """Obligation 12. `test_a_declared_outcome_and_its_field_note_are_the_same_list`
    already checks the panel's own vocabulary, but only through its one
    `taught is None and spec.get("panel")` branch -- the panel-only shape,
    exactly one seam in the tree (explore-an-idea's spec transition). At the
    three seams whose transition *also* stands a conductor on a form
    (run-an-issue's consolidate and plan-to-execute, run-a-gate's review),
    `_direct_taught` resolves the conductor's own vocabulary directly and
    that branch's body is never reached -- so the panel's own opinion is
    never separately held to the table there at all, and could drift from
    it in total silence.

    This is that independent check, run alongside the existing one rather
    than nested inside its guard: at every seam where a conductor form's own
    vocabulary is found (`_direct_taught` is not `None`) and a panel also
    reads the round, the panel's own `verdict` field must teach a subset of
    the same seam's declared `outcome` values -- subset, not equality,
    since the panel's two words (`pass | revise`) never spans a table that
    also carries `rework`, `up`, and (at review) `close`.

    Review carries no static `[[[segment.]transition.]panel]` anywhere in
    ASSEMBLY.toml on purpose -- its panel is minted at `select` from
    `SELECT.toml`'s own `panelists` field, whose blocks carry no form of
    their own. It is the one seam in the tree shaped that way, so it is
    named directly rather than discovered structurally, the same way
    `VOCABULARIES` above names its own hardcoded seams."""
    checked = 0
    for name in runmod.assemblies():
        asm = runmod.load_assembly(name)
        for seg in asm["segment"]:
            for spec in (seg, seg.get("transition", {})):
                fid = spec.get("decides")
                if not fid or _direct_taught(asm, seg, spec, fid) is None:
                    continue
                is_review = name == "run-a-gate" and seg["id"] == "review" and spec is seg
                panel = spec.get("panel") or ([{}] if is_review else None)
                if panel is None:
                    continue
                taught = _panel_verdict_taught(asm, panel)
                if taught is None:
                    continue
                declared = [o["value"] for o in spec.get("outcome", [])]
                assert set(taught) <= set(declared), (
                    f"{name}/{seg['id']}: panel teaches {taught}, not a subset "
                    f"of the declared outcomes {declared}")
                checked += 1
    assert checked == 3, (
        f"expected exactly the three named seams (consolidate, "
        f"plan-to-execute, review), got {checked}")


def _glossary_entry(text, name):
    """The bullet's own text, from `- **name** —` to the next `- **` bullet or
    end of file. A `re.search` for the name alone would match a substring of a
    longer term (`work location` inside some future `work location id`), so
    the anchor is the literal bold-and-dash opening every entry uses."""
    m = re.search(rf"- \*\*{re.escape(name)}\*\* —.*?(?=\n- \*\*|\Z)",
                   text, re.DOTALL)
    assert m, f"no glossary entry named {name!r}"
    return m.group(0)


GLOSSARY = (ROOT / "standards" / "glossary.md").read_text()
V2_DESIGN = (ROOT / "docs" / "V2_DESIGN.md").read_text()
CONSTELLATION_TOML = (ROOT / "constellation.toml").read_text()
README = (ROOT / "README.md").read_text()


def test_readmes_git_claim_matches_what_cmd_open_actually_refuses_on():
    """README says an issue run needs a git checkout with a remote.
    `_open_root_worktree` is the ground truth: its two refusals are the only
    places `cmd_open` checks git at all, and both fire only for an issue-tier
    assembly -- a claim that drops that scope would say the engine needs git
    for every run, which is not what the code does."""
    src = ENGINE_SRC
    assert '"not a git checkout"' in src
    assert '"the checkout has no remote"' in src
    # cmd_open only calls the function that raises those refusals when the
    # assembly is issue-tier -- the guard README's scoping claim rests on.
    assert "if on_issue_tier:\n        worktree, cut_point = _open_root_worktree" in src
    para = README.split("An issue run needs a git checkout")[1].split("\n\n")[0]
    assert "remote" in para
    assert "issue" in para  # scoped to the issue tier, not stated as a blanket engine requirement


def test_readmes_gitignore_assumption_is_held_loosely_not_hardcoded():
    """The principal's caveat: hold the `.agent-work/` gitignore assumption
    loosely rather than hardcode it. Grounded both ways -- README must say
    nothing enforces it, and the engine must in fact never parse `.gitignore`
    to decide anything; if it ever does, this claim goes false, not moot."""
    para = README.split("The engine assumes")[1].split("\n\n")[0]
    assert "nothing enforces" in para
    assert ".gitignore" not in ENGINE_SRC


def test_glossary_work_location_drops_the_visible_to_everyone_claim():
    """The old entry said a work location is 'visible to everyone' -- false
    once an issue-tier run's location can live inside its own worktree
    instead of the top-level checkout. `root_for` is the ground truth for how
    it is actually found."""
    entry = _glossary_entry(GLOSSARY, "work location")
    assert "visible to everyone" not in entry
    assert "sibling" in entry  # root_for's own two-tree search
    root_for_src = inspect.getsource(journal.root_for)
    assert "sibling" in root_for_src or "_worktree_agent_work_dirs" in root_for_src


def test_glossary_work_location_states_the_artifact_path_convention():
    """`_measure_artifacts` already leans on a convention no document stated:
    a stored artifact path is recorded work-location-inclusive. The gate's
    own risk is a wrong entry passing an exists-sweep, so this checks the
    words, not just that the bullet is there."""
    entry = _glossary_entry(GLOSSARY, "work location")
    assert "work-location-inclusive" in entry
    assert "work-location-inclusive" in ENGINE_SRC  # the convention this entry names is real, not invented


def test_glossary_worktree_and_archive_paths_match_the_engine():
    """The new `worktree` and `archive` entries state literal paths; both
    must match the paths `cli.py` actually builds, not a paraphrase of them."""
    worktree = _glossary_entry(GLOSSARY, "worktree")
    archive = _glossary_entry(GLOSSARY, "archive")
    assert '_WORKTREES_DIR = ".worktrees"' in ENGINE_SRC
    assert ".worktrees/<work-id>" in worktree
    assert 'top / ".agent-work" / "archive"' in ENGINE_SRC
    # [archive-nesting]
    # Rationale: The engine builds nested paths by splitting the work-id on dots:
    # `dest = top / ".agent-work" / "archive" / pathlib.Path(*wid.split("."))`.
    # For `issue17.g1`, this produces `.agent-work/archive/issue17/g1/`, not a
    # flat path with a `<work-id>` template. The glossary entry correctly
    # describes this nesting with a worked example; check for that example
    # instead of the stale template.
    assert ".agent-work/archive/issue17/g1" in archive
    assert "<project>" not in worktree
    assert "<project>" not in archive


def test_v2_design_drops_the_false_constellation_toml_archive_claim():
    """Ruling 8 used to say whether a repo commits the archive is a call made
    in `constellation.toml`. It is not: `constellation.toml` has no archive
    setting at all, so the claim was false the moment anyone read the file it
    pointed at."""
    ruling8 = V2_DESIGN.split("**8. Git is the issue tier's")[1].split("\n\n**9.")[0]
    assert "constellation.toml" not in ruling8
    assert "archive" not in CONSTELLATION_TOML.lower()


def test_v2_design_names_the_top_level_checkout_one_way():
    """Ruling 8 called the same tree `<project>` in one sentence and 'the
    top-level checkout' in the next; the open-beat table row carried the same
    `<project>` spelling. One name for one thing, so neither should reappear
    anywhere `top-level checkout` is also used for the same tree."""
    assert "<project>" not in V2_DESIGN
    assert V2_DESIGN.count("top-level checkout") >= 3  # table's open row, table's close row, ruling 8


def test_gitignore_actually_covers_the_paths_the_docs_call_gitignored():
    """`README.md`, the glossary's `archive`, and `docs/AGENT_GUIDE.md` all
    call `.agent-work/` and `.worktrees/` gitignored. `.gitignore` is the only
    thing that can make that true."""
    gi = (ROOT / ".gitignore").read_text()
    assert ".agent-work/" in gi
    assert ".worktrees/" in gi


def test_agent_guide_worktrees_row_is_accurate_if_present():
    """`.worktrees/` only belongs in the layout table if an agent actually
    meets that path -- `render.brief`'s `tree` line and `cmd_open`/`cmd_close`
    both print it literally, so it qualifies. If the row exists, it must say
    the path is gitignored, since that is the claim it would otherwise get
    wrong silently."""
    guide = (ROOT / "docs" / "AGENT_GUIDE.md").read_text()
    assert "worktree}" in (ROOT / "engine" / "render.py").read_text()  # the agent-facing print this row rests on
    rows = [l for l in guide.splitlines() if l.startswith("| `.worktrees/`")]
    assert rows, "docs/AGENT_GUIDE.md's layout table has no .worktrees/ row"
    assert "gitignored" in rows[0].lower()


def test_every_role_an_assembly_names_has_a_skill_behind_it():
    """An assembly naming a role with nobody behind it is a promise nothing
    can fill. `gate-executor` outlived its own removal in four files because
    this suite checked assembly *keys* and never their values, and the edit
    that dropped it silently failed to match in every file but one.

    The roster is what is on disk. It was scraped out of the design doc's
    prose until that document stopped being a source of truth; a role we want
    to exist and have not built belongs in a plan, not in a check.

    A `skills/<role>/` directory is the whole bar. `run.resolve_skill` reads a
    role with no SKILL.md as answered rather than failed, so demanding one
    here would hold an assembly to more than the engine does.
    """
    roles_on_disk = {d.name for d in (ROOT / "skills").iterdir() if d.is_dir()}
    assert roles_on_disk, "no skills on disk -- this test swept nothing"
    for a in ASSEMBLIES:
        spec = tomllib.load(open(a, "rb"))
        named = {spec.get("conductor", "")}
        for seg in spec["segment"]:
            # A segment need not declare a transition at all -- a board with
            # nothing standing the run on a step, run-an-issue's own
            # execution-state, has none.
            transition = seg.get("transition", {})
            named |= {seg.get("worker", ""), transition.get("filler", "")}
            named |= {p.get("worker", "") for p in transition.get("panel", [])}
        # `filler = "conductor"` is an indirection, not a role: it means
        # whoever conducts this assembly. Resolve it before checking.
        named = {spec.get("conductor", "") if r == "conductor" else r for r in named}
        for role in named - {""}:
            assert role in roles_on_disk, (
                f"{a.parent.name} names role {role!r}, which has no skills/{role}/")


def test_run_a_gates_conductor_field_agrees_with_its_skill_files_and_design_doc():
    """Four claims went false the moment `run-a-gate`'s `conductor` field
    became `gate-conductor`, and prose has no proof behind it: two skill
    files an agent reads live mid-run said the implementer conducts a gate,
    and `docs/V2_DESIGN.md` said the assembly on disk still names the
    implementer. Each is pinned the way this file already pins a known-false
    substring -- the retired phrase, paired with the field that retired it --
    so an edit reintroducing one fails here rather than misdirecting an agent
    a run later. This is not a scanner for arbitrary claims about arbitrary
    roles: it is four named strings and the one field they all depend on."""
    gate = tomllib.load(open(ROOT / "assemblies" / "run-a-gate" / "ASSEMBLY.toml", "rb"))
    assert gate["conductor"] == "gate-conductor"
    implementer = (ROOT / "skills" / "implementer" / "SKILL.md").read_text()
    assert "you conduct this gate" not in implementer
    issue_conductor = (ROOT / "skills" / "issue-conductor" / "SKILL.md").read_text()
    assert "the implementer's to conduct" not in issue_conductor
    assert "names the implementer as its conductor" not in V2_DESIGN
    assert "the assembly on disk names the implementer" not in V2_DESIGN


# [up-mints-nothing-property]
# Rationale: four rounds in a row (issue84's plan, rounds 4, 6, 7, 8) each
#   found one new site claiming a settled `up` adds nothing to the run,
#   terminates it outright, or advances it straight to its own last step --
#   `assemblies/`+`skills/` first, then a row's own trailing comment -- and
#   each was closed in place with a new file name, a new regex alternative,
#   or a new bespoke file-scoped grep. Round 9 found a fifth site in
#   `engine/cli.py` itself, outside every one of those sweeps' own declared
#   directories, which is what showed the *unit* was wrong: the property
#   this test checks was never actually a claim about corpus
#   (`assemblies/`, `skills/`) vs. non-corpus text. Rooted at the repository
#   instead, with the same two exclusions the gate spec names:
#   `docs/V2_DESIGN.md` (its own line naming a decision the run's answerer
#   may make after being asked, not a claim about what ruling `up` itself
#   does) and `.agent-work/` (this run's own working directory, whose
#   journals and plans are records of what was thought at the time and are
#   never retroactively corrected -- confirmed to hold the largest number
#   of matches in the whole tree for exactly this reason). The four phrases
#   themselves are built from fragments below, joined through a name rather
#   than literal `+`, so CPython's own constant folding (which collapses
#   `"a" + "b"` into one string at compile time) does not hand the compiled
#   `.pyc` a single embedded constant spelling the whole phrase -- that
#   folding is exactly what made an earlier draft of this same fragment
#   technique a hit on its own bytecode. Still rooted wrong: rglob walked
#   the filesystem, not the repository, so it also caught a sibling
#   issue-tier worktree and generated map output; walking `git ls-files`
#   instead drops those for free and lets `docs/process-notes/` join
#   `V2_DESIGN.md` as a third exclusion, since a dated record quoting the
#   claim as evidence of a defect is not a standing claim either.
def test_no_text_in_the_repository_claims_up_mints_nothing_or_ends_the_run():
    _j = ""  # a name, not a literal -- see the rationale above
    fragments = [
        "refill" + _j + "s nothing",
        "end" + _j + "s the run",
        "walk" + _j + "s? to its close",
        "walk" + _j + "s? to its terminal step",
    ]
    pattern = re.compile("|".join(fragments))
    hits = []
    tracked = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True,
    ).stdout.split(b"\0")
    for raw in tracked:
        if not raw:
            continue
        rel = raw.decode()
        if rel == "docs/V2_DESIGN.md" or rel.startswith("docs/process-notes/"):
            continue  # a decision the answerer may name, or a dated record
            # quoting the claim as evidence -- neither is standing prose
        try:
            text = (ROOT / rel).read_text()
        except (UnicodeDecodeError, OSError):
            continue  # not a text file this property could ever be stated in
        if pattern.search(text):
            hits.append(rel)
    assert not hits, f"stale claims about what `up` does survive at: {hits}"
