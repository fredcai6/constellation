"""Fold the journal into where you are.

There is no state file. A run is its journal, and everything below is a
question asked of the entry list: which steps exist, which are done, what is
current. Two sessions interleaving is a fact the fold reports, never a
condition it prevents.
"""

import pathlib
import re
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
#   the conductor, who works the board in `board-worker`'s posture -- the
#   issue-conductor wears the interrogator's hat -- because a live principal is
#   reachable only from the top of the run. A run with a parent has no human
#   in reach, so it wears the delegated variant where one is written; where
#   none is, the plain posture, which is the parked state (#15). Scoped to a
#   step whose own filler is still the bare `"conductor"` indirection --
#   understand's own spec-writer round (a board segment's `step-form`, a
#   second hand distinct from the board's) already names its worker directly
#   on the step, and this override would otherwise clobber it back to the
#   board's hat regardless.
# Rejected: naming the board's own hat `worker`, the field `step-form`
#   already reads for who fills that round. One segment, one board, one
#   step-form, but two hands now -- `board-worker` is read nowhere else, so
#   nothing forces it to agree with `worker`, which is the point: they name
#   different work.
# Rejected: a worker child driving its parent's board. A child not handed an
#   id cannot drive its dispatcher's run, by design, and the board is the
#   parent's own segment.
def hat(assembly, step, st):
    """The posture a step is worked under: the filler's, or -- on a board
    segment, while the step's own filler is still bare `"conductor"` --
    `board-worker`'s. Delegated when the run has a parent."""
    seg = next((s for s in assembly["segment"] if s["id"] == step.get("segment")), {})
    on_board = seg.get("interior") == "board" and step.get("filler", "conductor") == "conductor"
    worker = seg.get("board-worker", "") if on_board else ""
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

    A segment may declare `step-form` beside either interior kind: a
    worklist segment's own round (run-a-gate's work), or a board segment's
    -- run-an-issue's understand, where the board is seeded separately (see
    `_mint`, engine/cli.py) and this step is the spec-writer's own round,
    ordered between the board and the segment's transition by `_ordered`.
    """
    steps = []
    for seg in assembly["segment"]:
        form = seg.get("step-form")
        # Rationale: `interior` still names two kinds of contents, board or
        #   worklist -- this branch no longer cares which, only whether a
        #   step-form was declared. A board segment's own rows are seeded
        #   elsewhere (`_mint`); what changes here is only whether its
        #   step-form also mints an interior step, the way a worklist
        #   segment's always has.
        # Rejected: a second branch keyed on `interior == "board"`. Same
        #   step shape either way -- id, filler, the open/steps defaults --
        #   so a second copy of it would diverge from this one by accident,
        #   not by design.
        if form and seg.get("interior") in ("steps", "board"):
            step = {"id": seg["id"] + "-1", "segment": seg["id"],
                    "filler": seg.get("worker", "conductor"), "anchor": False,
                    "terminal": False, "validates": "", "source": "open"}
            # [plan-round-is-a-dispatch]
            # Rationale: a segment can declare a `dispatches` target beside its
            #   own step-form -- run-an-issue's plan segment is the first. The
            #   round this seeds is the first cut, and the conductor that will
            #   judge it cannot also be the hand that drafted it, so it opens as
            #   a fresh child's step, not a form on this run's own worklist. A
            #   later rework round is minted by `_mint_segment_round` instead,
            #   which knows only forms -- so only round one takes this branch.
            if seg.get("dispatches"):
                step["dispatches"] = seg["dispatches"]
            else:
                step["form"] = form
            # [interior-panel]
            # Rationale: a panel is not only a transition's -- design-it-twice
            #   (ruling 10) declares one on the segment itself, read here so
            #   round one's interior step carries it too. `_mint_segment_round`
            #   mints every later round and does not read `segment.panel`, so a
            #   rework round stays single-planner; re-arguing a settled
            #   alternative belongs to round one only.
            if seg.get("panel"):
                step["panel"] = seg["panel"]
            steps.append(step)
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
    """Revise outranks pass: any blocking finding outranks a clean one. The
    panel's whole vocabulary is `pass | revise` -- there is no third word, so
    one revise among the returns is what decides it."""
    vs = [forms.leading_word((r.get("fields") or {}).get("verdict", "")) for r in returns]
    if "revise" in vs:
        return "revise"
    return "pass"


# [pair-return-by-pn-index]
# Rationale: a panel step's several children are each read against their own
#   history (commitment 11), so a return is attributed to its own panelist by
#   the child id's own `pN` tag -- the same tag `_panel_status` (engine/cli.py)
#   mints as `f"{wid}.{step['id']}.p{i}"` -- indexed into `panel_forms` the
#   way every existing reader indexes `step["panel"][N-1]`.
# Rejected: zipping `returns` against `panel_forms` in arrival order. Returns
#   land in journal order, not dispatch order, so the first return home is
#   not necessarily panelist one's.
# Rejected: keying by role name. Two panelists can share a role (two
#   critics), so role alone cannot tell them apart; the child id's own tag
#   already does, unambiguously.
_PANEL_CHILD_TAG = re.compile(r"\.(p\d+)$")


def _voice_form(panel_forms, tag):
    """The panelist form the voice tagged `tag` (e.g. `"p2"`) was dispatched
    under, or `{}` where the tag cannot be read -- `_voice_outcome` then
    finds no `verdict` field on it and resolves quiet, same as a form that
    truly declares none."""
    n = int(tag[1:]) if tag else 0
    return panel_forms[n - 1] if 1 <= n <= len(panel_forms) else {}


# [voice-outcome-vocabulary]
# Rationale: `forms.enforced_vocabulary` already answers "what will the
#   engine accept here" from the panelist's own form -- a return's leading
#   word is resolved against that voice's declared vocabulary, never a
#   panel-wide one, so two panelists under two different forms (a critic and
#   a reviewer, say) are each held to their own.
def _voice_outcome(tag, ret, form):
    """One panelist's own outcome: `("clean", word)` -- the return's leading
    word, in the form's own vocabulary; `("refused", tag)` -- a vocabulary
    declared but the word is not in it (missing, empty, or foreign), naming
    this voice so a panel-wide refusal can say which one; or `("quiet",
    None)` -- the form declares no `verdict` field at all, PLAN.toml's own
    case, true regardless of what the return's fields hold."""
    field = next((f for f in (form or {}).get("fields", []) if f.get("id") == "verdict"), None)
    vocab = forms.enforced_vocabulary(field) if field else []
    if not vocab:
        return ("quiet", None)
    word = forms.leading_word((ret.get("fields") or {}).get("verdict", ""))
    return ("clean", word) if word in vocab else ("refused", tag)


