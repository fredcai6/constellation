"""`spine` -- the seven verbs.

Argument shape is deliberately flat: the work id comes first and is always
required, because an id inferred from the environment is how a dispatched
crew ends up driving its dispatcher's run. A bare `spine` prints the ledger,
never your run.
"""

import os
import pathlib
import re
import secrets
import subprocess
import sys
import tomllib

from engine import boards
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
spine open <assembly> --parent <id> --row <row-id>     open an excursion from
    a board row -- the row is the brief, its return lands under the row, and
    it completes no step. Assemblies: find-prior-art, build-a-prototype,
    draw-a-picture
spine                               every open run
spine <work-id> trace               this run and its children, as one timeline"""

CHECK_TIMEOUT = 600  # a check that never returns wedges the agent's turn


def _check_id(wid):
    """A work id names a directory under .agent-work; anything that could
    climb out of it is refused rather than sanitized, because a sanitized id
    no longer addresses the run the caller asked for."""
    parts = str(wid).split(".")
    if (not wid or "/" in wid or "\\" in wid or pathlib.Path(wid).is_absolute()
            or any(p in ("", "..") for p in parts)):
        raise SystemExit(render.refusal("work id", f"{wid!r} is not a usable name -- "
                                        "letters, digits, and dots between parts"))
    return wid


def mint_id(issue=None, kind="issue"):
    """A tracker number when there is one -- it is already collision-free and
    it associates the run to the issue for free. Otherwise random: two
    worktrees allocating in parallel cannot see each other's next number.
    The kind is the assembly's last word -- issue, gate, idea."""
    if issue:
        return f"issue{issue}"
    while True:
        wid = f"{kind}{secrets.token_hex(2)}"
        if not journal.exists(wid):
            return wid


def _palette():
    p = pathlib.Path("constellation.toml")
    return tomllib.load(open(p, "rb")) if p.exists() else {}


