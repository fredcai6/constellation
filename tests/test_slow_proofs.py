"""A proof slower than the caller's turn.

#72, measured: a dispatched agent's harness moves any foreground command still
running at ~120s into the background and the agent's turn ends there, never
woken. The engine's process survived and journaled its submit 25 seconds
later; nobody was left to read it. So the fix is not survival, it is that
`submit` returns control first -- and #36 is the other half, because the
number it returns against cannot be one more hardcoded constant.

Every test here drives real processes, and keeps them under a couple of
seconds by making both numbers small.
"""

import json
import pathlib
import subprocess
import sys
import time

import pytest

from engine import checks, cli, journal, run as runmod
from gitremote import init_checkout


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONSTELLATION_SESSION", "test-session")
    init_checkout(tmp_path)
    return tmp_path


def _gate(proof, wid="g1", **spec):
    """A gate standing on IMPLEMENT.toml with a chosen proof, and whatever
    else of a gate spec the caller wants in its orders."""
    pathlib.Path("constellation.toml").write_text('[models]\nstandard = "x"\n')
    cli.main(["open", "run-a-gate", "--id", wid])
    journal.append(wid, "prefill", fields={"proof": proof, **spec})
    pathlib.Path(f".agent-work/{wid}/IMPLEMENT.toml").write_text(
        'change = "c"\ndeviations = "waived: none"\n')
    return wid


def _kinds(wid):
    return [e.get("kind") for e in journal.read(wid)]


def _await(wid, kind, seconds=20):
    """Wait for the detached runner to append its own outcome. Polls the
    journal because that is the only thing the two processes share."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        entry = next((e for e in journal.read(wid) if e.get("kind") == kind), None)
        if entry:
            return entry
        time.sleep(0.05)
    raise AssertionError(f"no {kind} entry landed in {seconds}s: {_kinds(wid)}")


# -- the common path, unchanged ----------------------------------------------


def test_a_proof_that_finishes_inside_the_handback_submits_exactly_as_before(
        workdir, capsys):
    """The overwhelming majority of steps. The check runs, passes, and the
    submit lands with it inline, in one journal entry and one turn."""
    _gate("true")
    capsys.readouterr()

    cli.main(["g1", "submit"])

    assert "submitted work-1" in capsys.readouterr().out
    submits = [e for e in journal.read("g1") if e.get("kind") == "submit"]
    assert len(submits) == 1
    assert submits[0]["step"] == "work-1"
    assert submits[0]["checks"] == [{"command": "true", "exit": 0, "output": ""}]
    assert "check-started" not in _kinds("g1")     # nothing to say: it finished
    assert runmod.state("g1")["current"]["id"] != "work-1"


def test_a_proof_that_fails_inside_the_handback_refuses_and_records_no_submit(
        workdir):
    """The guarantee the whole design is arranged around, on the path that
    always had it: a failing proof records the check and no submit."""
    _gate("exit 3")

    with pytest.raises(SystemExit) as e:
        cli.main(["g1", "submit"])

    assert "exited 3" in str(e.value)
    assert "amend close" in str(e.value)
    assert "submit" not in _kinds("g1")
    checked = [x for x in journal.read("g1") if x.get("kind") == "check"]
    assert checked[-1]["exit"] == 3 and checked[-1]["command"] == "exit 3"
    assert runmod.state("g1")["current"]["id"] == "work-1"


# -- past the handback -------------------------------------------------------


def test_a_proof_past_the_handback_returns_control_and_journals_no_submit(
        workdir, capsys, monkeypatch):
    """The whole point. The caller gets its turn back while the proof is still
    running, and what is recorded at that moment is that the check started --
    never the submit, which nobody yet has an exit status for."""
    monkeypatch.setattr(checks, "HANDBACK", 1)
    _gate("sleep 30")
    capsys.readouterr()

    began = time.time()
    assert cli.main(["g1", "submit"]) == 0        # returns, and does not refuse
    held = time.time() - began

    assert held < 10, f"held the caller for {held:.1f}s"
    assert "submit" not in _kinds("g1")
    started = journal.read("g1")[-1]
    assert started["kind"] == "check-started"
    assert started["step"] == "work-1"
    assert started["commands"] == [{"field": "proof", "command": "sleep 30"}]

    st = runmod.state("g1")
    assert st["current"]["id"] == "work-1"        # the step is not done
    assert runmod.in_flight(st, st["current"]) == started

    out = capsys.readouterr().out
    assert "in flight" in out and str(started["pid"]) in out


def test_the_detached_proof_appends_its_own_submit_when_it_passes(
        workdir, capsys, monkeypatch):
    """The caller left with nothing journaled but a start. The submit that
    lands afterwards is the runner's, and it advances the run."""
    monkeypatch.setattr(checks, "HANDBACK", 1)
    _gate("sleep 2; true")
    cli.main(["g1", "submit"])
    assert "submit" not in _kinds("g1")

    landed = _await("g1", "submit")

    assert landed["step"] == "work-1"
    assert landed["checks"] == [{"command": "sleep 2; true", "exit": 0, "output": ""}]
    st = runmod.state("g1")
    assert "work-1" in st["done"]
    assert not st["in_flight"]                    # the started entry is answered
    assert st["current"]["id"] != "work-1"        # and the next step was minted

    capsys.readouterr()
    cli.main(["g1"])
    assert "in flight" not in capsys.readouterr().out


