"""The machinery cap's instrument: how many lines of code a tree holds. The
same module also holds the corpus budget's instrument, `--words`:

    python3 -m tools.count_lines engine spine
    python3 -m tools.count_lines --words skills standards assemblies docs/AGENT_GUIDE.md

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
import re
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


# A run of letters is a word-token: `tr -sc 'A-Za-z' '\n' | grep -c .`
# squeezed to newlines and counted, which this matches without a subprocess.
WORD = re.compile(r"[A-Za-z]+")

# Only TOML is scanned for `#` comments; other corpus files (`.md`) have no
# comment syntax of their own and are counted whole.
TOML_QUOTES = ('"""', "'''", '"', "'")


def split_toml_comments(source):
    """`(body, comments)`: `source` with every `#` comment pulled into its
    own string, quote state tracked so a `#` inside a TOML string -- basic,
    literal, or triple of either -- is not mistaken for one. Mirrors what
    `tokenize.COMMENT` does for `code_lines` above: a trailing `# note` is a
    comment exactly like a line that is nothing else, because both are the
    same token in TOML as they are in Python.
    """
    body, comments = [], []
    i, n, state = 0, len(source), None
    while i < n:
        if state is None:
            for q in TOML_QUOTES:
                if source.startswith(q, i):
                    state = q
                    body.append(q)
                    i += len(q)
                    break
            else:
                ch = source[i]
                if ch == "#":
                    end = source.find("\n", i)
                    end = n if end == -1 else end
                    comments.append(source[i:end])
                    i = end
                else:
                    body.append(ch)
                    i += 1
            continue
        if source.startswith(state, i):
            body.append(state)
            i += len(state)
            state = None
            continue
        # A basic string (single- or triple-quoted `"`) allows `\` escapes;
        # a literal one (`'`) does not, so a backslash there is just a char.
        if state[0] == '"' and source[i] == "\\" and i + 1 < n:
            body.append(source[i:i + 2])
            i += 2
            continue
        if len(state) == 1 and source[i] == "\n":
            state = None  # an unterminated single-line string; stop guessing
        body.append(source[i])
        i += 1
    return "".join(body), "".join(comments)


def is_toml(path):
    return path.endswith(".toml")


def measure_words(path):
    """`(words, comment_words)` for one file: alphabetic word-tokens outside
    any TOML `#` comment, and the same tokens found inside one. Non-TOML
    files have no comment syntax here, so every token is a word and the
    comment count is zero."""
    source = open(path, encoding="utf-8").read()
    body, comments = split_toml_comments(source) if is_toml(path) else (source, "")
    return len(WORD.findall(body)), len(WORD.findall(comments))


def raw_word_count(files):
    """Plain `wc -w` over `files`, kept alongside the tokenizer's headline so
    the two methods' divergence is a live number rather than a claim frozen
    in prose."""
    out = subprocess.run(["wc", "-w", *files], capture_output=True, text=True,
                         check=True)
    # The last line is the total when more than one file is given, and the
    # only line when one is: either way, the leading field is the count.
    return int(out.stdout.strip().splitlines()[-1].split()[0])


def main_words(paths):
    files = tracked(paths)
    if not files:
        print(f"no tracked files under {' '.join(paths)}")
        return 1
    width = max(len(f) for f in files)
    total_words = total_comments = 0
    for f in files:
        words, comment_words = measure_words(f)
        total_words += words
        total_comments += comment_words
        print(f"  {f:<{width}}  {words:>5}  {comment_words:>5} comments")
    print(f"  {'':<{width}}  {'-' * 5}")
    # Assembly `#` comments are maintainer rationale for why the engine mints
    # as it does; a conductor never reads them, because the engine hands it
    # rendered forms, never raw TOML -- so they are excluded from the
    # headline count the same way `code_lines` excludes them above, and
    # printed beside it rather than folded in, for the same reason prose is
    # beside code: the corpus budget's headroom should not be spendable by
    # moving words into a column nobody reads. Nothing exits non-zero here
    # either -- see the note on `main`.
    print(f"  {'words':<{width}}  {total_words:>5}")
    print(f"  {'comments':<{width}}  {total_comments:>5}  TOML `#` comments")
    print(f"  {'raw':<{width}}  {raw_word_count(files):>5}  what `wc -w` returns")
    return 0


def main(argv):
    if argv[:1] == ["--words"]:
        return main_words(argv[1:] or ["skills", "standards", "assemblies",
                                        "docs/AGENT_GUIDE.md"])
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
    # The cap's number lives in docs/AGENT_GUIDE.md and is not repeated here:
    # this reports, and a report that also judged would be two sources of
    # truth for one budget. Nothing exits non-zero on a count.
    print(f"  {'code':<{width}}  {code:>5}")
    print(f"  {'prose':<{width}}  {prose:>5}  comments and docstrings")
    print(f"  {'blank':<{width}}  {blank:>5}")
    print(f"  {'raw':<{width}}  {code + prose + blank:>5}  what `wc -l` returns")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
