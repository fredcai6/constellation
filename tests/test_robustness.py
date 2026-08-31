"""Ways the engine could lose or corrupt the record.

Every case here was found by a fresh-context reviewer probing the running system, not
by the suite that was green at the time. The secretary's one duty is to keep
the record; each of these broke that duty silently.
"""

import pathlib
import tomllib

import pytest

from engine import checks, cli, forms, journal, render, run as runmod, tomlw
from gitremote import init_checkout


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONSTELLATION_SESSION", "test-session")
    init_checkout(tmp_path)
    return tmp_path


def _open(wid="issue17"):
    cli.main(["open", "run-an-issue", "--id", wid, "--title", "t"])


def _issue_file(wid="issue17"):
    """The `issue` field names a file in the work location. Write it, and
    return the path the form points at."""
    path = pathlib.Path(f".agent-work/{wid}/issue.md")
    path.write_text("The parser drops the last record of a file with no "
                    "trailing newline.\n")
    return path


def _asm():
    """An assembly declaring no outcomes, so `_check_vocabulary` is the only
    enforcer -- the case this test is about."""
    return {"segment": [{"id": "s", "transition": {}}]}


def _step():
    return {"segment": "s", "form": "SYNTHETIC.toml"}


def tmp_form(workdir, body):
    """A form on disk, for a shape the corpus does not have and should not
    gain just to be tested against."""
    path = workdir / "SYNTHETIC.toml"
    path.write_text(body)
    return str(path)


def test_a_torn_journal_reads_as_the_work_before_the_tear(workdir, capsys):
    """An append interrupted mid-block -- Ctrl-C, OOM, full disk -- must not
    brick every verb on the run. State is a fold over this file, so a raising
    read would make the run unusable until someone hand-repaired TOML."""
    _open()
    capsys.readouterr()
    before = len(journal.read("issue17"))

    with open(".agent-work/issue17/journal.toml", "a") as f:
        f.write('\n[[entry]]\nkind = "note"\nat = "2026-08-24T0')

    assert len(journal.read("issue17")) == before   # the torn tail is dropped
    cli.main(["issue17"])                            # and every verb still works
    assert "issue17" in capsys.readouterr().out
    cli.main(["issue17", "note", "observation", "still usable"])


def test_a_malformed_plan_field_refuses_before_anything_is_recorded(workdir, capsys):
    """A plan field of the wrong shape used to journal the submit and then die
    minting, leaving a run that looked advanced with no work in it."""
    _open()
    pathlib.Path(".agent-work/issue17/OPEN.toml").write_text(
        f'issue = "{_issue_file()}"\nauthority = "Tommy."\n'
        'questions = "not a list of blocks"\n')
    capsys.readouterr()

    with pytest.raises(SystemExit) as e:
        cli.main(["issue17", "submit"])
    assert "questions" in str(e.value)
    assert "nothing was recorded" in str(e.value)

    st = runmod.state("issue17")
    assert st["current"]["id"] == "open"                 # did not advance
    assert "open" not in st["done"]                      # and nothing was journaled
    assert not st["boards"]


def _pass_spec(wid="issue17"):
    """Take the spec-writer's own round through its cold panel, board rows
    left untouched -- so the transition ahead (consolidate) is reachable to
    prove what it alone still checks: the board, not the spec."""
    loc = pathlib.Path(f".agent-work/{wid}")
    (loc / "spec.md").write_text("1. placeholder commitment.\n")
    (loc / "SPEC.toml").write_text('spec = "%s/spec.md"\n' % loc)
    cli.main([wid, "submit"])
    panel = next(s for s in runmod.state(wid)["steps"] if s["id"] == "understand")["panel"]
    for n in range(1, len(panel) + 1):
        tag = f"understand.p{n}"
        cli.main(["open", "give-a-verdict", "--parent", wid, "--step", tag])
        panelist = f"{wid}.{tag}"
        (journal.location(panelist) / "CRITIC.toml").write_text(
            'findings = "none: waived: clean"\n'
            'vocabulary = "waived: consistent"\nverdict = "pass"\n')
        cli.main([panelist, "submit"])
        cli.main([panelist, "close"])


def _critic_step(wid="c1"):
    """A run standing on one CRITIC.toml -- the cheapest way to reach a field
    a decision field's note declares, with no panel plumbing in the way."""
    journal.append(wid, "run", title="t", assembly="give-a-verdict")
    journal.append(wid, "step", id="verdict", segment="verdict",
                   form="skills/critic/forms/CRITIC.toml", filler="reviewer",
                   anchor=True, terminal=True, validates="", source="open")
    cli.main([wid])                      # materializes the response template
    return wid


