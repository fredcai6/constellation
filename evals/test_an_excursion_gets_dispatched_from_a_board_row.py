"""The one eval that can falsify the bet issue 43 turns on.

Twelve prior runs chose `ask` 12 times, `read` 24, `trace` 20 and `reproduce`
7 across 63 understand rows, and an excursion zero times, while the ideas
board -- which gives every row its own `excursion` column -- dispatched twelve
off 87. So the column moved onto the understand board. Whether that made the
move *reachable* is a claim about a model's behaviour, and only a model can
settle it.

What this deliberately does not assert: that the `excursion` field is present,
or that it is non-empty. A cold panelist drove a light model on a two-row board
under the *unmodified* form and the outside-the-repo row came back answered
`reproduce` -- not declined -- so "row A was not declined" is already true with
nothing changed, and any eval resting on it passes on a change that did
nothing. The assertion here is a child run on disk: a dispatch is a run the
engine opened, never a string somebody typed into a column.

The lightest model is deliberate, same as this file's neighbours: if reaching
for an excursion needs a strong model, the board is at fault, not the model.
"""

import json
import pathlib
import shutil
import tomllib

import pytest

from engine import boards
from evals import harness


@pytest.fixture
def workdir(tmp_path):
    shutil.copy(harness.ROOT / "constellation.toml", tmp_path)
    # Row B is answerable by reading, so there has to be something to read.
    (tmp_path / "retry.py").write_text(
        "def retry_delay(attempt):\n"
        "    \"\"\"Seconds to wait before retry attempt N.\"\"\"\n"
        "    return min(2 ** (attempt - 1), 4)\n")
    return tmp_path


# [seed-open-form]
# Rationale: fill the OPEN.toml the engine just minted rather than writing one,
#   and repeat its own `[[questions]]` block per seed -- which is literally
#   what the template's "Repeat this block per item" tells a conductor to do.
#   Every column a seeded row carries then reaches the board because the form
#   put it there. That matters for exactly one column: a fill that omits
#   `excursion` produces rows without it (`_seed_board` writes what it is
#   handed), so a hand-written fixture would be presupposing the shape this
#   eval exists to measure, and would keep passing if gate one were reverted.
# Rejected: writing OPEN.toml from scratch with `excursion = ""` typed in. It
#   is three lines shorter and it tests the fixture instead of the form.
# See: engine/cli.py `_seed_board`, assemblies/run-an-issue/forms/OPEN.toml
def seed_open(workdir, wid, seeds):
    """Fill the minted OPEN.toml the way a conductor does, one block per seed."""
    p = pathlib.Path(workdir) / ".agent-work" / wid / "OPEN.toml"
    head, mark, block = p.read_text().partition("[[questions]]")
    head = head.replace('issue = ""', 'issue = "issue-43"')
    # The authority has to be true of the room the drive actually runs in.
    # "your principal is the human at the keyboard" is what a root run
    # normally records, and it is a lie here -- a driven model has nobody to
    # ask, and the first run seeded that way spent its whole budget writing a
    # clarifying question to an empty chair and left both rows open. Both
    # seeds are `fact` rows, which the interrogator resolves itself, so
    # saying so costs the measurement nothing and removes a confound that
    # was never what this eval is about.
    head = head.replace('authority = """\n"""',
                        'authority = """\nNo live principal is in reach for '
                        'this run -- there is nobody to ask, and asking as if '
                        'there were would fabricate their words. Every seeded '
                        'row is a fact you resolve yourself, with evidence. '
                        'You own the understanding.\n"""')
    body = ""
    for question, kind in seeds:
        b = block.replace('question = ""', f"question = {json.dumps(question)}")
        b = b.replace('type = ""', f"type = {json.dumps(kind)}")
        body += mark + b
    p.write_text(head + body)


def excursions(workdir, wid):
    """Every child run opened from a board row of `wid`, as (row, assembly, id).

    Read from the children's own journals: `_open_excursion` stamps the row it
    came from onto the child's `run` entry, so this counts dispatches that
    actually happened rather than rows that claim one."""
    base = pathlib.Path(workdir) / ".agent-work" / wid.replace(".", "/")
    out = []
    for j in sorted(base.glob("*/journal.toml")):
        entries = tomllib.loads(j.read_text()).get("entry", [])
        run = next((e for e in entries if e.get("kind") == "run"), {})
        if run.get("row"):
            out.append((run["row"], run.get("assembly", ""), j.parent.name))
    return out


