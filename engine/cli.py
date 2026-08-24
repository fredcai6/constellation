"""`spine` -- the six verbs.

Argument shape is deliberately flat: the work id comes first and is always
required, because an id inferred from the environment is how a dispatched
crew ends up driving its dispatcher's run. A bare `spine` prints the ledger,
never your run.
"""

import pathlib
import secrets
import subprocess
import sys
import tomllib

from engine import forms
from engine import journal
from engine import render
from engine import run as runmod

USAGE = """spine <work-id>                     where you are
spine <work-id> submit              hand in the filled response form
spine <work-id> note <kind> <text>  record an observation, block, or decision
spine <work-id> amend add --segment S --form F --reason "..."
spine <work-id> amend close <step-id> --reason "..."
spine <work-id> amend reorder <step-id> --before <step-id> --reason "..."
spine <work-id> close               terminal: legal once every step is done
spine open <assembly> --title T [--issue N]
spine open <assembly> --parent <id> --step <step-id>   open a dispatched child
spine                               every open run"""

_GATE_ADJUDICATION_FORM = "forms/GATE_TRANSITION.toml"  # see run-an-issue's execute segment


def mint_id(kind="issue", issue=None):
    """A tracker number when there is one -- it is already collision-free and
    it associates the run to the issue for free. Otherwise random: two
    worktrees allocating in parallel cannot see each other's next number."""
    if issue:
        return f"{kind}{issue}"
    while True:
        wid = f"{kind}{secrets.token_hex(2)}"
        if not journal.exists(wid):
            return wid


def _palette():
    p = pathlib.Path("constellation.toml")
    return tomllib.load(open(p, "rb")) if p.exists() else {}


def _resolve_command(text):
    """`palette:test args` -> the host repo's test command plus args."""
    if not text.startswith("palette:"):
        return text
    name, _, rest = text[len("palette:"):].partition(" ")
    cmd = _palette().get("commands", {}).get(name)
    if not cmd:
        raise SystemExit(f"command palette has no entry named {name!r}")
    return f"{cmd} {rest}".strip()


def _tier(step, asm):
    """A dispatch step's model tier: its own prefill override, else the
    assembly segment's default."""
    seg = next((s for s in asm["segment"] if s["id"] == step["segment"]), {})
    return (step.get("prefill") or {}).get("model") or seg.get("model", "")


def _runner(tier):
    return _palette().get("models", {}).get(tier, "")


def _current_form(st):
    asm = runmod.load_assembly(st["assembly"])
    step = st["current"]
    if step.get("dispatches"):
        return asm, step, None  # rendered as a command, not a form
    return asm, step, forms.load(runmod.resolve_form(asm, step["form"]))


def _response_path(st, step):
    name = pathlib.Path(step["form"]).stem + ".toml"
    return journal.location(st["id"]) / name


def cmd_open(argv):
    assembly = argv[0]
    parent = _opt(argv, "--parent")
    if parent:
        return _open_child(assembly, parent, _opt(argv, "--step"))
    title = _opt(argv, "--title") or ""
    issue = _opt(argv, "--issue")
    wid = _opt(argv, "--id") or mint_id(issue=issue)
    if journal.exists(wid):
        raise SystemExit(f"{wid} already exists")
    asm = runmod.load_assembly(assembly)
    journal.append(wid, "run", title=title, assembly=assembly,
                   conductor=asm.get("conductor", ""))
    for step in runmod.skeleton(asm):
        journal.append(wid, "step", **step)
    print(f"opened {wid}\n")
    return cmd_status([wid])


def _open_child(assembly, parent, pstep_id):
    """A child is dispatched, never composed: its id, its orders, and the
    tier it runs under all come from the parent's dispatch step."""
    pst = runmod.state(parent)
    if pst is None:
        raise SystemExit(f"no run named {parent}")
    pstep = next((s for s in pst["steps"] if s["id"] == pstep_id), None)
    if pstep is None or not pstep.get("dispatches"):
        raise SystemExit(render.refusal(pstep_id or "step", "not a dispatch step"))
    wid = pstep.get("child") or f"{parent}.{pstep_id}"
    if journal.exists(wid):
        raise SystemExit(f"{wid} already exists")
    pasm = runmod.load_assembly(pst["assembly"])
    tier = _tier(pstep, pasm)
    asm = runmod.load_assembly(assembly)
    prefill = pstep.get("prefill") or {}
    title = prefill.get("purpose", pstep_id)
    journal.append(wid, "run", title=title, assembly=assembly,
                   conductor=asm.get("conductor", ""), parent=parent,
                   parent_step=pstep_id, model=tier)
    journal.append(wid, "prefill", fields=prefill)
    for step in runmod.skeleton(asm):
        journal.append(wid, "step", **step)
    print(f"opened {wid} -- dispatched by {parent} at {pstep_id}\n")
    return cmd_status([wid])