def _fill_critic(wid, verdict):
    pathlib.Path(f".agent-work/{wid}/CRITIC.toml").write_text(
        'findings = "none: waived: clean"\nvocabulary = "waived: consistent"\n'
        f'verdict = "{verdict}"\n')


def test_a_value_outside_a_fields_vocabulary_refuses_and_names_it(workdir, capsys):
    """A decision field used to take anything its note did not list: the
    submit landed, the step was released, and the act downstream matched no
    branch and performed nothing. The refusal names the field and quotes the
    alternatives the note already taught."""
    _critic_step()
    _fill_critic("c1", "looks good to me")
    capsys.readouterr()

    before = len(journal.read("c1"))
    with pytest.raises(SystemExit) as e:
        cli.main(["c1", "submit"])
    msg = str(e.value)
    assert "verdict" in msg
    assert "pass | revise" in msg          # the note's own list
    assert len(journal.read("c1")) == before          # not even the submit landed
    assert not runmod.state("c1")["done"]

    # what the acts do read is the leading word, in any case -- so a declared
    # word carrying its reason is the value, not a near-miss, and the sentence
    # rides along into the record rather than having to be left out to be read
    _fill_critic("c1", "Pass, nothing here would change what gets built")
    cli.main(["c1", "submit"])
    landed = runmod.state("c1")["done"]["verdict"]["fields"]["verdict"]
    assert landed == "Pass, nothing here would change what gets built"


def test_a_near_miss_verb_refuses_instead_of_rendering_the_room(workdir, capsys):
    """`spine <id> sumbit` fell through to `status`: it rendered the room and
    exited 0, so a typo read as a successful hand-in."""
    _open()
    capsys.readouterr()

    with pytest.raises(SystemExit) as e:
        cli.main(["issue17", "sumbit"])
    msg = str(e.value)
    assert "sumbit" in msg and "submit" in msg        # names the miss and the verbs
    assert not capsys.readouterr().out                # and rendered no room
    assert "open" not in runmod.state("issue17")["done"]

    cli.main(["issue17"])                             # the bare id is still status
    assert "issue17" in capsys.readouterr().out


def test_an_unhandled_mints_value_refuses_instead_of_minting_nothing(workdir, capsys,
                                                                     monkeypatch):
    """`_mint` accepts `_BOARD_MINT` ("board rows") plus whatever `_mintable`
    derives from the assembly's own `dispatches` segments -- no engine-held
    list of names. A form declaring a value outside that set minted nothing
    and released the step anyway -- a run that looks advanced with no work
    in it, which is what the plan check exists to prevent. Refused before
    the submit is journaled, like its sibling."""
    real = forms.load

    def third_thing(path):
        form = real(path)
        for f in form["fields"]:
            if f.get("mints"):
                f["mints"] = "prophecies"
        return form

    monkeypatch.setattr(forms, "load", third_thing)
    _open()
    pathlib.Path(".agent-work/issue17/OPEN.toml").write_text(
        f'issue = "{_issue_file()}"\nauthority = "Tommy."\n\n[[questions]]\n'
        'question = "which inputs drop the last record?"\ntype = "fact"\n')
    capsys.readouterr()

    before = len(journal.read("issue17"))
    with pytest.raises(SystemExit) as e:
        cli.main(["issue17", "submit"])
    msg = str(e.value)
    assert "prophecies" in msg and "board rows" in msg
    assert len(journal.read("issue17")) == before
    st = runmod.state("issue17")
    assert st["current"]["id"] == "open" and not st["boards"]


def test_amended_step_ids_do_not_collide(workdir):
    """Ids were counted from what exists, so two sessions amending at once
    minted the same id -- and `done` is keyed by id, so one submit would
    complete every step sharing it, silently dropping the rest."""
    _open()
    for i in range(6):
        cli.main(["issue17", "amend", "add", "--segment", "plan", "--form",
                  "forms/PLAN.toml", "--reason", f"r{i}"])
    ids = [s["id"] for s in runmod.state("issue17")["steps"] if "-a" in s["id"]]
    assert len(ids) == len(set(ids)) == 6


def test_note_ids_do_not_collide_and_resumed_clears_its_block(workdir, capsys):
    """`note resumed <id>` is the command the engine prints in its own output;
    it recorded the target under the wrong key and never cleared anything."""
    _open()
    cli.main(["issue17", "note", "blocked", "needs a ruling"])
    st = runmod.state("issue17")
    block = runmod.blocks(st)[0]
    assert block["text"] == "needs a ruling"

    cli.main(["issue17", "note", "resumed", block["id"], "Tommy ruled"])
    assert runmod.blocks(runmod.state("issue17")) == []

    capsys.readouterr()
    cli.main(["issue17"])
    assert "BLOCKED" not in capsys.readouterr().out


