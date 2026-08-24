"""Write TOML. stdlib reads it (tomllib) but cannot write it; this is that half.

Narrow on purpose: the value shapes the journal and forms actually use --
strings, numbers, bools, lists of scalars, and tables one level deep. A shape
outside that is a bug in the caller, not a gap here.
"""


def _basic(s: str) -> str:
    """One-line basic string."""
    out = s.replace("\\", "\\\\").replace('"', '\\"')
    return '"' + out.replace("\n", "\\n").replace("\t", "\\t") + '"'


def _multiline(s: str) -> str:
    """Multi-line basic string, for prose. Escapes only what would end it."""
    out = s.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
    if out.endswith('"'):
        out = out[:-1] + '\\"'
    return '"""\n' + out + '"""'


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
