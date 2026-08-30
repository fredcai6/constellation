"""Ways the engine could lose or corrupt the record.

Every case here was found by a fresh-context reviewer probing the running system, not
by the suite that was green at the time. The secretary's one duty is to keep
the record; each of these broke that duty silently.
"""

import pathlib

import pytest

from engine import cli, forms, journal, run as runmod
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
    agent's turn with no way out."""
    monkeypatch.setattr(cli, "CHECK_TIMEOUT", 1)
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
    # drive the review panel for real: one panelist, a pass verdict
    cli.main(["open", "give-a-verdict", "--parent", child, "--step", "review.p1"])
    panelist = f"{child}.review.p1"
    pathlib.Path(f".agent-work/issue17/g1/review/p1/REVIEW.toml").write_text(
        'verify = "read it"\nfindings = "none: waived: clean"\n'
        'vocabulary = "waived: consistent"\nverdict = "pass"\n')
    cli.main([panelist, "submit"])
    cli.main([panelist, "close"])
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
