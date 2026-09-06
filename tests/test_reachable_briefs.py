"""A gate spec a conductor cannot act on is not shipped, even if every test
passes.

Two defects the live proof run found by driving the system, neither caught
by the suite: (1) the plan segment's design-it-twice panel (ruling 10, since
shelved -- #96) declared no `model` of its own and sat on a segment that
declared none either, so `_panel_status`'s `panelist.get("model") or
seg.get("model", "")` resolved to `""` -- the brief printed `tier (unset)`
and `runner (unresolved)`, and nothing could dispatch the round. (2) CONSOLIDATE.toml
declared `obligations` (`kind = "plan"`, an array-of-tables) before
`resolution` (`kind = "decision"`, a scalar) -- `forms.materialize` writes a
plan field as a bare `[[obligations]]` header, and TOML nests any later
bare `key = value` under the last table opened, so a correct top-to-bottom
fill silently wrote `resolution` inside the last obligation instead of
beside it.

Both tests below pin desired behaviour: they failed before the fixes in
`assemblies/run-an-issue/ASSEMBLY.toml` (the plan segment's `model`) and
`assemblies/run-an-issue/forms/CONSOLIDATE.toml` (the field order), and they
are written to keep failing if either regresses -- or if a new form or
panel entry reintroduces either shape.
"""

import pathlib
import tomllib

from engine import forms, run as runmod

ROOT = pathlib.Path(__file__).resolve().parent.parent
FORMS = sorted(list((ROOT / "assemblies").rglob("forms/*.toml"))
               + list((ROOT / "skills").rglob("forms/*.toml")))
MODELS = tomllib.loads((ROOT / "constellation.toml").read_text()).get("models", {})


def _panel_entries(asm):
    """Every panelist, paired with the top-level segment that owns it -- the
    same segment `_panel_status` looks up by the step's own `segment` id, for
    both a segment's own panel (design-it-twice's own, before it was shelved
    -- #96, was the tree's one example) and its transition's."""
    for seg in asm.get("segment", []):
        for panelist in seg.get("panel", []):
            yield seg, panelist
        for panelist in seg.get("transition", {}).get("panel", []):
            yield seg, panelist


def test_every_panel_entry_resolves_a_known_tier():
    """Desired behaviour: a real conductor can dispatch every panelist in
    every assembly -- a brief with an unset tier and an unresolved runner
    cannot be acted on. Mirrors `_panel_status`'s own resolution
    (`engine/cli.py`) rather than calling it, so the test does not need a
    live run's state to exercise a purely structural fact."""
    misses = []
    for name in runmod.assemblies():
        asm = runmod.load_assembly(name)
        for seg, panelist in _panel_entries(asm):
            tier = panelist.get("model") or seg.get("model", "")
            if not tier:
                misses.append(f"{name}:{seg['id']} panel entry "
                               f"{panelist.get('criteria') or panelist.get('worker')!r} "
                               "has no resolvable model tier")
            elif tier not in MODELS:
                misses.append(f"{name}:{seg['id']} panel entry resolves tier "
                               f"{tier!r}, not in constellation.toml [models]")
    assert not misses, "\n".join(misses)


def test_no_form_declares_a_scalar_field_after_a_plan_field():
    """Desired behaviour, general guard: `forms.materialize` writes a
    `kind = "plan"` field as a bare `[[id]]` array-of-tables header; any
    scalar field declared after it in the same form renders as a bare
    `key = ""` line that TOML nests inside the array-of-tables' last block
    instead of writing a sibling field. A `check` field never reaches the
    template (`materialize`'s own `shown` filter), so it is exempt the same
    way. The next form to grow a plan field hits this again unless
    something is standing here."""
    misses = []
    for path in FORMS:
        form = forms.load(path)
        shown = [f for f in form["fields"] if f["kind"] != "check"]
        seen_plan = False
        for field in shown:
            if field["kind"] == "plan":
                seen_plan = True
            elif seen_plan:
                misses.append(f"{path.relative_to(ROOT)}: scalar field "
                               f"{field['id']!r} (kind={field['kind']!r}) "
                               "declared after a plan field")
    assert not misses, "\n".join(misses)
