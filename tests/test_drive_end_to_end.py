"""End-to-end proof of the childless-form-step filler mechanism
(commitment 13): one call to `drive`, over a real `run-a-gate` open, walks
the run through two genuine childless form steps -- `work-1` (filler
`implementer`) and `select` (filler `conductor`, `skeleton()`'s own
pre-minted transition, `assemblies/run-a-gate/ASSEMBLY.toml`) -- each
resolved by a real spawned process running through the same `[commands]
dispatch` entry `spawn_dispatch`/`spawn_form_filler` share
(`checks._dispatch_launch`). Never `claude`, always a short-lived
`python3 -c ...` of this test's own choosing; for the form-filler shape,
one that actually reads its own `{brief}`, finds its response form's
absolute path, fills every blank slot the materialized template left (the
same slots a human would fill by hand -- generic, not one script per form),
and runs `spine <wid> submit` for real. The two-step mix needs no second
assembly file and no monkeypatch: `run-a-gate`'s own `work` segment mints
both its interior step and its transition (`select`) at `open` time
(`runmod.skeleton`), and neither declares an outcome table its own
scalar fields drive (`work`'s `decides` names `ruling`, a field only
`IMPASSE.toml` carries; `select` declares no `decides` at all), so
submitting either does nothing beyond marking it done and -- `select`
alone -- minting the panel its own `panelists` plan field describes
(`assemblies/run-a-gate/ASSEMBLY.toml`'s own `_PANEL_MINT` branch).

That panel is real too, but its own panelist is never meant to resolve:
this test's one dispatch entry does nothing for a dispatch child's own
brief (which never carries a "your response form:" line -- that wording is
`_form_filler_brief`'s alone), so the spawned stand-in exits almost at
once. `checkrun.alive` reads that exit as gone (a zombie answers "exited",
#101), so `drive` restarts the panelist up to `checkrun.MAX_STARTS` and
then stops on its own with the child spent -- before its `--for` bound,
which is why the elapsed time is asserted short rather than long. The
panel never resolving is proven directly, with a real dead pid, in
`test_drive.py`'s own cases; here it is only what ends the drive.
"""

import json
import os
import pathlib
import sys
import threading
import time

from engine import checks as checkrun
from engine import cli, journal
from engine import run as runmod

_SCRIPT_TEMPLATE = r'''
import os, pathlib, re, sys
marker_dir = pathlib.Path({marker_dir!r})
marker_dir.mkdir(parents=True, exist_ok=True)
brief = sys.argv[1]
(marker_dir / f"{{os.getpid()}}.brief").write_text(brief)
m = re.search(r"your response form: (\S+)", brief)
if m:
    os.environ["CONSTELLATION_SESSION"] = str(os.getpid())
    dest = pathlib.Path(m.group(1))
    text = dest.read_text()
    def _fill_block(g):
        return g.group(1) + ' = """\nthrowaway\n"""'
    def _fill_short(g):
        return g.group(1) + ' = "throwaway"'
    text = re.sub(r'^(\w+) = """\n"""$', _fill_block, text, flags=re.M)
    text = re.sub(r'^(\w+) = ""$', _fill_short, text, flags=re.M)
    dest.write_text(text)
    wid = dest.parent.name
    from engine import cli
    cli.main([wid, "submit"])
'''


# [e2e-dispatch-and-fill]
# Rationale: one `[commands] dispatch` entry, shared by every dispatch
#   child (the review panel this test's own `select` submit mints) and
#   every form filler alike -- the same real command
#   `spawn_dispatch`/`spawn_form_filler` both launch through
#   (`checks._dispatch_launch`). A dispatch child's own brief
#   (`render.brief`) never carries a "your response form:" line -- that
#   wording is `_form_filler_brief`'s alone -- so the two are told apart by
#   its presence in `{brief}`, not by a second dispatch entry: a dispatch
#   child's own brief leaves the `if m:` body unreached and the process
#   simply exits, which is exactly the "dies almost at once" shape the
#   module docstring's own review-panel paragraph depends on.
def _e2e_dispatch(root, marker_dir):
    script = _SCRIPT_TEMPLATE.format(marker_dir=str(marker_dir))
    entry = [sys.executable, "-c", script, "{brief}"]
    pathlib.Path(root, "constellation.toml").write_text(
        '[roles]\nimplementer = "standard"\n\n'
        "[commands]\ndispatch = " + json.dumps(entry) + "\n")


def test_drive_fills_and_submits_two_real_childless_form_steps(
        bare_workdir, capsys, monkeypatch):
    monkeypatch.setattr(checkrun, "WAIT_POLL", 0.05)
    # The review panel `select`'s own real submit mints is never meant to
    # resolve (see module docstring) -- pinned small so the one nested
    # `wait` call blocking on it cannot itself outrun `drive`'s own bound.
    monkeypatch.setattr(checkrun, "WAIT_BOUND", 0.3)
    marker = bare_workdir / "spawned"
    _e2e_dispatch(bare_workdir, marker)
    wid = "g1"
    cli.main(["open", "run-a-gate", "--id", wid])
    capsys.readouterr()

    began = time.monotonic()
    code = cli.main([wid, "drive", "--for", "8"])
    elapsed = time.monotonic() - began
    capsys.readouterr()

    assert code == 0
    assert elapsed < 8, f"elapsed {elapsed}"   # stopped spent, not on the bound
    panel_starts = [e for e in journal.read(wid) if e.get("kind") == "dispatch-started"]
    assert len(panel_starts) == checkrun.MAX_STARTS

    filler_entries = {e["step"]: e for e in journal.read(wid)
                      if e.get("kind") == "form-filler-started"}
    assert set(filler_entries) == {"work-1", "select"}

    submits = {e["step"]: e for e in journal.read(wid)
              if e.get("kind") == "submit" and e.get("step") in ("work-1", "select")}
    assert set(submits) == {"work-1", "select"}
    assert submits["work-1"]["fields"] == {"change": "throwaway", "deviations": "throwaway"}
    assert submits["select"]["fields"]["omitted"] == "throwaway"
    assert submits["select"]["fields"]["panelists"] == [
        {"worker": "throwaway", "model": "throwaway", "criteria": "throwaway"}]

    # Each submit's own `session` is the spawned filler's real pid -- proof
    # that the spawned process did the submitting, not this test's own.
    for step_id, submit in submits.items():
        assert submit["session"] == str(filler_entries[step_id]["pid"])
        assert submit["session"] != str(os.getpid())

    # The review panel `select`'s own submit minted is real; its one
    # panelist never resolves, so the run is still open, standing on it.
    assert not runmod.state(wid)["awaiting_close"]