def _dispatch_status(wid, st, asm, step, blocked):
    """A dispatch step renders a command, not a form: the engine launches
    nothing, so the whole job is making the right invocation the only thing
    there is to type."""
    tier = _tier(step, asm)
    runner = _runner(tier)
    i, n, seg = runmod.position(st, asm)
    lines = [f"{wid} · {st.get('assembly','')} · {seg} ({i} of {n})", ""]
    if st.get("title"):
        lines.append(f"  {wid}: {st['title']}")
        lines.append("")
    for b in blocked:
        lines.append(f"  BLOCKED — {b.get('text','')}".rstrip())
        lines.append(f"  resume with: spine {wid} note resumed {b.get('id','')}")
        lines.append("")
    lines.append(f"  dispatch {step['dispatches']} -- tier {tier or '(unset)'}, "
                 f"runner {runner or '(unresolved -- check constellation.toml [models])'}")
    lines.append("")
    lines.append("  open the child with:")
    lines.append(f"    spine open {step['dispatches']} --parent {wid} --step {step['id']}")
    lines.append("")
    lines.append(f"  also legal:        spine {wid} note ...   spine {wid} amend ...")
    return "\n".join(lines)


def cmd_status(argv):
    wid = argv[0]
    st = runmod.state(wid)
    if st is None:
        raise SystemExit(f"no run named {wid}")
    if not st["open"] or st["awaiting_close"]:
        print(render.status(st, {}, "", position=runmod.position(st, None)))
        return 0
    asm, step, form = _current_form(st)
    if step.get("dispatches"):
        print(_dispatch_status(wid, st, asm, step, runmod.blocks(st)))
        return 0
    dest = _response_path(st, step)
    if not dest.exists():
        forms.materialize(form, dest, work_id=wid, submit=f"spine {wid} submit")
    ret = st["returns_by_child"].get(step.get("child", "")) if step.get("child") else None
    returns = {**ret.get("summary", {}), **ret.get("fields", {})} if ret else None
    print(render.status(st, form, dest, prefill=st.get("prefill") or step.get("prefill"),
                        returns=returns, blocked=runmod.blocks(st),
                        position=runmod.position(st, asm)))
    return 0


def cmd_submit(argv):
    wid = argv[0]
    st = runmod.state(wid)
    if st is None or not st["open"] or st["awaiting_close"]:
        raise SystemExit(f"{wid} has no current step"
                         + (f" -- close it: spine {wid} close"
                            if st and st["awaiting_close"] else ""))
    asm, step, form = _current_form(st)
    if step.get("dispatches"):
        raise SystemExit(render.refusal(
            step["id"],
            f"a dispatch step is not submitted -- open its child: "
            f"spine open {step['dispatches']} --parent {wid} --step {step['id']}"))
    dest = _response_path(st, step)
    if not dest.exists():
        raise SystemExit(f"no response form yet — run: spine {wid}")
    filled = forms.parse(dest)

    checks, fields = {}, {}
    for f in form["fields"]:
        fid, kind = f["id"], f.get("kind", "evidence")
        if kind == "check":
            continue  # the engine runs these; they are never on the template
        if fid not in filled:
            if f.get("optional"):
                continue
            raise SystemExit(render.refusal(fid, "no answer"))
        fields[fid] = filled[fid]

    for f in form["fields"]:
        if f.get("kind") != "check":
            continue
        # A check's command comes from the orders: the step's own prefill when
        # it has one, else the run's -- a dispatched child carries its spec at
        # the run level, and its first step is minted before that spec exists.
        orders = {**(st.get("prefill") or {}), **(step.get("prefill") or {})}
        cmd = _resolve_command(orders.get(f["id"], ""))
        if not cmd:
            continue
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        checks[f["id"]] = {"command": cmd, "exit": r.returncode,
                           "output": (r.stdout + r.stderr)[-4000:]}
        if r.returncode != 0:
            journal.append(wid, "check", step=step["id"], **checks[f["id"]])
            raise SystemExit(render.refusal(f["id"], f"`{cmd}` exited {r.returncode}"))

    journal.append(wid, "submit", step=step["id"], fields=fields,
                   checks=list(checks.values()) or None)
    _mint(wid, asm, step, form, fields)
    print(f"submitted {step['id']}\n")
    return cmd_status([wid])