def test_a_work_id_cannot_escape_the_work_tree(workdir):
    # an omitted --id legitimately mints one, so "" is not in this list
    for bad in ["../../escape", "a/b", "..", "a..b", "/abs/path", "x/../../y"]:
        with pytest.raises(SystemExit):
            cli.main(["open", "run-an-issue", "--id", bad, "--title", "t"])
    assert not list(workdir.glob("escape*"))
    assert not (workdir.parent / "escape").exists()


def test_a_hanging_check_refuses_instead_of_wedging_the_turn(workdir, monkeypatch):
    """A check command that never returns used to block forever, burning the
    agent's turn with no way out.

    The number it hangs against is now the budget rather than the one
    `CHECK_TIMEOUT` held: past the handback the check is handed back and the
    step stays open, and only the budget says the command is broken. So this
    is the same test against the number that still refuses."""
    monkeypatch.setattr(checks, "BUDGET", 1)
    pathlib.Path("constellation.toml").write_text('[models]\nstandard = "x"\n')
    cli.main(["open", "run-a-gate", "--id", "g1"])
    journal.append("g1", "prefill", fields={"proof": "sleep 30"})
    pathlib.Path(".agent-work/g1/IMPLEMENT.toml").write_text(
        'change = "c"\ndeviations = "waived: none"\n')

    with pytest.raises(SystemExit) as e:
        cli.main(["g1", "submit"])
    msg = str(e.value)
    assert "did not finish" in msg
    assert "amend close" in msg  # the refusal states the way out


def test_closing_to_a_missing_parent_does_not_fabricate_one(workdir, capsys):
    """The return used to create the parent's journal from nothing: a run with
    no opening, no title, no assembly, sitting in the ledger."""
    _open("issue17")
    journal.append("issue17", "step", id="g1", segment="execute",
                   dispatches="run-a-gate", prefill={"purpose": "p"},
                   child="issue17.g1", source="mint")
    cli.main(["open", "run-a-gate", "--parent", "issue17", "--step", "g1"])
    child = "issue17.g1"
    pathlib.Path(f".agent-work/issue17/g1/IMPLEMENT.toml").write_text(
        'change = "c"\ndeviations = "waived: none"\n')
    cli.main([child, "submit"])
    # select the panel, then drive it for real: one panelist, a pass verdict
    from test_nesting import _select_panel
    _select_panel(child)
    review = runmod.state(child)["current"]["id"]
    cli.main(["open", "give-a-verdict", "--parent", child, "--step", f"{review}.p1"])
    panelist = f"{child}.{review}.p1"
    pathlib.Path(f".agent-work/issue17/g1/{review}/p1/REVIEW.toml").write_text(
        'verify = "read it"\nfindings = "none: waived: clean"\n'
        'vocabulary = "waived: consistent"\nverdict = "pass"\n')
    cli.main([panelist, "submit"])
    cli.main([panelist, "close"])
    # a pass releases nothing on its own now: the round is disposed of on the
    # review step's own conductor form, which is what walks the gate to close
    pathlib.Path(f".agent-work/issue17/g1/ROUTE.toml").write_text(
        'resolution = "close"\n')
    cli.main([child, "submit"])
    pathlib.Path(f".agent-work/issue17/g1/GATE_CLOSE.toml").write_text(
        'commit = "refuse-or-name-the-escape @ 0000000"\nresidue = "waived: none"\n')
    cli.main([child, "submit"])

    # the parent's record disappears -- a wiped worktree, a bad cleanup
    pathlib.Path(".agent-work/issue17/journal.toml").unlink()
    capsys.readouterr()

    cli.main([child, "close"])
    assert "not found" in capsys.readouterr().out
    assert not journal.exists("issue17")          # no phantom parent minted
    assert runmod.blocks(runmod.state(child))     # the undelivered return is a block


def test_the_off_path_never_shows_a_traceback(workdir):
    """A fresh agent meets these by mistyping. Each must answer with the way
    forward, not a Python line number."""
    for argv, want in [
        (["open"], "assemblies:"),
        (["open", "bogus", "--title", "t"], "no assembly named"),
        (["nosuchrun"], "no run named"),
    ]:
        with pytest.raises(SystemExit) as e:
            cli.main(argv)
        assert want in str(e.value)


def test_a_near_miss_note_kind_refuses_instead_of_no_opping(workdir):
    """`note block ...` printed success and did nothing -- only the exact word
    is ever acted on, so a near miss must not look like a hit."""
    _open()
    with pytest.raises(SystemExit) as e:
        cli.main(["issue17", "note", "block", "oops"])
    assert "blocked" in str(e.value)


