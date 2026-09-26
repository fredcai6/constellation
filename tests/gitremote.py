"""A git checkout for the fast suite -- never the network.

`cmd_open`'s root-run path resolves a top-level checkout, refuses one with no
remote, and pushes a branch before it journals anything. The twelve modules
that open a root run against a bare `tmp_path` need somewhere real for all
three to land, without ever reaching a live remote: `init_checkout` makes
`tmp_path` a checkout with one commit and a local bare repo as its `origin`.

Explicit, never autouse -- `test_code_map.py` asserts a bare, non-checkout
root is refused by name, and an autouse fixture would turn that refusal
green for the wrong reason rather than a real one.
"""

import json
import pathlib
import subprocess
import tomllib

# Mirrors this repo's own .agent-work/.worktrees rules, so `_commit_open`'s
# "nothing staged" path -- the ordinary case in production -- is the
# ordinary case in the fast suite too, rather than one the suite never hits.
_GITIGNORE = ".agent-work/\n.worktrees/\n"


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=str(cwd), check=True,
                   capture_output=True, text=True)


def init_checkout(tmp_path):
    """Make tmp_path a git checkout with one commit and a local bare remote
    named `origin`. Returns the bare repo's path.

    Stages everything already on disk, not just the `.gitignore` this writes
    -- a caller that drops `constellation.toml` into `tmp_path` before
    calling this expects it to be tracked, so `git worktree add` actually
    carries it into every worktree opened from here. A worktree only ever
    gets what the branch has committed."""
    remote = tmp_path.parent / f"{tmp_path.name}-remote.git"
    _git(tmp_path.parent, "init", "--quiet", "--bare", str(remote))
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "test")
    _git(tmp_path, "remote", "add", "origin", str(remote))
    (tmp_path / ".gitignore").write_text(_GITIGNORE)
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "--quiet", "-m", "initial")
    return remote


# [stub-gh]
# Rationale: intercept `gh` on argv, the way `tests/test_eval_harness.py`
#   already intercepts `claude` -- so `cmd_close`'s push-and-open-a-PR step
#   never reaches the real GitHub API. A test that let this fall through to
#   a real `gh` binary could open a real pull request against whatever
#   `origin` happens to point at, which is not acceptable at any cost even
#   once (`origin` here is always `init_checkout`'s own local bare repo, so
#   a real `gh` would only ever fail to resolve it -- but "fails safely" is
#   not the same guarantee as "never asked").
# Rejected: monkeypatching `engine.cli.subprocess.run` by name instead of
#   the bare module. They are the same object -- `import subprocess`
#   anywhere binds the one module in `sys.modules` -- so patching the
#   module directly reaches every caller, `_git` included, with one seam.
def stub_gh(monkeypatch, ok=True, pr_url="https://example.invalid/pr/1", stderr="",
           calls=None, open_pr="", prs=None):
    """Every `gh ...` call returns as if it had succeeded (or failed, with
    `ok=False`); every other subprocess call goes through untouched.

    `calls`, given a list, gets the argv of every intercepted `gh` call
    appended to it -- how a test asserts the command actually ran, without
    asserting on a stub it wrote itself for anything but "ran" and "with
    what argv".

    `prs` is what `gh pr list` finds on the branch, as `{"url", "state"}`
    dicts: nothing by default. `open_pr` is shorthand for one open PR."""
    if prs is None:
        prs = [{"url": open_pr, "state": "OPEN"}] if open_pr else []
    real = subprocess.run

    def run(cmd, **kw):
        if isinstance(cmd, (list, tuple)) and cmd and cmd[0] == "gh":
            if calls is not None:
                calls.append(list(cmd))
            if ok and list(cmd[1:3]) == ["pr", "list"]:
                return subprocess.CompletedProcess(cmd, 0, _pr_list(list(cmd), prs), "")
            if ok:
                return subprocess.CompletedProcess(cmd, 0, f"{pr_url}\n", "")
            return subprocess.CompletedProcess(cmd, 1, "", stderr or "gh: failed")
        return real(cmd, **kw)

    monkeypatch.setattr(subprocess, "run", run)


def _pr_list(argv, prs):
    """What `gh pr list` prints for `prs`: filtered by `--state` as gh does
    (it defaults to open), and, under a `--jq`, the first URL -- the one
    filter the engine has ever asked for."""
    state = argv[argv.index("--state") + 1] if "--state" in argv else "open"
    found = [p for p in prs if state == "all" or p["state"] == state.upper()]
    if "--jq" in argv:
        return f"{found[0]['url']}\n" if found else ""
    return json.dumps(found)


def read_archived(top, wid, kind=None):
    """Read a closed and archived run's journal straight off disk.

    Once `cmd_close` archives a root run, its id no longer resolves through
    `journal.root_for` -- that is the point of archiving, not a bug this
    helper works around -- so a test that wants to see what landed reads the
    file directly, the same way a human would."""
    path = (pathlib.Path(top) / ".agent-work" / "archive"
            / pathlib.Path(*wid.split(".")) / "journal.toml")
    entries = tomllib.loads(path.read_text()).get("entry", [])
    return entries if kind is None else next(e for e in entries if e["kind"] == kind)
