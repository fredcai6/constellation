"""Pure-AST statement extractor with its own cross-file name resolution.

Python stdlib only (ast, os, json, hashlib). No SCIP, no type inference beyond
the two cheap rules stated in RESOLUTION RULES below.

Two passes:
  pass 1  index every corpus module's *module-level* binding table
          (defs, classes, assignments, imports and what each import binds)
  pass 2  walk the same files, tracking scopes, and emit one statement per
          fact with the resolved symbol -- or an explicit unresolved marker.

Both passes read the mappable corpus from `discovery.discover_corpus`. The
prototype this was ported from indexed three hardcoded directories of one
external checkout and took its pass-2 file list from a handwritten manifest.

RESOLUTION RULES (the honest cheap version)
  R1 scope chain      a name bound in an enclosing function scope is `local`
  R2 module table     else a module-level def/class/assign -> mod:name
  R3 imports          from m import n [as a] -> a binds (m, n)
                      import m.n [as a]      -> a binds module m.n
                      relative imports resolved from the file's package path
  R3b namespace pkgs  `from p import m` where p carries no `__init__.py`
                      (PEP 420) has no p to index, so p.m is looked up as a
                      module before p is called external
  R4 re-export chase  if m's own table says n is itself an import, follow it
                      (max 5 hops) to the defining module
  R5 attribute base   module alias  -> mod:attr (then R4)
                      class name    -> mod:Class.attr (walk same-module bases)
                      self in C     -> mod:C.attr (walk same-module bases)
                      local var whose ONLY assignment is `v = Known(...)`
                                    -> mod:Known.attr        [inference rule 1]
                      param annotated `p: Known`
                                    -> mod:Known.attr        [inference rule 2]
                      anything else -> UNRESOLVED/dispatch-unknown-base
  R6 star import      from m import * : if m is internal and has the name,
                      resolve; else UNRESOLVED/star-import
  R7 builtins         -> external
  R8 dynamic          getattr/setattr/importlib -> UNRESOLVED/dynamic

Statement line shape:
  {"s","p","o","q":{"file","line","col"},"ref":"ast","hash"}
plus two measurement-only fields:
  "res"  internal|external|local|unresolved|literal
  "why"  failure class, present only when res == unresolved

THE LINE BASE IS DECLARED, NOT IMPLIED (defect D1)
--------------------------------------------------
`q.line` is written in the base named by `LINE_BASE` below, and every file the
extractor reads gets an `extraction-window` statement that says so in the store
itself. Before this the store was 0-based and the schema was silent; the proof
of the silence was the renderer's bare `+1` at the read site, which a reader who
trusted the schema had no way to know he needed. Consumers read the declared
base; they do not add one.

The window statement is also the extractor's own coverage boundary: a file that
failed to parse gets no window, so a reader can tell a fact that is ABSENT FROM
THE CODE from a fact that was never looked at. `q.line` on the window is the
first line of the file in the declared base, so the window itself is not an
exception to the base it declares.
"""
import ast
import builtins
import hashlib
import json
import os
import re
import sys

from .discovery import discover_corpus

# The repository being mapped. `run()` sets it; the module-level resolvers below
# read it to turn absolute paths into module names.
ROOT = None
BUILTINS = set(dir(builtins))

STATEMENTS_NAME = "statements.jsonl"
REPORT_NAME = "extract_report.json"

#: The base every `q.line` in the store is written in. Declared here and in
#: every `extraction-window` statement, so a consumer reads it instead of
#: guessing. Moving it is a deliberate act with a test that says so
#: (`StatementSchemaLineBaseTests`), because every consumer inherits it.
LINE_BASE = 0

#: The predicate carrying one file's extraction window and the conventions the
#: facts in it were written under.
WINDOW = "extraction-window"


def store_line(lineno):
    """A 1-based `ast` line number in the store's declared base."""
    return lineno - 1 + LINE_BASE


def signature_of(node):
    """A function's signature as source: annotations, defaults, `*args`,
    `**kwargs`, the keyword-only marker and the return type.

    The whole value of the field is that a reader answers a cross-module
    signature question without opening the file -- the two clear wins of the
    rendering trial were exactly that."""
    a = node.args
    parts = []
    posonly = getattr(a, "posonlyargs", [])

    def one(arg, default=None):
        s = arg.arg
        if arg.annotation is not None:
            s += ": " + ast.unparse(arg.annotation)
        if default is not None:
            s += ("=" if arg.annotation is None else " = ") + ast.unparse(default)
        return s

    defaults = list(a.defaults)
    positional = posonly + a.args
    pad = [None] * (len(positional) - len(defaults)) + defaults
    for arg, d in zip(posonly, pad[: len(posonly)]):
        parts.append(one(arg, d))
    if posonly:
        parts.append("/")
    for arg, d in zip(a.args, pad[len(posonly):]):
        parts.append(one(arg, d))
    if a.vararg is not None:
        parts.append("*" + one(a.vararg))
    elif a.kwonlyargs:
        parts.append("*")
    for arg, d in zip(a.kwonlyargs, a.kw_defaults):
        parts.append(one(arg, d))
    if a.kwarg is not None:
        parts.append("**" + one(a.kwarg))
    ret = " -> " + ast.unparse(node.returns) if node.returns is not None else ""
    return "(%s)%s" % (", ".join(parts), ret)


#: An authored identity: a comment line holding NOTHING but a bracketed
#: kebab slug, directly above the definition or assignment it names. `ast`
#: discards comments, so this is read from the file's own text.
ANCHOR = re.compile(r"^[ \t]*#[ \t]*\[([a-z0-9]+(?:-[a-z0-9]+)*)\][ \t]*$")

# [markdown-anchor-is-an-html-comment]
# Rationale: epic #138 finding 10 -- a purpose chain must be able to root at
#   one claim in a governing document, not the whole file, and the only
#   governing documents (`docs/PURPOSE.md`, `standards/approach.md`) are
#   markdown. `#` opens a heading there, so `ANCHOR`'s own spelling cannot be
#   reused as-is above a claim without becoming one. An HTML comment is the
#   one construct markdown already renders as nothing at all -- not a code
#   span, not a footnote, nothing a reader ever sees -- so the same payload
#   (a bracketed kebab slug, alone on its line) rides inside `<!-- -->`
#   instead of behind `#`. Same fact, same shape, the wrapper each language
#   already uses to hide a line from its own reader.
# Rejected: a bracket in plain text directly above the claim, e.g. a line
#   reading only `[slug]`. It would render -- CommonMark has no bare-text
#   hiding construct -- so "invisible when the markdown renders" fails on
#   the first line written. `standards/prose.md` rule 2 and the glossary's
#   `anchor` entry bar a second, differently-shaped id syntax; this keeps
#   the one shape (`[slug]`) and changes only the comment wrapper around it,
#   which is exactly the axis `#` and `<!-- -->` already differ on.
MD_ANCHOR = re.compile(r"^[ \t]*<!--[ \t]*\[([a-z0-9]+(?:-[a-z0-9]+)*)\][ \t]*-->[ \t]*$")


def _is_hash_comment(line):
    return line.lstrip().startswith("#")


