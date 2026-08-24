"""Boards: read and validate the understand board's `[[question]]` rows.

A board is a living TOML file the interrogator skill seeds and the agent
edits in place (skills/interrogator/forms/UNDERSTAND.toml is the template).
This module does not write boards -- only reads rows and checks them at the
consolidate transition, per the design ruling: an open row refuses; a
decision answered without the principal's words refuses; the escape is
`deferred: <reason>`, journaled. Nothing more -- this engine is a secretary,
not an auditor.
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