def test_status_names_the_board_it_will_validate(workdir, capsys):
    """The board was invisible in status while the imperative claimed it was
    already worked -- the room description lying about the room."""
    _open()
    pathlib.Path(".agent-work/issue17/OPEN.toml").write_text(
        f'issue = "{_issue_file()}"\nauthority = "T."\n'
        '[[questions]]\nquestion = "q?"\ntype = "fact"\n')
    cli.main(["issue17", "submit"])
    capsys.readouterr()
    _pass_spec()
    capsys.readouterr()
    cli.main(["issue17"])
    out = capsys.readouterr().out
    assert "UNDERSTAND.toml" in out
    assert "will not pass while a row is open" in out


def test_every_refusal_states_an_escape_that_works(workdir):
    """A refusal used to append one hardcoded suffix -- correct for a form
    field, wrong for a board row (which takes deferred:, not waived:), and
    nonsensical for a lookup. Printing an escape that does not work is worse
    than printing none."""
    _open()
    pathlib.Path(".agent-work/issue17/OPEN.toml").write_text(
        f'issue = "{_issue_file()}"\nauthority = "T."\n'
        '[[questions]]\nquestion = "q?"\ntype = "fact"\n')
    cli.main(["issue17", "submit"])
    _pass_spec()
    pathlib.Path(".agent-work/issue17/CONSOLIDATE.toml").write_text(
        'spec = ".agent-work/issue17/spec.md"\nkey-terms = "waived: none"\n'
        'settle = "waived: none"\n')

    with pytest.raises(SystemExit) as e:
        cli.main(["issue17", "submit"])
    msg = str(e.value)
    assert "deferred:" in msg
    assert "waived:" not in msg   # the escape boards.validate does not accept

    with pytest.raises(SystemExit) as e:
        cli.main(["issue17", "amend", "close", "nosuch", "--reason", "r"])
    assert "pending:" in str(e.value)   # names the ids that were in scope all along


def test_a_refusal_on_a_vocabulary_field_offers_its_values_not_an_escape_it_refuses(
        workdir, capsys):
    """The escape above is the other half of the same promise. `waived:` and
    `unknown:` are refused on a decision field whose note declares values -- a
    waived verdict falls through `merged_verdict` to a `pass` -- but the
    refusal surface went on offering them, so an agent that took the advice on
    an empty or in-hand field was refused on its very next submit.

    Driven, not read: the escape the engine prints is parsed back out of the
    refusal and submitted as the answer. A test that asserted on the constant
    would prove nothing about the path that uses it."""
    _critic_step()
    capsys.readouterr()

    offered = []
    # The two refusals a `verdict` can draw before its value is ever checked:
    # a field left unanswered, and a field still in hand.
    for verdict in ("", "working: still reading the diff"):
        _fill_critic("c1", verdict)
        with pytest.raises(SystemExit) as e:
            cli.main(["c1", "submit"])
        msg = str(e.value)
        assert "verdict" in msg
        assert "waived:" not in msg and "unknown:" not in msg, (
            "the refusal offers an escape its own next submit refuses:\n" + msg)
        line = next(ln for ln in msg.splitlines() if "one of:" in ln)
        offered.append([v.strip() for v in line.split("one of:")[1].split("|")])

    assert offered[0] == offered[1] == ["pass", "revise"]

    # Take the escape at its word. Were it naming a value the submit refuses,
    # this raises -- which is exactly the defect, one step later.
    _fill_critic("c1", offered[0][0])
    cli.main(["c1", "submit"])
    assert runmod.state("c1")["done"]["verdict"]["fields"]["verdict"] == "pass"


def test_a_crash_is_never_a_refusal(workdir):
    """Two paths raised bare Python errors: nothing journaled, no way forward.
    Worse than an illegitimate refusal."""
    _open()
    with pytest.raises(SystemExit):
        cli.main(["issue17", "amend"])            # was IndexError

    pathlib.Path(".agent-work/issue17/OPEN.toml").write_text('issue = "unclosed\n')
    with pytest.raises(SystemExit) as e:
        cli.main(["issue17", "submit"])           # was TOMLDecodeError
    assert "not valid TOML" in str(e.value)
    assert "nothing was recorded" in str(e.value)


def test_an_amended_anchor_is_flagged_where_it_will_be_read(workdir):
    """The design's freeze is visibility, not refusal: amending an anchor is
    allowed and must be loud in the record the tier above reads."""
    _open()
    cli.main(["issue17", "amend", "close", "understand",
              "--reason", "issue already states it"])
    from engine import render
    lines = render.amends(runmod.state("issue17")["amends"])
    assert lines and lines[0].startswith("ANCHOR ")
    assert "issue already states it" in lines[0]


