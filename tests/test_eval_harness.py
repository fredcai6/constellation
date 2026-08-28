"""A driven eval's red has to say which of its failures it is.

`evals/test_an_excursion_gets_dispatched_from_a_board_row.py` is the falsifier
for #43's bet, and a falsifier is only worth the name if its red means one
thing. Two very different runs used to land on the same `assert []`: a light
model that worked row q1 and settled it without ever reaching for an
excursion -- the finding the eval exists to report -- and a drive killed at
its budget with q1 never touched, which measures nothing at all. Read the
second as the first and a broken instrument gets filed as a result; read the
first as the second and a real negative gets rerun until it goes green.

This is the fast check on that seam, so it stands in for the model rather than
paying for one: the drive is replaced, the board is left in each of the two
states, and the two reds are compared. What it cannot check is whether a real
light model reaches the excursion -- that is the eval's own job, and it costs
a real drive.
"""

import pathlib
import shutil
import subprocess

import pytest

from evals import harness
from evals import test_an_excursion_gets_dispatched_from_a_board_row as excursion

EVAL = excursion.test_a_row_answerable_only_from_outside_the_repo_gets_an_excursion

# The load-bearing phrase of each red, quoted from the eval. If one of these
# stops matching, the eval stopped saying which failure it hit, which is the
# whole thing this file is here to hold.
DECLINE = "settled without an excursion"
INSTRUMENT = "measured nothing"


def _workdir(tmp_path):
    """The eval's own `workdir` fixture, which a fixture cannot be lent to
    another module -- the same two files, copied rather than imported."""
    shutil.copy(harness.ROOT / "constellation.toml", tmp_path)
    (tmp_path / "retry.py").write_text(
        "def retry_delay(attempt):\n"
        "    return min(2 ** (attempt - 1), 4)\n")
    return tmp_path


# [stand-in-drive]
# Rationale: intercept `subprocess.run` at the `claude` argv rather than
#   replacing `harness.drive`, so everything `drive` does around the model --
#   catching the timeout, marking the result, recording the budget -- is the
#   real code under test. Replacing `drive` outright would leave this file
#   asserting on a stub it wrote itself, which is how a seam test comes to
#   pass while the seam is broken.
# Rejected: driving a real light model here. It is minutes and an API bill for
#   a question about message text, and the fast suite is run constantly.
def _instead_of_the_model(monkeypatch, behaviour):
    """Run `behaviour(workdir, timeout)` wherever the harness would run
    `claude`; every other subprocess the run makes goes through untouched."""
    real = subprocess.run

    def run(cmd, **kw):
        if isinstance(cmd, (list, tuple)) and cmd and cmd[0] == "claude":
            return behaviour(pathlib.Path(kw["cwd"]), kw.get("timeout"))
        return real(cmd, **kw)

    monkeypatch.setattr(harness.subprocess, "run", run)


def _ran_out_of_clock(workdir, timeout):
    """A drive killed at its budget with the board untouched."""
    raise subprocess.TimeoutExpired(
        ["claude"], timeout, output=b"I'll start by reading the board.")


def _declined_the_excursion(workdir, timeout):
    """A drive that settled both rows in place and dispatched nothing --
    the model reaching for `read` with the excursion column in front of it."""
    board = workdir / ".agent-work" / "r1" / "UNDERSTAND.toml"
    # Only below the seeded rows' own marker: the columns above it are the
    # commented template, and a replace over the whole file rewrites the
    # documentation as well as the board.
    head, mark, rows = board.read_text().partition("# --- the board ---")
    rows = rows.replace('status = "open"',
                        'status = "answered"\nmove = "read"\n'
                        'answer = "settled by reading retry.py"')
    rows = rows.replace('excursion = ""',
                        'excursion = "declined -- reading was enough"')
    board.write_text(head + mark + rows)
    return subprocess.CompletedProcess(["claude"], 0, "both rows settled.", "")


def _red_from(tmp_path, monkeypatch, behaviour):
    """Run the eval against a stood-in drive and hand back what it failed with."""
    _instead_of_the_model(monkeypatch, behaviour)
    with pytest.raises(BaseException) as caught:
        EVAL(_workdir(tmp_path))
    return str(caught.value)


def test_drive_timeout_is_not_a_silent_empty(tmp_path, monkeypatch):
    """A drive that ran out of clock fails as an instrument, not as a finding."""
    red = _red_from(tmp_path, monkeypatch, _ran_out_of_clock)
    assert INSTRUMENT in red, f"the timeout did not name itself:\n{red}"
    assert DECLINE not in red, (
        f"a killed drive was reported as the model declining the "
        f"excursion:\n{red}")
    # The budget belongs in the red: "cut off after 420s" is what tells a
    # reader to look at the clock rather than at the model.
    assert "cut off after 420s" in red, (
        f"the red does not say what budget was exhausted:\n{red}")


def test_a_settled_row_without_an_excursion_is_reported_as_the_finding(
        tmp_path, monkeypatch):
    """The other half of the seam: q1 worked and settled, no dispatch."""
    red = _red_from(tmp_path, monkeypatch, _declined_the_excursion)
    assert DECLINE in red, f"the decline did not name itself:\n{red}"
    assert INSTRUMENT not in red, (
        f"a model that settled q1 by reading was reported as a broken "
        f"drive:\n{red}")


def test_the_two_reds_do_not_read_alike(tmp_path, monkeypatch):
    """Distinguishable is the property, so it gets asserted directly."""
    timeout = _red_from(tmp_path, monkeypatch, _ran_out_of_clock)
    decline = _red_from(tmp_path, monkeypatch, _declined_the_excursion)
    assert timeout.splitlines()[0] != decline.splitlines()[0]


def test_a_completed_drive_is_not_marked_unfinished():
    """`unfinished` is what the reds are built from, so it says "" exactly
    when the drive ran to the end."""
    ok = subprocess.CompletedProcess(["claude"], 0, "", "")
    assert harness.unfinished(ok) == ""
    crashed = subprocess.CompletedProcess(["claude"], 1, "", "")
    assert "exited 1" in harness.unfinished(crashed)
