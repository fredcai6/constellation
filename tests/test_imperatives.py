"""No room is silent about what to do next.

Every *form* step ended with an imperative and one way to reply. A *brief*
step -- a dispatch, a review panel -- ended with a table and nothing else, and
a light model filled that silence with the most available reading: a reviewer
has been assigned, so I will wait. Then it waited for something that was never
coming, about half the time.

So the property under test is not "the dispatch imperative exists". It is that
every room a run can stand in tells the reader who acts and gives them a
command to act with -- swept across a whole run rather than asserted at the
one site that happened to break.
"""

import pathlib
import re

from engine import cli, render, run as runmod
from test_nesting import (
    _dispatch_and_close_child, _dispatch_and_close_plan, _fill_consolidate,
    _fill_gate_transition, _fill_implement, _fill_open, _fill_plan,
    _fill_plan_to_execute, _dispatch_plan_critic, _work_the_board,
)

REPO = pathlib.Path(__file__).resolve().parent.parent
SPINE = render.spine_cmd()


def _room(capsys, wid):
    capsys.readouterr()
    cli.main([wid])
    return capsys.readouterr().out


def _speaks(out):
    """The room said something instructive.

    Prose and tables are told apart by shape rather than content, so this
    keeps working as the words change: `_pairs` aligns a label against its
    value with a run of two or more spaces, and `_para` never does. Drop the
    tables and the command lines, join what wrapping split, and ask whether a
    sentence is left."""
    prose = " ".join(l.strip() for l in out.splitlines()
                     if l.strip() and SPINE not in l and "  " not in l.strip())
    # A sentence ends a word, not an identifier: the dot in `g1.review.p1` is
    # not speech, and taking it for speech is how this sweep first failed to
    # catch a room it was written to catch.
    return bool(re.search(r"[a-z]{2}\.(?=\s|$)", prose)) and len(prose.split()) >= 10


def _offers_a_move(out):
    """At least one command the reader can type, self-located so it runs."""
    return bool(re.search(re.escape(SPINE) + r"\s+\S", out))


# -- the sweep: every room in a real run --------------------------------------


def test_every_room_in_a_whole_issue_speaks_and_offers_a_move(workdir, capsys):
    """Walk run-an-issue end to end and check every room it stands in. This
    is the test that would have caught the panel step: it asserts the
    property, not the site."""
    seen = []

    def check(wid):
        out = _room(capsys, wid)
        seen.append((wid, runmod.state(wid)["current"]))
        assert _speaks(out), f"{wid} stood in a silent room:\n{out}"
        assert _offers_a_move(out), f"{wid} offered no typeable move:\n{out}"

    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    wid = "issue17"
    check(wid); _fill_open(wid); cli.main([wid, "submit"])
    check(wid); _work_the_board(wid); _fill_consolidate(wid); cli.main([wid, "submit"])
    check(wid); _dispatch_and_close_plan(wid)
    check(wid)                      # the plan's critic panel -- a brief step
    _dispatch_plan_critic(wid)
    check(wid)                      # two voices: the form half, panel passed
    _fill_plan_to_execute(wid); cli.main([wid, "submit"])
    check(wid)                      # the g1 dispatch -- a brief step
    _dispatch_and_close_child(wid, "g1")
    check(wid)                      # adjudication, a child returned
    _fill_gate_transition(wid); cli.main([wid, "submit"])

    assert len(seen) >= 7, seen


def test_every_room_in_a_gate_speaks_and_offers_a_move(workdir, capsys):
    """The same sweep one level down, where the review panel lives."""
    cli.main(["open", "run-a-gate", "--id", "g1"])
    for advance in (lambda: (_fill_implement("g1", "work-1"), cli.main(["g1", "submit"])),
                    lambda: _dispatch_review_here(),
                    lambda: None):
        out = _room(capsys, "g1")
        assert _speaks(out), f"a gate room was silent:\n{out}"
        assert _offers_a_move(out), f"a gate room offered no move:\n{out}"
        advance()


def _dispatch_review_here():
    from test_nesting import _dispatch_review
    _dispatch_review("g1")


# -- the two sentences that were missing --------------------------------------


def test_a_dispatch_step_says_the_conductor_is_the_one_who_runs_it(workdir, capsys):
    from test_brief import _mint_dispatch_step
    _mint_dispatch_step()
    out = _room(capsys, "d1")
    # wrapping can fold a long sentence across lines -- normalize before matching
    normalized = " ".join(out.split())
    assert "you are the one who runs it" in normalized
    # and it still carries the brief it always did
    assert "open it:" in out and "d1.g1" in out


def test_a_panel_step_says_the_verdict_is_the_panels_to_give(workdir, capsys):
    """The exact reading that stalled the implementer eval: a panelist is
    listed, so surely someone else is coming. The room now says who acts."""
    from test_brief import _mint_panel_step
    _mint_panel_step()
    out = _room(capsys, "g9")
    normalized = " ".join(out.split())
    assert "you are the one who runs it" in normalized
    assert "the panel's to give" in normalized
    assert "open it:" in out