def test_a_field_in_hand_is_not_mistaken_for_an_answer(workdir, capsys):
    """`working: <what is left>` is the status an agent sets while a field is
    still in hand. Submitting it would record work-in-progress as an answer,
    and the next reader could not tell the difference."""
    cli.main(["open", "run-a-gate", "--id", "g1"])
    pathlib.Path(".agent-work/g1/IMPLEMENT.toml").write_text(
        'change = "working: still tracing the EOF branch"\n'
        'deviations = "waived: none"\n')
    capsys.readouterr()

    with pytest.raises(SystemExit) as e:
        cli.main(["g1", "submit"])
    msg = str(e.value)
    assert "still tracing" in msg           # says what is left, not just that it is
    assert "waived:" in msg                 # and the honest ways to close it

    cli.main(["g1"])                        # status surfaces it unasked
    out = capsys.readouterr().out
    assert "still in hand" in out and "still tracing the EOF branch" in out

    # finishing it is one edit
    pathlib.Path(".agent-work/g1/IMPLEMENT.toml").write_text(
        'change = "traced it; flushed at capacity"\ndeviations = "waived: none"\n')
    cli.main(["g1", "submit"])
    assert "work-1" in runmod.state("g1")["done"]


def test_a_pipe_in_ordinary_prose_does_not_become_an_enum_the_engine_enforces(workdir):
    """Enforcement follows `kind = "decision"`, never the punctuation alone.

    The first cut of this derived the enum from the note and nothing else, so
    any field whose note happened to carry ` | ` in its opening sentence
    silently became an enum -- `Name the risk | the mitigation | who owns it`
    would have refused every answer but those three. The values still come from
    the note, because that is the sentence the agent reads and a second copy
    would drift from it; what the note cannot do is decide *whether* the engine
    acts on the field. A form author picks that on purpose.
    """
    src = tmp_form(workdir, """
imperative = "Fill it."

[[field]]
id = "risks"
kind = "evidence"
note = "Name the risk | the mitigation | who owns it, in one line each."

[[field]]
id = "ruling"
kind = "decision"
note = "advance | rework | up. What happens to the artifact."
""")
    form = forms.load(src)
    prose, decision = form["fields"]

    assert forms.vocabulary(prose["note"]) == ["Name the risk", "the mitigation",
                                               "who owns it"]
    assert forms.enforced_vocabulary(prose) == []
    assert forms.enforced_vocabulary(decision) == ["advance", "rework", "up"]

    # the prose field takes an answer that is none of its three "alternatives"
    cli._check_vocabulary(_asm(), _step(), form, {"risks": "the parser drops the last record",
                                 "ruling": "rework"})

    with pytest.raises(SystemExit) as e:
        cli._check_vocabulary(_asm(), _step(), form, {"ruling": "keep going"})
    assert "not a value this step can act on" in str(e.value)


# --- #70: a TOML escape sequence in a form field ---------------------------
#
# Found live on `issue57` while filling a plan form: a word-boundary regex,
# written as ordinary prose, decodes through `tomllib` to a 0x08 byte. The
# byte was written raw into the journal, which made the file unreadable, and
# the torn-tail recovery above then dropped the submit without a word. Two
# submits landed and neither folded.


def test_a_control_character_round_trips_through_write_and_read():
    """`tomlw` owes its caller one property: what it writes, `tomllib` reads
    back unchanged. A raw control byte breaks that -- and it is reachable
    from any field an agent writes prose into, since `\\b` in a form is a
    word boundary to the agent and a backspace to the parser."""
    for raw in ("match on \bword\b boundaries",     # the live case
                "a\x0cform feed", "a\rcarriage return", "a\x00null"):
        written = tomlw.table("entry", {"text": raw})
        back = tomllib.loads(written)["entry"][0]["text"]
        assert back == raw, f"{raw!r} did not survive the round trip"


def test_a_control_character_round_trips_inside_prose():
    """The multi-line writer is the one prose actually takes: any field whose
    value has a newline in it renders as a multi-line basic string."""
    raw = "first line\nmatch on \bword\b boundaries\nlast line"
    written = tomlw.table("entry", {"text": raw})
    assert tomllib.loads(written)["entry"][0]["text"] == raw


