"""Fold the journal into where you are.

There is no state file. A run is its journal, and everything below is a
question asked of the entry list: which steps exist, which are done, what is
current. Two sessions interleaving is a fact the fold reports, never a
condition it prevents.
"""

import pathlib
import tomllib

from engine import forms, journal


def assembly_dir(name):
    return pathlib.Path(__file__).resolve().parent.parent / "assemblies" / name


def assemblies():
    root = pathlib.Path(__file__).resolve().parent.parent / "assemblies"
    return sorted(p.name for p in root.iterdir() if (p / "ASSEMBLY.toml").exists())


def load_assembly(name):
    d = assembly_dir(name)
    if not (d / "ASSEMBLY.toml").exists():
        raise SystemExit(f"no assembly named {name!r} -- try: "
                         + ", ".join(assemblies()))
    spec = tomllib.load(open(d / "ASSEMBLY.toml", "rb"))
    spec["dir"] = d
    return spec


def resolve_form(assembly, ref):
    """A form reference is either skill-owned (repo-relative, begins with
    `skills/`) or assembly-owned (relative to the assembly directory).

    A skill-owned ref never reads `assembly`, so `None` is a legal assembly
    for one -- which is what `resolve_skill` passes.
    """
    root = pathlib.Path(__file__).resolve().parent.parent
    return root / ref if ref.startswith("skills/") else assembly["dir"] / ref


# [resolve-skill]
# Rationale: a role name is resolved by the same convention as a skill-owned
#   form ref, through `resolve_form` itself, so where a bundle lives is written
#   in exactly one place. That is why a skill's form is delivered today and the
#   skill is not -- the convention existed, nothing applied it to the role.
# Rejected: joining the role to a cwd-relative root (the one `_palette` reads,
#   engine/cli.py). `install.py` copies each bundle next to `engine/`, so a
#   child working in some other tree would be handed a path that is not there.
# Rejected: raising when a role has no SKILL.md. Five rostered roles --
#   epic-conductor, issue-conductor-delegated, interrogator-delegated, triage, how-to-talk
#   -- have no skills/ directory at all, so absence is an answer, not a
#   failure -- the caller renders no line.
def resolve_skill(role):
    """Where a role's posture is written, or None when the role has none.

    `conductor` is not a role -- it is the assembly's indirection for whoever
    conducts it -- so it is resolved before it gets here, never looked up as
    `skills/conductor/`.
    """
    if not role:
        return None
    path = resolve_form(None, f"skills/{role}/SKILL.md")
    return path if path.is_file() else None


# [role-of]
# Rationale: `filler = "conductor"` means whoever conducts this assembly, and
#   the two places that announce a role both have to unwrap it the same way.
def role_of(assembly, step):
    """Which role fills this step, with the `conductor` indirection resolved."""
    filler = step.get("filler", "")
    return (assembly or {}).get("conductor", "") if filler == "conductor" else filler


# [hat]
# Rationale: nothing dispatches a board's worker. Its transition is filled by
#   the conductor, who works the board in the worker's posture -- the
#   issue-conductor wears the interrogator's hat -- because a live principal is
#   reachable only from the top of the run. A run with a parent has no human
#   in reach, so it wears the delegated variant where one is written; where
#   none is, the plain posture, which is the parked state (#15).
# Rejected: a worker child driving its parent's board. A child not handed an
#   id cannot drive its dispatcher's run, by design, and the board is the
#   parent's own segment.
def hat(assembly, step, st):
    """The posture a step is worked under: the filler's, or on a board
    segment the worker's -- delegated when the run has a parent."""
    seg = next((s for s in assembly["segment"] if s["id"] == step.get("segment")), {})
    worker = seg.get("worker", "") if seg.get("interior") == "board" else ""
    if not worker:
        return role_of(assembly, step)
    delegated = f"{worker}-delegated"
    return delegated if st.get("parent") and resolve_skill(delegated) else worker


# [rework-rounds]
# Rationale: the count is of rounds on one artifact, not rounds in the run --
#   `skills/issue-conductor/SKILL.md` conditions its stopping rule on repetition
#   against the same thing. A step-form mint is a replan, which is a new
#   artifact, so it restarts the count; a rework-form mint is another pass at
#   the same one.
# Rejected: counting `source == "mint"` regardless of form. Simpler, and it
#   cannot be walked around by replanning -- but it counts effort rather than
#   repetition, which is not what the rule is about.
def rework_rounds(st, assembly, seg_id):
    """How many times this segment has been sent back to the same artifact.

    A segment that declares a rework-form distinguishes the two send-backs it
    has: a rework is another pass at the same artifact, a replan is a new one,
    so the step-form restarts the count. A segment with no rework-form --
    run-a-gate's work -- has only one, and every mint of its step-form counts.
    Either way the opening step is `source=open` and is not a send-back.
    """
    seg = next((s for s in assembly["segment"] if s["id"] == seg_id), {})
    rework, step = seg.get("rework-form", ""), seg.get("step-form", "")
    n = 0
    for s in st["steps"]:
        if s.get("segment") != seg_id or s.get("source") != "mint":
            continue
        if rework and s.get("form") == step:
            n = 0
        elif s.get("form") == (rework or step):
            n += 1
    return n


