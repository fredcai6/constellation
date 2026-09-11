"""The journal: one append-only TOML file per run, and nothing else that's state.

A run's whole history is `.agent-work/<work-id>/journal.toml`, a sequence of
`[[entry]]` blocks. Current state is a fold over the file -- there is no
mutable spine, so two sessions appending to the same run is a fact the record
shows, never a race the engine has to prevent.
"""

import datetime
import os
import pathlib
import sys
import time
import tomllib

from engine import tomlw

_RETRY_WINERRORS = (32, 33)  # sharing violation, lock violation


# [worktree-reach]
# Rationale: a work id addresses the same run whether the caller stands in
#   the top-level checkout or inside the issue worktree that run's work
#   location actually lives in -- ruling 8 put git at the issue tier, which
#   means every id below the root physically nests inside one of these.
#   `.worktrees` is a sibling of the top-level checkout's own tracked tree
#   (never nested inside a worktree itself), so this is reachable only from
#   the top level and from inside the one worktree it names -- never from a
#   second, unrelated worktree, which cannot see a sibling it did not make.
# Rejected: threading a project-root parameter through every call site that
#   addresses a run. The id is the address; a second parameter carrying the
#   same information by another route is the thing ruling 8's "never
#   inferred from cwd" was already refusing, aimed at a different word.
_WORKTREES_DIR = ".worktrees"  # mirrors engine/cli.py's own -- both name the
                                # one convention a worktree is made under


def _worktree_agent_work_dirs() -> list[pathlib.Path]:
    """Every sibling worktree's own `.agent-work`, present only from the
    top-level checkout."""
    d = pathlib.Path(_WORKTREES_DIR)
    if not d.is_dir():
        return []
    return [p / ".agent-work" for p in sorted(d.iterdir()) if (p / ".agent-work").is_dir()]


def agent_work_roots() -> list[pathlib.Path]:
    """Every `.agent-work` reachable from here: this checkout's own, then
    each sibling worktree's -- what a scan for every open run needs in order
    to see one that lives inside a worktree from the top level."""
    roots = [pathlib.Path(".agent-work")] if pathlib.Path(".agent-work").is_dir() else []
    return roots + _worktree_agent_work_dirs()


def searched_roots() -> str:
    """Where `root_for` just looked for a work id it could not find, said in
    one line -- `agent_work_roots`'s own list, since a refusal that named
    different roots than the search actually walked would point a caller
    somewhere the lookup never went. `"none here"` when this cwd carries
    neither a `.agent-work` of its own nor a `.worktrees` holding one --
    ruling 8's own case, and #67's second finding: a subagent's cwd resets
    between bash calls, so a bare `spine <id> note ...` run from the wrong
    directory must say where it looked rather than read as lost work."""
    roots = agent_work_roots()
    return ", ".join(str(r) for r in roots) if roots else "none here"


def root_for(work_id: str) -> pathlib.Path:
    """Where an existing work id's `.agent-work` actually lives: this
    checkout's own, tried first, then each sibling worktree's. Found in
    neither -- the ordinary case for a run not yet minted -- defaults to
    here, exactly where it has always landed."""
    rel = pathlib.Path(*work_id.split("."))
    if (pathlib.Path(".agent-work") / rel).exists():
        return pathlib.Path(".")
    for d in _worktree_agent_work_dirs():
        if (d / rel).exists():
            return d.parent
    return pathlib.Path(".")


def location(work_id: str, root: pathlib.Path = None) -> pathlib.Path:
    """Work location for an id; dotted ids nest ("issue17.g1" -> issue17/g1).

    Resolved against `root_for` by default, so an id addresses the same run
    from the top level or from inside its own worktree. `root` is an escape
    for the one caller that must not use that resolution: `_open_child`
    minting a brand-new child, which exists in neither root yet and so would
    otherwise resolve against cwd -- wrong when cwd is not the child's
    parent's own worktree. That caller passes the parent's actual root
    instead of leaving this to guess.
    """
    return (root_for(work_id) if root is None else root) / ".agent-work" / pathlib.Path(*work_id.split("."))


