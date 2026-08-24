"""`spine` -- the six verbs.

Argument shape is deliberately flat: the work id comes first and is always
required, because an id inferred from the environment is how a dispatched
crew ends up driving its dispatcher's run. A bare `spine` prints the ledger,
never your run.
"""

import os
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
spine open <assembly> --title T [--issue N]
spine                               every open run"""


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


def _current_form(st):
    asm = runmod.load_assembly(st["assembly"])
    step = st["current"]
    return asm, step, forms.load(runmod.resolve_form(asm, step["form"]))


def _response_path(st, step):
    name = pathlib.Path(step["form"]).stem + ".toml"
    return journal.location(st["id"]) / name


def cmd_open(argv):
    assembly = argv[0]
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


def cmd_status(argv):
    wid = argv[0]
    st = runmod.state(wid)
    if st is None:
        raise SystemExit(f"no run named {wid}")
    if not st["open"]:
        print(render.status(st, {}, "", position=runmod.position(st, None)))
        return 0
    asm, step, form = _current_form(st)
    dest = _response_path(st, step)
    if not dest.exists():
        forms.materialize(form, dest, work_id=wid, submit=f"spine {wid} submit")
    print(render.status(st, form, dest, prefill=step.get("prefill"),
                        blocked=runmod.blocks(st),
                        position=runmod.position(st, asm)))
    return 0


def cmd_submit(argv):
    wid = argv[0]
    st = runmod.state(wid)
    if st is None or not st["open"]:
        raise SystemExit(f"{wid} has no current step")
    asm, step, form = _current_form(st)
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
        cmd = _resolve_command((step.get("prefill") or {}).get(f["id"], ""))
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
        seg = next((s for s in asm["segment"] if s.get("interior") == "board"), None)
        if f.get("mints") == "board rows" and seg:
            path = journal.location(wid) / (pathlib.Path(seg["board"]).stem + ".toml")
            _seed_board(runmod.resolve_form(asm, seg["board"]), path, rows)
            journal.append(wid, "board", segment=seg["id"], path=str(path), rows=rows)


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
    return {"status": cmd_status, "submit": cmd_submit,
            "note": cmd_note}.get(verb, cmd_status)([argv[0]] + argv[2:])


if __name__ == "__main__":
    sys.exit(main() or 0)
