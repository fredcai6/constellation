"""Render `status`: where you are, what to do, what you can say.

This is the entire agent-facing surface of the engine. Everything an agent
must know arrives here, at the moment it applies, and nothing about the
engine is resident between steps -- so this file is doctrine delivery, not
formatting. Two rules hold it honest: never make the reader guess a verb
(every legal move is spelled out as a typeable command), and never surface
engine mechanics that are not the reader's business. Every block wraps to
WIDTH; `_para` and `_pairs` are how.
"""

import pathlib
import re
import textwrap

from engine import run as runmod

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


def imperative(text):
    """The step's own instruction, wrapped. Named rather than inlined so the
    one shape every room shares -- say what to do, then give the one move
    that does it -- is a thing the code has a word for."""
    return _para(text)


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


def checks(entries):
    """One line per check the gate ran. The command is itself the re-run a
    conductor's root-verify performs, so it prints bare enough to paste."""
    return [f"exit {c.get('exit')} {c.get('command','')}" for c in entries or []]


def cycles(entries):
    """One line per segment re-minted beyond its first pass -- the
    implement/review churn a conductor reads as a count, not a detail."""
    return [f"{c.get('segment','')} x{c.get('count')}" for c in entries or []]


def triage(entries):
    """One line per triage note this run journaled -- the record CLOSE.toml's
    own triage field asks for, so it is filled from what was said, not
    memory."""
    return [e.get("text", "") for e in entries or []]


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


# Every form step ends with an imperative and one way to reply. A brief step
# had a table and silence, and a light model filled that silence with the most
# available reading -- "a reviewer has been assigned, so I will wait" -- and
# then waited for something that was never coming. These are the sentences the
# engine knew and did not say. They live here rather than in an assembly
# because a dispatch is a dispatch in every assembly; the text is a property of
# the kind of step, not of the run it appears in.

DISPATCH = """
You dispatch this yourself. Run the open command below -- in a subagent if you
have one, in this session if you do not -- and carry the child through to its
own close. It returns here when it closes, and this step completes then."""

# Every verb here is one the reader performs. The first draft of PANEL ended
# "dispatch each panelist and wait for its verdict", and a light model did the
# waiting literally -- it started a background monitor to poll for a verdict
# nobody was coming to give, and stopped. A passive tail on an imperative
# reads as permission to stop acting, so these end on the reader's own move.

PANEL = """
You open each outstanding panelist below and carry it through to its own
close -- that close is what returns its verdict here. Run each in a subagent
if you have one, in this session if you do not. Every panelist is a fresh
cold reader and its brief is the whole handoff; the verdict on this work is
the panel's to give, which is the whole reason for a second voice. This step
completes once the last verdict has returned."""