def test_a_form_field_carrying_an_escape_sequence_folds(workdir, capsys):
    """End to end, the way it was hit: the agent writes the escape into its
    response form, the engine journals it, and the submit must fold. The
    defect was silent -- the step stayed current, which invited the retry
    that corrupted the file a second time."""
    _open()
    pathlib.Path(".agent-work/issue17/OPEN.toml").write_text(
        f'issue = "{_issue_file()}"\n'
        'authority = "Tommy. Terms are matched on \\bword\\b boundaries."\n'
        '\n[[questions]]\nquestion = "q?"\ntype = "fact"\n')
    capsys.readouterr()

    cli.main(["issue17", "submit"])

    submits = [e for e in journal.read("issue17") if e.get("kind") == "submit"]
    assert submits, "the submit was journaled and then dropped by the read"
    assert "\bword\b" in submits[-1]["fields"]["authority"]


def test_a_read_that_discards_an_entry_says_so(workdir, capsys):
    """The recovery above is right to keep the work, and wrong to keep it
    quietly. A dropped entry is lost state; the agent that wrote it is the
    one person who can put it back, and it is told nothing today."""
    _open()
    capsys.readouterr()
    with open(".agent-work/issue17/journal.toml", "a") as f:
        f.write('\n[[entry]]\nkind = "note"\nat = "2026-08-24T0')

    journal.read("issue17")

    err = capsys.readouterr().err
    assert "journal.toml" in err, "a discarded entry was dropped silently"
    assert "1 entry" in err, "the count of what was dropped is not named"


# --- #71: a form that no longer exists -------------------------------------
#
# A journal is append-only and its `step` entries name form paths, so a gate
# that renames a form strands every run already standing on it -- including
# its own. On `issue57.g4` the rename of REVIEW_ROUND.toml to ROUTE.toml made
# `spine issue57.g4` die with a traceback: the run could not be advanced,
# closed, or even looked at, and was unwedged only by `amend close`.


def _rename_current_form(wid="issue17"):
    """Move the form the run's current step names, the way a gate renaming a
    form does. Returns the path that is now missing."""
    st = runmod.state(wid)
    asm = runmod.load_assembly(st["assembly"])
    path = runmod.resolve_form(asm, st["current"]["form"])
    path.rename(path.with_name("RENAMED.toml"))
    return path


def test_a_missing_form_refuses_and_names_it(workdir, capsys):
    """The engine is a secretary and never crashes. A form it cannot resolve
    is a refusal that names the form -- a traceback is neither a refusal nor
    a hand-in."""
    _open()
    capsys.readouterr()
    missing = _rename_current_form()
    try:
        with pytest.raises(SystemExit) as e:
            cli.main(["issue17"])
    finally:
        missing.with_name("RENAMED.toml").rename(missing)  # the tree is shared
    assert missing.name in str(e.value), "the refusal does not name the form"


def test_a_run_standing_on_a_missing_form_can_still_be_unwedged(workdir, capsys):
    """The escape the refusal offers has to work -- that is what
    `test_promises` asks of every refusal, and it is the whole difference
    between a wedged run and a recoverable one."""
    _open()
    capsys.readouterr()
    missing = _rename_current_form()
    step = runmod.state("issue17")["current"]["id"]
    try:
        with pytest.raises(SystemExit) as e:
            cli.main(["issue17"])
        assert f"amend close {step}" in str(e.value)
        cli.main(["issue17", "amend", "close", step, "--reason", "form renamed"])
    finally:
        missing.with_name("RENAMED.toml").rename(missing)
    assert runmod.state("issue17")["current"]["id"] != step


# --- #49: one malformed journal, and the whole ledger ----------------------
#
# Bare `spine` folds every run under every `.agent-work` root. `.agent-work`
# is exactly where hand-written debris accumulates, and three agents hit this
# independently during #43: a stub journal with no `segment` on a step entry
# raised KeyError out of `_ordered` and took the ledger down for every run.


def _debris(path=".agent-work/bogus/journal.toml"):
    """A journal of the shape hand-written test debris actually takes: a step
    entry with no `segment`, which every real one carries."""
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('[[entry]]\nkind = "run"\nassembly = "run-an-issue"\n\n'
                 '[[entry]]\nkind = "step"\nform = "x"\n')
    return p


def test_one_malformed_journal_does_not_take_down_the_ledger(workdir, capsys):
    """The ledger is how an agent finds its own run. A single unreadable
    journal beside it must not be able to hide every other run in the tree."""
    _open()
    _debris()
    capsys.readouterr()

    assert cli.main([]) == 0
    out = capsys.readouterr().out
    assert "issue17" in out, "a real run was hidden by unreadable debris"


def test_a_journal_the_ledger_cannot_fold_is_named(workdir, capsys):
    """Skipping it quietly would leave an agent looking for a run the ledger
    will never show. The secretary says which journal it could not read."""
    _open()
    bad = _debris()
    capsys.readouterr()

    cli.main([])
    both = capsys.readouterr()
    assert str(bad) in both.out + both.err, "the unreadable journal is not named"