def _mint(wid, asm, step, form, fields):
    """A `plan` field's content becomes structure: board rows, or steps."""
    for f in form["fields"]:
        if f.get("kind") != "plan" or f["id"] not in fields:
            continue
        rows = fields[f["id"]]
        mints = f.get("mints")
        if mints == "board rows":
            seg = next((s for s in asm["segment"] if s.get("interior") == "board"), None)
            if seg:
                path = journal.location(wid) / (pathlib.Path(seg["board"]).stem + ".toml")
                _seed_board(runmod.resolve_form(asm, seg["board"]), path, rows)
                journal.append(wid, "board", segment=seg["id"], path=str(path), rows=rows)
        elif mints == "run-a-gate":
            seg = next((s for s in asm["segment"] if s.get("dispatches") == mints), None)
            if seg:
                _mint_gates(wid, seg, rows)


def _mint_gates(wid, seg, gates):
    """Each gate block becomes a dispatch step and, right after it, the
    adjudication step that will hold its returns -- the pair the execute
    segment's worklist is made of."""
    for i, gate in enumerate(gates, start=1):
        gid = gate.get("id") or f"g{i}"
        prefill = {k: v for k, v in gate.items() if k != "id"}
        child = f"{wid}.{gid}"
        journal.append(wid, "step", id=gid, segment=seg["id"], dispatches="run-a-gate",
                       prefill=prefill, child=child, anchor=False, terminal=False,
                       source="mint")
        journal.append(wid, "step", id=f"{gid}-adjudicate", segment=seg["id"],
                       form=_GATE_ADJUDICATION_FORM, filler="conductor", child=child,
                       anchor=False, terminal=False, validates="", source="mint")


def _seed_board(template, dest, rows):
    """Write the board with every word of its guidance intact, seed rows below.

    The template's blank row is commented out rather than dropped: its inline
    notes are where the column-by-column doctrine lives (what `type` means,
    never self-answering a decision, how to carry options to a principal), and
    a board is worked over many turns by agents who may arrive fresh. The
    instructions belong at the artifact, not in a doc read once.
    """
    from engine import tomlw
    text = template.read_text().rstrip()
    head, sep, example = text.partition("[[question]]")
    quoted = "\n".join(
        line if line.startswith("#") else f"# {line}" if line.strip() else "#"
        for line in (sep + example).splitlines()
    )
    body = "".join(tomlw.table("question", {"id": f"q{i+1}", "status": "open", **r})
                   + "\n" for i, r in enumerate(rows))
    dest.write_text(f"{head.rstrip()}\n\n# --- the columns, and what they mean ---\n"
                    f"{quoted}\n\n# --- the board ---\n\n{body}")


def cmd_note(argv):
    wid, kind, text = argv[0], argv[1], " ".join(argv[2:])
    st = runmod.state(wid)
    if st is None:
        raise SystemExit(f"no run named {wid}")
    n = len([e for e in journal.read(wid) if e.get("kind") == "note"]) + 1
    journal.append(wid, "note", id=f"n{n}", kind_detail=kind, text=text,
                   step=(st["current"] or {}).get("id", ""))
    print(f"noted n{n} ({kind})")
    return 0


def cmd_amend(argv):
    wid, action = argv[0], argv[1]
    reason = _opt(argv, "--reason")
    if not reason:
        raise SystemExit(render.refusal("reason", "amend needs --reason"))
    st = runmod.state(wid)
    if st is None:
        raise SystemExit(f"no run named {wid}")
    if action == "add":
        return _amend_add(wid, st, argv[2:], reason)
    if action == "close":
        return _amend_close(wid, st, argv[2], reason)
    if action == "reorder":
        return _amend_reorder(wid, st, argv[2], reason, _opt(argv, "--before"))
    raise SystemExit(f"unknown amend action {action!r} -- add | close | reorder")


def _amend_add(wid, st, argv, reason):
    seg = _opt(argv, "--segment")
    if not seg:
        raise SystemExit(render.refusal("segment", "amend add needs --segment"))
    form_ref = _opt(argv, "--form")
    if not form_ref:
        raise SystemExit(render.refusal("form", "amend add needs --form"))
    asm = runmod.load_assembly(st["assembly"])
    if not any(s["id"] == seg for s in asm["segment"]):
        raise SystemExit(render.refusal("segment", f"no segment named {seg!r}"))
    n = len([s for s in st["steps"] if s["segment"] == seg]) + 1
    sid = f"{seg}-a{n}"
    # a dispatched run's own prefill (its orders) rides its amended steps too --
    # that is how a `check` field on the interior's own form (IMPLEMENT.toml's
    # `done`) finds the gate spec's command without a --prefill flag to type.
    journal.append(wid, "step", id=sid, segment=seg, form=form_ref, filler="conductor",
                   prefill=st.get("prefill"), anchor=False, terminal=False,
                   validates="", source="amend")
    journal.append(wid, "amend", action="add", segment=seg, step=sid, reason=reason,
                   anchor=False)
    print(f"amended: added {sid} to {seg}\n")
    return cmd_status([wid])