def _prose_words(path):
    """Words of prose in an artifact: fenced blocks, tables and indented code
    do not count.

    A plan that grows because its gates now carry their proofs inline has not
    accreted; a plan that grows because a settled alternative got re-argued
    has. Counting everything cannot tell those apart, and the count an agent
    is shown decides what it thinks it should cut."""
    try:
        text = pathlib.Path(path).read_text()
    except OSError:
        return 0
    out, fenced = [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced or line.startswith(("    ", "\t")) or line.lstrip().startswith("|"):
            continue
        out.append(line)
    return len(" ".join(out).split())


def _measure_artifacts(wid, step, form, fields):
    """Record each artifact field's prose length, so a later round can say how
    the artifact moved. Recorded, never enforced -- the engine has no opinion
    about the number and refuses nothing on it."""
    for f in form.get("fields", []):
        if f.get("kind") != "artifact" or not isinstance(fields.get(f["id"]), str):
            continue
        words = _prose_words(fields[f["id"]])
        if words:
            journal.append(wid, "measure", segment=step["segment"], step=step["id"],
                           field=f["id"], path=fields[f["id"]], words=words)

def _resolve_command(text):
    """`palette:test args` -> the host repo's test command plus args. A proof
    chaining several named jobs with `&&` (`palette:test && palette:lines`)
    resolves each side on its own, so the second name is looked up rather
    than handed to the shell as a literal command it does not have."""
    return " && ".join(_resolve_one(part.strip()) for part in text.split("&&"))


def _resolve_one(text):
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
    if runmod.panel_outstanding(st, step):
        return asm, step, None  # rendered as N commands; the outcome is mechanical
    return asm, step, forms.load(runmod.resolve_form(asm, step["form"]))


def _response_path(st, step):
    name = pathlib.Path(step["form"]).stem + ".toml"
    return journal.location(st["id"]) / name


def cmd_open(argv):
    if not argv or argv[0].startswith("--"):
        raise SystemExit("spine open <assembly> --title T [--issue N]\n  assemblies: "
                         + ", ".join(runmod.assemblies()))
    assembly = argv[0]
    parent = _opt(argv, "--parent")
    if parent:
        return _open_child(assembly, parent, _opt(argv, "--step"), _opt(argv, "--row"))
    title = _opt(argv, "--title") or ""
    issue = _opt(argv, "--issue")
    wid = _check_id(_opt(argv, "--id") or mint_id(issue=issue, kind=assembly.rsplit("-", 1)[-1]))
    if journal.exists(wid):
        raise SystemExit(render.located(f"{wid} already exists\n  where it stands: spine {wid}"))
    asm = runmod.load_assembly(assembly)
    journal.append(wid, "run", title=title, assembly=assembly,
                   conductor=asm.get("conductor", ""))
    for step in runmod.skeleton(asm):
        journal.append(wid, "step", **step)
    print(f"opened {wid}\n")
    return cmd_status([wid])


_PANEL_TAG = re.compile(r"^(.+)\.(p\d+)$")  # "<step-id>.pN" addresses one panelist


def _open_child(assembly, parent, pstep_id, row_id=""):
    """A child is dispatched, never composed: its id, its orders, and the
    tier it runs under all come from the parent's step. A panelist is the
    same mechanism one entry finer -- `<step-id>.pN` names which panel
    entry, and the tag rides the work id so several children can share one
    parent step without colliding. An excursion is the same mechanism from
    a board row: the row is its brief, and its return lands under the row
    rather than completing any step."""
    pst = runmod.state(parent)
    if pst is None:
        raise SystemExit(render.located(f"no run named {parent}\n  open runs: spine"))
    if row_id:
        return _open_excursion(assembly, parent, pst, row_id)
    m = _PANEL_TAG.match(pstep_id or "")
    step_id, tag = (m.group(1), m.group(2)) if m else (pstep_id, "")
    n = int(tag[1:]) if tag else 0
    pstep = next((s for s in pst["steps"] if s["id"] == step_id), None)
    if pstep is None or not (pstep.get("dispatches") or
                             (tag and pstep.get("panel") and 1 <= n <= len(pstep["panel"]))):
        raise SystemExit(render.refusal(
            pstep_id or "step", "not a dispatch step or a panelist",
            escape="steps here: " + ", ".join(s["id"] for s in pst["steps"])))
    wid = _check_id(pstep.get("child") or f"{parent}.{pstep_id}")
    if journal.exists(wid):
        raise SystemExit(render.located(f"{wid} already exists\n  where it stands: spine {wid}"))
    pasm = runmod.load_assembly(pst["assembly"])
    if tag:
        panelist = pstep["panel"][n - 1]
        assembly = "give-a-verdict"
        seg = next((s for s in pasm["segment"] if s["id"] == pstep["segment"]), {})
        tier = panelist.get("model") or seg.get("model", "")
        # the artifact under review is whatever the segment's most recent
        # non-panel step produced -- the latest implement, cycles included
        prior = [s for s in pst["steps"]
                if s["segment"] == pstep["segment"] and s["id"] != step_id]
        artifact = pst["done"].get(prior[-1]["id"], {}) if prior else {}
        # A panelist gets the artifact and its criteria. Fields marked
        # record-only stay behind: they are the producer's account of a
        # previous round, and a reviewer told what was wrong last time is
        # aimed at those spots and steered off everything else. A finding
        # that was not really fixed gets found again, which is the check
        # working rather than a gap in it. Which fields are record-only is
        # the producing step's form -- the artifact's own shape, not the
        # panel step's transition form.
        pform = (forms.load(runmod.resolve_form(pasm, prior[-1]["form"]))
                 if prior and prior[-1].get("form") else {})
        private = {f["id"] for f in pform.get("fields", []) if f.get("record-only")}
        prefill = {**(pst.get("prefill") or {}),
                   **{k: v for k, v in artifact.get("fields", {}).items()
                      if k not in private},
                   "criteria": panelist.get("criteria", "")}
        title = f"verdict: {step_id}"
    else:
        tier = _tier(pstep, pasm)
        prefill = pstep.get("prefill") or {}
        title = prefill.get("purpose", pstep_id)
    asm = runmod.load_assembly(assembly)
    journal.append(wid, "run", title=title, assembly=assembly,
                   conductor=asm.get("conductor", ""), parent=parent,
                   parent_step=step_id, model=tier)
    journal.append(wid, "prefill", fields=prefill)
    for step in runmod.skeleton(asm):
        # A panel names the form its panelist fills -- a critic reads a plan
        # with the critic's form, not the reviewer's. Without this the panel's
        # own `form` key is declared and unread.
        if tag and panelist.get("form"):
            step = {**step, "form": panelist["form"]}
        # A panelist's role is its own `worker` -- a critic is told it is a
        # critic by the room it stands in, not just by its brief. Without
        # this the dispatched child's step keeps give-a-verdict's literal
        # `reviewer` filler no matter which worker the panel entry names.
        if tag and panelist.get("worker"):
            step = {**step, "filler": panelist["worker"]}
        journal.append(wid, "step", **step)
    print(f"opened {wid} -- dispatched by {parent} at {pstep_id}\n")
    return cmd_status([wid])


# [excursion]
# Rationale: the row is the brief. Its string columns -- the idea or
#   question, the excursion's named question and budget -- are the child's
#   prefill, so nothing is typed twice and the board stays the record of
#   what was asked. The return is journaled with the row, never as the
#   step's: an excursion answers a row, and a row completes nothing.
# Rejected: the engine writing the return into the board. Two writers on one
#   file is the hazard a board avoids; the return renders, the agent folds.
def _open_excursion(assembly, parent, pst, row_id):
    seg_id, row = next(((sid, r) for sid, p in pst["boards"].items()
                        for r in boards.rows(p) if r.get("id") == row_id), ("", None))
    if row is None:
        raise SystemExit(render.refusal(row_id, "no board row by that id",
                                        escape=f"the board: spine {parent}"))
    wid = _check_id(f"{parent}.{row_id}")
    while journal.exists(wid):  # a second variant off the same row
        wid = _check_id(f"{parent}.{row_id}-a{secrets.token_hex(2)}")
    pasm = runmod.load_assembly(pst["assembly"])
    seg = next((s for s in pasm["segment"] if s["id"] == seg_id), {})
    prefill = {k: v for k, v in row.items()
               if k not in ("id", "status") and isinstance(v, str) and v.strip()}
    asm = runmod.load_assembly(assembly)
    journal.append(wid, "run", title=boards.label(row)[:72], assembly=assembly,
                   conductor=asm.get("conductor", ""), parent=parent,
                   parent_step=seg_id, row=row_id, model=seg.get("model", ""))
    journal.append(wid, "prefill", fields=prefill)
    for step in runmod.skeleton(asm):
        journal.append(wid, "step", **step)
    print(f"opened {wid} -- an excursion from {parent}, row {row_id}\n")
    return cmd_status([wid])


def _finishing(asm, form_override=""):
    """What finishing a dispatched assembly means: the form its terminal
    step fills -- the last thing the child does before `close` stamps its
    return back to the step that dispatched it.

    A panel entry may name its own form, and `_open_child` honours it, so a
    brief that quoted the assembly's default would name a file the agent
    will not be given -- the brief lying about the step it just opened.
    """
    if form_override:
        return form_override
    seg = next((s for s in asm["segment"] if s.get("transition", {}).get("terminal")), None)
    return (seg.get("transition", {}).get("form", "")) if seg else ""


def _dispatch_status(wid, st, asm, step, blocked):
    """A dispatch step renders a brief, not a form: the engine launches
    nothing, so making the one right invocation is the whole job. The brief
    is what a conductor copies into whatever harness it dispatches."""
    dispatched = runmod.load_assembly(step["dispatches"])
    tier = _tier(step, asm)
    child_id = step.get("child") or f"{wid}.{step['id']}"
    open_cmd = f"spine open {step['dispatches']} --parent {wid} --step {step['id']}"
    lines = render.preamble(st, blocked, runmod.position(st, asm))
    lines.append(render.imperative(render.DISPATCH))
    lines.append("")
    lines.append(render.brief(child_id, dispatched.get("conductor", ""), tier,
                              _runner(tier), open_cmd, _finishing(dispatched)))
    lines.append("")
    lines.append(render.legal_moves(wid))
    return "\n".join(lines)


def _panel_status(wid, st, asm, step, blocked):
    """A panel step renders one brief per panelist -- copied, never
    composed -- with who has returned and who is still outstanding. A
    panelist's role is its own `worker`, not the give-a-verdict assembly's
    conductor: `_open_child` stamps that worker onto the dispatched child's
    step as its `filler`, so the panel entry is the source of truth, not
    just the brief that names it."""
    seg = next((s for s in asm["segment"] if s["id"] == step["segment"]), {})
    verdict_asm = runmod.load_assembly("give-a-verdict")
    returned = {r["child"].rsplit(".", 1)[-1] for r in st["returns"].get(step["id"], [])}
    lines = render.preamble(st, blocked, runmod.position(st, asm))
    lines.append(render.imperative(render.PANEL))
    lines.append("")
    for i, panelist in enumerate(step["panel"], start=1):
        tag = f"p{i}"
        tier = panelist.get("model") or seg.get("model", "")
        finishing = _finishing(verdict_asm, panelist.get("form", ""))
        outstanding = tag not in returned
        lines.append(f"  panelist {tag} ({'returned' if not outstanding else 'outstanding'})"
                     f" -- criteria: {panelist.get('criteria', '')}")
        if outstanding:
            child_id = f"{wid}.{step['id']}.{tag}"
            open_cmd = f"spine open give-a-verdict --parent {wid} --step {step['id']}.{tag}"
            lines.append(render.brief(child_id, panelist.get("worker", ""), tier,
                                      _runner(tier), open_cmd, finishing))
        lines.append("")
    lines.append(render.legal_moves(wid))
    return "\n".join(lines)


def _onward(st):
    """Where this run's returns land -- read off its own opening entry, which
    has held the answer since `open` wrote it.

    A parent whose journal is gone gets nothing: `close` already says the
    return was not delivered, and offering a command that fails on top of
    that is worse than offering none.
    """
    parent, pstep = st.get("parent"), st.get("parent_step")
    return (parent, pstep) if parent and pstep and journal.exists(parent) else None


def _board_state(path):
    """Everything `render._board` needs, computed once here rather than in
    the render layer -- `render.py` formats what it is given, it does not go
    read a board itself."""
    if not path:
        return None
    found = boards.rows(path)
    return {"path": path, "prose": boards.prose(path), "summary": boards.summary(path),
            "tree": [(d, r.get("id", ""), str(r.get("status", "")), boards.label(r))
                     for d, r in boards.tree(found)],
            "askable": [(r.get("id", ""), boards.label(r)) for r in boards.askable(found)],
            "held": [(r.get("id", ""), "held by " + ", ".join(ids))
                     for r, ids in boards.held(found)],
            "clusters": boards.clusters(found)}


# [returned-verdict]
# Rationale: a panel that ruled anything but pass is the reason the room the
#   reader is standing in exists -- the outlet an escalate minted, the fresh
#   round a revise minted, the close an escalated gate walked to. The verdict
#   itself was engine-side only: findings arrived as prefill and the word the
#   panel merged on never did, so the reader had to infer it.
# Rejected: naming every returned panel, pass included. A pass is the room
#   arriving normally; saying so is noise on every step after it.
def _returned_verdict(st):
    """The most recently returned panel's merged verdict, when it is not
    `pass`. Read from the last panel step that has a full house of returns,
    so a re-fired panel still waiting on its own critics reports the round
    that actually ruled, not silence."""
    for s in reversed(st["steps"]):
        rs = st["returns"].get(s["id"]) or []
        if s.get("panel") and rs and not runmod.panel_outstanding(st, s):
            verdict = runmod.merged_verdict(rs)
            return "" if verdict == "pass" else verdict
    return ""


def cmd_status(argv):
    wid = argv[0]
    st = runmod.state(wid)
    if st is None:
        raise SystemExit(render.located(f"no run named {wid}\n  open runs: spine"))
    if not st["open"] or st["awaiting_close"]:
        print(render.status(st, {}, "", position=runmod.position(st, None),
                            onward_to=_onward(st)))
        return 0
    asm, step, form = _current_form(st)
    if step.get("dispatches"):
        print(_dispatch_status(wid, st, asm, step, runmod.blocks(st)))
        return 0
    if runmod.panel_outstanding(st, step):
        print(_panel_status(wid, st, asm, step, runmod.blocks(st)))
        return 0
    dest = _response_path(st, step)
    if not dest.exists():
        forms.materialize(form, dest, work_id=wid,
                          submit=render.located(f"spine {wid} submit"))
    ret = st["returns_by_child"].get(step.get("child", "")) if step.get("child") else None
    returns = {**ret.get("summary", {}), **ret.get("fields", {})} if ret else None
    if returns:
        # Every structured value the summary can carry, spelled out rather
        # than left as a raw list -- str() on a list prints Python reprs, not
        # something a conductor can act on. A field's own form answer (e.g.
        # CLOSE.toml's `triage`) is a string that already overrode the
        # summary's list by the time it lands here, so only a survivor gets
        # rendered; the isinstance check is what tells the two apart.
        for key, fn in (("checks", render.checks), ("cycles", render.cycles),
                        ("amends", render.amends), ("triage", render.triage)):
            if isinstance(returns.get(key), list):
                returns[key] = "; ".join(fn(returns[key])) or "none"
    # Rendered whenever the segment has a board; `validates` decides only
    # whether submit refuses on it. The ideas board is read at every cycle
    # and refused at none.
    board = _board_state(st["boards"].get(step["segment"]))
    prefill = {**(st.get("prefill") or {}), **(step.get("prefill") or {})}
    print(render.status(st, form, dest, prefill=prefill,
                        returns=returns, returns_from=step.get("child", ""),
                        verdict=_returned_verdict(st),
                        blocked=runmod.blocks(st),
                        position=runmod.position(st, asm), board=board,
                        in_hand=forms.in_hand(dest) if dest.exists() else None,
                        triage_notes=[n for n in st["notes"] if n.get("kind_detail") == "triage"],
                        role=runmod.hat(asm, step, st), row_returns=st["row_returns"]))
    return 0


def cmd_submit(argv):
    wid = argv[0]
    st = runmod.state(wid)
    if st is None or not st["open"] or st["awaiting_close"]:
        raise SystemExit(render.located(
            f"{wid} has no current step"
            + (f" -- close it: spine {wid} close" if st and st["awaiting_close"] else "")))
    asm, step, form = _current_form(st)
    if step.get("dispatches"):
        raise SystemExit(render.refusal(
            step["id"],
            f"a dispatch step is not submitted -- open its child: "
            f"spine open {step['dispatches']} --parent {wid} --step {step['id']}"))
    if runmod.panel_outstanding(st, step):
        raise SystemExit(render.refusal(
            step["id"], "a panel step is not submitted -- the panelists' verdicts "
            "complete it", escape=f"who is outstanding: spine {wid}"))
    dest = _response_path(st, step)
    if not dest.exists():
        raise SystemExit(render.located(f"no response form yet — run: spine {wid}"))
    filled = forms.parse(dest)

    if step.get("validates") == "board":
        board = st["boards"].get(step["segment"], "")
        problems = boards.validate(board) if board else []
        if problems:
            raise SystemExit(render.refusal(pathlib.Path(board).name,
                                            "\n  ".join(problems), escape=""))

    checks, fields = {}, {}
    for f in form["fields"]:
        fid, kind = f["id"], f.get("kind", "evidence")
        if kind == "check":
            continue  # the engine runs these; they are never on the template
        # The escape both refusals below offer is the field's own: a decision
        # field refuses the nulls, so it is offered the values its note lists.
        vocab = forms.enforced_vocabulary(f)
        if fid not in filled:
            if f.get("optional"):
                continue
            raise SystemExit(render.refusal(fid, "no answer",
                                            escape=render.escape_for(vocab)))
        # A field the agent marked as still in hand. Submitting it would
        # record work-in-progress as an answer, and the next reader could not
        # tell the difference -- so say what is still open and let the agent
        # finish it, or close it honestly with one of the values it does take.
        if str(filled[fid]).strip().startswith("working:"):
            raise SystemExit(render.refusal(
                fid, str(filled[fid]).strip(),
                escape=render.escape_for(vocab, verb="finish")))
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
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                               timeout=CHECK_TIMEOUT)
        except subprocess.TimeoutExpired:
            journal.append(wid, "check", step=step["id"], command=cmd,
                           exit=-1, output=f"no result after {CHECK_TIMEOUT}s")
            raise SystemExit(render.refusal(
                f["id"], f"`{cmd}` did not finish in {CHECK_TIMEOUT}s -- fix the "
                f"command, or drop this step: spine {wid} amend close {step['id']} "
                "--reason ..."))
        checks[f["id"]] = {"command": cmd, "exit": r.returncode,
                           "output": (r.stdout + r.stderr)[-4000:]}
        if r.returncode != 0:
            journal.append(wid, "check", step=step["id"], **checks[f["id"]])
            raise SystemExit(render.located(
                f"{f['id']}: `{cmd}` exited {r.returncode}\n"
                f"  a check is run by the engine, not filled in -- make it pass,\n"
                f"  or drop this step: spine {wid} amend close {step['id']} --reason ..."))

    _check_plan(asm, form, fields)
    _check_vocabulary(asm, step, form, fields)
    outcome = _outcome(asm, step, fields, st)
    journal.append(wid, "submit", step=step["id"], fields=fields,
                   checks=list(checks.values()) or None)
    _measure_artifacts(wid, step, form, fields)

    # A transition marked `carries` folds its fields into the run's own
    # prefill, so everything dispatched afterwards gets them. Consolidate is
    # the case this exists for: a panelist's prefill is built from prior steps
    # in its own segment, so without this the run's understanding never crosses
    # a segment boundary and the coldest reader in the run -- the one the
    # understanding was written for -- is the only one who never sees it.
    if step.get("carries"):
        journal.append(wid, "prefill",
                       fields={**(st.get("prefill") or {}), **fields})
    _mint(wid, asm, step, form, fields)
    if outcome:
        _perform(wid, asm, *outcome, fields, step)
    print(f"submitted {step['id']}\n")
    return cmd_status([wid])


