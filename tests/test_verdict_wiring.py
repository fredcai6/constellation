"""`verdict_fold` wired: the seven sites that read a panel's verdict, driven
through real runs rather than proved against hand-built returns.

`tests/test_verdict_fold.py` holds the fold's own logic in isolation. This
file is the other half -- the fold is now the only one there is, so what a
seam does with `("clean", word)`, `("refused", tag)` and `("quiet", None)`
is a question about real journals, real assemblies and real panelist forms,
and every case below drives one. The differential test that used to stand
between them (the fold's word against `merged_verdict`'s) went out with
`merged_verdict`; these are what replaced it.

Three things a refusal is, and all three arrive here the same way. A word
the panelist's own form does not declare; a form path that is no longer in
the tree, which is the same unreadable vocabulary reached from the other
side; and -- distinct from both -- a panel whose form declares no verdict
field at all, which is quiet, never refused.

A foreign verdict word cannot reach a journal through a panelist's own
submit: `_check_vocabulary` refuses it there, which
`test_verdict_panels.py::test_a_verdict_outside_the_vocabulary_refuses_at_the_panelists_submit`
already pins. That guard is the first of two on the same word, and this
file is the second -- what happens to a return that is in the append-only
journal already when the form's own note is reworded under it. So where a
foreign word is wanted below it is appended as the return entry it would be
by then, the same way `test_returns.py` and `test_dispatch_wiring.py`
already build a panel's returns directly.
"""

import pathlib
import tomllib

from engine import cli, journal, render, review_yield, run as runmod
from gitremote import stub_gh
from test_nesting import _fill_close, _fill_gate_close, _response
from test_two_voices import _dispatch_critic, _fill_consolidate, _fill_open, _fill_spec
from test_verdict_panels import (
    _fill_implement, _fill_review, _fill_route, _open_gate, _open_panelist,
    _review_step, _select,
)

CRITIC = "skills/critic/forms/CRITIC.toml"
# The rename this whole issue exists to make free, seen from the fold's side:
# a path a journal already names and the tree no longer has.
GONE = "skills/critic/forms/CRITIC_RENAMED_AWAY.toml"


def _fill(path, text):
    path.write_text(text)


# -- run-an-issue's consolidate: a two-voices seam, three critics -----------