# --- #33: two refusals that do not refuse ----------------------------------
#
# The third observation -- an unrecognized verb printing the room and exiting
# 0 -- is fixed and guarded in test_promises. These two stand.


def test_an_unknown_palette_entry_refuses_and_names_the_entries(workdir):
    """`tests/test_robustness` already requires that every refusal states an
    escape that works; this one raised a bare SystemExit through neither
    `refusal` nor `located`, so it named no way forward. The whole
    `palette:` branch had no coverage, which is how it stayed that way."""
    pathlib.Path("constellation.toml").write_text(
        '[commands]\ntest = "python3 -m pytest -q"\n')

    with pytest.raises(SystemExit) as e:
        cli._resolve_one("palette:nosuch")

    said = str(e.value)
    assert "nosuch" in said
    assert "test" in said, "the refusal does not name the entries that exist"


REPO_ROOT = str(pathlib.Path(__file__).resolve().parent.parent)


def test_a_refusal_locates_its_escape_and_never_its_why(workdir):
    """`located` rewrites the word `spine` into an absolute path so a printed
    command is runnable. Routed over an agent's own answer it edits the
    record instead -- observed as `change: working: rewrite the
    /home/tommy/.../spine module and its tests`. In this repo `spine` is a
    word agents write.

    The division is structural rather than remembered: the escape is the
    engine's own command and is always located; `why` is where a refusal
    quotes back what it was given and is never located. A caller cannot
    forget to opt in, because there is nothing to opt in to."""
    said = render.refusal("change", "'rewrite the spine module' is not a value",
                          escape="then: spine issue17 submit")

    assert "'rewrite the spine module' is not a value" in said, \
        "the agent's own prose was rewritten"
    assert f"then: {REPO_ROOT}/spine issue17 submit" in said, \
        "the escape must still be a runnable command"


def test_the_field_id_a_refusal_names_is_not_rewritten_either(workdir):
    """A refusal's subject is often agent-supplied too -- a board row id, a
    step id, a `--segment` argument. It is quoted back for the same reason
    and must survive for the same reason."""
    said = render.refusal("spine", "no board row by that id", escape="the board: spine w1")

    assert said.startswith("spine: "), "the field id was rewritten"
    assert f"the board: {REPO_ROOT}/spine w1" in said


def test_located_still_rewrites_a_command_the_engine_prints():
    """The rewrite is correct everywhere it applies to engine-authored text,
    which is the reason the fix is at the call site rather than in the
    regex. Guard that half so a narrowing does not creep in later."""
    assert render.located("spine issue17 submit").startswith(
        str(pathlib.Path(__file__).resolve().parent.parent))
    assert render.located("  open runs: spine").endswith("spine")


def test_no_refusal_in_the_engine_rewrites_what_the_agent_typed(workdir, capsys):
    """#33 was fixed at the site it was measured at, and the class went
    unswept -- five refusals still interpolated agent text into `why`. These
    are those five, driven rather than grepped, because a grep-shaped test
    rots the moment someone writes the sixth."""
    _open()
    capsys.readouterr()

    # a work id the agent passed
    with pytest.raises(SystemExit) as e:
        cli.main(["open", "run-an-issue", "--id", "../spine", "--title", "t"])
    assert "'../spine'" in str(e.value) and REPO_ROOT not in str(e.value)

    # a `--segment` the agent passed
    with pytest.raises(SystemExit) as e:
        cli.main(["issue17", "amend", "add", "--segment", "spine",
                  "--form", "x.toml", "--reason", "r"])
    assert "'spine'" in str(e.value) and REPO_ROOT not in str(e.value)

    # a step id the agent passed
    with pytest.raises(SystemExit) as e:
        cli.main(["issue17", "amend", "close", "spine", "--reason", "r"])
    assert "spine" in str(e.value) and REPO_ROOT not in str(e.value)


def test_an_undeclared_outcome_quotes_the_agents_word_unrewritten(workdir, capsys):
    """`_outcome`'s two refusals -- an undeclared value, and a placeholder
    whose argument names no pending step -- both quote back what the agent
    wrote. Neither went through the #33 fix."""
    _critic_step()
    _fill_critic("c1", "spine forward")
    capsys.readouterr()

    with pytest.raises(SystemExit) as e:
        cli.main(["c1", "submit"])
    said = str(e.value)
    assert "spine forward" in said or "'spine'" in said
    assert REPO_ROOT not in said, "the agent's own word was rewritten"


