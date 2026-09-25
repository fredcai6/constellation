"""A run's own review yield: per seam, per round, the panel's verdict, how
many findings, and how the conductor called each -- read off the journal
this run and everything it dispatched already hold, never tabulated by
hand. `docs/DERIVED_IS_CODE.md` is the rule; issue #16's first cut is this
module -- the same table kept by hand is the defect it replaces.

A seam is a panel-bearing transition: a segment whose transition declares a
panel outright (run-an-issue's consolidate, plan-to-execute) or whose round
is minted at `select` through a `route-form` (run-a-gate's review). A round
is one disposal of one artifact at the seam -- a panel dispatch where the
round carries a panel, the conductor's route form alone where it does not
(run-an-issue's plan seam after the opening cut) -- the count
`run.rework_rounds` uses, plus the first. A finding is one block a panelist returned in its own
`findings` field, empty or `waived:`/`none:` counting as zero. A call is the
conductor's `blocking | accepted | beyond | rejected` on one finding, read
from a route form's `calls` table where the deciding submit carried one --
run-a-gate's `ROUTE.toml`, run-an-issue's `PLAN_TO_EXECUTE.toml` and
`CONSOLIDATE.toml`. A seam with no route form of its own (explore-an-idea's
spec, the one left) renders its findings uncalled rather than guessed at.
A round whose panel a conductor waived (`amend waive`) is still a round:
it counts the voices that did return, reports the rest as waived with the
reason, and waived whole folds as a quiet panel with the count and reason
as its whole line -- so the seam's history shows the round happened and
says why.
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
def _round(returns, done_entry, panel_forms, table, waived=None):
    """One disposal of one artifact at the seam: the round's own verdict
    record, how many of the panel sent it back, how many findings, and --
    where the deciding submit carried a `calls` table -- a tally of how each
    was called, in the order the conductor ruled them. `waived` is
    `run.waived_panel`'s own triple for a round a conductor waived in part
    or in full: the count and reason ride the record. A round waived whole
    has no voice to fold, so its verdict record is the quiet panel's own
    `""` -- the count and reason are what the line then says. A round that
    carried no panel at all (run-an-issue's plan seam after the opening cut;
    `panel_forms` is empty) has no verdict to record either, so the
    conductor's own disposing word -- the `decides` field the seam's table
    names, read off the round's done entry -- stands in its place: the
    record of the round is what the conductor said of it."""
    n_waived, reason = (waived[0], waived[2]) if waived else (0, "")
    verdict = runmod.verdict_record(runmod.verdict_fold(returns, panel_forms, table))
    if not returns and not panel_forms and done_entry:
        verdict = forms.leading_word(
            (done_entry.get("fields") or {}).get(table.get("decides", ""), ""))
    revising = sum(1 for kind, word in runmod.voice_outcomes(returns, panel_forms)
                   if kind == "clean" and runmod.declared_does(table, word)
                   not in (None, "release"))
    calls = _calls((done_entry or {}).get("fields"))
    findings = len(calls) if calls is not None else _panel_findings(returns)
    tally = {}
    for word in calls or []:
        tally[word] = tally.get(word, 0) + 1
    return {"verdict": verdict, "revising": revising, "findings": findings,
            "called": calls is not None, "calls": tally,
            "waived": n_waived, "reason": reason}


# [seam-round-steps]
# Rationale: `seam_rounds` and `seam_round_steps_since_release` both need
#   the landed rounds at a seam -- one to tally every verdict for the yield,
#   the other to cut that list at the seam's last release for issue113's
#   run-level round-cap. Splitting the predicate out is what lets both read
#   one definition of "a landed round" rather than two copies drifting
#   apart.
def _landed_round(st, seg, step):
    """Whether `step` is a landed round at this seam: in the seam's own
    segment, on its disposing form, carrying a panel that has returned --
    or was waived, which lands the round by the conductor's ruling -- or,
    where the round carries no panel (run-an-issue's plan seam after the
    opening cut, `panel-rounds = "opening"`), disposed of by its conductor."""
    if step.get("segment") != seg["id"] or step.get("form") != _seam_form(seg):
        return False
    if step.get("panel"):
        return bool(st["returns"].get(step["id"]) or step.get("waived"))
    return step["id"] in st["done"]


def seam_round_steps(st, seg):
    """The steps behind a landed round at this seam, in journal order: round
    one from `skeleton()`'s own mint or `select`'s first panel mint, every
    later round `_mint_segment_round`/`_mint` (cli.py) minted fresh under its
    own random tag -- found by segment and the seam's own disposing form,
    never by a hardcoded id. A round has landed once its panel has returned
    or, where the round carries no panel, once its conductor has disposed of
    it. A round with neither yet (an outstanding one, on a live run `trace
    --yield` can reach) is left out -- nothing to report, and nothing yet
    decided for a cap to count -- unless its panel was waived: that round
    landed by the conductor's own ruling, and the yield owes the seam's
    history the fact and the reason."""
    return [step for step in st["steps"] if _landed_round(st, seg, step)]


def _released(assembly, step, done):
    """Whether the word `done` decided on `step` is one the table governing
    that step resolves to the inert `release` -- the seam routing its round
    onward rather than back, up, or nowhere yet."""
    _, spec = runmod.deciding_spec(assembly, step)
    word = forms.leading_word(str((done.get("fields") or {}).get(spec.get("decides", ""), "") or ""))
    return runmod.declared_does(spec, word) == "release"


# [rounds-since-release]
# Rationale: issue113's cap exists to catch a seam sending the same plan back
#   round after round with nothing released -- issue99's nineteen rounds at
#   plan-to-execute -- and the count it first read was `seam_rounds`, every
#   round since the run opened. A rolling-horizon run re-enters the plan seam
#   once per gate by design, so an eight-gate run landed its sixth plan round
#   with no send-back at all and the cap fired on structure, not churn
#   (issue811's first run, 2026-09-06, in the conductor's own words). A
#   release is the seam doing its job; the rounds it has sent back since it
#   last did are the churn a human wants to hear about. The yield still
#   reads `seam_rounds`: a reader tallying verdicts wants the whole history,
#   the cap wants the run of send-backs, and those are two functions rather
#   than one with a flag.
# Rejected: counting per artifact (`run.rework_rounds`). That is
#   `impasse-after`'s count, and an impasse ruling `rework` keeps the same
#   artifact -- the cap has to reach past that outlet to the loop of impasse
#   rulings that is issue99's shape, which only a release ends.
def seam_round_steps_since_release(st, seg, assembly):
    """The landed rounds at this seam since it last released, in journal
    order -- `seam_round_steps`'s own list, started over at the most recent
    step in this segment standing on the seam's form whose decided word its
    table resolves to `release`: plan-to-execute's `pass` projecting a gate,
    review's `pass` or `close` walking on to GATE_CLOSE. Read with or
    without a panel on the releasing step, since an impasse `advance` mints
    the form alone and the release lands there. Every round left in the
    list was sent back, paused, or is still being decided; a seam that has
    never released carries its whole history here. A round a pause's answer
    opened starts the list over too."""
    since = []
    for step in st["steps"]:
        if step.get("segment") != seg["id"] or step.get("form") != _seam_form(seg):
            continue
        # The round a paused seam's answer opened starts the count over: the
        # answer is the ruling the cap stopped to get (#177).
        if step.get("resumed"):
            since = []
        if _landed_round(st, seg, step):
            since.append(step)
        done = st["done"].get(step["id"])
        if done and _released(assembly, step, done):
            since = []
    return since


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
        rounds.append(_round(st["returns"].get(step["id"]) or [],
                             st["done"].get(step["id"]),
                             runmod.panel_forms(assembly, step), table,
                             runmod.waived_panel(step)))
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