def _is_html_comment(line):
    return line.lstrip().startswith("<!--")


def anchors_in(src, pattern=ANCHOR, is_comment=_is_hash_comment):
    """1-based line -> the authored slugs minted at it, in authored order.

    Ids are minted ON DEMAND: most definitions never get one, and that is the
    point -- the symbol path is derived and disposable, and the slug is the one
    thing the mind map stores. A slug binds to the next line that is neither
    blank nor a comment, so a reader can stack a bracket above a docstringed
    comment block and still name what he meant.

    A LIST at each line, not one slug: two anchors stacked directly above the
    same definition both name it, on purpose -- a reader mints a second bracket
    to give a second fact about the same target its own stable id, not to
    replace the first. A single-slug-per-line dict (`out[j + 1] = ...`) silently
    overwrote the earlier one, so the map bound only the last bracket and the
    rest never became a page anyone could see -- three of them across the
    tracked corpus at one measured rev, and a `check` run before this fix had
    nothing to say about any of them.

    `pattern`/`is_comment` are the one grammar's two spellings, not two
    grammars: the defaults are Python's (`# [slug]`, `#`-comment lines);
    `md_anchors_in` below calls back in with markdown's own (`<!-- [slug]
    -->`, `<!--`-comment lines). A markdown heading starts with `#` too, so
    the Python `is_comment` would wrongly skip PAST a heading while forward-
    scanning for what a markdown anchor names -- the two predicates cannot
    share a default, only the loop that uses them."""
    lines = src.splitlines()
    out = {}
    for i, line in enumerate(lines):
        match = pattern.match(line)
        if not match:
            continue
        for j in range(i + 1, len(lines)):
            if lines[j].strip() and not is_comment(lines[j]):
                out.setdefault(j + 1, []).append(match.group(1))
                break
    return out


def md_anchors_in(src):
    """`anchors_in`, spelled for markdown: 1-based line -> the authored
    slugs minted at it via `<!-- [slug] -->`, in authored order.

    Same forward-scan, same stacking, same on-demand minting -- only the
    wrapper and what counts as a comment line change. See `MD_ANCHOR`."""
    return anchors_in(src, pattern=MD_ANCHOR, is_comment=_is_html_comment)


#: Gate g7, grammar v0 as ruled by DESIGN_SPEC (the cull test is applied at
#: render time, not here): a bare `Word:` paragraph prefix in an ordinary
#: comment, prior art shape is Go's `Deprecated:` convention. `Rationale:` is
#: the survivor of the cull test's collapse (see cull-verdict.json).
#: `Rejected:` and `See:` were never collapse candidates: SY5's finding and
#: the cull test both scope to "Assumption:/Constraint:/Rationale:" only --
#: a rejected alternative and a reference are different KINDS of fact, not
#: another flavor of rationale.
#:
#: Gate g7 remediation fix 2: `Assumption:`/`Constraint:` ARE recognised
#: here -- the cull verdict is ALIAS, not retirement (see cull-verdict.json).
#: The real f1Brainz PR #733 corpus has 4 of 6 tags authored with
#: `Constraint:`; retiring it silently converted four real, working tags
#: into inert prose with zero signal. `TAG_KIND_ALIAS` normalizes the KIND
#: at the emission site (`tag_check`), so a comment authored with either
#: retired word still extracts and renders, as `Rationale:`.
TAG_START = re.compile(
    r"^[ \t]*#[ \t]*(Assumption|Constraint|Rationale|Rejected|See):[ \t]*(.*)$")
TAG_CONT = re.compile(r"^[ \t]*#[ \t]?(.*)$")

#: The alias mapping fix 2 builds: a RECOGNIZED keyword whose KIND is
#: normalized to its survivor before the statement is ever emitted, so
#: `render.py:tag_lines` stays exactly as branch-free as the cull test
#: proved it -- one lookup here, never a dispatch in the renderer.
TAG_KIND_ALIAS = {"Assumption": "Rationale", "Constraint": "Rationale"}


def tags_in(src):
    """1-based line -> the authored tags minted directly above it.

    Mirrors `anchors_in`'s own forward-scan exactly: a tag paragraph binds to
    the next line that is neither blank nor a comment, skipping over BOTH a
    `[stable-id]` anchor bracket and any further comment lines in between --
    the same permissiveness `anchors_in` already grants, so a tag and a slug
    can share one comment block in either order.

    A comment paragraph is one or more `Word:` lines; a plain comment line
    right after one is a CONTINUATION of that same tag's text, and a second
    `Word:` line in the same block starts a NEW tag -- the real corpus's own
    shape (f1Brainz PR #733: a `Constraint:` paragraph immediately followed
    by a `Rejected:` paragraph, no blank line between)."""
    lines = src.splitlines()
    n = len(lines)
    out = {}
    i = 0
    while i < n:
        m = TAG_START.match(lines[i])
        if not m:
            i += 1
            continue
        tags = []
        kind, text = m.group(1), m.group(2).strip()
        i += 1
        while i < n and not ANCHOR.match(lines[i]):
            m2 = TAG_START.match(lines[i])
            if m2:
                tags.append({"kind": kind, "text": text.strip()})
                kind, text = m2.group(1), m2.group(2).strip()
                i += 1
                continue
            cm = TAG_CONT.match(lines[i])
            if cm and lines[i].strip() not in ("", "#"):
                text = (text + " " + cm.group(1).strip()).strip()
                i += 1
                continue
            break
        tags.append({"kind": kind, "text": text.strip()})
        for j in range(i, n):
            if lines[j].strip() and not lines[j].lstrip().startswith("#"):
                out.setdefault(j + 1, []).extend(tags)
                break
    return out


def span_hash(node):
    """A normalised hash of an entity's own AST subtree (gate g6, stale-tag
    detection): immune to reformatting -- indentation, line wraps, blank
    lines -- and to comments, by construction, because `ast.dump` never
    encodes source text, whitespace, or position (`include_attributes`
    defaults to False). The leading docstring statement, when present, is
    excluded too: prose describing behavior is not the behavior, the same
    reasoning that already excludes comments.

    NAMED BLIND SPOT, stated rather than hidden: this hash is NOT immune to
    renaming a local variable inside the span -- a rename changes the AST
    (`Name.id`) and trips the flag, even though the naive raw-text hash this
    replaces would ALSO have tripped on it. Treated as an accepted cost, not
    a defect: a Constraint/Rationale's prose can name a specific variable, so
    a rename is a real candidate for staleness review, not pure noise -- at
    the cost of occasionally flagging a rename that has no bearing on the
    tag's claim. What genuinely stays invisible: anything confined to the
    docstring body, or to a comment anywhere inside the span."""
    body = getattr(node, "body", None)
    trimmed = body
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        trimmed = body[1:]
    if trimmed is body:
        dumped = ast.dump(node, annotate_fields=False)
    else:
        node.body = trimmed
        try:
            dumped = ast.dump(node, annotate_fields=False)
        finally:
            node.body = body
    return hashlib.sha1(dumped.encode("utf-8")).hexdigest()[:16]


