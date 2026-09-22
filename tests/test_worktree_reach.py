"""Work-id resolution across two roots (#52): a run addresses the same tree
whether the caller stands in the top-level checkout or inside the issue
worktree its work location actually lives in.

Four cwd-relative reads used to disagree the moment a worktree existed:
`journal.location` itself, the ledger's and the rail's open-run scan, the
check's `palette:` resolution and the subprocess it drives, and a measured
artifact's stored path. All four are exercised here, driven for real rather
than read off the source -- and the write side too: `_open_child` must nest
a freshly dispatched gate or panelist inside its parent's actual worktree,
never wherever the dispatching shell happens to be standing, or g4's later
archive move cannot find it.
"""

import json
import pathlib
import re
import subprocess
import sys
import time

import pytest

from engine import cli, journal, rail, render, run as runmod
from test_brief import _mint_dispatch_step, _wait_brief
from test_nesting import _fill_implement, _fill_open, _fill_consolidate, _fill_plan, \
    _dispatch_and_close_plan, _dispatch_plan_critic, _select_panel, \
    _work_the_board, _fill_plan_to_execute


def _open_one_gate(wid, issue, proof):
    """Drive a run-an-issue open to one freshly minted gate dispatch step,
    with a caller-chosen `proof` -- the shape a check-resolution test needs,
    which `test_nesting._mint_first_gate` does not expose. The proof is the
    plan round's own field now (#27): it has to ride in through `_fill_plan`,
    not a PLAN_TO_EXECUTE.toml block -- a stale `[[gates]]` block there is
    silently ignored rather than refused, which is exactly the trap this
    comment is here to name for the next reader. `_fill_plan_to_execute`
    (test_nesting.py) is the route form's own conductor fill now (ruling 3):
    `resolution` and, on a pass, the `plan` pointer that projects the gate."""
    cli.main(["open", "run-an-issue", "--issue", issue, "--title", "t"])
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    _dispatch_and_close_plan(wid, fill_fn=lambda w: _fill_plan(
        w, purpose="gate purpose", scope="gate scope", proof=proof))
    _dispatch_plan_critic(wid)
    _fill_plan_to_execute(wid)
    cli.main([wid, "submit"])


# -- an unknown id says where it looked, and refuses loudly (#67) -----------


def test_unknown_id_from_a_bare_cwd_says_none_here_and_refuses_nonzero(
        tmp_path, monkeypatch):
    """A subagent's cwd resets between bash calls, so a bare `spine <id>
    note ...` from a conductor thread that never `cd`'d anywhere lands in a
    directory with no `.agent-work` and no `.worktrees` -- the exact shape
    that used to read as a silently lost note. `none here` says the search
    space was empty, not merely that this one id was not in it."""
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as e:
        cli.main(["xyz", "note", "observation", "text"])
    msg = str(e.value)
    assert "none here" in msg
    assert "run this from the checkout or the worktree" in msg


def test_unknown_id_names_the_agent_work_roots_actually_present(
        workdir, capsys, monkeypatch):
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    capsys.readouterr()
    monkeypatch.chdir(workdir)  # back at the top level; issue17 lives in its worktree

    with pytest.raises(SystemExit) as e:
        cli.main(["nope", "note", "observation", "text"])
    msg = str(e.value)
    assert "none here" not in msg
    assert str(pathlib.Path(".worktrees", "issue17", ".agent-work")) in msg


def test_a_subprocess_run_from_a_bare_cwd_exits_nonzero(tmp_path):
    """Driven end to end, not just through `runmod.state`'s own return: the
    real failure mode is a caller's `&&` chain, so the exit code has to be
    the process's own, not merely a Python exception a test harness caught."""
    r = subprocess.run([render.spine_cmd(), "xyz", "note", "observation", "text"],
                       cwd=tmp_path, capture_output=True, text=True, timeout=20)
    assert r.returncode != 0
    # an uncaught SystemExit with a message writes it to stderr, never stdout
    assert "none here" in r.stderr


# -- the read side: an id resolves from the top level -------------------


def test_a_run_status_resolves_from_the_top_level_when_it_lives_in_a_worktree(
        workdir, capsys, monkeypatch):
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "parser eof"])
    capsys.readouterr()
    monkeypatch.chdir(workdir)  # the shell never followed the printed `cd`

    assert journal.exists("issue17")
    assert runmod.state("issue17") is not None
    cli.main(["issue17"])  # must not raise "no run named issue17"
    assert "issue17" in capsys.readouterr().out