def _to_the_consolidate_panel(wid="issue19"):
    """run-an-issue driven to its own consolidate seam and left standing on
    it: the board answered, the spec-writer's round submitted, three critics
    dispatched and nothing yet returned."""
    cli.main(["open", "run-an-issue", "--issue", "19", "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    board = pathlib.Path(f".agent-work/{wid}/UNDERSTAND.toml")
    board.write_text(board.read_text().replace(
        'status = "open"', 'status = "answered"\nanswer = "settled."'))
    _fill_spec(wid)
    cli.main([wid, "submit"])
    assert runmod.state(wid)["current"]["id"] == "understand"
    return wid


def test_a_word_consolidates_own_critics_do_not_declare_holds_the_seam_and_names_that_voice(
        workdir, capsys):
    """Covering item 1. Two critics answer the table's own inert word and a
    third answers one CRITIC.toml declares nowhere. The seam stays open --
    a refusal is never released past the conductor whose form is standing
    there -- and the room names the voice rather than reporting a word it
    could not read or the clean word its co-panelists returned.

    That last part is what the refusal has to outrank: two clean `pass`
    returns beside one unreadable, and a fold that took a majority, or the
    first clean word it found, would report `pass` on a round nobody has
    read."""
    wid = _to_the_consolidate_panel()
    _dispatch_critic(wid, "understand", verdict="pass", n=1)
    _dispatch_critic(wid, "understand", verdict="pass", n=2)
    journal.append(wid, "return", step="understand", child=f"{wid}.understand.p3",
                   fields={"findings": "waived: clean", "verdict": "sound"})
    capsys.readouterr()

    st = runmod.state(wid)
    assert st["current"]["id"] == "understand"
    assert st["current"]["form"] == "forms/CONSOLIDATE.toml"
    assert "understand" not in st["done"]

    asm = runmod.load_assembly("run-an-issue")
    assert cli._returned_verdict(st, asm) == "unreadable p3"

    cli.main([wid])
    assert "unreadable p3" in capsys.readouterr().out


def test_the_same_seam_with_every_critic_clean_routes_exactly_as_it_did(workdir, capsys):
    """Covering item 3, a regression: the rewiring left the ordinary path
    alone. Three critics answer `revise` -- a word CRITIC.toml declares and
    consolidate's own table resolves -- and the seam behaves as it did
    before `verdict_fold` reached it: the step holds for CONSOLIDATE.toml,
    the room reports no refusal, and the conductor's own `incorporate` (one
    look, 2026-09-25 -- `rework` is gone from this table) is what mints the
    fresh spec-writer round.

    The room's line is `""` rather than the word itself, because
    consolidate declares both of the panel's words `release` (ruling 3's
    2026-09-03 follow-up) and an inert word is the quiet class the room has
    always suppressed. What matters here is that it is not `unreadable`:
    every clean word this seam can be answered with resolves through the
    table, exactly as it did."""
    wid = _to_the_consolidate_panel()
    for n in (1, 2, 3):
        _dispatch_critic(wid, "understand", verdict="revise",
                         findings="gap: the settle field is thin", n=n)
    capsys.readouterr()

    st = runmod.state(wid)
    asm = runmod.load_assembly("run-an-issue")
    assert st["current"]["id"] == "understand"
    room = cli._returned_verdict(st, asm)
    assert "unreadable" not in room
    assert room == ""

    _fill_consolidate(wid, resolution="incorporate")
    cli.main([wid, "submit"])
    capsys.readouterr()

    st = runmod.state(wid)
    fresh = [s for s in st["steps"]
            if s["segment"] == "understand" and s.get("source") == "mint"]
    assert fresh, "the conductor's own incorporate minted no fresh round"
    assert st["current"]["id"] == fresh[0]["id"]


# -- explore-an-idea's spec: the panel-only seam ----------------------------


def _to_the_spec_panel(capsys):
    """explore-an-idea driven to its own spec panel -- the one seam left in
    the tree with no conductor form behind it, so the panel's own word is
    the whole ruling."""
    cli.main(["open", "explore-an-idea", "--title", "memory graph"])
    wid = capsys.readouterr().out.split()[1]
    _fill(_response(wid), 'idea = "x"\nauthority = "Tommy"\n'
                            '[[seeds]]\nidea = "the itch"\n')
    cli.main([wid, "submit"])
    _fill(_response(wid), 'consolidation = "c"\ndecision = "converge"\n')
    cli.main([wid, "submit"])
    pathlib.Path("SPEC.md").write_text("1. the spec.\n")
    _fill(_response(wid), 'spec = "SPEC.md"\nrivals = "waived: none"\nkey-terms = "waived: none"\n')
    cli.main([wid, "submit"])
    return wid, runmod.state(wid)["current"]["id"]


def _dispatch_spec_critic(wid, step_id, n, verdict, findings="gap: no point"):
    cli.main(["open", "give-a-verdict", "--parent", wid, "--step", f"{step_id}.p{n}"])
    critic = f"{wid}.{step_id}.p{n}"
    _fill(_response(critic), f'findings = "{findings}"\nverdict = "{verdict}"\n')
    cli.main([critic, "submit"])
    cli.main([critic, "close"])
    return critic


def test_a_refusal_at_the_panel_only_seam_mints_nothing_and_still_closes(workdir, capsys):
    """Covering item 4. explore-an-idea's spec transition is the one seam
    whose panel word acts by itself -- `revise` declares `rework`, so a
    revising round mints the next one with no conductor in between. A
    refusal among the voices is not that word and is not any word, so
    nothing is minted; and because a panel-only step's own `done` never
    depended on the verdict in the first place, the run walks on exactly as
    a clean release round would leave it. `awaiting_close` is reached and
    `close` succeeds.

    What changes is only the record. The room and the close summary each
    name the refusing voice in place of the word a clean pass would have
    shown -- one convention, written once in `run.verdict_record`, not one
    spelling per surface.

    The review yield is the third surface that convention is for, and it
    does not reach this seam: `seam_rounds` matches a round by its seam's
    own disposing form, and this seam has none, so a panel-only round is
    invisible to the yield today. That is unchanged by this gate and pinned
    here rather than left to be discovered -- `test_review_yield.py`'s own
    docstring already records the same seam as the one it never exercises.
    The yield's own refusal rendering is driven at run-a-gate's review
    below, where a round does reach it."""
    wid, panel = _to_the_spec_panel(capsys)
    journal.append(wid, "return", step=panel, child=f"{wid}.{panel}.p1",
                   fields={"findings": "waived: clean", "verdict": "sound"})
    _dispatch_spec_critic(wid, panel, 2, "pass", findings="none: waived: clean")
    _dispatch_spec_critic(wid, panel, 3, "pass", findings="none: waived: clean")
    capsys.readouterr()

    st = runmod.state(wid)
    asm = runmod.load_assembly("explore-an-idea")
    assert panel in st["done"]
    assert not any(s["segment"] == "spec" and s.get("source") == "mint"
                   for s in st["steps"]), "a refusal minted a fresh round"
    assert st["current"]["form"] == "forms/CLOSE.toml"

    assert cli._returned_verdict(st, asm) == "unreadable p1"
    assert cli._summary(st)["verdict"] == "unreadable p1"
    assert review_yield.run_yield(wid) == []

    _fill(_response(wid), 'confirmed = "Tommy: yes, cut it"\nrouted = "issue 81"\n'
          'residue = "waived: none"\n')
    cli.main([wid, "submit"])
    assert runmod.state(wid)["awaiting_close"]
    cli.main([wid, "close"])
    capsys.readouterr()
    assert runmod.state(wid)["closed"]


def test_the_same_seam_with_every_voice_revising_still_mints_a_fresh_round(workdir, capsys):
    """Covering item 5, a regression beside item 4: the panel's own acting
    word still acts. Three critics answer `revise`, whose row at this seam
    declares `rework`, and the fresh REWORK round mints off the panel alone
    exactly as it did before the fold reached `_act_on_verdicts`."""
    wid, panel = _to_the_spec_panel(capsys)
    for n in (1, 2, 3):
        _dispatch_spec_critic(wid, panel, n, "revise")
    capsys.readouterr()

    st = runmod.state(wid)
    assert st["current"]["form"] == "forms/REWORK.toml"
    assert "gap: no point" in st["current"]["prefill"]["findings"]


# -- run-a-gate's review: a refusal in a run's history, and the yield ------


def test_a_refused_round_reaches_the_close_summary_and_the_review_yield(workdir, capsys):
    """Covering items 6 and 7. A gate whose first review round ruled clean
    and whose second could not be read, then closed: the close summary
    reports the refusal and the voice, never the clean word the earlier
    round left behind, and the review yield renders the same two words at
    the same round through `render._yield_round`.

    `_summary` walks every panel-bearing step in journal order with the last
    one winning, so a stale word is exactly the failure available here: the
    round that in fact settled nothing is the last one, and reporting `pass`
    for it would be reporting a ruling the gate never got."""
    _open_gate()
    first = _review_step("g1")
    panelist = _open_panelist("g1", first)
    _fill_review(panelist, "pass")
    cli.main([panelist, "submit"])
    cli.main([panelist, "close"])
    _fill_route("g1", "rework")
    cli.main(["g1", "submit"])

    _fill_implement("g1")
    cli.main(["g1", "submit"])
    second = _select("g1")
    journal.append("g1", "return", step=second, child=f"g1.{second}.p1",
                   fields={"verify": "read the diff", "findings": "waived: clean",
                           "verdict": "sound"})
    capsys.readouterr()

    st = runmod.state("g1")
    asm = runmod.load_assembly("run-a-gate")
    assert st["current"]["id"] == second, "the refused round released the seam"
    assert cli._returned_verdict(st, asm) == "unreadable p1"
    assert cli._summary(st)["verdict"] == "unreadable p1"

    entries = review_yield.run_yield("g1")
    rounds = next(e for e in entries if e["label"] == "review")["rounds"]
    assert [r["verdict"] for r in rounds] == ["pass", "unreadable p1"]
    table = render.review_yield(entries)
    assert "r2  unreadable p1" in table

    _fill_route("g1", "close")
    cli.main(["g1", "submit"])
    _fill_gate_close("g1")
    cli.main(["g1", "submit"])
    capsys.readouterr()
    cli.main(["g1", "close"])
    out = capsys.readouterr().out
    assert "unreadable p1" in out
    assert runmod.state("g1")["closed"]


# -- the yield's own head line, under a table whose words were renamed -----


# A critic's own form with the seam's two words renamed: CRITIC.toml's shape,
# `go | stop` in place of `pass | revise`. Written to disk, and reached
# through an assembly-relative ref, because `run.panel_forms` reads the path
# the step's own panel entry names -- which is what makes this a real read
# rather than a dict handed straight to the fold.
RENAMED_CRITIC = """
[[field]]
id = "findings"
kind = "evidence"
note = "One per finding. None found: waived: clean."

[[field]]
id = "verdict"
kind = "decision"
note = "go | stop. The seam's two words, renamed together."
"""


def _renamed_consolidate(tmp_path):
    """run-an-issue's consolidate seam with its own table and its panelists'
    own vocabulary renamed together -- the rename this issue exists to make
    free, which no seam in the tree can be driven under without editing
    `skills/`. `go` releases; `stop` is the row that acts -- the conductor's
    own `incorporate` (one look, 2026-09-25; `rework` is no longer a row on
    this table at all)."""
    (tmp_path / "RENAMED_CRITIC.toml").write_text(RENAMED_CRITIC)
    asm = runmod.load_assembly("run-an-issue")
    asm["dir"] = tmp_path
    seg = next(s for s in asm["segment"] if s["id"] == "understand")
    rows = seg["transition"]["outcome"]
    next(o for o in rows if o["value"] == "pass")["value"] = "go"
    next(o for o in rows if o["value"] == "incorporate")["value"] = "stop"
    return asm, seg


def _renamed_round(tmp_path, words):
    """One consolidate round under that renamed seam, through
    `review_yield.seam_rounds` -- the same threading `run_yield` does, with
    the assembly it already computes per child state."""
    asm, seg = _renamed_consolidate(tmp_path)
    step = {"id": "understand", "segment": "understand",
            "form": "forms/CONSOLIDATE.toml",
            "panel": [{"form": "RENAMED_CRITIC.toml"} for _ in words]}
    st = {"steps": [step], "done": {}, "returns": {"understand": [
        {"child": f"w.understand.p{n}",
         "fields": {"findings": "none: waived: clean", "verdict": word}}
        for n, word in enumerate(words, start=1)]}}
    rounds = review_yield.seam_rounds(st, seg, asm)
    assert len(rounds) == 1
    return rounds[0]


def test_the_yields_tally_and_its_head_line_read_the_table_not_the_word_revise(
        workdir, tmp_path):
    """Covering item 11, both halves.

    `_round`'s `revising` count is the seam's own table read per voice -- a
    voice whose word declares anything but the inert `release` is a voice
    sending the round back -- so renaming that row's value and the critics'
    own note together moves the tally with them. The literal comparison this
    replaced (`leading_word(...) == "revise"`) would read zero here, on a
    round two of three voices sent back.

    And one hop further than `_round`: the head line `render._yield_round`
    prints is the round's own verdict record, so it prints the renamed word
    too. A `"pass"` fallback for the not-revising branch -- a bare string
    literal that nothing compares against, which item 8's own `Eq`/`NotEq`
    sweep cannot see by construction -- would satisfy every other check in
    this file and still print the wrong word at every seam whose passing
    value was ever renamed. Asserting neither `pass` nor `revise` appears in
    the rendered table at all is what closes that."""
    rnd = _renamed_round(tmp_path, ["stop", "stop", "go"])
    assert rnd["verdict"] == "stop"
    assert rnd["revising"] == 2

    table = render.review_yield([{"label": "consolidate", "rounds": [rnd]}])
    assert "r1  2 stop" in table
    assert "pass" not in table and "revise" not in table


def test_the_yields_head_line_names_a_refusal_rather_than_falling_back_to_a_word(
        workdir, tmp_path):
    """The other half of the same head line, at the same renamed seam: a
    voice whose word neither the form nor the table declares renders as the
    refusal it is, naming that voice, and the count in front of it is
    dropped rather than printed as a zero. Nothing here can fall back to a
    remembered word, because there is no word to fall back to."""
    rnd = _renamed_round(tmp_path, ["go", "sound"])
    assert rnd["verdict"] == "unreadable p2"
    assert rnd["revising"] == 0

    table = render.review_yield([{"label": "consolidate", "rounds": [rnd]}])
    assert "r1  unreadable p2" in table
    assert "pass" not in table and "revise" not in table


# -- a panelist form path that is no longer in the tree ---------------------


def test_a_missing_panel_form_on_the_current_step_is_named_not_raised(workdir, capsys):
    """Covering item 12(a). A journal is append-only, so a step dispatched
    under a form path outlives that path's rename -- the ordinary, correct
    change `cli._load_form` already guards a step's own form against, for
    the reason its own comment records (a bare `forms.load` once left a real
    run dead with an uncaught `FileNotFoundError`). `run.panel_forms` is the
    same guard for a panelist's path, and it has to be: it runs inside
    `state()`'s own journal fold, which is the first thing every command
    does.

    So the command succeeds, and the voice whose form cannot be read is
    named exactly as a voice whose word cannot be read is -- one outcome,
    not two."""
    wid = _to_the_consolidate_panel()
    for n in (1, 2, 3):
        _dispatch_critic(wid, "understand", verdict="pass", n=n)
    capsys.readouterr()

    # the rename, seen from the fold's side: the entry keeps naming the path
    # it was dispatched under, and the path is gone. Only the first voice's,
    # so the refusal has a voice to name rather than being panel-wide.
    jp = journal.journal_path(wid)
    jp.write_text(jp.read_text().replace(f'form = "{CRITIC}"', f'form = "{GONE}"', 1))

    st = runmod.state(wid)
    assert st["current"]["id"] == "understand"
    asm = runmod.load_assembly("run-an-issue")
    assert cli._returned_verdict(st, asm) == "unreadable p1"

    cli.main([wid])
    assert "unreadable p1" in capsys.readouterr().out


def test_a_missing_panel_form_on_a_superseded_step_does_not_walk_the_run_backwards(
        workdir, capsys):
    """Covering item 12(b), the case the obvious construction misses.

    `state()` re-derives every historical two-voices step's own `done` on
    every fold, and a step the panel itself folded shut carries no later
    submit to re-affirm it. So resolving a missing panelist path straight to
    a refusal, with no further care, would newly read that ancient return as
    unreadable, hold the step open again and walk `current` back to it:
    `awaiting_close` goes false and `cmd_close`'s own pending list names a
    step the run finished long ago. That is the crash's silent twin -- a
    routine rename permanently damaging a run's readability -- and it is
    exposure this gate itself creates, since the pre-gate fold never read a
    panelist's form path at all.

    The journal is built here rather than driven, because no seam in the
    tree can produce one: every two-voices seam declares both of its panel's
    words `release`, so none of them folds shut on the panel alone today.
    The run below is what one would look like -- an earlier seam closed by
    its panel with no conductor submit behind it, a later seam judged and
    disposed of, and a close form waiting. The command driven against it is
    real, and its target is the later step, never the superseded one."""
    wid = "issue80"
    journal.append(wid, "run", title="t", assembly="run-an-issue")
    journal.append(wid, "step", id="understand", segment="understand", anchor=True,
                   form="forms/CONSOLIDATE.toml",
                   panel=[{"form": GONE}, {"form": GONE}, {"form": GONE}])
    journal.append(wid, "step", id="plan", segment="plan", anchor=True,
                   form="forms/PLAN_TO_EXECUTE.toml", panel=[{"form": CRITIC}])
    journal.append(wid, "step", id="close", segment="close", anchor=True,
                   terminal=True, form="forms/CLOSE.toml")
    for n in (1, 2, 3):
        journal.append(wid, "return", step="understand", child=f"{wid}.understand.p{n}",
                       fields={"findings": "waived: clean", "verdict": "pass"})
    journal.append(wid, "return", step="plan", child=f"{wid}.plan.p1",
                   fields={"findings": "waived: clean", "verdict": "pass"})
    journal.append(wid, "submit", step="plan", fields={"resolution": "pass"})

    st = runmod.state(wid)
    assert "understand" in st["done"], "a rename reopened a superseded step"
    assert st["current"]["id"] == "close"
    # `cmd_close`'s own pending computation, read the way it reads it
    assert [s["id"] for s in st["steps"] if s["id"] not in st["done"]] == ["close"]

    journal.append(wid, "submit", step="close", fields={"outcome": "shipped"})
    st = runmod.state(wid)
    assert st["awaiting_close"] and st["current"] is None

    cli.main([wid, "close"])
    capsys.readouterr()
    assert runmod.state(wid)["closed"]


# -- a quiet panel: quiet is not a stale word --------------------------------


def test_the_design_panels_own_round_reports_nothing_rather_than_a_stale_word(
        workdir, capsys, monkeypatch):
    """Covering item 13. A panel whose voices are dispatched under a form
    declaring no `verdict` field at all folds to `("quiet", None)` -- not a
    refusal, and not a word. design-it-twice's rival-planner panel (ruling
    10, shelved -- #96) was the tree's one live example of this shape,
    dispatched under PLAN.toml; the panel-only step here is hand-built into
    the journal directly instead (the same way the missing-panel-form test
    above builds its own run), since nothing left in the tree mints one.

    `_summary` is the one site that reaches it: `seam_rounds` visits only
    segments `_seam_segments` admits, and a panel-only interior step is
    neither a paneled transition nor a route-form segment, so the review
    yield structurally never sees a quiet round. `_summary` has no such
    filter -- it walks every panel-bearing step in journal order with the
    last one winning -- and this run closes with the hand-built quiet panel
    as its last judged round, which is an ordinary journal order rather than
    a contrived one (a rival-planner round recurred on every rework, before
    it was shelved).

    Two failures are available at that combination and this rules out both:
    rendering the `("quiet", None)` tuple as a string, and carrying the
    understand panel's own clean `pass` forward past a round that settled
    nothing about a verdict."""
    wid = "issue13"
    journal.append(wid, "run", title="t", assembly="run-an-issue")
    journal.append(wid, "step", id="understand", segment="understand", anchor=True,
                   form="forms/CONSOLIDATE.toml",
                   panel=[{"form": CRITIC}, {"form": CRITIC}, {"form": CRITIC}])
    journal.append(wid, "step", id="plan-1", segment="plan",
                   panel=[{"form": "skills/planner/forms/PLAN.toml"}])
    journal.append(wid, "step", id="close", segment="close", anchor=True,
                   terminal=True, form="forms/CLOSE.toml")
    for n in (1, 2, 3):
        journal.append(wid, "return", step="understand", child=f"{wid}.understand.p{n}",
                       fields={"findings": "waived: clean", "verdict": "pass"})
    journal.append(wid, "submit", step="understand",
                   fields={"resolution": "pass", "spec": f".agent-work/{wid}/spec.md",
                           "key-terms": "waived: none", "settle": "waived: none"})

    st = runmod.state(wid)
    assert st["current"]["id"] == "plan-1"
    assert cli._summary(st)["verdict"] == "pass", \
        "the understand panel's own clean word is the stale one available here"

    # the design panel's own single dispatch returns with no `verdict` field
    # at all (PLAN.toml declares none) -- quiet, and the step completes on it
    journal.append(wid, "return", step="plan-1", child=f"{wid}.plan-1.p1", fields={})
    capsys.readouterr()

    st = runmod.state(wid)
    assert "plan-1" in st["done"]
    assert cli._summary(st)["verdict"] == ""

    # and it survives the close, which is where the tuple would have been
    # rendered as a string if anything rendered it at all. This run has no
    # real worktree behind it (built straight into the journal, the same as
    # the missing-panel-form test above), so `close` leaves its record in
    # place rather than archiving it -- `state()["closed"]` is what the
    # sibling test above reads for the identical reason.
    _fill_close(wid)
    cli.main([wid, "submit"])
    capsys.readouterr()

    stub_gh(monkeypatch)
    cli.main([wid, "close"])
    capsys.readouterr()
    st = runmod.state(wid)
    assert st["closed"]
    entries = tomllib.loads((journal.location(wid) / "journal.toml").read_text())["entry"]
    closed = next(e for e in entries if e.get("kind") == "closed")
    assert closed["summary"]["verdict"] == ""