def test_a_value_the_step_cannot_act_on_still_names_what_was_rejected(workdir):
    """Protecting the agent's prose must not cost the refusal its subject:
    two agents reading it should still know which word was refused."""
    form = {"fields": [{"id": "ruling", "kind": "decision",
                        "note": "advance | rework. Say which."}]}
    with pytest.raises(SystemExit) as e:
        cli._check_vocabulary(_asm(), _step(), form, {"ruling": "spine forward"})
    said = str(e.value)
    assert "spine forward" in said or "'spine'" in said
    assert str(pathlib.Path(__file__).resolve().parent.parent) not in said


# --- #34: the error paths an agent meets most often ------------------------
#
# The suite covered the check that passes and the check that times out, and
# skipped the one in between -- the failing check is the case an implementer
# meets daily. `trace` is the verb reached when a run has already gone wrong,
# and three of its branches had never been executed.


def _gate_with_proof(proof, wid="g1"):
    """A gate standing on IMPLEMENT.toml with a caller-chosen proof command
    -- the same shape the hanging-check test above uses."""
    pathlib.Path("constellation.toml").write_text('[models]\nstandard = "x"\n')
    cli.main(["open", "run-a-gate", "--id", wid])
    journal.append(wid, "prefill", fields={"proof": proof})
    pathlib.Path(f".agent-work/{wid}/IMPLEMENT.toml").write_text(
        'change = "c"\ndeviations = "waived: none"\n')
    return wid


def test_a_failing_check_refuses_and_records_what_it_ran(workdir, capsys):
    """A check is run by the engine, not filled in, so a failure is not the
    agent's answer to correct -- the refusal has to say that and name a way
    out. The record of what actually ran is what the next reader needs."""
    _gate_with_proof("exit 1")
    capsys.readouterr()

    with pytest.raises(SystemExit) as e:
        cli.main(["g1", "submit"])

    msg = str(e.value)
    assert "exited 1" in msg
    assert "amend close" in msg              # the escape, and it works
    checks = [x for x in journal.read("g1") if x.get("kind") == "check"]
    assert checks and checks[-1]["exit"] == 1
    assert checks[-1]["command"] == "exit 1"


def test_trace_renders_a_run_that_had_a_failed_check_a_note_and_an_amend(
        workdir, capsys):
    """`trace` is the debugging verb: its output on a run that went wrong is
    the case it exists for, and the three branches that render exactly that
    had never been run. A standalone `check` entry is written only on
    failure, which is why the passing-check test could not reach this."""
    _gate_with_proof("exit 1")
    with pytest.raises(SystemExit):
        cli.main(["g1", "submit"])
    cli.main(["g1", "note", "observation", "the proof names the wrong suite"])
    step = runmod.state("g1")["current"]["id"]
    cli.main(["g1", "amend", "close", step, "--reason", "spec was wrong"])
    capsys.readouterr()

    cli.main(["g1", "trace"])
    out = capsys.readouterr().out

    assert "exit 1" in out          # render._event's `check` branch
    assert "observation" in out     # its `note` branch
    assert "spec was wrong" in out  # its `amend` branch


def test_a_journal_torn_in_two_places_reads_as_the_work_that_survives(
        workdir, capsys):
    """Recovery was tested past exactly one tear. The loop back past a second
    bad block is the arm that had never run -- and a file torn twice is what
    a second submit after a first failure actually produces."""
    _open()
    capsys.readouterr()
    before = len(journal.read("issue17"))
    with open(".agent-work/issue17/journal.toml", "a") as f:
        f.write('\n[[entry]]\nkind = "note"\nat = "2026-08-24T0')
        f.write('\n\n[[entry]]\nkind = "note"\nat = "2026-08-24T1')

    assert len(journal.read("issue17")) == before
    cli.main(["issue17"])                 # and every verb still works
    assert "issue17" in capsys.readouterr().out


def test_a_journal_destroyed_entirely_reads_as_no_history(workdir, capsys):
    """Total loss: nothing in the file parses, so there is no prefix to
    recover. It must read as empty rather than raise -- a raising read bricks
    the verbs that would repair the run.

    Note what this is *not*. #34 recorded the `return []` after the recovery
    loop as an uncovered line; it was uncovered because it was unreachable.
    `split` yields at least one block and the empty join parses, so the loop
    always returns and total loss arrives through it. The dead line is gone
    and this test pins the behaviour, which is the part that was ever real."""
    _open()
    capsys.readouterr()
    pathlib.Path(".agent-work/issue17/journal.toml").write_text(
        "[[entry]\nkind = ?not toml at all\n")

    assert journal.read("issue17") == []
    assert "could not be read" in capsys.readouterr().err