# [refusal-outranks-every-clean-word]
# Rationale: obligation 6 binds the seam not to release on a refusal, and a
#   clean word from a co-panelist cannot buy that back -- so a refusal from
#   any voice is the whole panel's result, naming the voice, ahead of any
#   ranking among the clean words and regardless of precedence among them.
# [quiet-needs-every-voice-quiet]
# Rationale: quiet is the design-it-twice panel's own case -- every voice's
#   form declares no vocabulary at all. One voice's form declaring a
#   vocabulary takes the whole panel out of quiet eligibility even where
#   that voice's own return is clean, so a no-vocabulary voice paired with a
#   vocabulary voice folds to the vocabulary voice's clean word, not quiet.
def verdict_fold(returns, panel_forms, table):
    """Fold a panel's returns to one panel-wide outcome: `("clean", word)`,
    `("refused", tag)`, or `("quiet", None)` -- three per-voice outcomes
    (`_voice_outcome`) combined by one rule, not by whichever branch an
    implementation happens to reach first.

    `panel_forms` is the panelist form each voice was dispatched under,
    positional with `step["panel"]`. `table` is the deciding segment's own
    outcome table, shaped like `deciding_spec`'s own second return value --
    this function never resolves that table itself (never `deciding_spec`,
    never an assembly, never a step); it only reads the table it is handed,
    through `declared_does`, so what a word does stays the table's call, not
    a string comparison.
    """
    outcomes = []
    for ret in returns:
        m = _PANEL_CHILD_TAG.search(ret.get("child", "") or "")
        tag = m.group(1) if m else ""
        outcomes.append(_voice_outcome(tag, ret, _voice_form(panel_forms, tag)))
    refusal = next((o for o in outcomes if o[0] == "refused"), None)
    if refusal:
        return refusal
    if all(o[0] == "quiet" for o in outcomes):
        return ("quiet", None)
    clean = [o for o in outcomes if o[0] == "clean"]
    # Ranked by what the table says each word does, first, never by the word
    # itself: a value `declared_does` resolves to something other than the
    # inert default outranks one it resolves to that default -- `None` (no
    # row at all) counts as the same inert default a row that names none
    # does (ruled: matches what every existing reader of `declared_does`
    # already treats as one bucket). Two words tied on that -- both inert,
    # which is the ordinary case at three of the tree's four panel-bearing
    # seams, where the table's own two rows both resolve to the same inert
    # default -- fall to `_table_row_rank` below.
    def _rank(word):
        inert = declared_does(table, word) in (None, "release")
        return (inert, -_table_row_rank(table, word))
    ranked = sorted(clean, key=lambda o: _rank(o[1]))
    return ranked[0]


