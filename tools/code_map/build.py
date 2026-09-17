"""tools/code_map/build.py -- the plain-importable build() seam.

`cli.py`'s `_build(args)` delegates here so there is exactly one build path,
not two that can drift: the CLI `build` subcommand and any library caller both
run through this same function.

Stage modules are imported inside the function rather than at module scope,
mirroring `cli.py`'s own docstring rationale: importing a caller of this
module must not pay for the extractor.
"""

from pathlib import Path

# Mirrors cli.py's ARTIFACTS_DIRNAME/MAP_DIRNAME -- the same default shape a
# library caller gets when it does not supply its own paths.
ARTIFACTS_DIRNAME = ".code-map"
MAP_DIRNAME = "map"


# [map-build-prints-parents-summary]
# Rationale: `parents.orphan_report`/`dangling_report` already existed with
#   no caller at any seam -- `docs/DERIVED_IS_CODE.md`'s "unwired derivation
#   is a missing call site, not dead weight." `build()` is that seam:
#   `constellation.toml`'s `map` entry (its own comment calls it "the
#   closeout call") runs this function, so printing here is the one place
#   that reaches every caller of the closeout call without also reaching the
#   narrower `render`/`extract` subcommands that are not "the build."
#
#   Counts only, never the id lists: `parents.main` already prints those on
#   request, and 169 orphan lines in every build would bury the two numbers
#   that matter under output nobody reads (epic #138: the defined portion is
#   currently a known-empty backfill, not a build-time surprise). Neither
#   number changes `build`'s return value -- `dangling_report`'s own
#   docstring says a stale reference is "raw material for a ranked backlog,
#   not a commit-time gate," and the same holds for an orphan: a purpose
#   graph that can block a build becomes a box-ticking exercise.
def _print_parents_summary(root):
    from . import parents

    result = parents.report(root, Path(root) / MAP_DIRNAME / parents.PARENTS_FILENAME)
    print("parents: %d anchor(s), %d parents.jsonl entr(ies) -- "
          "%d orphaned, %d dangling"
          % (result["anchors"], result["parents_entries"],
             len(result["orphans"]), len(result["dangling"])))
    print("  detail: python3 -m tools.code_map.parents --root %s" % root)


def build(root, *, artifacts=None, out=None, packages=()) -> int:
    """Run extract then render end to end against `root`.

    `artifacts`/`out` default to `<root>/.code-map` and `<root>/map` when
    omitted -- the same defaults `cli.py`'s argument parser resolves for the
    `build` subcommand. Returns the first nonzero stage status, or 0.

    `packages` narrows the RENDER to those dotted package prefixes and is
    passed to `render.run` alone: `extract` always walks the whole corpus, so
    a narrowed page still reports the callers it has outside the narrowing.
    See `render.in_render_scope`.

    Always prints the defined-portion summary (orphan/dangling counts) after
    render finishes, win or lose -- see `_print_parents_summary`. It reads
    `root`, not `artifacts` or `out`: the committed `map/parents.jsonl` lives
    at a fixed spot under `root` regardless of where a caller narrows or
    redirects the derived tree, mirroring `render.run`'s own read of it.
    """
    from . import extract, render

    root = Path(root)
    artifacts = Path(artifacts) if artifacts is not None else root / ARTIFACTS_DIRNAME
    out = Path(out) if out is not None else root / MAP_DIRNAME

    status = extract.run(root, artifacts)
    if status:
        return status
    status = render.run(root, artifacts, out, packages)
    _print_parents_summary(root)
    return status
