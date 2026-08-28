"""The machinery cap's instrument: how many lines of code a tree holds.

    python3 -m tools.count_lines engine spine

A cap on machinery should count machinery. `wc -l` counts blank lines,
comments and docstrings too, so the number it returns moves when someone
explains a decision better -- pressure pointed the wrong way in a repo whose
comments carry the reasons. This counts a physical line as code when it holds
at least one token that is not a comment and not a bare string expression,
which is cloc's rule for Python.

Prose is reported beside the code rather than dropped, so the cap's headroom
cannot be bought by moving a line from one column to the other unseen.

Paths are read through `git ls-files`, not the filesystem: the count is of
what is committed, and cannot drift with `engine/__pycache__/*.pyc`.
"""

import io
import subprocess
import sys
import tokenize

# INDENT and DEDENT carry no source of their own, and the newline kinds end a
# logical line rather than filling one. What is left, minus comments and the
# bare strings below, is code.
SKIP = (tokenize.INDENT, tokenize.DEDENT, tokenize.NEWLINE, tokenize.NL,
        tokenize.ENDMARKER)


def code_lines(source):
    """The 1-based physical lines of `source` that hold code.

    A STRING opening a logical line is a bare string expression -- a module,
    class or function docstring -- because no operator or name precedes it. A
    string anywhere else is a value, so it counts.

    Depth is tracked because tokenize emits NL inside brackets, so a string on
    its own line within a call would otherwise read as opening a statement:

        print("a"
              "b")        <- both lines are code, neither is a docstring
    """
    code = set()
    opening, depth = True, 0
    for kind, text, (first, _), (last, _), _ in tokenize.generate_tokens(
            io.StringIO(source).readline):
        if kind == tokenize.COMMENT:
            continue
        if kind in SKIP:
            opening = opening or depth == 0
            continue
        if kind == tokenize.STRING and opening:
            continue  # a docstring, or another part of the one before it
        if kind == tokenize.OP:
            depth += (text in "([{") - (text in ")]}")
        code.update(range(first, last + 1))
        opening = False
    return code


def is_python(path, lines):
    """`spine` is Python and says so on its first line rather than in its name,
    which is the whole reason this asks rather than trusting the suffix."""
    return path.endswith(".py") or (bool(lines) and "python" in lines[0])


def measure(path):
    """`(code, prose, blank)` line counts for one file.

    Anything that is not Python is counted by the coarser rule that every
    non-blank line is code. A shell script in the tree is machinery and should
    read as machinery rather than vanish from the cap, and guessing at another
    language's comments is a worse answer than declining to."""
    lines = open(path, encoding="utf-8").read().splitlines()
    filled = {i for i, line in enumerate(lines, 1) if line.strip()}
    code = filled
    if is_python(path, lines):
        try:
            code = code_lines("\n".join(lines) + "\n")
        except (tokenize.TokenError, SyntaxError, IndentationError):
            code = filled  # unparseable Python still counts as machinery
    return len(code), len(filled - code), len(lines) - len(filled)


def tracked(paths):
    """The tracked files under `paths`, in git's order."""
    out = subprocess.run(["git", "ls-files", "--", *paths],
                         capture_output=True, text=True, check=True)
    return out.stdout.split()


def main(argv):
    paths = argv or ["engine", "spine"]
    files = tracked(paths)
    if not files:
        print(f"no tracked files under {' '.join(paths)}")
        return 1
    width = max(len(f) for f in files)
    totals = [0, 0, 0]
    for f in files:
        counts = measure(f)
        totals = [t + c for t, c in zip(totals, counts)]
        print(f"  {f:<{width}}  {counts[0]:>5}  {counts[1]:>5} prose")
    code, prose, blank = totals
    print(f"  {'':<{width}}  {'-' * 5}")
    # The cap's number lives in V2_DESIGN.md's Size section and is not repeated
    # here: this reports, and a report that also judged would be two sources of
    # truth for one budget. Nothing exits non-zero on a count.
    print(f"  {'code':<{width}}  {code:>5}")
    print(f"  {'prose':<{width}}  {prose:>5}  comments and docstrings")
    print(f"  {'blank':<{width}}  {blank:>5}")
    print(f"  {'raw':<{width}}  {code + prose + blank:>5}  what `wc -l` returns")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