def _check_plan(asm, form, fields):
    """A plan field must be a list of blocks, and what it says it mints must be
    something `_mint` performs. Both checked before anything is journaled: a
    submit is durable the moment it lands, so minting that dies -- or that
    silently finds no branch -- afterwards would leave a run that looks
    advanced and has no work in it."""
    for f in form["fields"]:
        if f.get("kind") != "plan" or f["id"] not in fields:
            continue
        rows = fields[f["id"]]
        if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
            raise SystemExit(render.refusal(
                f["id"], "must be one or more [[" + f["id"] + "]] blocks, not a "
                "single value -- nothing was recorded"))
        mintable = _mintable(asm)
        if f.get("mints") and f["mints"] not in mintable:
            raise SystemExit(render.refusal(
                f["id"], f"mints = {f['mints']!r} is nothing this engine mints -- "
                "the form is wrong, not your answer; nothing was recorded",
                escape="one of: " + ", ".join(sorted(mintable))))


# [check-vocabulary]
# Rationale: a `decision` field -- one whose value the engine acts on -- is
#   checked against the alternatives its own note declares, read off by
#   `forms.enforced_vocabulary` -- so the enum the agent is told and the enum
#   the engine enforces are one string and cannot drift, and the refusal can
#   name the list the agent already read. The kind is what makes the note
#   load-bearing: punctuation alone would enum an ordinary prose note.
# Rejected: a table of field ids and their legal values kept here. It is the
#   same list written twice, and the copy that matters is the one in the form:
#   the engine would go on enforcing the old list against a reworded note.
def _decided_here(asm, step):
    """The field this step's assembly already declares outcomes for, if any.

    `_outcome` refuses an undeclared value on that field, and refuses it
    better: the assembly pairs each value with what it *does*, so the values
    and the acts are declared together and the engine names neither. This
    check stands down there rather than running first and refusing on
    stricter terms -- one field, one enforcer.
    """
    seg = next((s for s in asm["segment"] if s["id"] == step.get("segment")), {})
    t = seg.get("transition", {})
    spec = t if step.get("form") == t.get("form") else seg
    return spec.get("decides")


