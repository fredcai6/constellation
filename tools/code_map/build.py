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


def build(root, *, artifacts=None, out=None, packages=()) -> int:
    """Run extract then render end to end against `root`.

    `artifacts`/`out` default to `<root>/.code-map` and `<root>/map` when
    omitted -- the same defaults `cli.py`'s argument parser resolves for the
    `build` subcommand. Returns the first nonzero stage status, or 0.

    `packages` narrows the RENDER to those dotted package prefixes and is
    passed to `render.run` alone: `extract` always walks the whole corpus, so
    a narrowed page still reports the callers it has outside the narrowing.
    See `render.in_render_scope`.
    """
    from . import extract, render

    root = Path(root)
    artifacts = Path(artifacts) if artifacts is not None else root / ARTIFACTS_DIRNAME
    out = Path(out) if out is not None else root / MAP_DIRNAME

    status = extract.run(root, artifacts)
    if status:
        return status
    return render.run(root, artifacts, out, packages)