def test_the_detached_proof_appends_a_check_and_no_submit_when_it_fails(
        workdir, monkeypatch):
    """The guarantee, on the path that could have broken it: the runner holds
    the exit status, so it is the only process that can write a submit -- and
    it writes one only on exit 0."""
    monkeypatch.setattr(checks, "HANDBACK", 1)
    _gate("sleep 2; exit 4")
    cli.main(["g1", "submit"])

    failed = _await("g1", "check")

    assert failed["step"] == "work-1" and failed["exit"] == 4
    assert "submit" not in _kinds("g1")
    st = runmod.state("g1")
    assert st["current"]["id"] == "work-1"        # still standing on the step
    assert not st["in_flight"]                    # and no longer in flight


def test_a_second_submit_while_the_proof_is_running_refuses(workdir, monkeypatch):
    """Two runners against one step can both reach exit 0, and that is the one
    interleaving that would journal the submit twice."""
    monkeypatch.setattr(checks, "HANDBACK", 1)
    _gate("sleep 30")
    cli.main(["g1", "submit"])

    with pytest.raises(SystemExit) as e:
        cli.main(["g1", "submit"])

    assert "running since" in str(e.value)
    assert len([k for k in _kinds("g1") if k == "check-started"]) == 1


def test_a_started_check_whose_process_is_gone_reads_as_work_to_redo(
        workdir, capsys):
    """The orphan: killed mid-run, or the machine went away. Rendering it as a
    proof still in flight would leave the run waiting forever on nothing."""
    _gate("true")
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()                                   # a pid that is really gone
    journal.append("g1", "check-started", step="work-1", pid=dead.pid, cwd=".",
                   budget=600, log="check.work-1.log",
                   commands=[{"field": "proof", "command": "true"}])
    capsys.readouterr()

    cli.main(["g1"])
    out = capsys.readouterr().out
    assert "process is gone" in out
    assert "run it again" in out and "submit" in out

    cli.main(["g1", "submit"])                    # and the re-run is not refused
    assert "submit" in _kinds("g1")


# -- the budget --------------------------------------------------------------


def test_a_proof_that_outruns_its_budget_refuses_and_names_the_budget(
        workdir, monkeypatch):
    """#36: "fix the command, or drop this step" are both wrong for a check
    that is slow because it is correct. The refusal separates the two readings
    and names the declaration that buys the time."""
    monkeypatch.setattr(checks, "BUDGET", 1)
    _gate("sleep 30")

    with pytest.raises(SystemExit) as e:
        cli.main(["g1", "submit"])

    said = str(e.value)
    assert "did not finish in 1s" in said
    assert "needs longer" in said and 'budget = "2"' in said   # the new escape
    assert "amend close" in said                               # and the old one
    assert "submit" not in _kinds("g1")
    assert [x for x in journal.read("g1") if x.get("kind") == "check"][-1]["exit"] == -1


def test_a_gate_spec_declaring_its_own_budget_is_run_under_it(workdir, monkeypatch):
    """The budget is the gate spec's to declare, so a spec that says its proof
    is long must not be held to the engine's default -- and one that says it is
    short must be stopped there."""
    monkeypatch.setattr(checks, "BUDGET", 600)
    _gate("sleep 30", budget="1")

    with pytest.raises(SystemExit) as e:
        cli.main(["g1", "submit"])

    assert "did not finish in 1s" in str(e.value)     # 1, not the default 600
    payload = json.loads(pathlib.Path(
        ".agent-work/g1/check.work-1.json").read_text())
    assert payload["budget"] == 1


def test_a_budget_that_is_not_seconds_refuses_before_anything_runs(workdir):
    """A spec that meant fifteen minutes and typed `15m` has declared
    something. Running it under the default instead makes the declaration
    decoration."""
    _gate("true", budget="15m")

    with pytest.raises(SystemExit) as e:
        cli.main(["g1", "submit"])

    assert "'15m'" in str(e.value) and "seconds" in str(e.value)
    assert "submit" not in _kinds("g1")
    assert "check" not in _kinds("g1")