def _check_vocabulary(asm, step, form, fields):
    """A value the engine cannot act on refuses instead of releasing the step.

    Checked before anything is journaled, because past that point the submit
    is durable and an unhandled value walks the run forward having performed
    nothing -- the silent advance this check exists to end. Matching is exact:
    the acts downstream compare whole strings, so `advance, I think` is a value
    nothing performs. A placeholder alternative (`name <x>`) matches on its
    literal prefix alone, so a value naming a runtime argument is still a
    known move; once a field declares `decides`, this check stands down for
    it and `_outcome` owns the argument itself.
    """
    decided = _decided_here(asm, step)
    for f in form["fields"]:
        vocab = forms.enforced_vocabulary(f)
        if not vocab or f["id"] not in fields or f["id"] == decided:
            continue
        value = str(fields[f["id"]]).strip()
        word = forms.leading_word(value)
        if word not in [alt.split("<")[0].strip().lower() for alt in vocab]:
            raise SystemExit(render.refusal(
                f["id"], f"{word or 'empty'!r} is not a value this step can act on",
                escape="one of: " + " | ".join(vocab)))


def _mint_transition(wid, seg, prefill=None):
    """One fresh transition step for a segment: a board segment's refill,
    and the impasse's advance. A transition with a form is a step someone
    fills, so this mints it; one without -- run-a-gate's review -- has
    nothing to mint, and the run walks on."""
    t = seg.get("transition", {})
    if t.get("form"):
        journal.append(wid, "step", id=f"{seg['id']}-a{secrets.token_hex(2)}",
                       segment=seg["id"], form=t["form"], filler=t.get("filler", "conductor"),
                       prefill=prefill or {}, anchor=t.get("anchor", False),
                       terminal=t.get("terminal", False), validates=t.get("validates", ""),
                       source="mint")


