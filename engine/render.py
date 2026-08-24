"""Render `status`: where you are, what to do, what you can say.

This is the entire agent-facing surface of the engine. Everything an agent
must know arrives here, at the moment it applies, and nothing about the
engine is resident between steps -- so this file is doctrine delivery, not
formatting. Two rules hold it honest: never make the reader guess a verb
(every legal move is spelled out as a typeable command), and never surface
engine mechanics that are not the reader's business.
"""

import textwrap

WIDTH = 74


def _para(text, indent="  "):
    out = []
    for block in (text or "").strip().split("\n\n"):
        out.append(textwrap.fill(" ".join(block.split()), WIDTH,
                                 initial_indent=indent, subsequent_indent=indent))
    return "\n\n".join(out)


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


def status(st, form, response_path, prefill=None, returns=None, blocked=(),
           position=None):
    """The room description.

    Order is deliberate: a block first, because an open block outranks
    anything else; then who you are working for; then what arrived; then the
    imperative; then the one way to reply.
    """
    wid = st["id"]
    out = []

    head = f"{wid} · {st.get('assembly','')}"
    if position:
        i, n, seg = position
        head += f" · {seg} ({i} of {n})" if st.get("open") else " · closed"
    out.append(head)
    if st.get("title"):
        out.append(f"  {wid}: {st['title']}")
    out.append("")

    for b in blocked:
        out.append(f"  BLOCKED — {b.get('text','')}".rstrip())
        out.append(f"  resume with: spine {wid} note resumed {b.get('id','')}")
        out.append("")

    if not st.get("open"):
        out.append("  This run is closed. Its record is in "
                   f".agent-work/{wid.replace('.', '/')}/journal.toml")
        return "\n".join(out)

    if prefill:
        out.append("  your orders — contest them up, never edit them")
        out.append(_pairs(list(prefill.items())))
        out.append("")

    if returns:
        out.append("  returns")
        out.append(_pairs(list(returns.items())))
        out.append("")

    out.append(_para(form.get("imperative", "")))
    out.append("")

    out.append(f"  your response form: {response_path}")
    out.append(f"  fill it, then:     spine {wid} submit")
    out.append(f"  also legal:        spine {wid} note ...   spine {wid} amend ...")
    return "\n".join(out)


def refusal(field_id, why):
    """A refusal names the failing field and nothing else -- no lecture, and
    always the way out."""
    return (f"{field_id}: {why}\n"
            f"  fill it, or answer  waived: <reason>  /  unknown: <reason>")


def ledger(rows):
    """Every open run: id, title, where it stands. Generated, never stored."""
    if not rows:
        return "no open runs"
    return _pairs([(r["id"], f"{r.get('assembly','')}  {r.get('where','')}  "
                             f"{r.get('title','')}") for r in rows], indent="")
