"""The rail: an advisory Stop/SessionStart hook. Never blocks, never raises.

Two nudges, both read-only: Stop warns when a turn ends while a run is still
open; SessionStart re-injects resume context after compaction or a fresh
session. The escape from either is simply "proceed" -- v1's rail hard-refused
and the failures were the enforcement layer fighting itself. Every failure
mode here -- a malformed journal, a missing or unreadable .agent-work, empty
or garbage stdin -- must fall through to a clean exit and no output. A hook
that raises blocks the agent's turn, which is strictly worse than silence.
"""

import itertools
import json
import pathlib
import sys

from engine import run as runmod

SCAN_CAP = 20  # journals inspected, so an enormous tree can't slow the hook
SHOW_CAP = 3   # runs named before the rest collapse into a count


def _open_runs():
    root = pathlib.Path(".agent-work")
    if not root.exists():
        return []
    try:
        paths = list(itertools.islice(root.glob("**/journal.toml"), SCAN_CAP))
    except Exception:
        return []
    runs = []
    for p in paths:
        try:
            wid = str(p.parent.relative_to(root)).replace("/", ".")
            st = runmod.state(wid)
        except Exception:
            continue  # a malformed journal is silent, not a crash
        if st and st.get("open"):
            runs.append(st)
    return runs


def _event_name():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return ""
    return data.get("hook_event_name", "") if isinstance(data, dict) else ""


def _block(st, label, verb):
    i, n, seg = runmod.position(st, None)
    if st.get("awaiting_close"):
        # The quietest way to strand a parent: finish every step and walk away.
        return [f"{st['id']} needs closing · returns not yet stamped",
                f"  close it: spine {st['id']} close"]
    lines = [f"{st['id']} {label} · {seg} ({i} of {n})",
             f"  {verb}: spine {st['id']}"]
    for b in runmod.blocks(st):
        lines.append(f"  BLOCKED {b.get('id', '')} -- {b.get('text', '')}".rstrip())
    return lines


def message(event):
    runs = _open_runs()
    if not runs:
        return ""
    if event == "SessionStart":
        label, verb = "open", "resume"
    else:
        label, verb = "still open", "continue"
    shown, rest = runs[:SHOW_CAP], runs[SHOW_CAP:]
    out = []
    for st in shown:
        out.extend(_block(st, label, verb))
    if rest:
        out.append(f"...and {len(rest)} more open run{'s' if len(rest) != 1 else ''}")
    return "\n".join(out)


def main():
    try:
        text = message(_event_name())
    except Exception:
        text = ""
    if text:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