# [declared-outcomes]
# Rationale: a transition releases, refills, or goes elsewhere, and which
#   word does which is the assembly's to say: `decides` names the field,
#   `[[outcome]]` rows pair a `value` with what it `does` -- release; refill
#   [<segment>]; skip <segment>; transition [<segment>]; rework [<segment>];
#   remint <field>; close; several joined by ";". The engine matches the field's
#   first word, refuses one nothing declares naming those it can act on, and
#   performs the verbs. No assembly's words appear here. `transition` and
#   `rework` are the impasse's two moves, absorbed alongside the rest (#32)
#   -- an offered `ruling` is now a `decides` field like any other, and
#   `remint`/`close` are gate adjudication's, absorbed the same way.
# See: #32 -- gate adjudication still carries its own interpreter.
def _outcome(asm, step, fields, st):
    """(segment, does) for the outcome this submit selects; None when the
    step declares none or the field is nulled. Checked before the submit
    lands, so a value the engine cannot act on -- or a runtime argument that
    does not resolve -- never advances the run.

    A declared value may carry a placeholder (`name <x>`): matched on the
    word before the `<`, the same rule `_check_vocabulary` already used for
    it. Where a value does carry one, the rest of the field's own text is
    the argument, and its legal values are this step's own segment's
    not-done, non-terminal steps that do not share this step's `child` --
    the deciding step can never name its own pair, closing one step of a
    pair takes the other with it (a pair is exactly the steps sharing a
    `child`), and the segment's own terminal step is never a target (it has
    no `child` of its own, and is what closing the run means, not something
    a decision inside it drops). Neither idea is this field's; both are
    `_mint_gates`' own data, read structurally rather than declared or
    hardcoded.
    """
    seg = next((s for s in asm["segment"] if s["id"] == step.get("segment")), {})
    t = seg.get("transition", {})
    spec = t if step.get("form") == t.get("form") else seg
    field = spec.get("decides")
    if not field or field not in fields:
        return None
    raw = fields[field]
    value = forms.leading_word(raw)
    if value.startswith(("waived", "unknown")):
        return None
    outcomes = spec.get("outcome", [])
    legal = {o["value"].split("<")[0].strip().lower(): o for o in outcomes}
    if value not in legal:
        raise SystemExit(render.refusal(
            field, f"{value or 'empty'!r} is not an outcome this step declares",
            escape="one of: " + " | ".join(o["value"] for o in outcomes)))
    chosen = legal[value]
    declared = chosen["value"]
    if "<" in declared:
        parts = str(raw).split(None, 1)
        target = parts[1].strip() if len(parts) > 1 else ""
        pending = [s["id"] for s in st["steps"] if s["segment"] == step["segment"]
                  and s["id"] not in st["done"] and not s.get("terminal")
                  and s.get("child") != step.get("child")]
        if not target:
            raise SystemExit(render.refusal(
                field, f"{value} needs a gate id -- {declared}",
                escape="pending: " + (", ".join(pending) or "none")))
        if target not in pending:
            raise SystemExit(render.refusal(
                field, f"{target!r} is not a pending gate",
                escape="pending: " + (", ".join(pending) or "none")))
    does = chosen.get("does", "release")
    for verb in filter(None, (v.strip() for v in does.split(";"))):
        word, _, argfield = verb.partition(" ")
        if word == "remint" and not fields.get(argfield):
            raise SystemExit(render.refusal(
                argfield, "remint needs a new gate spec -- a remint with no "
                "spec is a drop wearing the wrong name"))
    return seg, does


# [impasse-verbs]
# Rationale: `advance` and `rework` used to be handled by a stand-alone
#   impasse actor, a reader outside the outcome mechanism. Absorbing the
#   ruling as an ordinary `decides` field meant `_perform` needed two verbs
#   nothing else spells:
#   `transition` mints the segment's own transition alone (what `advance`
#   does, over a live revise -- the panel's findings stay the record that
#   says so), and `rework` refills through the segment's rework-form -- or
#   its step-form where none is declared, run-a-gate's work -- carrying
#   forward the deciding step's own prefill (what caused the impasse) rather
#   than the ruling fields just submitted (the verdict on it). `up` needs
#   neither: `release`, the field's own default, mints nothing, and the run
#   walks to its terminal step. Gate adjudication added two more the same
#   way: `remint` mints a fresh dispatch/adjudication pair from the plan
#   field the deciding step's own form carries, and `close` closes the
#   not-done step this step's segment holds whose id matches the decided
#   field's own argument, and every step paired with it by `child`.
# Rejected: naming the verbs `advance`/`rework` to match the outcome values.
#   Verbs and values are already separate vocabularies elsewhere (`cycle`'s
#   value is `cycle`, its verb is `refill`); reusing the impasse's words here
#   would read that coincidence as a rule.
# See: #32 -- gate adjudication still carries its own interpreter.
def _perform(wid, asm, seg, does, fields, step):
    """The outcome's verbs, in order, against freshly folded state -- the
    deciding submit is already journaled, so `skip` and `close` never touch
    it. An amend's reason is the agent's own words -- the decided field's
    raw submitted text -- not the assembly's `does` string, which is a
    mechanism label no principal reading the amend log asked for.

    `skip` never closes a terminal step: `execute`'s own terminal step sits
    not-done for the whole time its gates run, exactly like every other step
    `skip` sweeps, so without this a replan mid-run would amend-close the run's
    own close step along with the gates it means to drop -- a run the amend
    log says is done and CLOSE.toml never filled. No existing `skip` target
    reaches a terminal step, so this narrows nothing already relied on."""
    field = _decided_here(asm, step)
    reason = str(fields.get(field, does)).strip() if field else does
    for verb in filter(None, (v.strip() for v in does.split(";"))):
        word, _, target = verb.partition(" ")
        tseg = next((s for s in asm["segment"] if s["id"] == (target or seg["id"])), seg)
        if word == "skip":
            st = runmod.state(wid)
            for s in st["steps"]:
                if (s["segment"] == tseg["id"] and s["id"] not in st["done"]
                        and not s.get("terminal")):
                    journal.append(wid, "amend", action="close", segment=tseg["id"],
                                   step=s["id"], reason=reason, anchor=s.get("anchor", False))
        elif word == "refill" and tseg.get("interior") == "board":
            _mint_transition(wid, tseg, prefill=fields)
        elif word == "refill":
            _mint_segment_round(wid, asm, tseg["id"], prefill=fields)
        elif word == "transition":
            _mint_transition(wid, tseg)
        elif word == "rework":
            _mint_segment_round(wid, asm, tseg["id"], prefill=step.get("prefill") or {},
                                form=tseg.get("rework-form", ""))
        elif word == "remint":
            _mint_gates(wid, seg, fields.get(target) or [])
        elif word == "close":
            parts = str(fields.get(field, "")).split(None, 1)
            target_id = parts[1].strip() if len(parts) > 1 else ""
            st = runmod.state(wid)
            hit = next((s for s in st["steps"] if s["id"] == target_id), None)
            if hit:
                for s in st["steps"]:
                    if s.get("child") == hit.get("child") and s["id"] not in st["done"]:
                        journal.append(wid, "amend", action="close", segment=s["segment"],
                                       step=s["id"], reason=reason,
                                       anchor=s.get("anchor", False))


# [mints]
# Rationale: "board rows" is the one mint value the engine itself names --
#   a board is engine vocabulary, no assembly declares one. Every other
#   value is an assembly name, legal exactly when some segment in this tree
#   dispatches it, so the set `_check_plan` refuses against is derived from
#   the assembly rather than kept as a second list beside the branches. A
#   third *kind* of mint still needs a branch added here -- that part a
#   tuple never bought.
_BOARD_MINT = "board rows"


def _mintable(asm):
    """The `mints` values legal in this assembly: `_BOARD_MINT`, plus every
    name a segment here declares as `dispatches`."""
    return {_BOARD_MINT} | {s["dispatches"] for s in asm["segment"] if s.get("dispatches")}