def _first_paragraph(doc):
    """Extract the first paragraph from a docstring (text up to first blank line).

    Invariant: no docstring content is ever silently dropped. If the summary
    (first paragraph) exceeds 160 characters, the overflow is preserved in
    the body, not discarded at the emit sites.

    Returns a tuple (paragraph, remainder) where:
    - paragraph: the joined first paragraph, truncated to 160 chars if needed
    - remainder: text after the blank line (if present) or overflow from summary
                 (if summary > 160 chars), combined if both exist. None if neither.
    Both are None if there is no content."""
    if not doc:
        return None, None
    lines = doc.strip().splitlines()
    if not lines:
        return None, None

    # Find the first blank line (empty string in splitlines output)
    para_lines = []
    body_start = None
    for i, line in enumerate(lines):
        if line.strip() == "":
            body_start = i + 1
            break
        para_lines.append(line)

    # Join paragraph lines with spaces to handle wrapped lines
    paragraph = " ".join(para_lines).strip() if para_lines else None

    # Extract post-blank-line content if present
    post_blank_body = None
    if body_start is not None and body_start < len(lines):
        body_lines = lines[body_start:]
        post_blank_body = "\n".join(body_lines).strip() or None

    # Handle overflow: if summary > 160 chars, split and preserve tail
    body = None
    if paragraph and len(paragraph) > 160:
        # Overflow: summary tail that won't fit in the truncation limit
        summary_overflow = paragraph[160:].lstrip()
        paragraph = paragraph[:160]

        # Combine overflow with any post-blank-line body
        if post_blank_body:
            body = summary_overflow + " " + post_blank_body if summary_overflow else post_blank_body
        else:
            body = summary_overflow or None
    else:
        # No overflow: use post-blank-line body as-is
        body = post_blank_body

    return paragraph, body


def doc_body_of(node):
    """A docstring past its summary paragraph, or None.

    The summary already has its own `documents` statement. The BODY is the
    Args/Returns/Raises/Examples a reader wanted the docstring for, and the
    store used to drop it."""
    doc = ast.get_docstring(node, clean=True)
    if not doc:
        return None
    _, body = _first_paragraph(doc)
    return body


def doc_summary_of(doc_text):
    """Extract the summary (first paragraph) from a docstring text.

    Returns the first paragraph with internal newlines collapsed to single
    spaces, or the whole docstring if there is no blank line. Returns None
    if the docstring is empty."""
    paragraph, _ = _first_paragraph(doc_text)
    return paragraph


# ------------------------------------------------------------------ pass 1


def mod_of(path):
    rel = os.path.relpath(path, ROOT).replace("\\", "/")
    parts = rel.split("/")
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][:-3]
    return ".".join(parts)


def pkg_of(path):
    m = mod_of(path)
    if path.endswith("__init__.py"):
        return m
    return m.rsplit(".", 1)[0] if "." in m else ""


def resolve_rel(pkg, level, name):
    parts = pkg.split(".") if pkg else []
    drop = level - 1
    base = parts[: len(parts) - drop] if drop else parts
    if name:
        base = base + name.split(".")
    return ".".join(base)


class ModuleTable:
    """Module-level bindings for one file."""

    def __init__(self, mod, path):
        self.mod = mod
        self.path = path
        self.defs = {}        # name -> 'func'|'class'|'var'
        self.imports = {}     # local name -> ('from', srcmod, origname) | ('mod', modname)
        self.stars = []       # modules star-imported
        self.bases = {}       # class name -> [base name strings]
        self.classes = {}     # class name -> set(member names)
        self.all = None       # __all__ contents if literal


def build_table(path):
    try:
        src = open(path, encoding="utf-8").read()
        src = src.lstrip('﻿')  # Strip UTF-8 BOM if present
        tree = ast.parse(src)
    except Exception:
        return None, None
    mod, pkg = mod_of(path), pkg_of(path)
    t = ModuleTable(mod, path)
    for n in tree.body:
        _table_stmt(n, t, pkg)
    return t, tree


def _table_stmt(n, t, pkg):
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
        t.defs[n.name] = "func"
    elif isinstance(n, ast.ClassDef):
        t.defs[n.name] = "class"
        t.bases[n.name] = [_dotted(b) for b in n.bases if _dotted(b)]
        members = set()
        for c in n.body:
            if isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef)):
                members.add(c.name)
            elif isinstance(c, ast.Assign):
                for tg in c.targets:
                    if isinstance(tg, ast.Name):
                        members.add(tg.id)
            elif isinstance(c, ast.AnnAssign) and isinstance(c.target, ast.Name):
                members.add(c.target.id)
            elif isinstance(c, ast.ClassDef):
                members.add(c.name)
        t.classes[n.name] = members
    elif isinstance(n, ast.Assign):
        for tg in n.targets:
            if isinstance(tg, ast.Name):
                t.defs[tg.id] = "var"
                if tg.id == "__all__":
                    try:
                        t.all = [e.value for e in n.value.elts
                                 if isinstance(e, ast.Constant)]
                    except Exception:
                        pass
    elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
        t.defs[n.target.id] = "var"
    elif isinstance(n, ast.Import):
        for a in n.names:
            if a.asname:
                t.imports[a.asname] = ("mod", a.name)
            else:
                t.imports[a.name.split(".")[0]] = ("mod", a.name.split(".")[0])
    elif isinstance(n, ast.ImportFrom):
        srcmod = resolve_rel(pkg, n.level, n.module or "") if n.level else (n.module or "")
        for a in n.names:
            if a.name == "*":
                t.stars.append(srcmod)
            else:
                t.imports[a.asname or a.name] = ("from", srcmod, a.name)
    elif isinstance(n, (ast.If, ast.Try, ast.With)):
        for c in ast.iter_child_nodes(n):
            if isinstance(c, ast.stmt):
                _table_stmt(c, t, pkg)