def test_bare_ledger_from_the_top_level_lists_a_run_living_in_a_worktree(
        workdir, capsys, monkeypatch):
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "parser eof"])
    capsys.readouterr()
    monkeypatch.chdir(workdir)

    cli.main([])
    out = capsys.readouterr().out
    assert "issue17" in out and "parser eof" in out


def test_rail_scan_reaches_a_run_living_in_a_worktree(workdir, capsys, monkeypatch):
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "parser eof"])
    capsys.readouterr()
    monkeypatch.chdir(workdir)

    runs = rail._open_runs()
    assert any(st["id"] == "issue17" for st in runs)


def test_trace_from_the_top_level_reaches_a_run_living_in_a_worktree(
        workdir, capsys, monkeypatch):
    """`cmd_trace` derives each nested run's id relative to this run's own
    `.agent-work` -- not a literal cwd-relative one -- since a traced run's
    tree may be a worktree's rather than here."""
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "parser eof"])
    capsys.readouterr()
    monkeypatch.chdir(workdir)

    cli.main(["issue17", "trace"])  # must not raise
    out = capsys.readouterr().out
    assert "issue17" in out


# -- a check resolves and runs against the run's own tree, not the shell ----


def test_a_gates_check_resolves_and_runs_against_the_runs_own_worktree(
        workdir, capsys, monkeypatch):
    """`palette:canary` must expand against the worktree's own
    constellation.toml -- not the top-level checkout's, which never gained
    the entry -- and the command it expands to must then run with the
    worktree as cwd -- not wherever the submitting shell stands -- proven by
    a file the command can only see from inside the worktree."""
    _open_one_gate("issue17", "17", "palette:canary")
    capsys.readouterr()
    worktree = workdir / ".worktrees" / "issue17"

    # the new entry belongs inside the existing [commands] table, not a
    # second one shadowing it, so insert right after the table header
    toml = worktree / "constellation.toml"
    text = toml.read_text()
    assert text.count("[commands]") == 1
    toml.write_text(text.replace(
        "[commands]\n", '[commands]\ncanary = "test -f canary.txt"\n', 1))
    (worktree / "canary.txt").write_text("only visible from inside the worktree\n")

    st = runmod.state("issue17")
    step_id = st["current"]["id"]
    cli.main(["open", "run-a-gate", "--parent", "issue17", "--step", step_id])
    child_wid = f"issue17.{step_id}"
    _fill_implement(child_wid, step_id)
    capsys.readouterr()

    monkeypatch.chdir(workdir)  # the shell drifted back to the top level
    cli.main([child_wid, "submit"])  # must not raise -- the check must pass

    checks = [e for e in journal.read(child_wid) if e.get("kind") == "submit"][-1]["checks"]
    assert checks and checks[0]["exit"] == 0, checks


# -- a measured artifact resolves against the run's own tree ---------------


def test_measured_artifact_resolves_against_the_runs_own_tree_from_any_cwd(
        workdir, capsys, monkeypatch):
    """The `plan` field stores a work-location-inclusive path
    (`.agent-work/issue21/plan-1/plan.md`). Measuring it from a cwd that is
    not the run's own worktree must still find the real file -- resolved
    against the run's own tree, not doubled against its own work location.
    Proven on the plan segment's own dispatch child, which inherits the
    parent's tree (ruling 8) exactly the way a gate's child does."""
    cli.main(["open", "run-an-issue", "--issue", "21", "--title", "t"])
    wid = "issue21"
    worktree = workdir / ".worktrees" / wid
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])

    cli.main(["open", "cut-a-gate", "--parent", wid, "--step", "plan-1"])
    child = f"{wid}.plan-1"
    plan_path = worktree / ".agent-work" / wid / "plan-1" / "plan.md"
    plan_path.write_text(" ".join(["word"] * 50) + "\n")
    _fill_plan(child)
    capsys.readouterr()

    monkeypatch.chdir(workdir)  # a fresh session that never cd'd into the worktree
    cli.main([child, "submit"])

    measures = [e for e in journal.read(child) if e.get("kind") == "measure"]
    assert measures, "no measure entry -- the artifact path did not resolve"
    assert measures[-1]["words"] >= 50


# -- the write side: a dispatched child nests inside its parent's tree -----


