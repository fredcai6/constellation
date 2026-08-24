"""Fold the journal into where you are.

There is no state file. A run is its journal, and everything below is a
question asked of the entry list: which steps exist, which are done, what is
current. Two sessions interleaving is a fact the fold reports, never a
condition it prevents.
"""

import pathlib
import tomllib

from engine import journal


def assembly_dir(name):
    return pathlib.Path(__file__).resolve().parent.parent / "assemblies" / name


def load_assembly(name):
    d = assembly_dir(name)
    spec = tomllib.load(open(d / "ASSEMBLY.toml", "rb"))
    spec["dir"] = d
    return spec


def resolve_form(assembly, ref):
    """A form reference is either skill-owned (repo-relative, begins with
    `skills/`) or assembly-owned (relative to the assembly directory)."""
    root = pathlib.Path(__file__).resolve().parent.parent
    return root / ref if ref.startswith("skills/") else assembly["dir"] / ref


def skeleton(assembly):
    """The steps `open` mints: one transition per segment, in order.

    Interiors are not minted here. A worklist fills as work is discovered and
    a board is seeded as its own entry, so the skeleton is only the fixed
    part -- which is exactly the promise that the skeleton does not move.
    """
    steps = []
    for seg in assembly["segment"]:
        t = seg.get("transition", {})
        if not t.get("form"):
            continue  # a mechanical transition (verdicts decide it) has no form to fill
        steps.append(
            {
                "id": t.get("id", seg["id"]),
                "segment": seg["id"],
                "form": t["form"],
                "filler": t.get("filler", "conductor"),
                "anchor": t.get("anchor", False),
                "terminal": t.get("terminal", False),
                "validates": t.get("validates", ""),
                "source": "open",
            }
        )
    return steps


def state(work_id):
    """Fold the journal: the run's identity, its steps, and where it stands."""
    entries = journal.read(work_id)
    if not entries:
        return None
    st = {"id": work_id, "steps": [], "done": {}, "boards": {}, "notes": []}
    for e in entries:
        kind = e.get("kind")
        if kind == "run":
            st.update(title=e.get("title", ""), assembly=e.get("assembly", ""),
                      opened=e.get("at", ""))
        elif kind == "step":
            st["steps"].append(e)
        elif kind == "submit":
            st["done"][e["step"]] = e
        elif kind == "board":
            st["boards"][e["segment"]] = e.get("path", "")
        elif kind == "note":
            st["notes"].append(e)
    st["current"] = next((s for s in st["steps"] if s["id"] not in st["done"]), None)
    st["open"] = st["current"] is not None
    return st


def position(st, assembly):
    """Human-facing place in the run: (index, total, segment id)."""
    cur = st["current"]
    if not cur:
        return len(st["steps"]), len(st["steps"]), "closed"
    return st["steps"].index(cur) + 1, len(st["steps"]), cur["segment"]


def blocks(st):
    """Open blocked notes, newest first -- status surfaces these before all else."""
    resumed = {n.get("about") for n in st["notes"] if n.get("kind_detail") == "resumed"}
    return [n for n in st["notes"]
            if n.get("kind_detail") == "blocked" and n.get("id") not in resumed]