def _mint(wid, asm, step, form, fields):
    """A `plan` field's content becomes structure: board rows, or steps."""
    for f in form["fields"]:
        if f.get("kind") != "plan" or f["id"] not in fields:
            continue
        rows = fields[f["id"]]
        mints = f.get("mints")
        if mints == _BOARD_MINT:
            seg = next((s for s in asm["segment"] if s.get("interior") == "board"), None)
            if seg:
                path = journal.location(wid) / (pathlib.Path(seg["board"]).stem + ".toml")
                _seed_board(runmod.resolve_form(asm, seg["board"]), path, rows)
                journal.append(wid, "board", segment=seg["id"], path=str(path), rows=rows)
        elif mints:
            seg = next((s for s in asm["segment"] if s.get("dispatches") == mints), None)
            if seg:
                _mint_gates(wid, seg, rows)


def _mint_gates(wid, seg, gates):
    """Each gate block becomes a dispatch step and, right after it, the
    adjudication step that will hold its returns -- the pair the execute
    segment's worklist is made of. The adjudication form is the dispatching
    segment's own declared `adjudication-form`, read the way `step-form` and
    `rework-form` already are -- not an engine constant, so which form a
    gate is adjudicated against is the assembly's to say.

    Ids are journal-aware: numbering by position was safe only while closing
    a gate freed its id. A remint no longer closes, so a derived id still
    live in the journal (its gate ran and stands) collides -- `done` is
    keyed by step id, and a duplicate would silently complete both."""
    existing = {s["id"] for s in runmod.state(wid)["steps"]}
    for i, gate in enumerate(gates, start=1):
        gid = _unique_id(gate.get("id") or f"g{i}", existing)
        existing.add(gid)
        existing.add(f"{gid}-adjudicate")
        prefill = {k: v for k, v in gate.items() if k != "id"}
        child = f"{wid}.{gid}"
        journal.append(wid, "step", id=gid, segment=seg["id"], dispatches=seg["dispatches"],
                       prefill=prefill, child=child, anchor=False, terminal=False,
                       source="mint")
        journal.append(wid, "step", id=f"{gid}-adjudicate", segment=seg["id"],
                       form=seg["adjudication-form"], filler="conductor", child=child,
                       anchor=False, terminal=False, validates="", source="mint")


def _unique_id(base, existing):
    """`base` if it is free, else `base` with a random distinguishing suffix
    -- readable in the common case, and a collision (which would silently
    complete every step sharing the id) becomes structurally impossible
    rather than merely unlikely. Random, not counted, matching `amend add`
    and the verdict refill: a counted suffix only needs to be right once,
    read at the moment of the check, and a check-then-suffix window is
    exactly the race that produces the duplicate this guards against."""
    if base not in existing:
        return base
    while True:
        candidate = f"{base}-a{secrets.token_hex(2)}"
        if candidate not in existing:
            return candidate


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
    table = re.search(r"^\[\[(\w+)\]\]", text, re.M)
    head, sep, example = text.partition(table.group(0))
    quoted = "\n".join(
        line if line.startswith("#") else f"# {line}" if line.strip() else "#"
        for line in (sep + example).splitlines()
    )
    # The template's blank row is the convention: what the rows are called,
    # how an id is spelled, which status a fresh row starts in.
    blank = tomllib.loads(sep + example)[table.group(1)][0]
    prefix = re.match(r"[a-z]*", str(blank.get("id", ""))).group(0) or "r"
    body = ""
    for i, r in enumerate(rows):
        row = {"id": f"{prefix}{i+1}", "status": blank.get("status", "open"), **r}
        body += tomlw.table(table.group(1), row) + "\n"
    dest.write_text(f"{head.rstrip()}\n\n# --- the columns, and what they mean ---\n"
                    f"{quoted}\n\n# --- the board ---\n\n{body}")


NOTE_KINDS = ("blocked", "resumed", "observation", "decision", "triage")


def cmd_note(argv):
    if len(argv) < 2:
        raise SystemExit(f"spine <work-id> note <{'|'.join(NOTE_KINDS)}> <text>")
    wid, kind, text = argv[0], argv[1], " ".join(argv[2:])
    if kind not in NOTE_KINDS:
        # `note block ...` used to print success and do nothing at all: only
        # the exact word is acted on, so a near-miss must not look like a hit.
        raise SystemExit(f"no note kind {kind!r} -- one of: {', '.join(NOTE_KINDS)}")
    st = runmod.state(wid)
    if st is None:
        raise SystemExit(render.located(f"no run named {wid}\n  open runs: spine"))
    # `note resumed n1` names the block it clears; the rest of the words are
    # the note. Counting existing notes to pick an id collides when two
    # sessions note at once, and a shared id would clear the wrong block.
    about = argv[2] if kind == "resumed" and len(argv) > 2 else ""
    if about:
        text = " ".join(argv[3:])
    journal.append(wid, "note", id=f"n{secrets.token_hex(2)}", kind_detail=kind,
                   text=text, about=about,
                   step=(st["current"] or {}).get("id", ""))
    print(f"noted {kind}" + (f" — cleared {about}" if about else ""))
    return 0


def cmd_amend(argv):
    if len(argv) < 2:
        raise SystemExit("spine <work-id> amend add|close|reorder ... --reason \"...\"")
    wid, action = argv[0], argv[1]
    reason = _opt(argv, "--reason")
    if not reason:
        raise SystemExit(render.refusal("reason", "amend needs --reason"))
    st = runmod.state(wid)
    if st is None:
        raise SystemExit(render.located(f"no run named {wid}\n  open runs: spine"))
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
    if not form_ref and "--transition" not in argv:
        raise SystemExit(render.refusal("form", "amend add needs --form, or --transition"))
    asm = runmod.load_assembly(st["assembly"])
    if not any(s["id"] == seg for s in asm["segment"]):
        raise SystemExit(render.refusal(
            "segment", f"no segment named {seg!r}",
            escape="segments: " + ", ".join(s["id"] for s in asm["segment"])))
    if "--transition" in argv:
        # The segment's transition as the assembly declares it today -- form
        # and panel both. A run stops depending on its template at open, so
        # this is how a live run catches up with a template that grew a
        # panelist: one journaled amend, loud if the step it replaces was
        # anchored.
        t = next(x for x in asm["segment"] if x["id"] == seg).get("transition", {})
        sid = f"{seg}-a{secrets.token_hex(2)}"
        step = {"id": sid, "segment": seg, "filler": t.get("filler", "conductor"),
                "anchor": t.get("anchor", False), "terminal": t.get("terminal", False),
                "validates": t.get("validates", ""), "source": "amend"}
        if t.get("form"):
            step["form"] = t["form"]
        if t.get("panel"):
            step["panel"] = t["panel"]
        journal.append(wid, "step", **step)
        journal.append(wid, "amend", action="add", segment=seg, step=sid, reason=reason,
                       anchor=step["anchor"])
        print(f"amended: added {sid} to {seg}\n")
        return cmd_status([wid])
    # Random, not counted: two sessions amending at once both compute the same
    # next number, and duplicate ids are worse than ugly -- `done` is keyed by
    # step id, so one submit would silently complete every step sharing it.
    sid = f"{seg}-a{secrets.token_hex(2)}"
    # a dispatched run's own prefill (its orders) rides its amended steps too --
    # that is how a `check` field on the interior's own form (IMPLEMENT.toml's
    # `proof`) finds the gate spec's command without a --prefill flag to type.
    journal.append(wid, "step", id=sid, segment=seg, form=form_ref, filler="conductor",
                   prefill=st.get("prefill"), anchor=False, terminal=False,
                   validates="", source="amend")
    journal.append(wid, "amend", action="add", segment=seg, step=sid, reason=reason,
                   anchor=False)
    print(f"amended: added {sid} to {seg}\n")
    return cmd_status([wid])