def skeleton(assembly):
    """The steps `open` mints: per segment, the first interior step (when the
    segment declares one) and then its transition.

    A worklist grows and shrinks as work is discovered, but it starts with one
    step, because the work to do is what the segment is for -- a gate that
    opens with nothing to implement, or a plan phase with nothing to plan, is
    a worklist that cannot be started. Interiors minted by a `plan` field
    (gates) and boards are seeded by their own entries, not here.

    A transition mints a step when it declares a `form`, a `panel`, or both --
    a panel-only step has a conductor standing there to fire it, not a form to
    fill. `form` is therefore omitted from the step, not carried empty.
    """
    steps = []
    for seg in assembly["segment"]:
        form = seg.get("step-form")
        if form and seg.get("interior") == "steps":
            steps.append({"id": seg["id"] + "-1", "segment": seg["id"], "form": form,
                          "filler": seg.get("worker", "conductor"), "anchor": False,
                          "terminal": False, "validates": "", "source": "open"})
        t = seg.get("transition", {})
        panel = t.get("panel")
        if not t.get("form") and not panel:
            continue  # nothing to stand on: no form to fill and no panel to fire
        step = {
            "id": t.get("id", seg["id"]),
            "segment": seg["id"],
            "filler": t.get("filler", "conductor"),
            "anchor": t.get("anchor", False),
            "terminal": t.get("terminal", False),
            "validates": t.get("validates", ""),
            "carries": t.get("carries", False),
            "source": "open",
        }
        if t.get("form"):
            step["form"] = t["form"]
        if panel:
            step["panel"] = panel
        steps.append(step)
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


def merged_verdict(returns):
    """Escalate outranks revise outranks pass: a wrong spec outranks a wrong
    diff, and any blocking finding outranks a clean one."""
    vs = [forms.leading_word((r.get("fields") or {}).get("verdict", "")) for r in returns]
    if "escalate" in vs:
        return "escalate"
    if "revise" in vs:
        return "revise"
    return "pass"


def state(work_id):
    """Fold the journal: the run's identity, its steps, and where it stands."""
    entries = journal.read(work_id)
    if not entries:
        return None
    st = {"id": work_id, "steps": [], "done": {}, "boards": {}, "notes": [],
          "returns": {}, "returns_by_child": {}, "row_returns": {}, "amends": [],
          "checks": [], "measures": [], "closed": False}
    raw_steps = []
    for e in entries:
        kind = e.get("kind")
        if kind == "run":
            st.update(title=e.get("title", ""), assembly=e.get("assembly", ""),
                      opened=e.get("at", ""), parent=e.get("parent", ""),
                      parent_step=e.get("parent_step", ""), model=e.get("model", ""),
                      row=e.get("row", ""))
        elif kind == "step":
            raw_steps.append(dict(e))
        elif kind == "submit":
            st["done"][e["step"]] = e
            st["checks"].extend(e.get("checks") or [])
        elif kind == "return" and e.get("row"):
            # An excursion's return: it answers a board row, so it lands
            # under the row and completes no step.
            st["row_returns"].setdefault(e["row"], []).append(e)
        elif kind == "return":
            # `returns` accumulates in arrival order rather than overwriting --
            # a panel step gets one return per dispatched panelist, all on the
            # same step id, and each must stay attributable to its child.
            # `done` only lands once every expected panelist has answered; a
            # step with no `panel` expects one, so a single-child dispatch
            # completes on its first (and only) return exactly as before. A
            # step carrying both a panel and a form is the two-voices
            # transition: the returns are the panel's voice, the form is the
            # conductor's, so a full house only lands in `done` here when the
            # merged verdict is not `pass` -- exactly like a panel-only step,
            # which releases on any verdict because it has no form to hold
            # for. A `pass` instead leaves it open; it completes on submit.
            step = next((s for s in raw_steps if s["id"] == e["step"]), None)
            expected = len(step["panel"]) if step and step.get("panel") else 1
            returns = st["returns"].setdefault(e["step"], [])
            returns.append(e)
            st["returns_by_child"][e.get("child", "")] = e
            two_voices = bool(step and step.get("panel") and step.get("form"))
            if len(returns) >= expected and not (two_voices and merged_verdict(returns) == "pass"):
                st["done"][e["step"]] = e
        elif kind == "check":
            st["checks"].append({"command": e.get("command"), "exit": e.get("exit"),
                                 "output": e.get("output")})
        elif kind == "board":
            st["boards"][e["segment"]] = e.get("path", "")
        elif kind == "note":
            st["notes"].append(e)
        elif kind == "measure":
            st["measures"].append(e)
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


def panel_outstanding(st, step):
    """A step's panel has not finished voting -- fewer returns than
    panelists. True the same way for a panel-only step and a two-voices one;
    the difference between them shows up only once this is false, since a
    two-voices step whose panel resolved anything but `pass` is already
    `done` by then and can no longer be `st["current"]`."""
    panel = step.get("panel")
    return bool(panel) and len(st["returns"].get(step["id"], [])) < len(panel)
