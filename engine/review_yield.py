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
run-a-gate's `ROUTE.toml`, run-an-issue's `PLAN_TO_EXECUTE.toml` and
`CONSOLIDATE.toml`. A seam with no route form of its own (explore-an-idea's
spec, the one left) renders its findings uncalled rather than guessed at.
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


def seam_label(seg):
    """What a human calls this seam: the disposing form's own name where the
    transition declares one (`consolidate`, `plan-to-execute`) -- the form is
    the thing a reader already knows by that name throughout the tree --
    or, where the transition declares neither form nor panel (run-a-gate's
    review, minted at `select`), the segment's own id, which is already the
    seam's whole identity there. Public: issue113's run-level round-cap
    names the seam in its own ask by this same lookup, never a second one."""
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
    or `None` where the deciding submit carried no such table at all (a seam
    with no route form, always; any other seam's round with nothing to
    call)."""
    rows = (fields or {}).get("calls")
    if not isinstance(rows, list):
        return None
    return [forms.leading_word(r.get("call", "")) for r in rows if isinstance(r, dict)]


# [revising-is-a-table-read]
# Rationale: "how many of the panel sent the round back" is a question the
#   seam's own outcome table answers per voice -- a word whose row does
#   anything but the inert `release` is a voice sending it back -- so the
#   tally reads `declared_does` against each voice's own resolved word, the
#   same reader every other consumer of a verdict already uses. A refused or
#   quiet voice counts as neither, having returned no word the table can act
#   on.
# Rejected: counting returns whose leading word is `revise`. Rename that
#   value in a seam's table and its form's note together -- the rename this
#   whole issue exists to make free -- and the tally silently reads zero on
#   every round that in fact sent the artifact back.
def _round(returns, done_entry, panel_forms, table):
    """One panel dispatch on one artifact: the round's own verdict record,
    how many of the panel sent it back, how many findings, and -- where the
    deciding submit carried a `calls` table -- a tally of how each was
    called, in the order the conductor ruled them."""
    verdict = runmod.verdict_record(runmod.verdict_fold(returns, panel_forms, table))
    revising = sum(1 for kind, word in runmod.voice_outcomes(returns, panel_forms)
                   if kind == "clean" and runmod.declared_does(table, word)
                   not in (None, "release"))
    calls = _calls((done_entry or {}).get("fields"))
    findings = len(calls) if calls is not None else _panel_findings(returns)
    tally = {}
    for word in calls or []:
        tally[word] = tally.get(word, 0) + 1
    return {"verdict": verdict, "revising": revising, "findings": findings,
            "called": calls is not None, "calls": tally}


# [seam-round-steps]
# Rationale: `seam_rounds` and issue113's run-level round-cap both need the
#   landed rounds at a seam -- one to tally verdicts, the other to walk each
#   round's own step for its findings text (`cli.py`'s cap-check branch).
#   Splitting the predicate out is what lets both read one definition of
#   "a landed round" rather than two copies drifting apart.
def seam_round_steps(st, seg):
    """The steps behind a landed round at this seam, in journal order: round
    one from `skeleton()`'s own mint or `select`'s first panel mint, every
    later round `_mint_segment_round`/`_mint` (cli.py) minted fresh under its
    own random tag -- found by segment and the seam's own disposing form,
    never by a hardcoded id. A round with no returns yet (an outstanding one,
    on a live run `trace --yield` can reach) is left out -- nothing to
    report, and nothing yet decided for a cap to count."""
    form = _seam_form(seg)
    return [step for step in st["steps"]
            if step.get("segment") == seg["id"] and step.get("form") == form
            and step.get("panel") and st["returns"].get(step["id"])]


def seam_rounds(st, seg, assembly):
    """Every round this seam's own artifact has been judged at, in journal
    order -- one entry per `seam_round_steps`."""
    rounds = []
    for step in seam_round_steps(st, seg):
        # Each round resolves its own table and its own panel forms from the
        # step it was dispatched on, never the seam's static declaration: a
        # round minted at `select` (run-a-gate's review) writes its panel at
        # runtime, and a round's own step is what says which of the segment's
        # two tables governs it.
        _, table = runmod.deciding_spec(assembly, step)
        rounds.append(_round(st["returns"][step["id"]], st["done"].get(step["id"]),
                             runmod.panel_forms(assembly, step), table))
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
            rounds = seam_rounds(cst, seg, assembly)
            if rounds:
                entries.append({"label": prefix + seam_label(seg), "rounds": rounds})
    return entries
