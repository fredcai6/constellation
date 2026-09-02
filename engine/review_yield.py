"""A run's own review yield: per seam, per round, the panel's verdict, how
many findings, and how the conductor called each -- read off the journal
this run and everything it dispatched already hold, never tabulated by
hand. `docs/DERIVED_IS_CODE.md` is the rule; issue #16's first cut is this
module -- `docs/process-notes/issue84.md` note 25's table, by hand, is the
defect this replaces.

A seam is a panel-bearing transition: a segment whose transition declares a
panel outright (run-an-issue's consolidate, plan-to-execute) or whose round
is minted at `select` through a `route-form` (run-a-gate's review). A round
is one panel dispatch on one artifact -- the count `run.rework_rounds` uses,
plus the first. A finding is one block a panelist returned in its own
`findings` field, empty or `waived:`/`none:` counting as zero. A call is the
conductor's `blocking | accepted | beyond | rejected` on one finding, read
from a route form's `calls` table where the deciding submit carried one --
run-a-gate's `ROUTE.toml`, run-an-issue's `PLAN_TO_EXECUTE.toml`. Consolidate
has no route form, so its findings render uncalled rather than guessed at.
"""

import os
import pathlib

from engine import forms, journal
from engine import run as runmod


def _seam_segments(assembly):
    """Every segment whose transition is a seam in this assembly, in segment
    order."""
    out = []
    for seg in assembly["segment"]:
        t = seg.get("transition", {})
        if t.get("panel") or seg.get("route-form"):
            out.append(seg)
    return out


def _seam_form(seg):
    """The form a round of this seam stands its conductor on -- the
    transition's own, or (run-a-gate's review, minted at `select`) the
    segment's `route-form`. The same fallback `_mint_transition` (cli.py)
    reads, so a seam is found here by the identical rule that mints it."""
    t = seg.get("transition", {})
    return t.get("form") or seg.get("route-form", "")


def _seam_label(seg):
    """What a human calls this seam: the disposing form's own name where the
    transition declares one (`consolidate`, `plan-to-execute`) -- the form is
    the thing a reader already knows by that name throughout the tree --
    or, where the transition declares neither form nor panel (run-a-gate's
    review, minted at `select`), the segment's own id, which is already the
    seam's whole identity there."""
    t = seg.get("transition", {})
    if t.get("form"):
        return pathlib.Path(t["form"]).stem.lower().replace("_", "-")
    return seg["id"]


def _is_empty_finding(text):
    word = forms.leading_word(text)
    return word in ("", "none", "waived")


def _panel_findings(returns):
    """One finding per panelist return whose own `findings` field is not
    empty or waived -- the whole field is the block, per module docstring:
    nothing in the journal says where inside a panelist's prose one finding
    ends and its own reasoning begins, so splitting it would be guessing at
    structure the record never captured."""
    return sum(1 for r in returns
               if not _is_empty_finding((r.get("fields") or {}).get("findings", "")))


def _calls(fields):
    """The `call` word of each row in a submitted `calls` table, in order --
    or `None` where the deciding submit carried no such table at all
    (consolidate, always; any other seam's round with nothing to call)."""
    rows = (fields or {}).get("calls")
    if not isinstance(rows, list):
        return None
    return [forms.leading_word(r.get("call", "")) for r in rows if isinstance(r, dict)]


def _round(returns, done_entry):
    """One panel dispatch on one artifact: the merged verdict, how many of
    the panel returned `revise`, how many findings, and -- where the
    deciding submit carried a `calls` table -- a tally of how each was
    called, in the order the conductor ruled them."""
    verdict = runmod.merged_verdict(returns)
    revising = sum(1 for r in returns if forms.leading_word(
        (r.get("fields") or {}).get("verdict", "")) == "revise")
    calls = _calls((done_entry or {}).get("fields"))
    findings = len(calls) if calls is not None else _panel_findings(returns)
    tally = {}
    for word in calls or []:
        tally[word] = tally.get(word, 0) + 1
    return {"verdict": verdict, "revising": revising, "findings": findings,
            "called": calls is not None, "calls": tally}


def seam_rounds(st, seg):
    """Every round this seam's own artifact has been judged at, in journal
    order: round one from `skeleton()`'s own mint or `select`'s first panel
    mint, every later round `_mint_segment_round`/`_mint` (cli.py) minted
    fresh under its own random tag -- found the same way both are, by
    segment and the seam's own disposing form, never by a hardcoded id.
    A round with no returns yet (an outstanding one, on a live run `trace
    --yield` can reach) is left out -- nothing to report."""
    form = _seam_form(seg)
    rounds = []
    for step in st["steps"]:
        if step.get("segment") != seg["id"] or step.get("form") != form or not step.get("panel"):
            continue
        returns = st["returns"].get(step["id"], [])
        if not returns:
            continue
        rounds.append(_round(returns, st["done"].get(step["id"])))
    return rounds


def run_yield(wid):
    """The review yield for `wid` and everything it dispatched: one entry
    per seam any of those runs was judged at, each carrying its own rounds
    in journal order. Walks descendant journals the way `cmd_trace` does --
    the same `.agent-work` glob -- so a gate's own review reaches this
    exactly as trace already reaches a gate's own history."""
    st = runmod.state(wid)
    if not st or not st.get("assembly"):
        return []
    root = journal.root_for(wid) / ".agent-work"
    entries = []
    for path in sorted(journal.location(wid).glob("**/journal.toml")):
        child = str(path.parent.relative_to(root)).replace(os.sep, ".")
        cst = st if child == wid else runmod.state(child)
        if not cst or not cst.get("assembly"):
            continue
        assembly = runmod.load_assembly(cst["assembly"])
        prefix = "" if child == wid else child.rsplit(".", 1)[-1] + " "
        for seg in _seam_segments(assembly):
            rounds = seam_rounds(cst, seg)
            if rounds:
                entries.append({"label": prefix + _seam_label(seg), "rounds": rounds})
    return entries
