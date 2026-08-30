"""Write TOML. stdlib reads it (tomllib) but cannot write it; this is that half.

Narrow on purpose: the value shapes the journal and forms actually use --
strings, numbers, bools, lists of scalars, and tables one level deep. A shape
outside that is a bug in the caller, not a gap here.
"""


# [control-escapes]
# Rationale: what this file writes, `tomllib` must read back unchanged --
#   that round trip is the whole contract, since the journal is written here
#   and folded there. TOML forbids a raw control character in a string, so
#   one written straight through makes the file unparseable: the entry is
#   then dropped by `journal.read`'s torn-tail recovery and the work in it is
#   gone. Reached by ordinary prose, not by corruption -- `\b` is a word
#   boundary to an agent writing a regex into a form field and a backspace to
#   the parser, and a Windows path or an escaped quote arrives the same way.
# Rejected: refusing the value at submit instead. That makes round-trip
#   safety the agent's problem, and the agent is writing prose in a language
#   whose escapes it has no reason to be thinking about. A writer that cannot
#   write what it was handed is the defect; naming the caller does not fix it.
_ESCAPES = {"\b": "\\b", "\f": "\\f", "\r": "\\r"}


def _controls(s: str, keep: str) -> str:
    """Every control character TOML will not read back, escaped. `keep` names
    the ones this context may leave literal -- a tab is legal in either
    string form, a newline only inside a multi-line one."""
    out = []
    for ch in s:
        if ch in keep:
            out.append(ch)
        elif ch in _ESCAPES:
            out.append(_ESCAPES[ch])
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append(f"\\u{ord(ch):04X}")
        else:
            out.append(ch)
    return "".join(out)


def _basic(s: str) -> str:
    """One-line basic string."""
    out = s.replace("\\", "\\\\").replace('"', '\\"')
    out = out.replace("\n", "\\n").replace("\t", "\\t")
    return '"' + _controls(out, keep="") + '"'


def _multiline(s: str) -> str:
    """Multi-line basic string, for prose. Escapes what would end it, and the
    control characters that would make it unreadable."""
    out = s.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
    if out.endswith('"'):
        out = out[:-1] + '\\"'
    return '"""\n' + _controls(out, keep="\n\t") + '"""'


def value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(value(x) for x in v) + "]"
    s = str(v)
    return _multiline(s) if "\n" in s else _basic(s)


def table(name: str, data: dict, array=True) -> str:
    """One table -- [[name]] by default, [name] when array is False.

    Scalar keys emit first so a nested sub-table cannot swallow the keys that
    follow it: in TOML every key after a sub-table header belongs to that
    sub-table, which is the one ordering mistake this format punishes.
    """
    head = f"[[{name}]]" if array else f"[{name}]"
    lines = [head]
    nested = []
    for k, v in data.items():
        if v is None:
            continue
        if isinstance(v, dict):
            nested.append(table(f"{name}.{k}", v, array=False))
        elif isinstance(v, list) and v and isinstance(v[0], dict):
            nested.extend(table(f"{name}.{k}", x) for x in v)
        else:
            lines.append(f"{k} = {value(v)}")
    return "\n".join(lines + nested) + "\n"
