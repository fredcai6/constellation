"""Boards: read, validate, and derive state from the understand board's
`[[question]]` rows.

A board is a living TOML file the interrogator skill seeds and the agent
edits in place (skills/interrogator/forms/UNDERSTAND.toml is the template).
This module does not write boards -- only reads rows, checks them at the
consolidate transition (an open row refuses; a decision answered without the
principal's words refuses; the escape is `deferred: <reason>`, journaled),
and computes what the board's own state already implies: which rows are
askable, which are held and by what, which clusters are ready, and the
counts. Nothing more -- this engine is a secretary, not an auditor.
"""

import tomllib

_DEFERRED = "deferred:"


def rows(board_path) -> list[dict]:
    """Every [[question]] row, in file order. Missing file -> []."""
    try:
        with open(board_path, "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        return []
    return data.get("question", [])


def validate(board_path) -> list[str]:
    """Human-readable problems, empty when the board is clean. Each string
    names the offending row id and what is wrong -- no lecture, and it
    states the way out."""
    try:
        found = rows(board_path)
    except Exception:
        return [f"{board_path}: not a readable board -- fix or delete it"]

    problems = []
    for i, row in enumerate(found):
        rid = row.get("id") or f"row {i + 1}"
        if not row.get("question") or not row.get("type"):
            problems.append(f"{rid}: missing question or type -- fill both, "
                            "or drop the row")
            continue
        status = str(row.get("status", "open"))
        reason = status[len(_DEFERRED):].strip() if status.startswith(_DEFERRED) else None
        if status in ("answered", "moot") or reason:
            # The engine can only catch a decision recorded with no words at
            # all -- it cannot verify a human actually spoke. That honesty
            # lives one tier up, at the principal.
            if row["type"] == "decision" and status == "answered" and not str(row.get("answer", "")).strip():
                problems.append(f"{rid}: decision answered with no words -- "
                                 "record the principal's answer, or deferred: <reason>")
        elif status.startswith("deferred"):
            problems.append(f"{rid}: deferred with no reason -- deferred: <reason>")
        else:
            problems.append(
                f"{rid}: sent up and not answered yet -- record the principal's "
                "answer, or deferred: <reason>" if status == "up" else
                f"{rid}: still {status} -- resolve it, or answer deferred: <reason>")
    return problems


def _open(row) -> bool:
    return str(row.get("status", "open")) == "open"


def _holding(row, by_id) -> list[str]:
    """Ids in `row`'s `after` that are still open or up -- with the
    principal or not yet reached, either way not settled. A deferred, moot,
    or answered dependency does not hold; an id naming no row on this board
    is not a dependency."""
    return [a for a in row.get("after", [])
            if a in by_id and str(by_id[a].get("status", "open")) in ("open", "up")]


def askable(rows) -> list[dict]:
    """Rows workable right now: open, with nothing in `after` still open or
    up."""
    by_id = {r["id"]: r for r in rows if r.get("id")}
    return [r for r in rows if _open(r) and not _holding(r, by_id)]


def held(rows) -> list[tuple]:
    """Open rows with an unresolved dependency, each paired with the ids
    holding it back."""
    by_id = {r["id"]: r for r in rows if r.get("id")}
    out = []
    for r in rows:
        if not _open(r):
            continue
        holders = _holding(r, by_id)
        if holders:
            out.append((r, holders))
    return out


def clusters(rows) -> dict:
    """Rows grouped by `cluster` tag, and which groups are ready to take to
    the principal in one sitting. The empty tag is not a cluster and groups
    nothing. A group is ready when it has at least one open row and every
    open row in it is askable -- scoped to open rows so that answering a
    cluster's first row does not retire the sitting, since boards are
    worked across sessions."""
    groups = {}
    for r in rows:
        tag = r.get("cluster", "")
        if tag:
            groups.setdefault(tag, []).append(r)
    askable_ids = {r["id"] for r in askable(rows) if r.get("id")}
    ready = {}
    for tag, members in groups.items():
        open_rows = [r for r in members if _open(r)]
        ready[tag] = bool(open_rows) and all(r.get("id") in askable_ids for r in open_rows)
    return {"groups": groups, "ready": ready}


def summary(board_path) -> dict:
    """Counts by status and by type, for the board segment's status render.
    Cheap; no judgment."""
    found = rows(board_path)
    by_status, by_type = {}, {}
    for row in found:
        s = str(row.get("status", "open"))
        by_status[s] = by_status.get(s, 0) + 1
        t = row.get("type", "")
        by_type[t] = by_type.get(t, 0) + 1
    return {"total": len(found), "by_status": by_status, "by_type": by_type}