# [table-row-tiebreak]
# Rationale: something declared has to break a tie between two clean words
#   the table resolves to the same disposition -- not arrival order, and
#   not a word the engine names -- so this reads the one thing every voice
#   in the panel is already judged against in common: the table
#   `verdict_fold` is handed, through `declared_does`. A row declared later
#   outranks one declared earlier that lands on the same disposition; a
#   word the table names no row for at all outranks nothing, so it never
#   beats a row that is actually there. That is a new meaning for row
#   order: today only a row's own `value` and `does` are read pointwise
#   (`declared_does`), and where a row sits relative to another means
#   nothing to any existing reader. From here it does, whenever two rows
#   land on the same disposition -- and every table in the tree that has
#   such a pair already reads this way unforced, before this gate ever
#   named it: the word that leaves the round alone sits first, the one that
#   sends it back sits after.
# Rejected: a panelist's own form -- the note its `verdict` field declares
#   its alternatives in. Two voices in one panel can be dispatched under
#   two different forms (commitment 11's own reason a return is paired by
#   the child's `pN` tag, not by position), so two notes' word orders are
#   not one order to rank across. The table is one order shared by the
#   whole panel already, and it is already the argument this function
#   reads -- no new parameter, no new pairing to get wrong.
# Rejected: comparing the two words to each other directly. That is the
#   defect this gate exists to remove.
def _table_row_rank(table, value):
    """`value`'s position among `table`'s own `[[outcome]]` rows, or `-1`
    where no row names it at all -- lower than any real position, so an
    undeclared value never outranks one the table actually declares."""
    for i, row in enumerate(table.get("outcome", [])):
        if row["value"].split("<")[0].strip().lower() == value:
            return i
    return -1


# [deciding-spec]
# Rationale: which of a segment's two outcome tables a step resolves against
#   is one rule read from three places -- `state`'s two-voices fold below,
#   and `_decided_here`/`_outcome` in cli.py. cli.py imports this module and
#   never the reverse, so the rule lives here and cli.py calls it: the fold
#   and the router then cannot disagree about which table governs a step,
#   which is the whole reason the fold consults a table at all.
# Rejected: state() re-deriving the lookup locally. Two walks over the same
#   rows drift, and the failure is silent -- a step held open for a form the
#   router is about to mint past, or folded shut on a round the router meant
#   a conductor to judge.
def deciding_spec(assembly, step):
    """(segment, spec) for `step`: the segment it sits in, and whichever of
    that segment or its transition declares the outcomes this step resolves
    against -- the transition when the step carries the transition's own
    form, the segment otherwise. A panel-only transition matches on both
    forms being absent, which is the case it has always taken."""
    seg = next((s for s in assembly["segment"] if s["id"] == step.get("segment")), {})
    t = seg.get("transition", {})
    return seg, (t if step.get("form") == t.get("form") else seg)


# [declared-does]
# Rationale: `release` is the documented default a row needs no verb word
#   for, so "what does this value do" is not `row["does"]` -- it is this,
#   and every reader of the table needs the same answer.
def declared_does(spec, value):
    """The verb string `spec` declares for `value` -- `release` where the row
    names none, `None` where no row declares the value at all."""
    row = next((o for o in spec.get("outcome", [])
                if o["value"].split("<")[0].strip().lower() == value), None)
    return row.get("does", "release") if row else None