def _pending(st):
    """The steps an amend can still touch -- named at every refusal, because
    the ids are right here and making the agent go look them up is the whole
    thing this engine exists not to do."""
    return "pending: " + (", ".join(
        s["id"] for s in st["steps"] if s["id"] not in st["done"]) or "none")


def _amend_close(wid, st, step_id, reason):
    step = next((s for s in st["steps"] if s["id"] == step_id), None)
    if step is None:
        raise SystemExit(render.refusal(step_id, "no such step", _pending(st)))
    if step_id in st["done"]:
        raise SystemExit(render.refusal(
            step_id, "already complete -- history is not amendable", _pending(st)))
    journal.append(wid, "amend", action="close", segment=step["segment"], step=step_id,
                   reason=reason, anchor=step.get("anchor", False))
    print(f"amended: closed {step_id}\n")
    return cmd_status([wid])


def _amend_reorder(wid, st, step_id, reason, before):
    step = next((s for s in st["steps"] if s["id"] == step_id), None)
    if step is None:
        raise SystemExit(render.refusal(step_id, "no such step", _pending(st)))
    if not before:
        raise SystemExit(render.refusal("before", "amend reorder needs --before"))
    if step_id in st["done"]:
        raise SystemExit(render.refusal(
            step_id, "already complete -- history is not amendable", _pending(st)))
    journal.append(wid, "amend", action="reorder", segment=step["segment"], step=step_id,
                   before=before, reason=reason, anchor=step.get("anchor", False))
    print(f"amended: reordered {step_id} before {before}\n")
    return cmd_status([wid])


def _mint_segment_round(wid, asm, seg_id, prefill=None, form=""):
    """Mint one fresh round of a segment: its step-form (or the form the
    caller names -- a revise passes the segment's rework form) as a fresh
    interior step, plus its transition's panel -- both read from the
    assembly, never copied from whatever minted last. The shared move a
    revise and a replan both need: the segment reopened for another pass,
    carrying the same challenge that judges it.

    Two independent random tags, not one shared: a transition's id defaults
    to its segment's id (run-an-issue's "plan" names both), and
    `f"{seg_id}-a{tag}"` would then equal `f"{step_id}-a{tag}"` for the same
    tag -- one mint silently overwriting the other in the journal.
    """
    seg = next(s for s in asm["segment"] if s["id"] == seg_id)
    t = seg.get("transition", {})
    journal.append(wid, "step", id=f"{seg_id}-a{secrets.token_hex(2)}", segment=seg_id,
                   form=form or seg["step-form"], filler=seg.get("worker", "conductor"),
                   prefill=prefill or {}, anchor=False, terminal=False, validates="",
                   source="mint")
    fresh_panel = {"id": f"{seg_id}-a{secrets.token_hex(2)}", "segment": seg_id,
                   "panel": t["panel"], "anchor": False, "terminal": False,
                   "source": "panel"}
    if t.get("form"):
        fresh_panel["form"] = t["form"]  # the two-voices shape survives a fresh round
    journal.append(wid, "step", **fresh_panel)


# [act-on-verdicts]
# Rationale: a two-voices step is the one place an escalate has nothing left
#   to release into. `run.py` marks it done on any verdict but pass -- right,
#   since an escalated plan should not fill its transition form -- so acting
#   only on `revise` here left the objection unanswered and walked the run to
#   its terminal step. Escalate mints the segment's outlet instead: its three
#   rulings are exactly the three moves a conductor has against a panel that
#   objected at the root -- advance over it, rework the artifact, or go up.
# Rejected: gating that on "the segment declares an outlet". Both assemblies
#   declare one, so it would fire for a panel-only review's escalate too --
#   and that one already releases correctly, the verdict riding the summary
#   up to whoever adjudicates next.
# See: assemblies/run-an-issue/forms/IMPASSE.toml
def _act_on_verdicts(pwid, step_id):
    """Once every panelist named by `step_id` has returned, the transition
    acts on the merged verdict. Pass releases: for a panel-only step there is
    nothing more to mint, the verdict itself rides the summary up to whoever
    adjudicates next; for a two-voices step, `state()` has already left it
    open instead, so this is a no-op and the form is what releases it.
    Revise refills the interior with a fresh round of the segment (see
    `_mint_segment_round`) -- findings concatenated, never summarised, and
    attributed to the panelist that raised them. Escalate on a two-voices
    step mints that segment's outlet, so a conductor rules on the objection
    rather than the run finishing around it."""
    pst = runmod.state(pwid)
    step = next((s for s in pst["steps"] if s["id"] == step_id), None)
    if not step or not step.get("panel") or runmod.panel_outstanding(pst, step):
        return
    returns = pst["returns"][step_id]
    verdict = runmod.merged_verdict(returns)
    # The two-voices shape -- a panel and a form on one step -- is what makes
    # an escalate here different from a panel-only one.
    escalated = bool(step.get("form")) and verdict == "escalate"
    if verdict != "revise" and not escalated:
        return
    findings = "\n\n".join(
        f"[{r['child'].rsplit('.', 1)[-1]}] {(r.get('fields') or {}).get('findings', '')}"
        for r in returns)
    asm = runmod.load_assembly(pst["assembly"])
    # Rationale: rework is its own move, so a revise mints the segment's
    # rework-form where one is declared; the choice lives here with the
    # verdict. A replan, and a segment without the key, mint the step-form.
    seg = next((s for s in asm["segment"] if s["id"] == step["segment"]), {})
    # Rationale: three reviews landing on one artifact means the artifact is
    #   not the one under repair, so the fourth revise mints a ruling instead
    #   of a fourth round -- and mints it alone, since a fourth fresh-context reader is
    #   the loop rather than the way out. The number and the form are the
    #   assembly's; the engine names neither.
    after, outlet = seg.get("impasse-after", 0), seg.get("impasse-form", "")
    looped = bool(after) and runmod.rework_rounds(pst, asm, step["segment"]) >= after
    # One mint, two ways in -- the outlet's prefill says which, because ruling
    # on a loop is not ruling on a root objection.
    if outlet and (escalated or looped):
        journal.append(pwid, "step", id=f"{step['segment']}-a{secrets.token_hex(2)}",
                       segment=step["segment"], form=outlet, filler="conductor",
                       prefill={"findings": findings,
                                "arrival": "escalate" if escalated else "rework-rounds"},
                       anchor=False, terminal=False, validates="", source="mint")
    elif not escalated:
        _mint_segment_round(pwid, asm, step["segment"], prefill={"findings": findings},
                            form=seg.get("rework-form", ""))


