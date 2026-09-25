"""Prior drops: every `rejected` call an archived run's own submit journaled,
read back from the record rather than a second file.

A finding has two destinations now (`docs/PURPOSE.md`): done, or dropped
with its reason recorded where a later run can find it. The record already
exists -- the `calls` table on the submit entry that ruled it `rejected`,
in the run's own journal, archived under `<top>/.agent-work/archive/` once
the run closes (`_sweep_to_archive`, engine/cli.py) -- so this reads that
rather than asking anything to write a second copy. `docs/DERIVED_IS_CODE.md`
is the rule this module follows.
"""

import pathlib
import re
import tomllib

from engine import forms

# A repo-relative path a finding or a reason names: a directory component,
# a file with an extension, and an optional trailing line number this
# strips rather than treats as part of the path -- `engine/cli.py` and
# `engine/cli.py:123` both name the one file.
_FILE = re.compile(r"\b[\w][\w./-]*/[\w.-]+\.[A-Za-z0-9]+\b(?::\d+)?")


def _files_in(text):
    """The repo-relative paths `text` names, `:line` stripped."""
    return {m.split(":")[0] for m in _FILE.findall(text or "")}


def _archived_journals(top):
    """`(run id, entries)` for every journal under `top`'s own archive, in
    no particular order -- an archive that does not exist yet (nothing has
    closed) yields none. A journal this process cannot parse is skipped
    rather than raising: it is a past run's own record, not this read's to
    hold open."""
    archive = pathlib.Path(top) / ".agent-work" / "archive"
    if not archive.is_dir():
        return
    for path in archive.glob("**/journal.toml"):
        wid = ".".join(path.relative_to(archive).parent.parts)
        try:
            entries = tomllib.loads(path.read_text(encoding="utf-8")).get("entry", [])
        except (OSError, tomllib.TOMLDecodeError):
            continue
        yield wid, entries


def rejected_calls(top):
    """Every `rejected` call any archived run's own submit journaled: the
    finding as it was written, the reason after the colon, the run id, the
    entry's own timestamp, and the files the finding and reason name.

    Nothing here is stored beyond the journal itself -- called fresh each
    time a room needs it, the way every other derived read in this engine
    is (`docs/DERIVED_IS_CODE.md`)."""
    out = []
    for wid, entries in _archived_journals(top):
        for entry in entries:
            if entry.get("kind") != "submit":
                continue
            rows = (entry.get("fields") or {}).get("calls")
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                call = str(row.get("call", ""))
                if forms.leading_word(call) != "rejected":
                    continue
                finding = str(row.get("finding", "")).strip()
                reason = call.split(":", 1)[1].strip() if ":" in call else ""
                out.append({
                    "run": wid,
                    "finding": finding,
                    "reason": reason,
                    "at": entry.get("at", ""),
                    "files": _files_in(finding) | _files_in(reason),
                })
    return out


def touching(drops, files):
    """`drops` narrowed to the ones whose own files intersect `files` --
    empty where `files` is empty, so a room with no diff yet shows none
    rather than every drop the archive has ever recorded."""
    files = set(files or ())
    if not files:
        return []
    return [d for d in drops if d["files"] & files]