def board_rows(workdir, wid):
    """The board as the agent left it -- for evidence, not for the assertion."""
    return boards.rows(pathlib.Path(workdir) / ".agent-work" / wid / "UNDERSTAND.toml")


def test_a_row_answerable_only_from_outside_the_repo_gets_an_excursion(workdir):
    """Two rows, and only one of them can be settled without leaving the tree.

    Row A is answerable only from outside this repository -- what the
    literature and other projects' practice say. That excludes `read`,
    `trace`, `reproduce` and `evidence-loop` by construction, because not one
    of them can reach outside the checkout, which leaves `prior-art` as the
    only move that answers it. (An earlier draft of this row asked for
    something "answerable only by running something", which `reproduce` and
    `trace` both satisfy -- it could not separate an excursion from the moves
    that stay on the board, so it could not fail for the right reason.)

    Row B is answerable by reading, and carries no assertion at all. Briefed
    or declined, both pass. Forcing a dispatch where reading works would be a
    compliance audit, and this repo's decision procedure refuses those: the
    point is that the excursion is *available*, not that it is mandatory.

    Nothing in the prompt names an excursion, prior art, or the column. If the
    agent gets there, it got there from the room.
    """
    harness.spine(workdir, "open", "run-an-issue", "--id", "r1")
    seed_open(workdir, "r1", [
        ("Outside this repository, what backoff ceiling do other retry "
         "implementations and the published literature settle on, and what do "
         "they say the tradeoff is? Nothing in this workdir records it -- the "
         "answer is in other projects' practice and the literature, not here.",
         "fact"),
        ("What does retry_delay in retry.py in this workdir return for "
         "attempt 3?", "fact"),
    ])
    harness.spine(workdir, "r1", "submit")
    rows = board_rows(workdir, "r1")
    assert [r.get("id") for r in rows] == ["q1", "q2"], f"the seed did not land: {rows}"
    assert all("excursion" in r for r in rows), (
        f"the seeded rows do not carry the excursion column, so this eval "
        f"cannot measure anything: {rows}")

    # 300s, below the harness default, because what is being measured is over
    # long before the run is: both observed drives settled the board in about
    # 90 seconds and then carried straight on into plan and execute despite
    # the last sentence of this prompt. Every dispatch that could count has
    # happened by then, so the extra minutes buy nothing and cost the whole
    # `palette:validate` budget. A drive cut here comes back marked, not
    # raised, and the assertion below still runs on the board it left.
    r = harness.drive(workdir, (
        "You are an agent working in this directory. Your work id is r1. "
        "Run `spine r1` to see where you are, read what it hands you, and do "
        "exactly what it tells you. Work every row on the board it names "
        "until that row is settled, each by whatever it actually takes to "
        "settle it. Nobody is going to answer you part-way through, so act on "
        "what you have rather than stopping to ask for it. Stop as soon as no "
        "row on that board is still open -- do not go on to whatever the run "
        "does next."), timeout=300)

    dispatched = excursions(workdir, "r1")
    after = board_rows(workdir, "r1")
    # Named separately because it is a different failure: a row still open is
    # a drive that ran out of room, not an agent that chose another move.
    still_open = [x.get("id") for x in after
                  if str(x.get("status", "open")) == "open"]
    detail = (f"\n-- the board as it was left --\n"
              f"{json.dumps(after, indent=2)}"
              f"\n-- rows still open --\n{still_open or 'none'}"
              f"\n-- excursions dispatched (row, assembly, id) --\n{dispatched}")
    assert [e for e in dispatched if e[0] == "q1"], (
        f"row q1 can only be answered from outside this repository, and no "
        f"excursion was dispatched from it -- the column is on the board and "
        f"the move is still not reachable.{detail}"
        f"{harness.evidence(workdir, 'r1', r)}")
