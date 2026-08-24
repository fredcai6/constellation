"""The journal: one append-only TOML file per run, and nothing else that's state.

A run's whole history is `.agent-work/<work-id>/journal.toml`, a sequence of
`[[entry]]` blocks. Current state is a fold over the file -- there is no
mutable spine, so two sessions appending to the same run is a fact the record
shows, never a race the engine has to prevent.
"""

import datetime
import os
import pathlib
import time
import tomllib

from engine import tomlw

_RETRY_WINERRORS = (32, 33)  # sharing violation, lock violation


def location(work_id: str) -> pathlib.Path:
    """Work location for an id; dotted ids nest ("issue17.g1" -> issue17/g1)."""
    return pathlib.Path(".agent-work", *work_id.split("."))


def journal_path(work_id: str) -> pathlib.Path:
    return location(work_id) / "journal.toml"


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


def append(work_id: str, kind: str, **data) -> dict:
    """Append one [[entry]] block; return the entry as written."""
    stamps = {
        "kind": kind,
        "at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "session": os.environ.get("CONSTELLATION_SESSION", str(os.getpid())),
    }
    entry = {**stamps, **data}  # caller-supplied keys win over stamps
    path = journal_path(work_id)
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
    """All entries in append order; a missing journal reads as no history."""
    path = journal_path(work_id)
    if not path.exists():
        return []
    with open(path, "rb") as f:
        return tomllib.load(f).get("entry", [])
