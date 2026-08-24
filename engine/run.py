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
    """The steps `open` mints: per segment, the first interior step (when the
    segment declares one) and then its transition.

    A worklist grows and shrinks as work is discovered, but it starts with one
    step, because the work to do is what the segment is for -- a gate that
    opens with nothing to implement, or a plan phase with nothing to plan, is
    a worklist that cannot be started. Interiors minted by a `plan` field
    (gates) and boards are seeded by their own entries, not here.
    """
    steps = []
    for seg in assembly["segment"]:
        form = seg.get("step-form")
        if form and seg.get("interior") == "steps":
            steps.append({"id": seg["id"] + "-1", "segment": seg["id"], "form": form,
                          "filler": seg.get("worker", "conductor"), "anchor": False,
                          "terminal": False, "validates": "", "source": "open"})
        t = seg.get("transition", {})
        if not t.get("form"):
            continue  # a mechanical transition (verdicts decide it) has no step to fill
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


def _apply_amend(raw_steps, e):
    """`close` drops a pending step; `reorder` moves one before another --
    both mutate the worklist in place, at the point they occur in the
    journal. `add` needs no mutation here: its own `step` entry (appended
    right alongside the amend entry) already carries the new step through
    the ordinary branch below.
    """
    action = e.get("action")
    if action == "close":
        raw_steps[:] = [s for s in raw_steps if s["id"] != e.get("step")]
    elif action == "reorder":
        step = next((s for s in raw_steps if s["id"] == e.get("step")), None)
        if step:
            raw_steps.remove(step)
            idx = next((i for i, s in enumerate(raw_steps) if s["id"] == e.get("before")),
                       len(raw_steps))
            raw_steps.insert(idx, step)


def _ordered(raw_steps, seg_order):
    """Segment order, not journal order.

    A mint or a late amend is appended to the journal after its segment's
    transition step (already written at `open`), so raw append order would
    put a segment's exit gate before work minted into it. Group by the
    assembly's true segment order instead, terminal step last within its
    group -- that is the one ordering a segment can have and still make
    sense read forward.
    """
    groups = {}
    for s in raw_steps:
        groups.setdefault(s["segment"], []).append(s)
    ordered = []
    for seg in seg_order:
        group = groups.pop(seg, [])
        ordered += [s for s in group if not s.get("terminal")]
        ordered += [s for s in group if s.get("terminal")]
    for group in groups.values():  # a segment the current assembly no longer names
        ordered += group
    return ordered


def state(work_id):
    """Fold the journal: the run's identity, its steps, and where it stands."""
    entries = journal.read(work_id)
    if not entries:
        return None
    st = {"id": work_id, "steps": [], "done": {}, "boards": {}, "notes": [],
          "returns": {}, "returns_by_child": {}, "amends": [], "checks": [],
          "closed": False}
    raw_steps = []
    for e in entries:
        kind = e.get("kind")
        if kind == "run":
            st.update(title=e.get("title", ""), assembly=e.get("assembly", ""),
                      opened=e.get("at", ""), parent=e.get("parent", ""),
                      parent_step=e.get("parent_step", ""), model=e.get("model", ""))
        elif kind == "step":
            raw_steps.append(dict(e))
        elif kind == "submit":
            st["done"][e["step"]] = e
            st["checks"].extend(e.get("checks") or [])
        elif kind == "return":
            st["done"][e["step"]] = e
            st["returns"][e["step"]] = e
            st["returns_by_child"][e.get("child", "")] = e
        elif kind == "check":
            st["checks"].append({"command": e.get("command"), "exit": e.get("exit"),
                                 "output": e.get("output")})
        elif kind == "board":
            st["boards"][e["segment"]] = e.get("path", "")
        elif kind == "note":
            st["notes"].append(e)
        elif kind == "prefill":
            st["prefill"] = e.get("fields") or {}
        elif kind == "amend":
            st["amends"].append(e)
            _apply_amend(raw_steps, e)
        elif kind == "closed":
            st["closed"] = True

    seg_order = [s["id"] for s in load_assembly(st["assembly"])["segment"]] if st.get("assembly") else []
    st["steps"] = _ordered(raw_steps, seg_order)
    st["current"] = next((s for s in st["steps"] if s["id"] not in st["done"]), None)
    # A run is open until it is closed -- not merely until its last step is
    # submitted. The difference is load-bearing: a run whose steps are all done
    # has not stamped its returns, so its parent's dispatch step is still
    # waiting. Reporting that as closed strands the parent silently.
    st["open"] = not st["closed"]
    st["awaiting_close"] = st["current"] is None and not st["closed"]
    return st


def position(st, assembly):
    """Human-facing place in the run: (index, total, where)."""
    cur = st["current"]
    if not cur:
        return len(st["steps"]), len(st["steps"]), \
            "closed" if st["closed"] else "awaiting close"
    return st["steps"].index(cur) + 1, len(st["steps"]), cur["segment"]


def blocks(st):
    """Open blocked notes, newest first -- status surfaces these before all else."""
    resumed = {n.get("about") for n in st["notes"] if n.get("kind_detail") == "resumed"}
    return [n for n in st["notes"]
            if n.get("kind_detail") == "blocked" and n.get("id") not in resumed]