def test_a_gate_dispatched_from_a_cwd_that_is_not_the_parents_worktree_still_nests_inside_it(
        workdir, capsys, monkeypatch):
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    wid = "issue17"
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    _dispatch_and_close_plan(wid)
    _dispatch_plan_critic(wid)
    _fill_plan_to_execute(wid)
    cli.main([wid, "submit"])
    step_id = runmod.state(wid)["current"]["id"]
    capsys.readouterr()

    monkeypatch.chdir(workdir)  # the conductor's shell never followed `open`'s cd
    cli.main(["open", "run-a-gate", "--parent", wid, "--step", step_id])

    child_wid = f"{wid}.{step_id}"
    worktree = workdir / ".worktrees" / wid
    assert (worktree / ".agent-work" / wid / step_id / "journal.toml").exists()
    assert not (workdir / ".agent-work").exists()  # no stray top-level work location
    assert journal.exists(child_wid)
    assert journal.location(child_wid).resolve() == worktree / ".agent-work" / wid / step_id
    cli.main([child_wid])  # must not raise -- resolves from the top level too


# -- the brief still names the worktree and the branch ----------------------
# The room itself never prints this any more (`o-single-dispatch-room`) --
# `_wait_brief` (test_brief.py) drives the real spawn and hands back what
# the process actually received.


def test_dispatch_brief_names_the_worktree_and_branch_for_a_root_run(workdir, capsys):
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    wid = "issue17"
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    _dispatch_and_close_plan(wid)
    _dispatch_plan_critic(wid)
    _fill_plan_to_execute(wid)
    cli.main([wid, "submit"])
    capsys.readouterr()

    text = _wait_brief(wid, workdir)
    worktree = workdir / ".worktrees" / wid
    assert str(worktree.resolve()) in text
    assert "branch" in text and wid in text


def test_review_panel_brief_on_a_nested_gate_names_the_parents_worktree_and_branch(
        workdir, capsys):
    """A gate's own run entry carries no branch or worktree of its own --
    only a root run's does -- so its review panel's brief must climb to the
    issue that dispatched it rather than come up empty."""
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    wid = "issue17"
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    _dispatch_and_close_plan(wid)
    _dispatch_plan_critic(wid)
    _fill_plan_to_execute(wid)
    cli.main([wid, "submit"])
    step_id = runmod.state(wid)["current"]["id"]
    cli.main(["open", "run-a-gate", "--parent", wid, "--step", step_id])
    child_wid = f"{wid}.{step_id}"
    _fill_implement(child_wid, step_id)
    cli.main([child_wid, "submit"])
    _select_panel(child_wid)               # mints the review step and its panel
    capsys.readouterr()

    text = _wait_brief(child_wid, workdir)
    worktree = workdir / ".worktrees" / wid
    assert str(worktree.resolve()) in text
    assert f"branch {wid}" in text


# -- #112 gate 2: a bound child cannot resolve outside its own subtree -----


def _await(path, seconds=20):
    end = time.time() + seconds
    while time.time() < end:
        if path.exists():
            return True
        time.sleep(0.05)
    return False


def _read_probe(path):
    """A probe file's own `<rc>\\n<combined output>` back into the two
    parts a test compares."""
    rc_line, _, rest = path.read_text(encoding="utf-8").partition("\n")
    return int(rc_line), rest