def _summary(st):
    """The mechanical record a `close` writes -- assembled from the journal,
    never typed: how many steps landed, how many were minted or amended into
    each segment beyond its first (the implement/review loop count), the
    review panel's verdict where this run had one, every check the engine
    ran, the tier this run was dispatched under, one line per amend, and
    every triage note -- the candidates this run raised, so a parent
    adjudicating the return sees them without opening the child's journal."""
    cycles = {}
    for s in st["steps"]:
        if s.get("source") in ("mint", "amend"):
            cycles[s["segment"]] = cycles.get(s["segment"], 0) + 1
    # A panel is a panel whether or not its step also carries a form: the
    # two-voices transition's critics rule on the plan exactly as a
    # panel-only review rules on a diff, and skipping them wrote the empty
    # string into the close summary of every run three critics had judged.
    verdict = ""
    for s in st["steps"]:
        if s.get("panel"):
            rs = st["returns"].get(s["id"]) or []
            if rs:
                verdict = runmod.merged_verdict(rs)
    amends = [{"action": a.get("action", ""), "step": a.get("step", ""),
               "segment": a.get("segment", ""), "reason": a.get("reason", ""),
               "anchor": a.get("anchor", False)} for a in st.get("amends", [])]
    triage = [{"text": n.get("text", "")} for n in st["notes"]
              if n.get("kind_detail") == "triage"]
    return {
        "steps_completed": len(st["done"]),
        "cycles": [{"segment": seg, "count": n} for seg, n in cycles.items()],
        "verdict": verdict,
        "checks": list(st.get("checks", [])),
        "model": st.get("model", ""),
        "amends": amends,
        "triage": triage,
    }


# [returned-decision]
# Rationale: a `decides` field is not only a panel's -- a two-voices step's
#   own ruling, and gate adjudication's `plan-holds`, are exactly as
#   returnable as a panel's merged verdict, and both should reach a return
#   through the one mechanism rather than a second one hardcoding which
#   field name to look for. Read off the most recent done step that
#   declares one, since an earlier round's decision (an impasse ruled, three
#   gates back) is stale the moment a later one lands.
# Rejected: reading only the terminal step. A run can close having decided
#   nothing on its own terminal form -- run-a-gate's GATE_CLOSE has no
#   `decides` field -- while an earlier step (its own impasse ruling) did;
#   the terminal step is the wrong place to stop looking.
def _last_decision(st, asm):
    """The value of the last `decides` field this run itself answered, or
    the empty string when it never declared one."""
    for s in reversed(st["steps"]):
        if s["id"] not in st["done"]:
            continue
        field = _decided_here(asm, s)
        value = (st["done"][s["id"]].get("fields") or {}).get(field, "") if field else ""
        if value:
            return value
    return ""


def cmd_close(argv):
    wid = argv[0]
    st = runmod.state(wid)
    if st is None:
        raise SystemExit(render.located(f"no run named {wid}\n  open runs: spine"))
    if st.get("closed"):
        raise SystemExit(f"{wid} is already closed")
    pending = [s for s in st["steps"] if s["id"] not in st["done"]]
    if pending:
        step = pending[0]
        # The way past a pending step depends on what kind it is: a step whose
        # panel is still outstanding has no form to fill yet -- true whether
        # or not it has one at all -- a dispatch step has no form either, and
        # offering the wrong escape is worse than offering none.
        if runmod.panel_outstanding(st, step):
            how = f"its panelists complete it: spine {wid}"
        elif step.get("dispatches"):
            how = f"open its child: spine open {step['dispatches']} --parent {wid} " \
                  f"--step {step['id']}"
        else:
            how = f"fill its form and submit it: spine {wid} submit"
        raise SystemExit(render.refusal(
            step["id"], "not complete",
            escape=f"{how}\n  or drop it: spine {wid} amend close {step['id']} --reason ..."))
    terminal = next((s for s in st["steps"] if s.get("terminal")), None)
    fields = st["done"][terminal["id"]].get("fields", {}) if terminal else {}
    summary = _summary(st)
    asm = runmod.load_assembly(st["assembly"])
    decision = _last_decision(st, asm)
    journal.append(wid, "closed", fields=fields, summary=summary, decision=decision)
    if st.get("parent") and st.get("parent_step"):
        if journal.exists(st["parent"]):
            journal.append(st["parent"], "return", step=st["parent_step"], child=wid,
                           row=st.get("row", ""), fields=fields, summary=summary,
                           decision=decision)
            _act_on_verdicts(st["parent"], st["parent_step"])
        else:
            # Writing anyway would create the parent's journal from nothing --
            # a run with no opening, no title, no assembly, sitting in the
            # ledger. Say the return went nowhere instead.
            journal.append(wid, "note", id=f"n{secrets.token_hex(2)}",
                           kind_detail="blocked", about="",
                           text=f"parent {st['parent']} not found -- return not delivered")
            print(f"warning: parent {st['parent']} not found -- return not delivered")
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


def cmd_trace(argv):
    """A run and everything it dispatched, as one timeline.

    Deliberately not offered in `status`'s legal moves. A run's agents are
    fresh on purpose -- nothing about the engine is resident between steps,
    and history is exactly what a room description withholds. This verb is
    for whoever is debugging the engine from outside a run, which is a
    different reader with different needs.
    """
    wid = argv[0]
    if not journal.exists(wid):
        raise SystemExit(render.located(f"no run named {wid}\n  open runs: spine"))
    rows = []
    for path in sorted(journal.location(wid).glob("**/journal.toml")):
        run = str(path.parent.relative_to(".agent-work")).replace(os.sep, ".")
        rows += [(e.get("at", ""), run, i, e)
                 for i, e in enumerate(journal.read(run))]
    # Stamps are second-resolution, so ties need a tiebreak, and the tie that
    # matters is a child's `closed` against the `return` it causes in its
    # parent -- the exact seam this verb exists to debug. Deepest run first
    # puts cause before effect there; within one run, file order still rules.
    rows.sort(key=lambda r: (r[0], -r[1].count("."), r[1], r[2]))
    print(render.trace(wid, rows))
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
    verbs = {"status": cmd_status, "submit": cmd_submit, "note": cmd_note,
             "amend": cmd_amend, "close": cmd_close, "trace": cmd_trace}
    if verb not in verbs:
        # `spine <id> sumbit` used to render the room and exit 0: only the exact
        # word is acted on, so a near-miss must not look like a hit.
        raise SystemExit(f"no verb {verb!r} -- one of: {', '.join(verbs)}\n\n{USAGE}")
    return verbs[verb]([argv[0]] + argv[2:])


if __name__ == "__main__":
    sys.exit(main() or 0)
