"""Render `status`: where you are, what to do, what you can say.

This is the entire agent-facing surface of the engine. Everything an agent
must know arrives here, at the moment it applies, and nothing about the
engine is resident between steps -- so this file is doctrine delivery, not
formatting. Two rules hold it honest: never make the reader guess a verb
(every legal move is spelled out as a typeable command), and never surface
engine mechanics that are not the reader's business.
"""

import pathlib
import re
import textwrap

WIDTH = 74


def spine_cmd():
    """This engine's own runnable path -- computed from `__file__`, the same
    trick `engine/install.py` and `engine/run.py` already use to find the
    repo root. A dispatched child has no shell of its own and nothing on
    PATH, so the bare word `spine` is not a command it can run; its own copy
    (install is a copy, never a rewrite) sits right beside this file."""
    return str(pathlib.Path(__file__).resolve().parent.parent / "spine")


def located(text):
    """Every rendered command is written as ordinary `spine ...` text and
    resolved here, once -- so the source stays readable and a second copy of
    the resolution never has the chance to drift."""
    path = spine_cmd()
    return re.sub(r"\bspine\b", lambda _m: path, text or "")


def _para(text, indent="  "):
    out = []
    for block in (text or "").strip().split("\n\n"):
        out.append(textwrap.fill(" ".join(block.split()), WIDTH,
                                 initial_indent=indent, subsequent_indent=indent))
    return "\n\n".join(out)


def amends(entries):
    """One line per amend, anchors called out. This is the whole enforcement
    of the freeze: the tier above reads it and accepts or contests. A flag
    nobody renders is not a safeguard, it is inert data."""
    out = []
    for a in entries or []:
        mark = "ANCHOR " if a.get("anchor") else ""
        out.append(f"{mark}{a.get('action','')} {a.get('step','')} "
                   f"in {a.get('segment','')} — {a.get('reason','')}".strip())
    return out


def _pairs(rows, indent="    "):
    """Aligned label/value lines, wrapped under the label."""
    if not rows:
        return ""
    pad = max(len(k) for k, _ in rows) + 2
    out = []
    for k, v in rows:
        body = textwrap.fill(" ".join(str(v).split()), WIDTH - len(indent) - pad) or ""
        first, *rest = body.split("\n") or [""]
        out.append(f"{indent}{k.ljust(pad)}{first}")
        out.extend(" " * (len(indent) + pad) + line for line in rest)
    return "\n".join(out)


def preamble(st, blocked=(), position=None):
    """Where you are, and anything blocking -- the opening of every status
    view, whatever kind of step you are standing on. One copy, because a
    second one drifts."""
    wid = st["id"]
    head = f"{wid} · {st.get('assembly','')}"
    if position:
        i, n, seg = position
        head += f" · {seg} ({i} of {n})" if st.get("open") else " · closed"
    out = [head]
    if st.get("title"):
        out.append(f"  {wid}: {st['title']}")
    out.append("")
    for b in blocked:
        out.append(f"  BLOCKED — {b.get('text','')}".rstrip())
        out.append(located(f"  resume with: spine {wid} note resumed {b.get('id','')}"))
        out.append("")
    return out


def legal_moves(wid):
    return located(f"  also legal:        spine {wid} note ...   spine {wid} amend ...")


def brief(child_id, role, tier, runner, open_cmd, finish_form):
    """One dispatch's whole brief, shared by a gate dispatch and a panelist
    so the two never render this as two drifting copies: who the child will
    be, what it runs under, the command that mints it, and what finishing
    means for the assembly it is about to run. This is the text a conductor
    hands its harness -- nothing else should be needed to start.
    """
    lines = [
        f"  brief -- {child_id}",
        f"    role         {role or '(unset)'}",
        f"    tier         {tier or '(unset)'}",
        f"    runner       {runner or '(unresolved -- check constellation.toml [models])'}",
        f"    open it:     {located(open_cmd)}",
    ]
    close_cmd = located(f"spine {child_id} close")
    if finish_form:
        lines.append(f"    finishing:   fill {finish_form}, then: {close_cmd}")
    else:
        lines.append(f"    finishing:   {close_cmd}")
    return "\n".join(lines)


def status(st, form, response_path, prefill=None, returns=None, blocked=(),
           position=None, board=None, in_hand=None):
    """The room description.

    Order is deliberate: a block first, because an open block outranks
    anything else; then who you are working for; then what arrived; then the
    imperative; then the one way to reply.
    """
    wid = st["id"]
    out = preamble(st, blocked, position)

    if st.get("awaiting_close"):
        out.append("  Every step is done. The run is not finished until it is")
        out.append("  closed -- closing is what stamps the returns to whoever")
        out.append("  dispatched this run.")
        out.append("")
        out.append(located(f"  close it with:     spine {wid} close"))
        return "\n".join(out)

    if not st.get("open"):
        out.append("  This run is closed. Its record is in "
                   f".agent-work/{wid.replace('.', '/')}/journal.toml")
        return "\n".join(out)

    if prefill:
        out.append("  your orders")
        out.append(_pairs(list(prefill.items())))
        out.append("")

    if returns:
        out.append("  returns")
        out.append(_pairs(list(returns.items())))
        out.append("")

    if board:
        out.append(f"  the board:          {board}")
        out.append("")

    out.append(_para(form.get("imperative", "")))
    out.append("")

    if in_hand:
        out.append("  still in hand on this form")
        out.append(_pairs(list(in_hand.items())))
        out.append("")

    out.append(f"  your response form: {response_path}")
    out.append(located(f"  fill it, then:     spine {wid} submit"))
    out.append(legal_moves(wid))
    return "\n".join(out)


FILL_OR_NULL = "fill it, or answer  waived: <reason>  /  unknown: <reason>"


def refusal(field_id, why, escape=FILL_OR_NULL):
    """A refusal names what failed and how to get past it -- no lecture.

    The escape is a parameter because it is not always the same one. A board
    row takes `deferred:`, not `waived:`; a lookup takes a different command
    entirely. One hardcoded suffix made half the refusals in this engine
    print an escape that does not work, which is worse than printing none.
    """
    return located(f"{field_id}: {why}" + (f"\n  {escape}" if escape else ""))


def ledger(rows):
    """Every open run: id, title, where it stands. Generated, never stored."""
    if not rows:
        return "no open runs"
    return _pairs([(r["id"], f"{r.get('assembly','')}  {r.get('where','')}  "
                             f"{r.get('title','')}") for r in rows], indent="")
