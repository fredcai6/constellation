"""Each round keeps its own copy of the artifact it produced.

An artifact field names a file the agent wrote, not one the engine
materialized: `_check_artifact` reads it, `_measure_artifacts` counts its
words, and nothing kept it. A rework writing to the same path overwrote the
spec it was reworking, so the run's record held how the artifact moved (a
word count per round) and never what it said.

The workaround was already in the archives twice, invented per-run: issue80
and issue99 both carry findings citing a `spec-r2.md` a conductor named by
hand, which leaves a stale `spec.md` beside it with nothing saying which is
current. The copy is taken by the engine now, under the same
`_per_step_name` rule the response form beside it takes.
"""

import pathlib

from engine import cli, journal, run as runmod

from test_nesting import (
    _dispatch_and_close_plan,
    _dispatch_plan_critic,
    _fill,
    _fill_consolidate,
    _fill_open,
    _fill_spec,
    _response,
    _work_the_board,
)


def _loc(wid):
    return journal.location(wid)


# -- 1. one naming rule, used by both files a round owns --------------------


def test_the_response_form_and_the_artifact_share_one_naming_rule(workdir):
    assert cli._per_step_name("skills/spec-writer/forms/SPEC.toml", "understand-a4d19") \
        == "SPEC.understand-a4d19.toml"
    assert cli._per_step_name("spec.md", "understand-a4d19") \
        == "spec.understand-a4d19.md"
    assert cli._per_step_name(pathlib.Path("/tmp/x/plan.md"), "plan-1") \
        == "plan.plan-1.md"


# -- 2. the copy is taken, and the submitted path still resolves -------------


def test_a_submitted_artifact_is_kept_under_the_round_that_wrote_it(workdir, capsys):
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    _fill_open("issue17")
    cli.main(["issue17", "submit"])
    b = _loc("issue17") / "UNDERSTAND.toml"
    b.write_text(b.read_text().replace(
        'status = "open"',
        'status = "answered"\nanswer = "EOF without a trailing newline only."'))
    step_id = runmod.state("issue17")["current"]["id"]
    _fill_spec("issue17")
    cli.main(["issue17", "submit"])
    capsys.readouterr()

    kept = _loc("issue17") / f"spec.{step_id}.md"
    assert kept.is_file(), (
        f"the round's own copy was not kept: {sorted(p.name for p in _loc('issue17').iterdir())}")
    assert kept.read_text() == (_loc("issue17") / "spec.md").read_text()
    assert (_loc("issue17") / "spec.md").is_file(), (
        "the path the submitted field names must keep resolving -- a later "
        "reader follows the journaled value")


def test_a_rework_round_does_not_destroy_the_round_it_reworks(workdir, capsys):
    """The defect itself: two rounds writing one path. Both copies survive,
    each under the round that wrote it."""
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    _fill_open("issue17")
    cli.main(["issue17", "submit"])
    b = _loc("issue17") / "UNDERSTAND.toml"
    b.write_text(b.read_text().replace(
        'status = "open"',
        'status = "answered"\nanswer = "EOF without a trailing newline only."'))

    first = runmod.state("issue17")["current"]["id"]
    (_loc("issue17") / "spec.md").write_text("round one's specification\n")
    cli._response_path(runmod.state("issue17"), runmod.state("issue17")["current"]) \
        .write_text('spec = ".agent-work/issue17/spec.md"\n')
    cli.main(["issue17", "submit"])
    _dispatch_plan_critic("issue17")
    _fill_consolidate("issue17", "incorporate",
                      calls='[[calls]]\nfinding = "f"\ncall = "writer"\n')
    cli.main(["issue17", "submit"])  # the send-back mints the fresh writer round directly
    capsys.readouterr()

    second = runmod.state("issue17")["current"]["id"]
    (_loc("issue17") / "spec.md").write_text("round two's specification, rewritten\n")
    cli._response_path(runmod.state("issue17"), runmod.state("issue17")["current"]) \
        .write_text('spec = ".agent-work/issue17/spec.md"\n')
    cli.main(["issue17", "submit"])
    capsys.readouterr()

    assert first != second
    assert (_loc("issue17") / f"spec.{first}.md").read_text() == "round one's specification\n", (
        "the rework overwrote the round it was reworking")
    assert (_loc("issue17") / f"spec.{second}.md").read_text() \
        == "round two's specification, rewritten\n"


# -- 3. what it must not do -------------------------------------------------


def test_a_null_artifact_answer_copies_nothing(workdir, capsys):
    """`waived:` names no file, and an unreadable path is refused by
    `_check_artifact` long before this runs."""
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    _fill_open("issue17")
    cli.main(["issue17", "submit"])
    capsys.readouterr()
    before = {p.name for p in _loc("issue17").iterdir()}

    cli._archive_artifact(journal.root_for("issue17"), "waived: none", "understand-1")
    cli._archive_artifact(journal.root_for("issue17"), ".agent-work/issue17/nope.md", "x")

    assert {p.name for p in _loc("issue17").iterdir()} == before


def test_a_long_waived_artifact_value_is_not_archived(workdir, capsys):
    """issue141: `_check_artifact` (pre-journal) treated any string whose
    leading word is `waived`/`unknown` as a non-answer, but
    `_measure_artifacts` (post-journal) admitted every string alike and
    handed it to `_archive_artifact`, whose `is_file()` raises `OSError` --
    not `False` -- once a path component exceeds the filesystem's 255-byte
    name limit. A `waived:` reason long enough to trip that crashed after
    the submit was already journaled (`complete_submit` journals first),
    exactly what happened live in run issue139. Both call sites now consult
    `forms.without_nulls`, the same predicate `_mint_gates` already uses, so
    a null of any length is skipped before it ever reaches a filesystem
    call -- no crash, and nothing archived."""
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    _fill_open("issue17")
    cli.main(["issue17", "submit"])
    _work_the_board("issue17")
    step_id = runmod.state("issue17")["current"]["id"]

    long_value = "waived: " + "x" * 300
    _fill(_response("issue17"),
          'resolution = "pass"\n'
          'spec = "%s"\n'
          'key-terms = "waived: none"\n'
          'settle = "waived: none"\n' % long_value)
    cli.main(["issue17", "submit"])  # must not raise
    capsys.readouterr()

    assert any(e.get("kind") == "submit" for e in journal.read("issue17"))
    measures = [e for e in journal.read("issue17") if e.get("kind") == "measure"]
    assert not any(m["step"] == step_id and m["field"] == "spec" for m in measures), (
        "a long null value must not be measured -- it names no file")
    assert not (_loc("issue17") / f"spec.{step_id}.md").exists(), (
        "a long null value must not be archived -- it names no file")