def _amend_close(wid, st, step_id, reason):
    step = next((s for s in st["steps"] if s["id"] == step_id), None)
    if step is None:
        raise SystemExit(render.refusal(step_id, "no such step"))
    if step_id in st["done"]:
        raise SystemExit(render.refusal(step_id, "already complete -- amend cannot drop done work"))
    journal.append(wid, "amend", action="close", segment=step["segment"], step=step_id,
                   reason=reason, anchor=step.get("anchor", False))
    print(f"amended: closed {step_id}\n")
    return cmd_status([wid])


def _amend_reorder(wid, st, step_id, reason, before):
    step = next((s for s in st["steps"] if s["id"] == step_id), None)
    if step is None:
        raise SystemExit(render.refusal(step_id, "no such step"))
    if not before:
        raise SystemExit(render.refusal("before", "amend reorder needs --before"))
    if step_id in st["done"]:
        raise SystemExit(render.refusal(step_id, "already complete -- amend cannot reorder done work"))
    journal.append(wid, "amend", action="reorder", segment=step["segment"], step=step_id,
                   before=before, reason=reason, anchor=step.get("anchor", False))
    print(f"amended: reordered {step_id} before {before}\n")
    return cmd_status([wid])


def _summary(st):
    """The mechanical record a `close` writes -- assembled from the journal,
    never typed: how many steps landed, how many were minted or amended into
    each segment beyond its first (the implement/review loop count), every
    check the engine ran, the tier this run was dispatched under, and one
    line per amend."""
    cycles = {}
    for s in st["steps"]:
        if s.get("source") in ("mint", "amend"):
            cycles[s["segment"]] = cycles.get(s["segment"], 0) + 1
    amends = [{"segment": a.get("segment", ""), "reason": a.get("reason", ""),
               "anchor": a.get("anchor", False)} for a in st.get("amends", [])]
    return {
        "steps_completed": len(st["done"]),
        "cycles": [{"segment": seg, "count": n} for seg, n in cycles.items()],
        "checks": list(st.get("checks", [])),
        "model": st.get("model", ""),
        "amends": amends,
    }


def cmd_close(argv):
    wid = argv[0]
    st = runmod.state(wid)
    if st is None:
        raise SystemExit(f"no run named {wid}")
    if st.get("closed"):
        raise SystemExit(f"{wid} is already closed")
    pending = [s["id"] for s in st["steps"] if s["id"] not in st["done"]]
    if pending:
        raise SystemExit(render.refusal(
            pending[0], "not complete -- submit it, open its child, or amend it away"))
    terminal = next((s for s in st["steps"] if s.get("terminal")), None)
    fields = st["done"][terminal["id"]].get("fields", {}) if terminal else {}
    summary = _summary(st)
    journal.append(wid, "closed", fields=fields, summary=summary)
    if st.get("parent") and st.get("parent_step"):
        journal.append(st["parent"], "return", step=st["parent_step"], child=wid,
                       fields=fields, summary=summary)
    print(f"closed {wid}\n")
    return cmd_status([wid])


def cmd_ledger():
    root = pathlib.Path(".agent-work")
    rows = []
    for j in sorted(root.glob("**/journal.toml")) if root.exists() else []:
        wid = str(j.parent.relative_to(root)).replace("/", ".")
        st = runmod.state(wid)
        if not st:
            continue
        i, n, seg = runmod.position(st, None)
        rows.append({"id": wid, "assembly": st.get("assembly", ""),
                     "where": f"{seg} ({i}/{n})" if st["open"] else "closed",
                     "title": st.get("title", "")})
    print(render.ledger(rows))
    return 0


def _opt(argv, name):
    return argv[argv.index(name) + 1] if name in argv else None


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    if not argv:
        return cmd_ledger()
    if argv[0] == "open":
        return cmd_open(argv[1:])
    if argv[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0
    verb = argv[1] if len(argv) > 1 else "status"
    return {"status": cmd_status, "submit": cmd_submit, "note": cmd_note,
            "amend": cmd_amend, "close": cmd_close}.get(verb, cmd_status)(
        [argv[0]] + argv[2:])


if __name__ == "__main__":
    sys.exit(main() or 0)