# [bound-probes-dispatch]
# Rationale: one real, test-configured `dispatch` entry, driven through
#   `cmd_wait`'s own real spawn (`checkrun.spawn_dispatch`) the way #112's
#   own `repro112.py` is -- never a hand-written `CONSTELLATION_BOUND` this
#   test sets itself, since the whole point is that the *engine* is the one
#   stamping it at spawn. The spawned process is a real bound child; every
#   `spine` call inside the script below is a real subprocess of that
#   child, inheriting whatever environment the engine gave it -- exactly
#   the position a rogue gate-conductor or panelist would stand in.
def _bound_probes_dispatch(root, out_dir, parent, step):
    out_dir = pathlib.Path(out_dir)
    script = (
        "import pathlib, subprocess, sys, os\n"
        f"out = pathlib.Path({str(out_dir)!r})\n"
        f"parent = {parent!r}\n"
        f"step = {step!r}\n"
        "out.mkdir(parents=True, exist_ok=True)\n"
        "brief = sys.argv[1]\n"
        "me = os.environ.get('CONSTELLATION_BOUND', '<unset>')\n"
        "(out / 'bound.txt').write_text(me)\n"
        "def spine(*a, env=None):\n"
        "    r = subprocess.run([sys.executable, '-m', 'engine.cli', *a],\n"
        "                       capture_output=True, text=True, env=env)\n"
        "    return f'{r.returncode}\\n{r.stdout}{r.stderr}'\n"
        # 1. its own id, and a further id it dispatches beneath itself
        "(out / 'own.txt').write_text(spine(me))\n"
        "from engine import journal\n"
        "sub = me + '.sub'\n"
        "journal.append(sub, 'run', title='t', assembly='run-a-gate')\n"
        "(out / 'sub.txt').write_text(spine(sub))\n"
        # 2. the parent that dispatched it, three ways
        "(out / 'parent_status.txt').write_text(spine(parent))\n"
        "(out / 'parent_amend.txt').write_text(\n"
        "    spine(parent, 'amend', 'close', step, '--reason', 'the child did this'))\n"
        "(out / 'parent_close.txt').write_text(spine(parent, 'close'))\n"
        # a genuinely never-minted control id, the same three ways
        "(out / 'control_status.txt').write_text(spine('zzz-never-minted'))\n"
        "(out / 'control_amend.txt').write_text(\n"
        "    spine('zzz-never-minted', 'amend', 'close', step, '--reason', 'the child did this'))\n"
        "(out / 'control_close.txt').write_text(spine('zzz-never-minted', 'close'))\n"
        # 3. every open run listed, none named
        "(out / 'bare.txt').write_text(spine())\n"
        # 4. the identical out-of-subtree command, two sessions
        "env_a = {**os.environ, 'CONSTELLATION_SESSION': 'probe-session-a'}\n"
        "env_b = {**os.environ, 'CONSTELLATION_SESSION': 'probe-session-b'}\n"
        "(out / 'session_a.txt').write_text(spine(parent, env=env_a))\n"
        "(out / 'session_b.txt').write_text(spine(parent, env=env_b))\n"
        "(out / 'done.txt').write_text('ok')\n"
    )
    entry = [sys.executable, "-c", script, "{brief}"]
    (pathlib.Path(root) / "constellation.toml").write_text(
        "[commands]\ndispatch = " + json.dumps(entry) + "\n")


def test_a_bound_childs_probes_resolve_only_its_own_subtree(bare_workdir, capsys):
    """Driven for real against `checkrun.spawn_dispatch`'s own spawn (never
    a hand-set env var): a dispatched child resolves itself and a further
    id it dispatches beneath itself, unaffected (o2's first half); reading
    its own dispatching parent three ways -- bare status, `amend close
    <step>`, `close` -- matches a genuinely-never-minted control id's own
    refusal byte for byte, apart from the id itself (o2's second half, and
    o3's "no new, differently-worded refusal"); and the bare ledger, every
    open run listed with none named, never surfaces the parent either (the
    "listed rather than named" half of o2)."""
    out = bare_workdir / "bound_probes"
    _mint_dispatch_step(wid="d1", child="d1.g1")
    _bound_probes_dispatch(bare_workdir, out, parent="d1", step="g1")

    cli.main(["d1", "wait", "--for", "1"])
    capsys.readouterr()
    assert _await(out / "done.txt"), "the bound child never finished its probes"

    assert (out / "bound.txt").read_text() == "d1.g1"

    rc, txt = _read_probe(out / "own.txt")
    assert rc == 0 and "d1.g1" in txt

    rc, txt = _read_probe(out / "sub.txt")
    assert rc == 0 and "d1.g1.sub" in txt

    for probe in ("status", "amend", "close"):
        p_rc, p_txt = _read_probe(out / f"parent_{probe}.txt")
        c_rc, c_txt = _read_probe(out / f"control_{probe}.txt")
        assert p_rc == c_rc != 0
        # the only difference between the two renders is the id named --
        # never a second, differently-worded refusal for "this is my parent"
        assert p_txt.replace("d1", "zzz-never-minted") == c_txt

    bare_rc, bare_txt = _read_probe(out / "bare.txt")
    assert re.search(r"(?m)^d1(\s|$)", bare_txt) is None  # never listed, only "d1.g1..." rows

    a_rc, a_txt = _read_probe(out / "session_a.txt")
    b_rc, b_txt = _read_probe(out / "session_b.txt")
    assert (a_rc, a_txt) == (b_rc, b_txt), \
        "a session- or caller-keyed guard could not survive this, even rendering the same words"


