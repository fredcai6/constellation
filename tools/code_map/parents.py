"""tools/code_map/parents.py -- the map's DEFINED portion: which purpose a
definition serves.

Epic #138, finding 1. Everything else the map holds is either code or
computed from code; the parent link is not -- which purpose a definition
serves is authored, never derived, so it lives in its own committed file
rather than in the gitignored statement store or page tree render.py builds.

`map/parents.jsonl` is that file: one JSON object per line, `{"id": "<anchor
slug>", "parents": ["<id>", ...]}`. A pure hierarchy -- a DAG, since a
definition may serve more than one purpose -- with no side links, no edge
types, no annotations. Nothing here MINTS a parents entry; this module only
reads what is already written and reports where the defined portion and the
tree disagree. Nothing writes parents yet -- that is finding 2 -- so on a
freshly checked-out tree this module's own orphan report names every anchor.

Stdlib only, matching the rest of `tools/code_map` (see `__init__.py`'s own
constraint): CI installs pytest and coverage and nothing else.
"""
import json
from pathlib import Path

from .discovery import discover_corpus
from .extract import anchors_in

#: Beside `extract.STATEMENTS_NAME` and `render.IDS_FILENAME` -- the same
#: directory, the opposite side of the commit rule: `ids.jsonl` is derived
#: identity, gitignored; `parents.jsonl` is authored structure, committed.
PARENTS_FILENAME = "parents.jsonl"


def read_parents(path):
    """`map/parents.jsonl` -> `{id: (parent id, ...)}`, in the file's own
    line order. A path that does not exist reads as empty -- a fresh
    checkout with no defined portion yet, not an error.

    No validation beyond well-formed JSON with an `id`: this is a reader,
    not a gate. A row naming a parent that is not an anchor is exactly what
    `dangling_report` below reports; this function does not refuse it."""
    path = Path(path)
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        out[row["id"]] = tuple(row.get("parents", ()))
    return out


# [parents-anchor-set-is-the-grammar]
# Rationale: this reads `anchors_in` -- the same forward-scan grammar
#   `extract.py`'s own `Extractor.anchor()` calls -- rather than the
#   `anchored` statements the built store carries. The two are not the same
#   set: `Extractor.anchor()` only ever fires from the handful of visitor
#   methods that call it (a class, a function, a module/class-level
#   assignment), so an anchor comment sitting above anything else parses
#   under the grammar and never reaches the store, silently (epic #138's
#   own evidence: "three anchors extract to nothing"). That gap is a
#   different, narrower finding (the check set's own "silent anchor
#   near-miss"). This module's job is the DEFINED portion against what an
#   author can legally write an anchor above, so it reads the grammar
#   directly and does not inherit the extractor's emission-site gap.
def anchor_ids(root):
    """Every anchor id in the mappable corpus, as a set.

    A set, not a count of occurrences: two anchors sharing one slug in
    different files is a duplicate id -- a separate authoring defect this
    reader does not paper over by counting positions instead of identities."""
    root = Path(root)
    ids = set()
    for rel in discover_corpus(root):
        src = (root / rel).read_text(encoding="utf-8")
        ids.update(anchors_in(src).values())
    return ids


def orphan_report(anchors, parents):
    """Anchor ids present in `anchors` with no entry in `parents`.

    Absence means orphan (epic #138, finding 1): nothing is seeded, so a
    freshly-checked-out `parents.jsonl` orphans every anchor in the tree.
    Raw material for a later ranked backlog -- this never refuses."""
    return sorted(set(anchors) - set(parents))


# [parents-dangling-checks-both-ends]
# Rationale: a `parents.jsonl` row names two kinds of id -- its own `id` and
#   each string in `parents` -- and either can go stale independently. A
#   row's own id goes dangling when the anchor it named is renamed or
#   deleted and nobody updated this file to match; a listed parent goes
#   dangling the same way, one hop further out. Both are the same failure
#   (an authored claim outliving the anchor it points at) and both are
#   reported here rather than splitting into two checks that would only
#   ever be run together.
def dangling_report(anchors, parents):
    """Every id `parents` names -- a row's own id or one of its parents --
    that is not in `anchors`.

    Reports, never refuses: a stale reference is raw material for the same
    ranked backlog `orphan_report` feeds, not a commit-time gate."""
    anchors = set(anchors)
    bad = set()
    for node_id, parent_ids in parents.items():
        if node_id not in anchors:
            bad.add(node_id)
        bad.update(p for p in parent_ids if p not in anchors)
    return sorted(bad)


def report(root, parents_path):
    """The two reports together, against the anchor set found under `root`."""
    anchors = anchor_ids(root)
    parents = read_parents(parents_path)
    return {
        "anchors": len(anchors),
        "parents_entries": len(parents),
        "orphans": orphan_report(anchors, parents),
        "dangling": dangling_report(anchors, parents),
    }


# ------------------------------------------------------------------- stage

def main(argv=None):
    """`python -m tools.code_map.parents [--root DIR] [--parents FILE]`

    Prints the orphan and dangling reports and always returns 0 -- neither
    report is a gate, so there is nothing here to fail a build over. A
    separate module, not a `tools.code_map.cli` subcommand: `cli.py` is
    shared with the rest of the pipeline, and this stays reachable on its
    own so a change here never has to touch it."""
    import argparse

    # tools/code_map/parents.py -> tools/code_map -> tools -> repo root.
    default_root = Path(__file__).resolve().parents[2]

    parser = argparse.ArgumentParser(
        prog="code_map.parents",
        description="Report on map/parents.jsonl: the map's defined portion.")
    parser.add_argument("--root", default=str(default_root),
                        help="repository to check (default: this repository)")
    parser.add_argument("--parents", default=None,
                        help="path to parents.jsonl (default: <root>/map/parents.jsonl)")
    args = parser.parse_args(argv)

    root = Path(args.root)
    parents_path = Path(args.parents) if args.parents else root / "map" / PARENTS_FILENAME

    result = report(root, parents_path)
    print(json.dumps(
        {"anchors": result["anchors"], "parents_entries": result["parents_entries"],
         "orphans": len(result["orphans"]), "dangling": len(result["dangling"])},
        indent=1))
    if result["orphans"]:
        print("orphans (anchors with no parents.jsonl entry):")
        for oid in result["orphans"]:
            print("  " + oid)
    if result["dangling"]:
        print("dangling (parents.jsonl ids that are not anchors in the tree):")
        for did in result["dangling"]:
            print("  " + did)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