def _dotted(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


TABLES = {}      # module name -> ModuleTable


def pass1(root, files):
    """Index the module-level binding table of every file in the corpus."""
    for rel in files:
        t, _ = build_table(os.path.join(root, rel))
        if t:
            TABLES[t.mod] = t


# ------------------------------------------------------------------ resolver

UNRES = "UNRESOLVED"


def chase(mod, name, hops=0):
    """Follow a (module, name) through re-exports to its defining module.
    Returns (symbol, res, why)."""
    if hops > 5:
        return UNRES, "unresolved", "reexport-depth"
    t = TABLES.get(mod)
    sub = mod + "." + name
    if t is None:
        # `mod` has no binding table of its own. Under PEP 420 that is exactly
        # what a namespace package looks like: no `__init__.py`, so there is no
        # module for pass 1 to index, while its submodules ARE indexed under
        # their own dotted names. So ask whether `mod.name` is an indexed module
        # before calling `mod` third-party. Without this the corpus's own
        # packages were classified `external` wholesale whenever they carried no
        # `__init__.py` -- the submodule lookup further down never ran, because
        # reaching it requires the table this branch just failed to find.
        if sub in TABLES:
            return sub + ":", "internal", None
        # not an indexed module -> external (stdlib / third-party)
        return "%s:%s" % (mod, name), "external", None
    if name in t.defs:
        return "%s:%s" % (mod, name), "internal", None
    if name in t.imports:
        b = t.imports[name]
        if b[0] == "from":
            return chase(b[1], b[2], hops + 1)
        return b[1] + ":", ("internal" if b[1] in TABLES else "external"), None
    # submodule of a package?  `from src.utils import config`
    if sub in TABLES:
        return sub + ":", "internal", None
    for st in t.stars:
        st_t = TABLES.get(st)
        if st_t and (name in st_t.defs or name in st_t.imports):
            return chase(st, name, hops + 1)
    if t.stars:
        return UNRES, "unresolved", "star-import"
    return UNRES, "unresolved", "missing-in-module"


class Scope:
    def __init__(self, kind, parent=None, cls=None):
        self.kind = kind            # 'module'|'func'|'class'|'comp'
        self.parent = parent
        self.cls = cls              # enclosing class name, if any
        self.func_sym = None        # owning transformer symbol, for params
        self.names = {}             # local name -> 'param'|'assign'|'import'|'def'
        self.imports = {}           # local name -> same binding shape as ModuleTable.imports
        self.types = {}             # local name -> inferred class name (same module)
        self.multi = set()          # names assigned more than once (kills inference)
        self.globals = set()

    def bind(self, name, how, typ=None):
        if name in self.names and typ != self.types.get(name):
            self.multi.add(name)
        # a parameter reassigned in its own body is still that parameter
        if not (self.names.get(name) == "param" and how == "assign"):
            self.names[name] = how
        if typ and name not in self.multi:
            self.types[name] = typ

    def lookup(self, name):
        s = self
        while s is not None:
            if s.kind == "class" and s is not self:
                s = s.parent
                continue
            if name in s.names:
                return s
            s = s.parent
        return None


class Extractor(ast.NodeVisitor):
    def __init__(self, path, tree, src):
        self.path = path
        self.rel = os.path.relpath(path, ROOT)
        self.mod = mod_of(path)
        self.table = TABLES[self.mod]
        self.tree = tree
        self.src = src            # the file's own text, for facts `ast` drops
        self.anchors = anchors_in(src)   # 1-based line -> authored slugs
        self.tags = tags_in(src)         # 1-based line -> authored [{"kind","text"}]
        # slug -> (owning symbol, span_hash) -- gate g6, collected as anchors
        # are emitted and read back by run() to diff against the PREVIOUS
        # extraction's own copy of this dict.
        self.anchor_hashes = {}
        # (owning symbol, tag text) -> (kind, span_hash, file, line, col) --
        # gate g7 remediation fix 1: a tag carries no slug, so its identity
        # across two extractions is its own text plus its owner, not an
        # allocator id. Collected the same way `anchor_hashes` is, and read
        # back by run() to diff against the PREVIOUS extraction's copy.
        self.tag_hashes = {}
        self.out = []
        self.scope = Scope("module")
        self.encl = [self.mod + ":"]     # enclosing transformer stack
        # enclosing DEFINITION NODES, pushed in lockstep with `encl` -- gate
        # g7 remediation fix 1 needs this (unlike g6's anchor(), which only
        # ever hashes the node its own slug sits above): a tag above a bare
        # statement binds to the ENCLOSING entity/module (`self.here()`),
        # not to that statement, so its staleness hash must cover the
        # enclosing entity's own span, not the statement's. `self.tree`
        # (the module) is the module-level entry, matching `encl[0]`.
        self.encl_nodes = [self.tree]
        self.clsstack = []
        # enclosing class SYMBOLS, pushed in lockstep with clsstack, so a
        # resolver that spells a class-qualified name spells the same string
        # the definition was emitted under -- including for a class that is
        # itself nested inside another class or inside a function.
        self.clsyms = []
        for k, v in self.table.defs.items():
            self.scope.bind(k, "def")
        for k in self.table.imports:
            self.scope.bind(k, "import")

    # -------------------------------------------------------- emit helpers
    def emit(self, s, p, o, line, col, res, why=None, extra=None, d=None):
        h = hashlib.sha1(("%s|%s|%s|%s|%s|%s" % (s, p, o, self.rel, line, col))
                         .encode("utf-8")).hexdigest()[:16]
        row = {"s": s, "p": p, "o": o,
               "q": {"file": self.rel.replace("\\", "/"), "line": line, "col": col},
               "ref": "ast", "hash": h, "res": res}
        if why:
            row["why"] = why
        if extra:
            row["q"].update(extra)
        if d is not None:
            # `d` is the DESCRIBED FACTS of the statement's object: a definition's
            # kind, signature, span, docstring body and decorators; a value's
            # annotation and value; a window's conventions. They ride the one
            # statement that already names the thing, so a reader gets a
            # definition's facts without a second store to join against.
            row["d"] = d
        self.out.append(row)

    def here(self):
        return self.encl[-1]

    def child_sym(self, name):
        """The symbol of a definition named `name` in the CURRENT scope.

        One rule for every definition: the enclosing scope's own symbol plus
        this name. `self.encl` already carries exactly that -- `"mod:"` at
        module level, the enclosing definition's own symbol otherwise -- so a
        closure in a method is `mod:Class.method.closure` and a class defined
        in a function is `mod:func.Class`. The result equals `supplement.py`'s
        qualified key by construction, which is what lets
        `checks.entity_symbol_join` compare whole symbols rather than leaves.
        """
        base = self.here()
        return base + name if base.endswith(":") else base + "." + name

    # -------------------------------------------------------- name resolution
    def resolve_name(self, node):
        """ast.Name -> (symbol, res, why)"""
        name = node.id
        sc = self.scope.lookup(name)
        if sc is not None and sc.kind in ("func", "comp"):
            # R1a: a parameter is a *named* symbol owned by its function,
            # not an anonymous local -- same model SCIP uses.
            if sc.names.get(name) == "param" and sc.func_sym:
                return "%s.%s" % (sc.func_sym, name), "internal", None
            if name in sc.imports:                      # D4: function-scoped import
                return self.from_binding(sc.imports[name])
            return "local:%s" % name, "local", None
        # R2a: directly inside a class body, the class namespace wins over the
        # module namespace. Inside a *method* it does not -- Python skips the
        # class scope there -- so this is gated on the innermost scope.
        # `build_table` records MODULE-LEVEL classes only, so the member-set
        # lookup is gated on a module-level class: for a nested class it would
        # silently read a same-named module-level class's members.
        if (self.scope.kind == "class" and len(self.clsstack) == 1
                and name in self.table.classes.get(self.clsstack[-1], ())):
            return "%s.%s" % (self.clsyms[-1], name), "internal", None
        if name in self.table.defs:
            return "%s:%s" % (self.mod, name), "internal", None
        if name in self.table.imports:
            b = self.table.imports[name]
            if b[0] == "from":
                return chase(b[1], b[2])
            return b[1] + ":", ("internal" if b[1] in TABLES else "external"), None
        if name in BUILTINS:
            return "builtins:%s" % name, "external", None
        if self.table.stars:
            for st in self.table.stars:
                t = TABLES.get(st)
                if t and (name in t.defs or name in t.imports):
                    return chase(st, name)
            return UNRES, "unresolved", "star-import"
        return UNRES, "unresolved", "unbound-name"

    def from_binding(self, b):
        """Resolve an import binding tuple -> (symbol, res, why)."""
        if b[0] == "from":
            return chase(b[1], b[2])
        return b[1] + ":", ("internal" if b[1] in TABLES else "external"), None

    def class_member(self, cls, attr, mod=None):
        """Look attr up on class cls, walking same-module bases. -> symbol|None"""
        mod = mod or self.mod
        t = TABLES.get(mod)
        if t is None:
            return None
        seen, stack = set(), [cls]
        while stack:
            c = stack.pop(0)
            if c in seen:
                continue
            seen.add(c)
            if c in t.classes and attr in t.classes[c]:
                return "%s:%s.%s" % (mod, c, attr)
            for b in t.bases.get(c, []):
                if "." in b:
                    continue
                if b in t.classes:
                    stack.append(b)
                elif b in t.imports and t.imports[b][0] == "from":
                    _m, _n = t.imports[b][1], t.imports[b][2]
                    r = self.class_member(_n, attr, _m)
                    if r:
                        return r
        return None

    def attr_via_import(self, b, dotted, head, attr, depth):
        """`head` is bound by an import; resolve `head....attr` through it."""
        if b[0] == "mod":
            full = b[1] + dotted[len(head):]
            return chase(full, attr)
        # from-import: base is a class/func/module in another module
        sym, res, why = chase(b[1], b[2])
        if res == "internal" and sym.endswith(":"):
            mid = dotted.split(".")[1:]
            return chase(".".join([sym[:-1]] + mid), attr)
        if depth > 1:
            return UNRES, "unresolved", "chained-attribute"
        if res == "internal":
            m, mem = sym.split(":", 1)
            if "." not in mem:
                r = self.class_member(mem, attr, m)
                if r:
                    return r, "internal", None
            return "%s.%s" % (sym, attr), "internal", None
        if res == "external":
            return "%s.%s" % (sym, attr), "external", None
        return UNRES, "unresolved", why or "dispatch-unknown-base"

    def resolve_attr(self, node):
        """ast.Attribute -> (symbol, res, why)"""
        attr = node.attr
        base = node.value
        # self.x inside a method
        if isinstance(base, ast.Name) and base.id == "self" and self.clsstack:
            r = self.class_member(self.clsstack[-1], attr)
            if r:
                return r, "internal", None
            return "%s.%s" % (self.clsyms[-1], attr), "internal", None
        if isinstance(base, ast.Name) and base.id == "cls" and self.clsstack:
            r = self.class_member(self.clsstack[-1], attr)
            if r:
                return r, "internal", None
            return "%s.%s" % (self.clsyms[-1], attr), "internal", None
        dotted = _dotted(base)
        if dotted:
            head = dotted.split(".")[0]
            # depth > 1 means the base is itself an attribute chain (a.b.c).
            # We know the type of `a` at best; the type of the FIELD `a.b` needs
            # real inference. Guessing would silently attribute `c` to a's class,
            # so for non-module heads we stop and say so.
            depth = len(dotted.split("."))
            sc = self.scope.lookup(head)
            islocal = sc is not None and sc.kind in ("func", "comp")
            # D4: a function-scoped import is a real binding, not an opaque local
            if islocal and head in sc.imports:
                return self.attr_via_import(sc.imports[head], dotted, head, attr, depth)
            # inferred local type (single-assignment or annotation)
            if islocal:
                typ = None
                s = self.scope
                while s is not None:
                    if head in s.types and head not in s.multi:
                        typ = s.types[head]
                        break
                    s = s.parent
                if typ and depth == 1:
                    tm, tc = typ
                    r = self.class_member(tc, attr, tm)
                    if r:
                        return r, "internal", None
                    return "%s:%s.%s" % (tm, tc, attr), "internal", None
                if typ:
                    return UNRES, "unresolved", "chained-attribute"
                return UNRES, "unresolved", "dispatch-unknown-base"
            # module alias or dotted module path
            if head in self.table.imports:
                return self.attr_via_import(self.table.imports[head],
                                            dotted, head, attr, depth)
            # class defined in this module
            if head in self.table.classes:
                if depth > 1:
                    return UNRES, "unresolved", "chained-attribute"
                r = self.class_member(head, attr)
                if r:
                    return r, "internal", None
                return "%s:%s.%s" % (self.mod, head, attr), "internal", None
            if head in self.table.defs:
                return UNRES, "unresolved", "dispatch-unknown-base"
            if head in BUILTINS:
                return "builtins:%s.%s" % (head, attr), "external", None
        return UNRES, "unresolved", "dispatch-unknown-base"

    def resolve_expr(self, node):
        if isinstance(node, ast.Name):
            return self.resolve_name(node)
        if isinstance(node, ast.Attribute):
            return self.resolve_attr(node)
        return UNRES, "unresolved", "non-name-expr"

    def pos_of(self, node):
        """Position of the *identifier* SCIP would mark (0-based line/col)."""
        if isinstance(node, ast.Attribute):
            return store_line(node.end_lineno), node.end_col_offset - len(node.attr)
        return store_line(node.lineno), node.col_offset

    # -------------------------------------------------------- type inference
    def infer_type(self, value):
        """`v = Known(...)` / annotation -> (module, class) or None."""
        if isinstance(value, ast.Call):
            sym, res, _ = self.resolve_expr(value.func)
            if res == "internal" and ":" in sym:
                m, mem = sym.split(":", 1)
                t = TABLES.get(m)
                if t and mem in t.classes:
                    return (m, mem)
        return None

    def infer_annotation(self, ann):
        if ann is None:
            return None
        d = _dotted(ann)
        if not d:
            return None
        head = d.split(".")[-1]
        if head in self.table.classes:
            return (self.mod, head)
        first = d.split(".")[0]
        if first in self.table.imports:
            b = self.table.imports[first]
            if b[0] == "from":
                sym, res, _ = chase(b[1], b[2])
                if res == "internal" and ":" in sym:
                    m, mem = sym.split(":", 1)
                    t = TABLES.get(m)
                    if t and mem in t.classes:
                        return (m, mem)
        return None

    # -------------------------------------------------------- visitors
    def window(self):
        """This file's extraction window: what was read, and under what
        conventions the facts from it were written.

        Emitted before the file's facts and only for a file that PARSED, so a
        reader can tell a fact that is absent from the code from a fact nobody
        looked for. The window is half-open in the declared base."""
        loc = len(self.src.splitlines())
        self.emit(self.mod + ":", WINDOW,
                  "[%d,%d)" % (LINE_BASE, LINE_BASE + loc),
                  LINE_BASE, 0, "literal",
                  d={"line_base": LINE_BASE, "loc": loc,
                     "doc_body": doc_body_of(self.tree), "all": self.table.all})

    def run(self):
        self.window()
        for n in self.tree.body:
            self.visit(n)
        doc = ast.get_docstring(self.tree)
        if doc:
            summary = doc_summary_of(doc)
            if summary:
                self.emit(self.mod + ":", "documents", summary[:160],
                          LINE_BASE, 0, "literal")
        return self.out

    def anchor(self, sym, node):
        """Emit every authored id minted directly above `node`, if there are any.

        A decorated definition is anchored above its FIRST decorator as well as
        above its `def`, because that is where a reader writes the comment.

        `self.anchors.get(line)` is a LIST (see `anchors_in`): two brackets
        stacked immediately above one definition both name it, and both get
        their own `anchored` statement here -- one per slug, all against the
        same span. A `return` after the loop, not inside it, still stops at
        whichever of the two candidate lines (decorator, then `def`) is the
        one that actually carries anchors.

        Gate g6: an anchor is the only authored-identity surface that exists
        pre-g7 (the real comment-tag vocabulary -- Assumption:/Constraint:/
        etc. -- is g7's build and reuses this SAME `[slug]` allocator), so
        this is where a future tag's span gets hashed and persisted. `d.end`
        already names this node's span in the `contains` statement `g3`
        emits (`described()`); `span_hash(node)` hashes that same subtree
        directly rather than re-deriving it from source-text positions."""
        lines = [node.lineno]
        if getattr(node, "decorator_list", None):
            lines.insert(0, node.decorator_list[0].lineno)
        for line in lines:
            slugs = self.anchors.get(line)
            if slugs:
                h = span_hash(node)
                ln, col = store_line(node.lineno), node.col_offset
                for slug in slugs:
                    self.emit(sym, "anchored", slug, ln, col, "literal",
                              d={"span_hash": h})
                    self.anchor_hashes[slug] = (sym, h, self.rel.replace("\\", "/"), ln, col)
                return

    def tag_check(self, sym, node, span_node=None):
        """Emit any tag paragraph minted directly above `node`, attributed
        to `sym` -- see `tags_in`.

        Gate g7's convention-gap resolution: `sym` is the CALLER's choice, not
        derived here. A whole-function tag (directly above a `def`/`class`)
        is called with the entity's OWN symbol; a tag above a statement
        inside a body is called with `self.here()`, the ENCLOSING entity or
        module -- there is no page finer than one per entity, so that is
        where it renders regardless of which statement it sat above. Same
        decorator-aware two-line check as `anchor()`, for the same reason: a
        reader writes the comment above the first decorator, not the `def`.

        Gate g7 remediation fix 1: `span_node` is the node whose span gets
        HASHED for staleness -- the gate's own rule is "flag when the
        ENCLOSING body changed while the tag text did not", not "when this
        exact statement changed". For a whole-function/class tag `span_node`
        defaults to `node` itself (the entity IS its own enclosing body,
        exactly like `anchor()`); the statement-level call sites
        (`visit_Assign`/`visit_AnnAssign`) pass the enclosing entity/module
        node explicitly, since `node` there is only the tagged statement."""
        span_node = node if span_node is None else span_node
        lines = [node.lineno]
        if getattr(node, "decorator_list", None):
            lines.insert(0, node.decorator_list[0].lineno)
        for line in lines:
            found = self.tags.get(line)
            if found:
                ln, col = store_line(node.lineno), node.col_offset
                h = span_hash(span_node)
                for t in found:
                    # Gate g7 remediation fix 2: normalize a retired keyword's
                    # kind to its survivor HERE, the one place a tag becomes a
                    # statement -- not in render.py, which stays branch-free.
                    kind = TAG_KIND_ALIAS.get(t["kind"], t["kind"])
                    self.emit(sym, "tag", kind, ln, col, "literal",
                              d={"text": t["text"], "span_hash": h})
                    self.tag_hashes[(sym, t["text"])] = (
                        kind, h, self.rel.replace("\\", "/"), ln, col)
                return

    def described(self, node, decorators):
        """The facts a `contains` statement carries about the definition it
        names: kind, signature, span, docstring body, decorators, bases.

        `kind` follows the rule the removed supplement stage used -- a
        definition whose enclosing scope is not the module is a `method` -- so
        the rendered word on a page did not change when the second pass went
        away."""
        if isinstance(node, ast.ClassDef):
            kind, signature = "class", None
            bases = [ast.unparse(b) for b in node.bases]
        else:
            kind = "method" if self.here() != self.mod + ":" else "function"
            if isinstance(node, ast.AsyncFunctionDef):
                kind = "async " + kind
            if "property" in decorators:
                kind = "property"
            elif "staticmethod" in decorators:
                kind = "static method"
            elif "classmethod" in decorators:
                kind = "class method"
            signature, bases = signature_of(node), None
        end = getattr(node, "end_lineno", None)
        return {"kind": kind,
                "signature": signature,
                "end": store_line(end) if end is not None else None,
                "doc_body": doc_body_of(node),
                "decorators": decorators,
                "bases": bases}

    def visit_ClassDef(self, node):
        sym = self.child_sym(node.name)
        decorators = [ast.unparse(d) for d in node.decorator_list]
        self.emit(self.here(), "contains", sym, store_line(node.lineno),
                  node.col_offset, "internal", d=self.described(node, decorators))
        self.anchor(sym, node)
        self.tag_check(sym, node)
        doc = ast.get_docstring(node)
        if doc:
            summary = doc_summary_of(doc)
            if summary:
                self.emit(sym, "documents", summary[:160],
                          store_line(node.lineno), node.col_offset, "literal")
        for b in node.bases:
            s2, r2, w2 = self.resolve_expr(b)
            ln, cl = self.pos_of(b)
            self.emit(sym, "inherits", s2, ln, cl, r2, w2)
        for d in node.decorator_list:
            self.visit(d)
        self.clsstack.append(node.name)
        self.clsyms.append(sym)
        prev = self.scope
        self.scope = Scope("class", prev, node.name)
        self.encl.append(sym)
        self.encl_nodes.append(node)
        for c in node.body:
            self.visit(c)
        self.encl_nodes.pop()
        self.encl.pop()
        self.scope = prev
        self.clsyms.pop()
        self.clsstack.pop()

    def _func(self, node):
        sym = self.child_sym(node.name)
        decorators = [ast.unparse(d) for d in node.decorator_list]
        self.emit(self.here(), "contains", sym, store_line(node.lineno),
                  node.col_offset, "internal", d=self.described(node, decorators))
        self.anchor(sym, node)
        self.tag_check(sym, node)
        doc = ast.get_docstring(node)
        if doc:
            summary = doc_summary_of(doc)
            if summary:
                self.emit(sym, "documents", summary[:160],
                          store_line(node.lineno), node.col_offset, "literal")
        for d in node.decorator_list:
            self.visit(d)
        prev = self.scope
        self.scope = Scope("func", prev, self.clsstack[-1] if self.clsstack else None)
        self.scope.func_sym = sym
        args = node.args
        allargs = list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)
        if args.vararg:
            allargs.append(args.vararg)
        if args.kwarg:
            allargs.append(args.kwarg)
        for a in allargs:
            self.emit("%s.%s" % (sym, a.arg), "param-of", sym,
                      store_line(a.lineno), a.col_offset, "internal")
            self.scope.bind(a.arg, "param", self.infer_annotation(a.annotation))
            if a.annotation is not None:
                self.visit(a.annotation)
        for d in list(args.defaults) + [d for d in args.kw_defaults if d]:
            self.visit(d)
        if node.returns is not None:
            self.visit(node.returns)
        self.encl.append(sym)
        self.encl_nodes.append(node)
        # pre-bind local assignment targets so forward references read as local
        self._prebind(node)
        for c in node.body:
            self.visit(c)
        self.encl_nodes.pop()
        self.encl.pop()
        self.scope = prev

    visit_FunctionDef = _func
    visit_AsyncFunctionDef = _func

    def _prebind(self, fnode):
        for n in ast.walk(fnode):
            if n is fnode:
                continue
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                self.scope.bind(n.name, "def")
            elif isinstance(n, ast.Assign):
                typ = self.infer_type(n.value)
                for t in n.targets:
                    for nm in _target_names(t):
                        self.scope.bind(nm, "assign", typ if len(n.targets) == 1 else None)
            elif isinstance(n, ast.AnnAssign):
                for nm in _target_names(n.target):
                    self.scope.bind(nm, "assign", self.infer_annotation(n.annotation))
            elif isinstance(n, (ast.For, ast.AsyncFor)):
                for nm in _target_names(n.target):
                    self.scope.bind(nm, "assign")
            elif isinstance(n, (ast.With, ast.AsyncWith)):
                for it in n.items:
                    if it.optional_vars is not None:
                        for nm in _target_names(it.optional_vars):
                            self.scope.bind(nm, "assign")
            elif isinstance(n, ast.ExceptHandler) and n.name:
                self.scope.bind(n.name, "assign")
            elif isinstance(n, ast.comprehension):
                for nm in _target_names(n.target):
                    self.scope.bind(nm, "assign")
            elif isinstance(n, (ast.Import, ast.ImportFrom)):
                # D4: record WHAT a function-scoped import binds, not just that
                # the name is taken. Binding the name and dropping the target
                # resolved every call through a function-local import to
                # `local:`, so it vanished from both the callee's `referenced by`
                # and the caller's `calls`.
                pkg = pkg_of(self.path)
                if isinstance(n, ast.ImportFrom):
                    srcmod = resolve_rel(pkg, n.level, n.module or "") if n.level \
                        else (n.module or "")
                for a in n.names:
                    if a.name == "*":
                        continue
                    local = a.asname or a.name.split(".")[0]
                    self.scope.bind(local, "import")
                    if isinstance(n, ast.ImportFrom):
                        self.scope.imports[local] = ("from", srcmod, a.name)
                    else:
                        self.scope.imports[local] = (
                            "mod", a.name if a.asname else a.name.split(".")[0])
            elif isinstance(n, ast.Global):
                self.scope.globals.update(n.names)
            elif isinstance(n, ast.NamedExpr):
                for nm in _target_names(n.target):
                    self.scope.bind(nm, "assign")

    def declare(self, target, node, annotation, value, form):
        """A value declared directly in a module or class body: its name, its
        annotation and WHAT IT IS SET TO.

        A declaration is a fact about its owner, not an entity: it gets no page,
        and `contains` -- which is what a page is counted from -- is deliberately
        not used. The store used to carry only a `writes` edge here, which said
        that a name was assigned and never to what, so a constant reached the map
        as a bare word.

        Only module and class bodies, matching what the removed stage collected:
        a function-local assignment is a local, not a declared surface."""
        if not isinstance(target, ast.Name):
            return
        if self.scope.kind not in ("module", "class"):
            return
        self.emit(self.here(), "declares", self.child_sym(target.id),
                  store_line(node.lineno), node.col_offset, "internal",
                  d={"annotation": annotation, "value": value, "form": form})
        self.anchor(self.child_sym(target.id), node)

    def visit_Assign(self, node):
        # Gate g7: the tag check runs regardless of scope -- unlike declare(),
        # which only fires at module/class level, a tag above a FUNCTION-LOCAL
        # assignment is the real corpus's own majority shape (5 of 6 tags in
        # f1Brainz PR #733), and it binds to the enclosing entity, not to a
        # declared name that scope would refuse to record at all. Gate g7
        # remediation fix 1: the STALENESS hash covers the ENCLOSING entity's
        # own span (`self.encl_nodes[-1]`), not just this one Assign
        # statement -- "the tagged statement changed" is not the gate's rule,
        # "the enclosing body changed" is.
        self.tag_check(self.here(), node, span_node=self.encl_nodes[-1])
        typ = self.infer_type(node.value)
        self.visit(node.value)
        for t in node.targets:
            self.declare(t, node, None, ast.unparse(node.value), "assign")
            self._store(t, typ)

    def visit_AnnAssign(self, node):
        self.tag_check(self.here(), node, span_node=self.encl_nodes[-1])
        if node.value is not None:
            self.visit(node.value)
        self.visit(node.annotation)
        self.declare(node.target, node, ast.unparse(node.annotation),
                     ast.unparse(node.value) if node.value is not None else None,
                     "annotation-only" if node.value is None else "annotated-assign")
        self._store(node.target, self.infer_annotation(node.annotation))

    def visit_AugAssign(self, node):
        self.visit(node.value)
        self._store(node.target, None)
        self._ref(node.target, "reads")

    def _store(self, t, typ=None):
        if isinstance(t, (ast.Tuple, ast.List)):
            for e in t.elts:
                self._store(e, None)
            return
        if isinstance(t, ast.Starred):
            return self._store(t.value, None)
        if isinstance(t, ast.Subscript):
            self.visit(t.value)
            self.visit(t.slice)
            s, r, w = self.resolve_expr(t.value)
            ln, cl = self.pos_of(t.value)
            self.emit(self.here(), "writes", s + "[]", ln, cl, r, w)
            return
        if isinstance(t, ast.Name):
            if self.scope.kind == "module" or self.scope.kind == "class":
                pass
            else:
                self.scope.bind(t.id, "assign", typ)
        if isinstance(t, (ast.Name, ast.Attribute)):
            if isinstance(t, ast.Attribute):
                self.visit(t.value)
            self._ref(t, "writes")

    def _ref(self, node, pred):
        s, r, w = self.resolve_expr(node)
        ln, cl = self.pos_of(node)
        self.emit(self.here(), pred, s, ln, cl, r, w)

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Store):
            self._store(node)
            return
        if isinstance(node.ctx, ast.Del):
            self._ref(node, "writes")
            return
        self._ref(node, "reads")

    def visit_Attribute(self, node):
        if isinstance(node.ctx, ast.Store):
            self.visit(node.value)
            self._ref(node, "writes")
            return
        self.visit(node.value)
        self._ref(node, "reads")

    def visit_Call(self, node):
        f = node.func
        if isinstance(f, (ast.Name, ast.Attribute)):
            if isinstance(f, ast.Name) and f.id in ("getattr", "setattr",
                                                    "__import__", "eval", "exec"):
                ln, cl = self.pos_of(f)
                self.emit(self.here(), "calls", UNRES, ln, cl, "unresolved", "dynamic")
            else:
                s, r, w = self.resolve_expr(f)
                ln, cl = self.pos_of(f)
                self.emit(self.here(), "calls", s, ln, cl, r, w)
            if isinstance(f, ast.Attribute):
                self.visit(f.value)
        else:
            self.visit(f)
        for a in node.args:
            self.visit(a)
        for k in node.keywords:
            self.visit(k.value)

    def visit_Import(self, node):
        for a in node.names:
            self.emit(self.mod + ":", "imports", a.name + ":",
                      store_line(node.lineno), node.col_offset,
                      "internal" if a.name in TABLES else "external")

    def visit_ImportFrom(self, node):
        pkg = pkg_of(self.path)
        srcmod = resolve_rel(pkg, node.level, node.module or "") if node.level \
            else (node.module or "")
        for a in node.names:
            if a.name == "*":
                self.emit(self.mod + ":", "imports", srcmod + ":*",
                          store_line(node.lineno), node.col_offset,
                          "unresolved", "star-import")
            else:
                s, r, w = chase(srcmod, a.name)
                self.emit(self.mod + ":", "imports", s,
                          store_line(node.lineno), node.col_offset, r, w)