def journal_path(work_id: str, root: pathlib.Path = None) -> pathlib.Path:
    return location(work_id, root) / "journal.toml"


def exists(work_id: str) -> bool:
    return journal_path(work_id).exists()


def _open_for_append(path: pathlib.Path, attempts=5, delay=0.05):
    """Open in append mode, retrying past transient Windows sharing violations.

    A no-op cost on POSIX: the retry loop only ever runs once there.
    """
    for i in range(attempts):
        try:
            return open(path, "a", encoding="utf-8")
        except OSError as e:
            transient = isinstance(e, PermissionError) or getattr(e, "winerror", None) in _RETRY_WINERRORS
            if not transient or i == attempts - 1:
                raise
            time.sleep(delay)


def stamp() -> str:
    """The one timestamp shape this repo writes: UTC, to the second. A
    journal entry's `at` and a check log's own attempt header are the same
    instant written the same way, so a reader lines them up by eye."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def append(work_id: str, kind: str, *, root: pathlib.Path = None, **data) -> dict:
    """Append one [[entry]] block; return the entry as written.

    `root` is the same escape `location` takes -- unused once a run's first
    entry has landed, since every append after that finds it through
    ordinary resolution.
    """
    stamps = {
        "kind": kind,
        "at": stamp(),
        "session": os.environ.get("CONSTELLATION_SESSION", str(os.getpid())),
    }
    entry = {**stamps, **data}  # caller-supplied keys win over stamps
    path = journal_path(work_id, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    block = tomlw.table("entry", entry) + "\n"
    f = _open_for_append(path)
    try:
        f.write(block)
        f.flush()
        os.fsync(f.fileno())
    finally:
        f.close()
    return entry


def read(work_id: str) -> list[dict]:
    """All entries in append order; a missing journal reads as no history.

    A torn tail reads as the history up to the tear. An append interrupted
    partway -- Ctrl-C, a harness timeout, an OOM kill, a full disk -- leaves
    a half-written block that fails the whole parse, and since state is a
    fold over this file, a raising read would brick every verb on the run.
    Entries are blank-line separated by construction, so the last intact
    boundary is recoverable: drop the torn block, keep the work.

    The loop always returns: `split` yields at least one block, and once the
    last has been popped the join is the empty string, which parses as no
    entries. Total loss is that case, not a separate arm -- there was a
    `return []` after this loop for years and no test could reach it, which
    is what #34 measured as an uncovered line and what it actually was.
    """
    path = journal_path(work_id)
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        return tomllib.loads(text).get("entry", [])
    except tomllib.TOMLDecodeError:
        pass
    blocks = text.split("\n\n")
    dropped = 0
    while True:
        blocks.pop()  # the torn tail, and any block it broke
        dropped += 1
        try:
            entries = tomllib.loads("\n\n".join(blocks)).get("entry", [])
        except tomllib.TOMLDecodeError:
            continue
        _say_dropped(path, dropped)
        return entries


# [never-drop-quietly]
# Rationale: keeping the work past a tear is right; keeping it quietly is
#   not. A discarded block is lost state, and the agent that just wrote it is
#   the only one who can put it back -- on `issue57` two submits landed,
#   neither folded, and the run looked untouched until the file was opened by
#   hand. The step also still reads as current, which invites the retry that
#   tears the file a second time.
# Rejected: raising instead. State is a fold over this file, so a raising
#   read bricks every verb on the run -- including the ones that would repair
#   it. The secretary says what it lost and carries on.
def _say_dropped(path, count):
    print(f"{path}: {count} entry block{'s' if count > 1 else ''} could not be read "
          f"and {'were' if count > 1 else 'was'} skipped -- the work in "
          f"{'them' if count > 1 else 'it'} is not in this run's state",
          file=sys.stderr)