PASSIVE_TAIL = re.compile(r"\b(wait|hold|monitor|expect)\b", re.IGNORECASE)
# A named command, not a bare co-occurrence: the passive word must sit inside
# a `spine <something> wait`-shaped construction, mirroring the literal
# `spine {work-id} wait` string test_promises.py's own regex scans for --
# "spine" appearing anywhere else in the sentence proves nothing.
NAMED_WAIT_COMMAND = re.compile(r"\bspine\s+\S+\s+wait\b", re.IGNORECASE)


def _ends_on_a_move(text):
    """The last sentence of an imperative must carry no passive-tail word
    (wait/hold/monitor/expect) that sits outside a named `spine <work-id>
    wait` command. Every passive-tail match has to lie inside some
    named-command match -- a real command elsewhere in the sentence does
    not excuse a second, unattached passive word. Shared by the real
    assertion below and its own three coverage cases, so the predicate is
    exercised once and not re-derived four times."""
    last_sentence = text.strip().rstrip(".").split(".")[-1]
    # Strip out the named-command spans first, then check what's left for a
    # passive word -- reads more plainly than walking both match lists and
    # confirming span containment, and is equivalent: a passive word left
    # over after stripping is, by definition, one that sat outside every
    # named-command match.
    without_named_commands = NAMED_WAIT_COMMAND.sub("", last_sentence)
    return not PASSIVE_TAIL.search(without_named_commands)


def test_a_brief_imperative_ends_on_a_move_the_reader_makes(workdir):
    """Measured, not stylistic. PANEL's first draft ended "dispatch each
    panelist and wait for its verdict", and a light model did the waiting
    literally: it started a background monitor to poll for a verdict nobody
    was coming to give, and stopped. Two of five runs, the trace showing no
    child ever opened.

    A passive tail on an imperative reads as permission to stop acting. This
    used to be checked by banning the word "wait" outright, but `spine
    <work-id> wait` is now the real, typeable command that starts a child --
    the word itself can no longer be the thing forbidden. What was always
    meant is narrower: the imperative must not *end* on a passive tail, a
    trailing "wait"/"hold"/"monitor"/"expect" with no move attached. A named
    command is not a passive tail, so DISPATCH and PANEL naming `spine
    <work-id> wait` still pass; the old PANEL draft, which trailed off on a
    bare "wait for its verdict", would not have. The exemption is
    structural, not a bare substring check -- see `_ends_on_a_move` and its
    own three coverage cases below, which is what proves that a sentence
    merely mentioning "spine" alongside a passive word, with no real
    command attached, still fails, and that a real command does not excuse
    a second, unattached passive word elsewhere in the same sentence."""
    for name, text in (("DISPATCH", render.DISPATCH), ("PANEL", render.PANEL)):
        assert _ends_on_a_move(text), (
            f"{name} ends on a passive tail; nothing is coming unless they act")
        assert "you " in text.lower(), f"{name} never names who acts"


def test_a_passive_tail_beside_the_bare_word_spine_still_fails():
    """The exemption admits a named command, not co-occurrence: this last
    sentence contains both a passive-tail word ("wait") and the bare word
    "spine", but no `spine <work-id> wait`-shaped command -- exactly the
    "Then wait for spine to notify you" shape this gate's own review caught
    as a false pass under the old bare-substring check."""
    assert not _ends_on_a_move("Carry the child through. Then wait for spine to notify you.")


def test_a_last_sentence_naming_the_real_spine_wait_command_passes():
    """The positive case the exemption exists for: a last sentence that
    correctly ends on a named `spine <work-id> wait` command is admitted,
    not merely passing by accident of the plain no-passive-word half."""
    assert _ends_on_a_move("Carry the child through. Then spine <work-id> wait starts it.")


def test_a_real_command_does_not_excuse_a_second_dangling_passive_tail():
    """The regression this gate's second review round caught: a last
    sentence naming a genuine `spine <work-id> wait` command *and* a
    separate, unattached passive tail elsewhere in the same sentence. The
    old bare-OR predicate passed this, because the command's mere presence
    satisfied one half of the OR regardless of the dangling tail. Fixed,
    it must fail -- every passive-tail match has to lie inside a
    named-command match, not just some match existing somewhere."""
    assert not _ends_on_a_move(
        "Carry the child through. Run spine <work-id> wait yourself, "
        "then wait for it to happen")


def test_the_implementer_skill_no_longer_repeats_the_room(workdir):
    """Doctrine belongs at the point of use. Once the panel step says it,
    the skill saying it too is a second copy with the usual fate.

    The second assertion used to be a word ratchet -- "< 222, the skill
    should have shrunk, not grown" -- which measured the wrong thing twice
    over: it passes a skill that repeats the room in fewer words, and it
    fails a skill that grows for a reason issue 14 never had in view. What
    repeating the room looks like is the panel step's own vocabulary turning
    up here; how large the skill may get is a budget, and it has exactly one
    definition (tests/test_promises.py).
    """
    skill = (REPO / "skills/implementer/SKILL.md").read_text().lower()
    assert "dispatch what each brief names" not in skill
    for phrase in ("subagent", "fresh context", "panelist"):
        assert phrase in render.PANEL.lower(), f"{phrase!r} is not the room's own word"
        assert phrase not in skill, (
            f"the skill says {phrase!r}; the panel step it stands you on "
            "already says it, and two copies is one too many")