def _target_names(t):
    if isinstance(t, ast.Name):
        return [t.id]
    if isinstance(t, (ast.Tuple, ast.List)):
        out = []
        for e in t.elts:
            out += _target_names(e)
        return out
    if isinstance(t, ast.Starred):
        return _target_names(t.value)
    return []


# ------------------------------------------------------------------ stage

def run(root, artifacts):
    """Extract the statement store for `root` into `artifacts`. Returns an exit code.

    The prototype read its file list from a handwritten manifest and indexed
    three hardcoded directories; both are now the discovered mappable corpus.
    """
    global ROOT
    ROOT = str(root)
    TABLES.clear()
    sys.setrecursionlimit(20000)

    files = discover_corpus(root)
    pass1(ROOT, files)
    print("pass1: %d modules indexed" % len(TABLES))

    artifacts = os.fspath(artifacts)
    os.makedirs(artifacts, exist_ok=True)
    failed = []
    nrows = 0
    outp = os.path.join(artifacts, STATEMENTS_NAME)

    # Stale-tag detection (gate g6): read what the PREVIOUS extraction into
    # this same `--artifacts` dir said about every anchor's span, before this
    # run overwrites it. Absent on a fresh checkout -- nothing to compare
    # against, so nothing is flagged, which is the correct bootstrap
    # behaviour rather than a false positive on every anchor in a new repo.
    old_hashes = {}
    # Gate g7 remediation fix 1: the SAME read, extended alongside, for tag
    # statements -- a tag has no slug, so its identity across two runs is
    # (owning symbol, tag text), not `st["o"]` (which for a tag is its KIND,
    # e.g. "Rationale", not a unique id).
    old_tag_hashes = {}   # (sym, text) -> span_hash
    if os.path.exists(outp):
        try:
            with open(outp, encoding="utf-8") as f:
                for line in f:
                    st = json.loads(line)
                    if st["p"] == "anchored":
                        sh = (st.get("d") or {}).get("span_hash")
                        if sh is not None:
                            old_hashes[st["o"]] = sh
                    elif st["p"] == "tag":
                        d = st.get("d") or {}
                        text, sh = d.get("text"), d.get("span_hash")
                        if text is not None and sh is not None:
                            old_tag_hashes[(st["s"], text)] = sh
        except (json.JSONDecodeError, UnicodeDecodeError, KeyError) as e:
            # A truncated or malformed leftover store -- e.g. from an
            # interrupted prior run, since the write below has no atomic
            # rename -- must not crash the run that reads it. Treat it as
            # absent, the same path a first-ever run takes: not a silent
            # skip, since a corrupt store silently disabling staleness
            # detection forever is the same disease in a different organ.
            old_hashes = {}
            old_tag_hashes = {}
            print("previous statements store at %s is unreadable (%s: %s) -- "
                  "treating as absent; staleness comparison is skipped for "
                  "this run" % (outp, type(e).__name__, e))

    new_hashes = {}       # slug -> (sym, hash, file, line, col)
    new_tag_hashes = {}   # (sym, text) -> (kind, hash, file, line, col)
    with open(outp, "w", encoding="utf-8", newline="\n") as f:
        for rel in files:
            p = os.path.join(ROOT, rel)
            try:
                src = open(p, encoding="utf-8").read()
                src = src.lstrip('﻿')  # Strip UTF-8 BOM if present
                tree = ast.parse(src)
            except Exception as e:
                failed.append((rel, "parse: " + str(e)))
                continue
            if mod_of(p) not in TABLES:
                failed.append((rel, "no module table"))
                continue
            ex = Extractor(p, tree, src)
            try:
                rows = ex.run()
            except RecursionError:
                failed.append((rel, "recursion"))
                continue
            for r in rows:
                f.write(json.dumps(r) + "\n")
            nrows += len(rows)
            new_hashes.update(ex.anchor_hashes)
            new_tag_hashes.update(ex.tag_hashes)

        # A slug present in BOTH runs is, by construction, the same "tag" --
        # today an anchor carries no text of its own besides the slug it was
        # minted with, so matching by slug already IS the "tag text did not
        # change" half of the gate's rule. Any hash delta on a matched slug
        # is exactly the flag this gate defines. A slug that is new, or that
        # disappeared, is a different event (minted / orphaned) and is not
        # this gate's concern -- see DESIGN_SPEC's Tombstones section.
        stale = sorted(slug for slug, meta in new_hashes.items()
                       if slug in old_hashes and old_hashes[slug] != meta[1])
        for slug in stale:
            sym, h, sfile, sline, scol = new_hashes[slug]
            row = {"s": sym, "p": "stale-anchor", "o": slug,
                   "q": {"file": sfile, "line": sline, "col": scol},
                   "ref": "derived", "hash": h, "res": "literal",
                   "d": {"old_hash": old_hashes[slug], "new_hash": h}}
            f.write(json.dumps(row) + "\n")
            nrows += 1

        # Gate g7 remediation fix 1: the SAME diff, extended alongside for
        # tags -- a (sym, text) key present in BOTH runs means the tag's own
        # text did not change (the gate's own rule's second half); a hash
        # delta on that matched key is the enclosing body changing while the
        # tag stayed put, exactly the flag this gate defines. A tag whose
        # text also changed has a different key and simply does not match --
        # not flagged, because the author already revisited it.
        stale_real_tags = sorted(
            key for key, meta in new_tag_hashes.items()
            if key in old_tag_hashes and old_tag_hashes[key] != meta[1])
        for key in stale_real_tags:
            sym, text = key
            kind, h, sfile, sline, scol = new_tag_hashes[key]
            row = {"s": sym, "p": "stale-tag", "o": ("%s: %s" % (kind, text))[:80],
                   "q": {"file": sfile, "line": sline, "col": scol},
                   "ref": "derived", "hash": h, "res": "literal",
                   "d": {"old_hash": old_tag_hashes[key], "new_hash": h, "kind": kind}}
            f.write(json.dumps(row) + "\n")
            nrows += 1

    print("statements: %d over %d files (%d failures)" % (nrows, len(files), len(failed)))
    for r in failed:
        print("  FAILED:", r)
    with open(os.path.join(artifacts, REPORT_NAME), "w", encoding="utf-8") as f:
        json.dump({"files": len(files), "statements": nrows,
                   "modules_indexed": len(TABLES),
                   "failures": [list(x) for x in failed],
                   "stale_tags": stale}, f, indent=1)
    return 0