# [two-voices-holds]
# Rationale: a two-voices step stays open for its conductor whenever the
#   transition's own outcome row for the merged verdict resolves to the
#   inert `release` -- not only when the word is `pass`. `release` mints
#   nothing, so folding the step into `done` on it walks the run past a form
#   nobody was ever stood on; any other verb mints the next round itself,
#   and the panel finishes the step alone exactly as before.
# Rejected: comparing the merged word against the literal `pass` here. That
#   was true of every table in the tree and true by rule of none of them --
#   a transition whose own `revise` releases (run-a-gate's review) folds
#   shut on exactly the round its conductor exists to judge.
def _holds_for_its_form(st, step, returns):
    """Does this two-voices step stay open for its own form to complete?"""
    if not st.get("assembly"):
        return merged_verdict(returns) == "pass"
    _, spec = deciding_spec(load_assembly(st["assembly"]), step)
    # `None` -- no row at all -- is the interior case: a design panel (ruling
    # 10) sits on a step whose own segment declares an impasse ruling, not a
    # verdict, so no verdict word ever resolves there and the form completes
    # the step exactly as it always has. Inert either way is what holds.
    return declared_does(spec, merged_verdict(returns)) in (None, "release")


def state(work_id):
    """Fold the journal: the run's identity, its steps, and where it stands."""
    entries = journal.read(work_id)
    if not entries:
        return None
    st = {"id": work_id, "steps": [], "done": {}, "boards": {}, "notes": [],
          "returns": {}, "returns_by_child": {}, "row_returns": {}, "amends": [],
          "checks": [], "measures": [], "in_flight": {}, "closed": False}
    raw_steps = []
    for e in entries:
        kind = e.get("kind")
        if kind == "run":
            st.update(title=e.get("title", ""), assembly=e.get("assembly", ""),
                      opened=e.get("at", ""), parent=e.get("parent", ""),
                      parent_step=e.get("parent_step", ""), model=e.get("model", ""),
                      row=e.get("row", ""), branch=e.get("branch", ""),
                      worktree=e.get("worktree", ""))
        elif kind == "step":
            raw_steps.append(dict(e))
        elif kind == "submit":
            st["done"][e["step"]] = e
            st["checks"].extend(e.get("checks") or [])
            st["in_flight"].pop(e["step"], None)
        elif kind == "check-started":
            # The caller was handed back while this step's proof was still
            # running. It completes no step: the process running the check
            # appends the submit itself, and only on exit 0 -- so a step is
            # in flight exactly while its own started entry is the last word
            # about it, which is what popping on a result below means.
            st["in_flight"][e["step"]] = e
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
            # merged verdict's own declared row does something -- exactly like
            # a panel-only step, which releases on any verdict because it has
            # no form to hold for. A verdict whose row is the inert `release`
            # instead leaves it open; it completes on submit.
            step = next((s for s in raw_steps if s["id"] == e["step"]), None)
            expected = len(step["panel"]) if step and step.get("panel") else 1
            returns = st["returns"].setdefault(e["step"], [])
            returns.append(e)
            st["returns_by_child"][e.get("child", "")] = e
            two_voices = bool(step and step.get("panel") and step.get("form"))
            if len(returns) >= expected and not (
                    two_voices and _holds_for_its_form(st, step, returns)):
                st["done"][e["step"]] = e
        elif kind == "check":
            st["checks"].append({"command": e.get("command"), "exit": e.get("exit"),
                                 "output": e.get("output")})
            st["in_flight"].pop(e.get("step"), None)
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

    # A started entry can land *after* the submit its own check produced: the
    # caller gives up on the wait in the same instant the runner journals. A
    # done step is done however its two entries were ordered.
    st["in_flight"] = {k: v for k, v in st["in_flight"].items() if k not in st["done"]}
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


# [paused-marker]
# Rationale: a paused run's own marker is recognized by the positive `paused`
#   key `_pause_gate` (engine/cli.py) writes -- never by the absence of
#   `form`, `panel` and `dispatches`, which `_amend_add --transition` already
#   mints today with no pause behind it at all. The key's own value is the
#   segment the parent's answer resumes, read back by `_resume_paused_child`
#   rather than re-derived, so the two ends of one pause cannot disagree
#   about where it resumes.
# Rejected: folding this into `state()` as a top-level flag. The fold stays
#   exactly what it was; a marker step is a step like any other; only whether
#   one is standing there changes.
def paused(step):
    """True for the marker step `_pause_gate` minted in place of the round it
    decided at -- the run stands on it until the parent it asked answers."""
    return bool(step.get("paused"))


def in_flight(st, step):
    """The `check-started` entry for this step while its proof is still the
    last word about it, or None. Derived from entries like everything else
    here -- a started check is not new state, it is another appender the
    journal already declares legitimate."""
    return st.get("in_flight", {}).get((step or {}).get("id"))