def test_review_panel_brief_from_inside_a_bound_child_still_names_its_own_branch(
        workdir, capsys, monkeypatch):
    """`_tree_info`'s own climb reads an ancestor -- exactly the id a bound
    process's own resolution cannot reach -- so without `_mint_child`'s
    `branch` stamp this brief would render an empty branch line the moment
    it runs inside a gate-conductor or panelist's own bound process. Proven
    by actually narrowing resolution with `CONSTELLATION_BOUND` (confirming
    the parent id really is unreachable first) rather than asserting on the
    stamp alone."""
    cli.main(["open", "run-an-issue", "--issue", "17", "--title", "t"])
    wid = "issue17"
    _fill_open(wid)
    cli.main([wid, "submit"])
    _work_the_board(wid)
    _fill_consolidate(wid)
    cli.main([wid, "submit"])
    _dispatch_and_close_plan(wid)
    _dispatch_plan_critic(wid)
    _fill_plan_to_execute(wid)
    cli.main([wid, "submit"])
    step_id = runmod.state(wid)["current"]["id"]
    cli.main(["open", "run-a-gate", "--parent", wid, "--step", step_id])
    child_wid = f"{wid}.{step_id}"
    _fill_implement(child_wid, step_id)
    cli.main([child_wid, "submit"])
    _select_panel(child_wid)               # mints the review step and its panel
    capsys.readouterr()

    monkeypatch.setenv("CONSTELLATION_BOUND", child_wid)  # standing inside the bound child
    assert journal.read(wid) == []  # the climb this stamp replaces would find nothing here

    text = _wait_brief(child_wid, workdir)  # still fully resolvable
    worktree = workdir / ".worktrees" / wid
    assert str(worktree.resolve()) in text
    assert f"branch {wid}" in text


# -- #112 gate 2, ruling 4: a bound child's own close still reaches its ------
# -- dispatching parent (`journal.unbound()`, engine/journal.py) ------------


# [bound-close-dispatch]
# Rationale: `cut-a-gate` -- one anchored, terminal step, no interior of its
#   own -- is the lightest real assembly in this repo that a dispatched
#   child can submit and close standing on nothing else, so the child here
#   is minted against it (`cli._mint_child`, the same mint `_spawn_outstanding`
#   itself would have made) and filled (`_fill_plan`) before the engine ever
#   spawns it -- the dispatch script below only submits and closes a form
#   that already carries an answer, never fills one itself, since filling is
#   plain file I/O this test process can do directly and the point under
#   test is `close`, not form-filling.
def _bound_close_dispatch(root, out_dir, child):
    out_dir = pathlib.Path(out_dir)
    script = (
        "import pathlib, subprocess, sys\n"
        f"out = pathlib.Path({str(out_dir)!r})\n"
        f"child = {child!r}\n"
        "out.mkdir(parents=True, exist_ok=True)\n"
        "brief = sys.argv[1]\n"
        "def spine(*a):\n"
        "    r = subprocess.run([sys.executable, '-m', 'engine.cli', *a],\n"
        "                       capture_output=True, text=True)\n"
        "    return f'{r.returncode}\\n{r.stdout}{r.stderr}'\n"
        "(out / 'submit.txt').write_text(spine(child, 'submit'))\n"
        "(out / 'close.txt').write_text(spine(child, 'close'))\n"
        "(out / 'done.txt').write_text('ok')\n"
    )
    entry = [sys.executable, "-c", script, "{brief}"]
    (pathlib.Path(root) / "constellation.toml").write_text(
        "[commands]\ndispatch = " + json.dumps(entry) + "\n")