# [posture-line]
# Rationale: a role name alone is a label; the agent has to be told where the
#   role is written and to go read it. The imperative is part of the line
#   because a bare labelled path leaves the reader to decide whether it is
#   worth opening, and a light model decides no.
# Rejected: two wordings, one per place a role is announced -- one string here
#   is what keeps the dispatch brief and the room saying the same thing.
# See: engine/run.py resolve_skill, which decides where and whether.
def posture(role):
    """Where this role is written, and the one thing to do with it.

    Empty for a role with no SKILL.md -- the caller renders no line at all,
    because naming a file that is not there is the defect this exists to fix,
    inverted.
    """
    path = runmod.resolve_skill(role)
    return f"{path} -- read it before you start" if path else ""


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
    ]
    written_at = posture(role)
    if written_at:
        lines.append(f"    posture      {written_at}")
    lines += [
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


def destination(onward_to):
    """Where this run's returns land, phrased once for the two places that
    say it -- before closing, as what closing will do, and after, as where
    the return went. `close` is the only move in this engine whose effect
    lands in a run other than the one you are standing in, which makes it
    the only move whose result has to be said out loud."""
    parent, step = onward_to
    return f"{parent}, at its step {step}"


def _board(state):
    """The board's own state -- the four things `understand`'s imperative
    asks the agent to leave true, so the agent reads them rather than
    counting rows by hand. A block appears only when it has something to
    say: no held rows or no ready cluster means that block does not print,
    since a heading over an empty list tells the reader less than no
    heading at all.
    """
    s = state["summary"]
    by_status = ", ".join(f"{k} {v}" for k, v in sorted(s["by_status"].items())) or "none"
    by_type = ", ".join(f"{k} {v}" for k, v in sorted(s["by_type"].items())) or "none"
    out = [f"  the board:          {state['path']}",
          f"    {s['total']} rows -- status: {by_status} -- type: {by_type}", ""]

    askable = state["askable"]
    if askable:
        out.append("  askable now")
        out.append(_pairs([(r.get("id", ""), r.get("question", "")) for r in askable]))
        out.append("")

    held = state["held"]
    if held:
        out.append("  held")
        out.append(_pairs([(r.get("id", ""), "held by " + ", ".join(ids))
                           for r, ids in held]))
        out.append("")

    groups, ready = state["clusters"]["groups"], state["clusters"]["ready"]
    ready_tags = [t for t in groups if ready.get(t)]
    if ready_tags:
        # A ready group still holds every member the board ever put in it --
        # answered, moot, deferred rows included. Readiness itself is scoped
        # to open rows (boards.clusters), so the sitting to print is that
        # same scope: only the rows still to be asked, which is exactly
        # `askable` for a ready group.
        askable_ids = {r.get("id", "") for r in askable}
        out.append("  ready for one sitting")
        out.append(_pairs([(t, ", ".join(r.get("id", "") for r in groups[t]
                                          if r.get("id", "") in askable_ids))
                           for t in ready_tags]))
        out.append("")

    return out


def drift(measures):
    """How an artifact has moved across the rounds of its own segment.

    A notice, not a verdict. It says what happened and asks for attention; it
    never says an artifact is too long, because the engine cannot tell
    legitimate growth from accretion and an agent shown a threshold treats it
    as one. The reader decides -- that is the whole of it."""
    if len(measures) < 2:
        return []
    first, last, now = measures[0], measures[-2], measures[-1]
    def pct(then):
        return round((now["words"] - then["words"]) / then["words"] * 100)
    parts = [f"{now['words']} prose words", f"{pct(first):+d}% on the first round"]
    if last is not first:
        parts.append(f"{pct(last):+d}% on the last")
    return ["  " + pathlib.Path(now["path"]).name + " -- " + ", ".join(parts),
            "    growth is not a defect; unexamined growth is. Say which this was.",
            ""]


def status(st, form, response_path, prefill=None, returns=None, blocked=(),
           position=None, board=None, in_hand=None, onward_to=None,
           returns_from="", triage_notes=(), role="", verdict=""):
    """The room description.

    Order is deliberate: a block first, because an open block outranks
    anything else; then who you are working for; then what arrived; then the
    imperative; then the one way to reply -- and `role` rides in the last of
    those, beside the form, because where the posture is written is only
    useful to whoever is about to fill it.
    """
    wid = st["id"]
    out = preamble(st, blocked, position)

    if st.get("awaiting_close"):
        # A root run has no dispatcher, so the old unconditional "returns to
        # whoever dispatched this run" was untrue exactly half the time.
        does = (f"closing is what stamps your returns to {destination(onward_to)}"
                if onward_to else "closing is what writes the record")
        out.append(_para(f"Every step is done. The run is not finished until it "
                         f"is closed -- {does}."))
        out.append("")
        out.append(located(f"  close it with:     spine {wid} close"))
        return "\n".join(out)

    if not st.get("open"):
        out.append("  This run is closed. Its record is in "
                   f".agent-work/{wid.replace('.', '/')}/journal.toml")
        if onward_to:
            # Deliberately not "its step is now complete": a panel step takes
            # one return per panelist, so that is false for every panelist but
            # the last. Name the destination, hand over one command, and let
            # the room at the other end describe itself.
            out.append("")
            out.append(f"  returned to {destination(onward_to)}.")
            out.append(located(f"  continue there:    spine {onward_to[0]}"))
        return "\n".join(out)

    if prefill:
        out.append("  your orders")
        out.append(_pairs(list(prefill.items())))
        out.append("")

    out.extend(drift([m for m in st.get("measures", [])
                      if m.get("segment") == (st["current"] or {}).get("segment")]))

    if returns:
        # Which child came back is the first thing a conductor with several
        # gates in flight needs, and the engine has known it all along.
        out.append(f"  returns from {returns_from}" if returns_from else "  returns")
        out.append(_pairs(list(returns.items())))
        out.append("")

    if verdict:
        # Said as a sentence, not a labelled value: the verdict is why this
        # room is the room, and a reader who only sees the findings has to
        # guess whether they are a round's notes or a panel's objection.
        out.append(_para(f"The panel that last ruled here returned {verdict}."))
        out.append("")

    if board:
        out.extend(_board(board))

    if triage_notes:
        # The candidates this run has already noted, so CLOSE.toml's triage
        # field is filled from the record rather than reconstructed from
        # memory at the last step. Notes joined by a blank line before a
        # single _para call, not one call per note: that blank line is what
        # marks a note's own continuation as still part of it, rather than
        # letting a wrapped line read as the start of the next note.
        out.append("  triage noted")
        out.append(_para("\n\n".join(triage(triage_notes)), indent="    "))
        out.append("")

    out.append(_para(form.get("imperative", "")))
    out.append("")

    if in_hand:
        out.append("  still in hand on this form")
        out.append(_pairs(list(in_hand.items())))
        out.append("")

    written_at = posture(role)
    if written_at:
        out.append(f"  your posture:       {written_at}")
    out.append(f"  your response form: {response_path}")
    out.append(located(f"  fill it, then:     spine {wid} submit"))
    out.append(legal_moves(wid))
    return "\n".join(out)


NULLS = "waived: <reason>  /  unknown: <reason>"


# [escape-for-field]
# Rationale: a field whose note declares a vocabulary refuses `waived:` and
#   `unknown:` -- `_check_vocabulary` rejects both, because a waived verdict
#   would fall through `merged_verdict` to a `pass`. So an empty or in-hand
#   answer on such a field cannot be offered the nulls: that is advice the very
#   next submit rejects. Where the note declares alternatives the escape names
#   them, in the phrasing `_check_vocabulary`'s own refusal already uses.
# Rejected: teaching `refusal()` to look the field up itself. It is handed a
#   field *id* -- sometimes a board file name, sometimes a bare word like
#   "reason" -- and most of its callers have no form field at all. The caller
#   holding the note is the only one that can answer.
# See: engine/cli.py `_check_vocabulary`, engine/forms.py `vocabulary`,
#   engine/forms.py `ESCAPES_REFUSED` -- the same correction on the template.
def escape_for(vocab, verb="fill"):
    """The escape a refusal offers on a field left unanswered: the two nulls,
    or -- where the field's note declares a vocabulary -- the values it takes.

    `verb` is what is left to do with the field: `fill` an empty one, `finish`
    one still carrying `working:`.
    """
    return (f"{verb} it with one of:  " + " | ".join(vocab) if vocab
            else f"{verb} it, or answer  {NULLS}")


FILL_OR_NULL = escape_for(())


def refusal(field_id, why, escape=FILL_OR_NULL):
    """A refusal names what failed and how to get past it -- no lecture.

    The escape is a parameter because it is not always the same one. A board
    row takes `deferred:`, not `waived:`; a field whose note declares a
    vocabulary takes one of its values and refuses the nulls; a lookup takes a
    different command entirely. One hardcoded suffix made half the refusals in
    this engine print an escape that does not work, which is worse than
    printing none.
    """
    return located(f"{field_id}: {why}" + (f"\n  {escape}" if escape else ""))


def _event(e):
    """One entry, said in one line. Every branch answers the same question --
    what happened -- so a trace stays greppable and diffable rather than
    needing to be read as prose."""
    k = e.get("kind")
    f = e.get("fields") or {}
    if k == "run":
        out = f"{e.get('assembly','')}  {e.get('title','')}"
        return out + (f"  <- dispatched by {e['parent']} at {e.get('parent_step','')}"
                      if e.get("parent") else "  (root)")
    if k == "step":
        what = (f"dispatches {e['dispatches']}" if e.get("dispatches")
                else f"panel x{len(e['panel'])}" if e.get("panel")
                else e.get("form", "(no form)"))
        return f"{e.get('id','')}  {what}  [{e.get('source','')}]"
    if k == "return":
        v = f.get("verdict") or f.get("plan-holds") or ""
        return (f"{e.get('step','')} <- {e.get('child','')}"
                + (f"  {v.strip().split(chr(10))[0][:40]}" if v else ""))
    if k == "check":
        return f"exit {e.get('exit')}  {e.get('command','')}"
    if k == "note":
        return f"{e.get('kind_detail','')}  {e.get('text','') or e.get('about','')}"
    if k == "amend":
        return (f"{'ANCHOR ' if e.get('anchor') else ''}{e.get('action','')} "
                f"{e.get('step','')}  {e.get('reason','')}")
    if k == "submit":
        # A submit carries the checks its step ran. Rendering only the step id
        # would drop the one output a trace is most often opened to find.
        ran = "  ".join(f"[exit {c.get('exit')}] {c.get('command','')}"
                        for c in e.get("checks") or [])
        return f"{e.get('step','')}  {ran}".rstrip()
    return {"board": e.get("path", ""),
            "prefill": ", ".join(e.get("fields", {})), "closed": ""}.get(k, "")


def trace(wid, rows):
    """A run and everything it dispatched, as one timeline.

    The journal has always been an ordered event log; until this, nothing
    rendered it as one, so tracing a defect meant reading raw TOML across
    several files -- and the bugs that keep surfacing here live precisely at
    the seam *between* runs, which no single journal shows.

    Stamps are second-resolution. `cmd_trace` breaks ties deepest-run-first,
    which puts a child's `closed` before the `return` it causes -- correct for
    the seam this exists to debug, and the record's precision is not enough to
    promise more than that.
    """
    if not rows:
        return f"no history for {wid}"
    head = f"{wid} -- {len({r[1] for r in rows})} runs, {len(rows)} events"
    pad = max(len(r[1]) for r in rows) + 2
    lines = [head, ""]
    for at, run, _i, e in rows:
        lines.append(f"  {at}  {run.ljust(pad)}{e.get('kind','').ljust(8)}"
                     f"{' '.join(_event(e).split())}".rstrip())
    return "\n".join(lines)


def ledger(rows):
    """Every open run: id, title, where it stands. Generated, never stored."""
    if not rows:
        return "no open runs"
    return _pairs([(r["id"], f"{r.get('assembly','')}  {r.get('where','')}  "
                             f"{r.get('title','')}") for r in rows], indent="")
