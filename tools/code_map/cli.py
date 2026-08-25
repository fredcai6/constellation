"""The code_map command line: one entrypoint in front of the whole pipeline.

    python -m tools.code_map build          extract -> render
    python -m tools.code_map discover       print the mappable corpus
    python -m tools.code_map extract        the statement store only
    python -m tools.code_map render         the page tree only
    python -m tools.code_map check          the print-only diagnostics

Every subcommand takes `--root`, so nothing here is pinned to one checkout; the
prototype this was ported from hardcoded an absolute path to another repository.

Stage modules are imported inside their handler rather than at module scope.
Parsing arguments must not pay for the extractor, and `discover` must run before
a later gate has finished moving the stages around.
"""

import argparse
from pathlib import Path

# tools/code_map/cli.py -> tools/code_map -> tools -> the repository root.
REPO_ROOT = Path(__file__).resolve().parents[2]

# The rebuilt statement store lives here; the page
# tree lives in MAP_DIRNAME. Both are relative to --root.
ARTIFACTS_DIRNAME = ".code-map"
MAP_DIRNAME = "map"

STAGES = (
    ("discover", "print the mappable corpus and stop"),
    ("extract", "walk the corpus and write the statement store"),
    ("render", "write the page tree from the stores"),
    ("build", "run extract and render end to end"),
    ("check", "print the diagnostics over the built map"),
)

_WANTS_ARTIFACTS = {"extract", "render", "build", "check"}
_WANTS_OUT = {"render", "build", "check"}


class _Parser(argparse.ArgumentParser):
    """Resolves the artifact and map directories against `--root` at parse time,
    so a caller reading the parsed arguments never has to redo that join and the
    two cannot drift apart."""

    def parse_args(self, args=None, namespace=None):
        parsed = super().parse_args(args, namespace)
        if getattr(parsed, "artifacts", None) is None:
            parsed.artifacts = str(Path(parsed.root) / ARTIFACTS_DIRNAME)
        if getattr(parsed, "out", None) is None:
            parsed.out = str(Path(parsed.root) / MAP_DIRNAME)
        return parsed


def build_parser():
    """The argument parser for every stage. One `--root` per subcommand rather
    than one before it, because `code_map build --root .` is the form people type."""
    parser = _Parser(prog="code_map", description="Derive a code map from this repository's source.")
    stages = parser.add_subparsers(dest="command", required=True, metavar="<stage>")
    for name, help_text in STAGES:
        stage = stages.add_parser(name, help=help_text)
        stage.add_argument("--root", default=str(REPO_ROOT),
                           help="repository to map (default: this repository)")
        if name in _WANTS_ARTIFACTS:
            stage.add_argument("--artifacts", default=None,
                               help=f"rebuilt stores (default: <root>/{ARTIFACTS_DIRNAME})")
        if name in _WANTS_OUT:
            stage.add_argument("--out", default=None,
                               help=f"page tree (default: <root>/{MAP_DIRNAME})")
    return parser


def _discover(args):
    from . import discovery
    for rel in discovery.discover_corpus(Path(args.root)):
        print(rel)
    return 0


def _extract(args):
    from . import extract
    return extract.run(Path(args.root), Path(args.artifacts))


def _render(args):
    from . import render
    return render.run(Path(args.root), Path(args.artifacts), Path(args.out))


def _build(args):
    from .build import build
    return build(args.root, artifacts=args.artifacts, out=args.out)


def _check(args):
    from . import checks
    return checks.run(Path(args.root), Path(args.artifacts), Path(args.out))


HANDLERS = {
    "discover": _discover,
    "extract": _extract,
    "render": _render,
    "build": _build,
    "check": _check,
}


def main(argv=None):
    args = build_parser().parse_args(argv)
    return HANDLERS[args.command](args)
