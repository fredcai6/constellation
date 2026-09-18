# Purpose in code

Where the *why* lives after the work is done: on the definition that carries it out, in one
graph that climbs to a root purpose in `docs/PURPOSE.md` or `standards/approach.md`. Those two pages
say what this repository is for and how Tommy builds; this page says how a line of code reaches
them, and what an implementer writes down to make the connection real.

## The graph

Every node is an **anchor** on something that already exists — a definition in the tree, or one
of the eleven root purposes in the two roots documents. An anchor is a comment line holding only a
bracketed kebab slug, directly above what it names: `# [slug]` in Python, `<!-- [slug] -->` in
markdown. A slug is minted on demand, is unique across the tree, and reads as the purpose it
names rather than as the symbol underneath it. There is no purpose artifact and no second kind
of node: a purpose you cannot attach to an existing definition is not a node yet, but a purpose
waiting for code, or one to drop.

Edges live in `map/parents.jsonl`, the one authored file in an otherwise derived map. One JSON
object per line, naming an anchor and the purposes it serves:

```
{"id": "markdown-anchor-is-an-html-comment", "parents": ["purpose-keeps-the-why-attached"]}
{"id": "purpose-keeps-the-why-attached", "parents": []}
```

One row per id, and a row may name more than one parent — a definition can serve two purposes,
which makes this a DAG rather than a tree. An id with no row is an **orphan**: absence means
unmapped, so a fresh checkout orphans every anchor in the tree. A root purpose carries a row with
an empty `parents` list, which renders as `none -- declared root`; without a row it renders as
`ORPHAN` like anything else (`tools/code_map/render.py`, `PARENTS_ROOT`).

Which documents hold roots is named in `constellation.toml`'s `[roots]` table rather than in a
check's source, so a root set can differ per repository — `standards/approach.md` travels and
`docs/PURPOSE.md` does not. That table's own comment carries the full reasoning.

A row resolves against two corpora and only those two: tracked Python for anchors
(`tools/code_map/discovery.py`), and the roots documents for root purposes
(`tools/code_map/parents.py`, `root_claim_ids`). Both ends of every row are checked against them,
so a row naming a root purpose resolves like any other. A markdown anchor written anywhere else
is in neither corpus and dangles forever — the mechanical half of why a node is a definition in
the tree or a root purpose, and never a third thing.

## A rung goes next to its executor

A **rung** is one anchor plus its row — one step of the climb. Put each rung on the definition
that carries out that purpose, usually a module docstring, sometimes one function whose purpose
differs from its module's. A purpose sitting next to the code that executes it can be checked
against that code by the next reader, and contradicted by it. That is the whole value.

**Never author a rung with no executor.** If no definition carries out the purpose, there is
nothing to anchor: write the code, or drop the purpose.

A chain that reaches a root in two rungs is complete, not lazy. Inventing a middle rung to pad
the ladder is the defect, because it puts a purpose somewhere no code can contradict it, and a
purpose nothing can falsify is exactly what this graph exists to stop.

Stop climbing at a root purpose. A root is where the chain terminates, never a node to climb past.

## Duty is one path, not a subtree

When a spec decomposes a problem, it traces its obligations up to a root purpose and builds
whatever rungs are missing along that path. That path, and nothing beside it. Neighboring code
stays unmapped until something touches it.

Backfill is a detour on a path you are already walking, never a cartography project. The rung
you need and cannot find, you write. The rung next to it that is also missing, you leave.

A new project flows down naturally: the spec arrives with its why, and each definition is
anchored as it is written. An existing project gets reworked a path at a time. This tree holds
169 anchors and no rows at all (`python3 -m tools.code_map.parents`, rev 3a46f47). That number
comes down through runs doing their own work, not through a run that maps for its own sake.

## Never cite an obligation from code — cite the purpose it carried

An obligation is scaffolding: it distills a spec into items an implementer can act on, and it
falls away once the implementation lands. Obligations live in `.agent-work/`, gitignored and
perishable. The code outlives them, so a comment that cites one points into a directory that is
already gone.

`engine/` holds 44 such comments at rev 3a46f47 — 34 in `cli.py`, 7 in `checks.py`, 2 in
`run.py`, 1 in `render.py` (`grep -c commitment engine/*.py`) — saying things like *this is the
read half of commitment 7's contract*. Each is broken twice over. The specs they cite were in
`.agent-work/` and are gone, and they address by sequence number, an addressing scheme this
repo abandoned when a commitment gained a key that survives a rework (commit 0f0ef79). Someone
pushed the obligation's number into the code instead of the purpose it carried.

Write what the contract *is*, anchor it, and let the row carry the link upward. Those 44 get
fixed as backfill when a run touches that area, not as a sweep.

## Nothing refuses

Orphan and dangling are reports. `orphan_report` and `dangling_report` in
`tools/code_map/parents.py` return lists, and that module's `main` always returns 0; a page for
an unmapped anchor says `ORPHAN` and renders anyway.

That is deliberate. A purpose graph that can block a commit becomes a box-ticking exercise, and
Grudin's 1996 work on design-rationale capture is that rationale nobody wants to write does not
get written honestly — it gets written to clear the gate. A gate here would buy coverage and
spend the truth of every entry. This graph earns its keep by being worth reading.
