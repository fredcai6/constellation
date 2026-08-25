"""The numbers gate `gb` commits, and the one-line action for when each fires.

Every threshold here is a RATIO or a run-time INVARIANT, never an absolute
count -- this run adds `.py` files (including its own tests) to the corpus it
measures, so an absolute count goes stale by construction. Concrete proof:
`g5`'s remediation added one test method and the map -- which self-indexes
`tests/` -- moved from 3752 to 3753 entities and 3864 to 3865 pages with no
change to what the map itself does.

Each constant states, right here, what a human does when the tripwire built
on it fires. A threshold with no action is noise (the human's own ruling on
what makes a tripwire useful). A tripwire earns its place only if tripping it
means something is actually WRONG -- not merely changed -- so every ceiling
below is set with real headroom above measured healthy behaviour, never at
the measured value itself.
"""

#: holes / entities must stay under this. NOT a documentation-completeness
#: gate -- ordinary content edits (more code, fewer or more docstrings) never
#: approach it. It exists to catch a CATASTROPHIC docstring-extraction
#: regression: something that stops `extract.doc_body_of` / the `documents`
#: statement from reaching the store at all, which would push the ratio
#: toward 100%. Measured at commit c1fccdd8: this repo 67.3% (2525/3753
#: holes/entities), f1Brainz (read-only, 1227 modules / 15037 entities)
#: 57.2% (8603/15037) -- both far under, on two corpora of very different
#: shape and scale, neither anywhere near this ceiling.
#:
#: WHEN THIS FIRES: open tools/code_map/extract.py's `documents` statement
#: emission and `doc_body_of`, then render.py's `docs` dict wiring in
#: `load_stores` -- the ratio only approaches this ceiling if docstrings stop
#: reaching the store, never because the corpus merely grew or shrank.
HOLE_RATIO_CEILING = 0.90

#: map-tree diff lines / source diff lines (the SAME unit the design process
#: measured at cycle-4: 98 map lines vs 84 source lines, ~1.2x), on an edit
#: that stays local to a handful of entities. MEASURED at gate `gb` on this
#: real repo (isolated git worktree, commit bd932921): a docstring edit to
#: `tools/code_map/discovery.is_mappable` produced 14 map diff lines / 11
#: source diff lines = **1.27x**. Held comfortably under the ceiling.
#:
#: WHEN THIS FIRES: the edit that triggered it touched far more of the map
#: than its own size justifies -- open the map diff and look for pages that
#: changed without the entity they describe having changed (a rendering
#: instability, not a content change).
CHURN_RATIO_CEILING_LOCAL_EDIT = 3.0

#: The SAME ceiling, on the adversarial case: renaming a symbol with many
#: in-corpus callers. NEVER MEASURED before gate `gb` -- at design confirm it
#: was signed off "accepted-untested". MEASURED at gate `gb` (isolated git
#: worktree, commit bd932921): renamed `tests.test_checklist_engine:gated`
#: (this real repo's highest-fan-in internal symbol -- 212 distinct caller
#: entities, identified by an inbound scan of a fresh build, not guessed) to
#: `gated_plan` throughout that one file. 466 map diff lines / 458 source
#: diff lines = **1.02x**. The ceiling HELD -- and it held for a structural
#: reason worth stating: a pure identifier rename changes exactly one line
#: per call site on BOTH sides (the source line naming it, the caller page's
#: "uses" line naming it back), so the ratio stays near 1x however many
#: callers exist, even though the PAGE COUNT touched (217 of 3865) looks
#: alarming in isolation. See the churn tests' own module docstring
#: (`ChurnRatioTests` in tests/test_code_map.py) for the small-scale
#: version of this same finding, reproduced on every suite run.
#:
#: WHEN THIS FIRES: the one-line-per-call-site relationship above has broken,
#: so a rename is producing MORE map diff lines than the call sites it
#: touches -- a different symptom from the local-edit ceiling's rendering
#: instability. Open the renamed symbol's own caller-list line first and check
#: it was edited in place rather than rewrapped or re-sorted wholesale; then
#: check whether the NEW name collides with an existing symbol's page path,
#: which turns edits into whole-page creations and deletions.
CHURN_RATIO_CEILING_RENAME = 3.0

#: Edge recall (matched / hand-labeled-true) per predicate, on a small
#: hand-authored fixture -- see the recall tests' own docstring for the
#: fixture and the hand count. No automated oracle stands behind these
#: numbers: this pipeline is stdlib only (no SCIP), and the design-time SCIP
#: cross-check was blind to `writes` anyway (DESIGN_SPEC TS7). So EVERY
#: predicate, including `writes`, is derived the SAME way -- a hand count
#: over a fixture small enough to verify exhaustively -- stated here rather
#: than left implicit.
#:
#: WHEN THIS FIRES: a predicate's extraction or resolution broke -- open
#: extract.py's Extractor.visit_Call / visit_Name / visit_Attribute / _store
#: for the predicate named in the failure and re-run the fixture by hand.
RECALL_FLOORS = {
    "calls": 1.0,
    "reads": 1.0,
    "writes": 1.0,
}

RECALL_FLOOR_DERIVATION = (
    "hand-labeled fixture in tests/test_code_map.py (RecallFloorTests) -- "
    "every predicate's ground truth is a manual read of the fixture source, "
    "not an automated oracle; writes is included on the same basis as calls "
    "and reads, stated rather than left implicit"
)

#: Not a ratio: an INVARIANT. Every literal string segment render.py authors
#: itself must be ASCII -- decided by exact provenance (the segment's origin
#: in render.py's own AST: a bare string Constant, or the literal parts of an
#: f-string, never the interpolated {expr} parts that carry source content),
#: never by matching substrings against rendered page text.
#:
#: WHEN THIS FIRES: a non-ASCII character was pasted into a literal in
#: render.py -- open the named line, replace the character. Do NOT touch the
#: 386 pre-existing non-ASCII pages this repo already has -- those are
#: correct, verbatim-reproduced source prose (an em-dash in
#: scripts/agent_work_root.py's docstring), not template text, and this
#: invariant is deliberately blind to them.
TEMPLATE_ASCII_INVARIANT = (
    "every literal string segment render.py authors itself (not fed by "
    "source-content interpolation) must satisfy str.isascii()"
)