def test_a_bound_childs_own_close_delivers_its_return_to_its_dispatching_parent(
        bare_workdir, capsys):
    """RULING 4's required case: without `cmd_close`'s own `journal.unbound()`
    block, a bound dispatched child's own `close` falls straight to the
    "parent not found" branch -- `journal.exists(st["parent"])` narrowed to
    the child's own subtree never admits the parent that dispatched it. Driven
    for real: the child submits and closes from inside its own dispatched
    subprocess, engine-bound (`CONSTELLATION_BOUND=d1.g1`, never hand-set),
    and the assertion reads the parent's own journal afterward for the
    `return` entry that delivery writes."""
    out = bare_workdir / "close_probe"
    journal.append("d1", "run", title="fix the parser", assembly="run-an-issue")
    journal.append("d1", "step", id="g1", segment="execute", dispatches="cut-a-gate",
                   prefill={"purpose": "bound close delivers its return"},
                   child="d1.g1", anchor=False, terminal=False, source="mint")
    cli._mint_child("cut-a-gate", "d1", "g1")
    _fill_plan("d1.g1")
    _bound_close_dispatch(bare_workdir, out, child="d1.g1")

    cli.main(["d1", "wait", "--for", "1"])
    capsys.readouterr()
    assert _await(out / "done.txt"), "the bound child never finished submit/close"

    rc, txt = _read_probe(out / "submit.txt")
    assert rc == 0, txt
    rc, txt = _read_probe(out / "close.txt")
    assert rc == 0, txt

    returns = [e for e in journal.read("d1") if e.get("kind") == "return"]
    assert any(r.get("child") == "d1.g1" and r.get("step") == "g1" for r in returns), \
        "d1.g1's close never delivered its return into d1's own journal"


# -- #112 gate 2 rework: the write guard stays scope-blind ------------------


def _bound_open_dispatch(root, out_dir, parent, assembly):
    """A bound child's own dispatched subprocess attempts `open <assembly>
    --id <parent>` -- the exact shape ruling 2/3 repaired: `cmd_open`'s guard
    has to read as "is this name already taken", not "can I resolve this id
    from here", or a bound `--id` naming its own parent would slip past it
    and overwrite that parent's journal in place."""
    out_dir = pathlib.Path(out_dir)
    script = (
        "import pathlib, subprocess, sys\n"
        f"out = pathlib.Path({str(out_dir)!r})\n"
        f"parent = {parent!r}\n"
        f"assembly = {assembly!r}\n"
        "out.mkdir(parents=True, exist_ok=True)\n"
        "brief = sys.argv[1]\n"
        "def spine(*a):\n"
        "    r = subprocess.run([sys.executable, '-m', 'engine.cli', *a],\n"
        "                       capture_output=True, text=True)\n"
        "    return f'{r.returncode}\\n{r.stdout}{r.stderr}'\n"
        "(out / 'open.txt').write_text(\n"
        "    spine('open', assembly, '--id', parent, '--issue', '99',\n"
        "          '--title', 'PWNED BY THE CHILD'))\n"
        "(out / 'done.txt').write_text('ok')\n"
    )
    entry = [sys.executable, "-c", script, "{brief}"]
    (pathlib.Path(root) / "constellation.toml").write_text(
        "[commands]\ndispatch = " + json.dumps(entry) + "\n")


def test_a_bound_childs_open_with_its_parents_id_refuses_and_leaves_the_parents_journal_untouched(
        bare_workdir, capsys):
    """RULING 2/3's required case, driven for real rather than by hand:
    reverting the two-line swap (`journal.journal_path(wid).exists()` back
    to `journal.exists(wid)` in `cmd_open`) leaves this silently green while
    the parent's journal gets clobbered in place -- exactly the exposure
    this test exists to hold shut. The child attempts the open from inside
    its own dispatched subprocess, engine-bound (`CONSTELLATION_BOUND=d1.g1`,
    never hand-set); the assertions read the parent's own journal before and
    after -- byte-identical, no new `run` entry -- and compare the refusal
    text to the same already-exists message an unbound caller gets for the
    identical id."""
    _mint_dispatch_step(wid="d1", child="d1.g1")
    before = journal.read("d1")
    out = bare_workdir / "open_probe"
    _bound_open_dispatch(bare_workdir, out, parent="d1", assembly="run-an-issue")

    cli.main(["d1", "wait", "--for", "1"])
    capsys.readouterr()
    assert _await(out / "done.txt"), "the bound child never finished its open attempt"

    rc, txt = _read_probe(out / "open.txt")
    assert rc != 0
    expected = render.located("d1 already exists\n  where it stands: spine d1")
    assert expected in txt

    after = journal.read("d1")
    # `wait` itself appends one `dispatch-started` entry when it spawns the
    # child -- the only growth this parent's journal should show. Anything
    # beyond it is the bound open having written through.
    new_kinds = [e.get("kind") for e in after[len(before):]]
    assert new_kinds == ["dispatch-started"], \
        f"the parent's journal grew by more than the dispatch itself: {new_kinds}"
    run_entries = [e for e in after if e.get("kind") == "run"]
    assert len(run_entries) == 1
    assert run_entries[0]["title"] == "fix the parser"
