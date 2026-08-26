"""Checks over the built map that CAN FAIL.

`check` exits non-zero when any invariant below is violated. Before gate g1
every function here printed a measurement, asserted nothing, and `run()` ended
in a literal `return 0`, so a completely broken map passed. The measurements are
gone: they were diagnostics wearing a suite's clothes.

What belongs here
-----------------
A **move-invariant** relates two independently-derived facts and holds at any
corpus size: `pages - 1 - modules == entity_pages`, a page's caller list against
a second scan of the store, a page that exists and holds nothing. It survives
every later gate that changes the map's shape, because it never mentions the
shape's numbers.

A **baseline** pins a remembered constant -- "103 modules", "3411 entities", a
page's rendered text, the header format, the section order. It goes red at every
gate that legitimately moves the map, so it would be deleted rather than
believed. Baselines belong to `gB`, after the last gate that moves the numbers.

The distinction is not "does it mention a count". It is: does the expected value
come from a memory of this corpus, or from the map itself?

What these checks read
----------------------
The store DIRECTLY, never through `render.load_stores`, and -- since `g3` --
the SOURCE. A check whose expected value is computed by the code under test can
only ever agree with it, which is not a check. So the store scan below is
written a second time on purpose, the source scan beside it derives definition
names without borrowing a line of the extractor, and both are compared against
the RENDERED PAGES -- the artifact a reader actually gets -- rather than against
the renderer's own in-memory state.

What they do NOT prove is recorded honestly beside each check.

`check` EXITS 1 ON THIS REPO TODAY, and that is correct
------------------------------------------------------
`page_accounting` is red by exactly one page: two entities named `Verdict` and
`verdict` resolve to one filename on a case-insensitive filesystem, so the map
advertises a page it does not have. Gate `g2` owns the rename; `g1` only asserts
it. Do not silence the check to make the command green.
"""
import ast
import collections
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

from .extract import STATEMENTS_NAME, WINDOW

#: How many offending items a failing check names before it summarizes. A check
#: reports every failure it found in its count; it prints the first few.
MAX_REPORTED = 10

#: The directory that holds the `tools` package, so a rebuild can be launched
#: as `python -m tools.code_map` in a FRESH process. Taken from this module's
#: own location, so a mutated copy of the package rebuilds through the mutated
#: copy -- which is what lets a mutation test drive this check at all.
PACKAGE_HOST = pathlib.Path(__file__).resolve().parents[2]


class MapUnderCheck:
    """The built map, loaded the way a reader gets it: pages off disk, and the
    stores read straight from their files.

    Deliberately not a wrapper over `render.py`. The renderer's indexes are the
    thing under test; rebuilding them here from the same source is what makes a
    disagreement meaningful."""

    def __init__(self, root, artifacts, out, packages=()):
        self.root = pathlib.Path(root)
        self.artifacts = pathlib.Path(artifacts)
        self.out = pathlib.Path(out)
        #: The dotted package prefixes the render was NARROWED to, empty for a
        #: whole-corpus render. The CALLER's argument, restated to `check` --
        #: never read back out of the render report. A check that asked the
        #: renderer which pages it decided to write could only ever agree with
        #: it, and every check below joins the store to the tree.
        self.packages = tuple(packages)
        self._pages = None
        self._scan = None
        self._source = None
        self._modules = None
        self._entities = None
        self._text = {}

    # -- the stores ------------------------------------------------------

    def in_scope(self, mod):
        """True when a module was asked for by this render.

        Written out here rather than imported from `render.in_render_scope`,
        for the same reason `is_test_module` and `module_of` below are: half
        of a comparison that borrows the other half's code is not a
        comparison. Empty `packages` narrows nothing."""
        return (not self.packages
                or any(mod == p or mod.startswith(p + ".") for p in self.packages))

    @property
    def entities(self):
        """Every entity the tree is required to hold a page for -- the store's,
        less the modules this render was not asked to write."""
        if self._entities is None:
            self._entities = {k: v for k, v in self.scan.entities.items()
                              if self.in_scope(k.split(":", 1)[0])}
        return self._entities

    @property
    def modules(self):
        """Every module the tree is required to hold an index for.

        `source` reads this, so the SOURCE scan narrows with it and
        `entity_symbol_join`'s coverage arm asks for a page only where a page
        was asked for. What does NOT narrow is `scan.inbound`: a page's caller
        counts are still checked against the whole store, because the walk
        behind the render is still whole."""
        if self._modules is None:
            self._modules = {m: v for m, v in self.scan.modules.items()
                             if self.in_scope(m)}
        return self._modules

    def statements(self):
        with open(self.artifacts / STATEMENTS_NAME, encoding="utf-8") as f:
            for line in f:
                yield json.loads(line)

    @property
    def scan(self):
        """The store read a SECOND time -- see `StoreScan`."""
        if self._scan is None:
            self._scan = StoreScan(self.statements())
        return self._scan

    @property
    def source(self):
        """The corpus read from SOURCE -- see `SourceScan`."""
        if self._source is None:
            self._source = SourceScan(
                self.root, {m["file"] for m in self.modules.values()})
        return self._source

    def position_of(self, key):
        """Where the store says a definition is: (file, 1-based source line).

        Not a symbol lookup. The position is what the source scan is asked
        about, and the symbol is what the two derivations are compared on."""
        entity = self.entities.get(key)
        module = self.modules.get(key.split(":", 1)[0])
        if entity is None or module is None:
            return None
        return (module["file"],
                entity["line"] + (1 - self.scan.line_base[module["file"]]))

    # -- the page tree ---------------------------------------------------

    @property
    def pages(self):
        """Every page in the tree, sorted. The same `rglob` the render report
        counts with -- that is the point: the report's number is checked against
        what the tree is STRUCTURALLY required to hold, not against itself."""
        if self._pages is None:
            self._pages = sorted(self.out.rglob("*.md"))
        return self._pages

    def text(self, page):
        if page not in self._text:
            self._text[page] = page.read_text(encoding="utf-8")
        return self._text[page]

    def title_key(self, page):
        """What a page SAYS it is about: its title line.

        Pages are classified by this rather than by filename, so a page that
        landed on another page's path is still read as the entity it
        describes."""
        lines = self.text(page).splitlines()
        if lines and lines[0].startswith("# "):
            return lines[0][2:].strip()
        return None

    @property
    def entity_pages(self):
        """(page, supplement key) for every page whose title names an entity."""
        out = []
        for page in self.pages:
            key = self.title_key(page)
            if key in self.entities:
                out.append((page, key))
        return out

    def rel(self, path):
        return path.relative_to(self.out).as_posix()


class StoreScan:
    """A second reading of the statement store, written from the schema rather
    than borrowed from `render.load_stores`.

    Two facts are collected:

    - `defined_at`  (file, 1-based SOURCE line) -> store symbol, from `contains`.
      The store declares the base its lines are written in, one
      `extraction-window` statement per file, and this converts through that
      declaration rather than compensating with an unexplained `+1` (defect D1,
      closed at g3).
    - `inbound`     target symbol -> {caller module: sites}, from every `calls`
      and `reads` statement that did not resolve locally.

    **What a disagreement here does and does not prove.** This scan and the
    renderer read the SAME store and share its two schema conventions. So this
    catches the renderer losing, miscounting or misattributing what the store
    says -- and it does NOT audit the store against the source. An extractor
    that never recorded a call, or recorded it at the wrong line, agrees with
    itself and passes. That is a real limit, stated rather than narrowed away."""

    def __init__(self, statements):
        self.defined_at = {}
        self.entities = {}
        self.modules = {}
        self.inbound = collections.defaultdict(collections.Counter)
        self.line_base = {}
        for st in statements:
            predicate = st["p"]
            q = st["q"]
            if predicate == WINDOW:
                self.line_base[q["file"]] = st["d"]["line_base"]
                self.modules[st["s"].split(":", 1)[0]] = {
                    "file": q["file"], "loc": st["d"]["loc"]}
            elif predicate == "contains":
                self.entities[st["o"]] = {"line": q["line"], "end": st["d"]["end"]}
                self.defined_at[(q["file"],
                                 q["line"] + (1 - self.line_base[q["file"]]))] = st["o"]
            elif predicate in ("calls", "reads") and st.get("res") != "local":
                caller_module = st["s"].split(":", 1)[0]
                self.inbound[st["o"]][caller_module] += 1


class SourceScan:
    """Every definition in the corpus and its QUALIFIED NAME, derived from the
    source text and sharing no code path with the extractor.

    This exists because gate `g3` deleted the map's second AST pass. That pass
    was one of two independent derivations `entity_symbol_join` compared; left
    on one derivation the check would have compared a symbol against itself and
    become incapable of failing -- the exact defect this gate exists to stamp
    out, arriving through a legitimate refactor.

    So the second derivation moved HERE, where a second derivation belongs: a
    check is the right home for one, a pipeline stage was not. Nothing is
    imported from `extract`; the module name comes from the file path, the
    qualified name from this recursion, and the two are compared only on the
    position.

    It is deliberately NOT the recursion the deleted stage had. That one
    descended `node.body`, so a definition inside a `with`, `if`, `try` or `for`
    block was invisible to it (`tc34`). This descends EVERY child node and
    extends the qualified prefix only at a definition, which is what Python
    actually does.

    Every child, not every statement child: `scripts/checklist_engine.py`
    defines a fallback function inside an `except ImportError:` handler, and an
    `ExceptHandler` is not an `ast.stmt`. A statement-only descent skipped it,
    and this check went red on the real corpus and said so -- which is the
    behavior a second derivation is for."""

    def __init__(self, root, files):
        self.root = pathlib.Path(root)
        self.qualified_at = {}      # (file, 1-based line) -> "module:Qualified.name"
        self.unreadable = []
        for rel in sorted(files):
            try:
                src = (self.root / rel).read_text(encoding="utf-8")
                src = src.lstrip('﻿')  # Strip UTF-8 BOM if present
                tree = ast.parse(src)
            except Exception as error:
                self.unreadable.append((rel, str(error)))
                continue
            self._walk(tree, rel, self.module_of(rel), "")

    @staticmethod
    def module_of(rel):
        """`pkg/thing.py` -> `pkg.thing`, `pkg/__init__.py` -> `pkg`.

        Written out rather than imported: half of a comparison that borrows the
        other half's code is not a comparison."""
        parts = rel.split("/")
        if parts[-1] == "__init__.py":
            parts = parts[:-1]
        else:
            parts[-1] = parts[-1][:-len(".py")]
        return ".".join(parts)

    def _walk(self, node, rel, module, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                qualified = f"{prefix}.{child.name}" if prefix else child.name
                self.qualified_at[(rel, child.lineno)] = f"{module}:{qualified}"
                self._walk(child, rel, module, qualified)
            else:
                # not a definition, so not a scope: descend, do not qualify
                self._walk(child, rel, module, prefix)


# ------------------------------------------------------- the rendered line
# The ONE place that knows how a page spells its inbound references. Every
# check below works in terms of what the line MEANS -- sites, distinct caller
# modules, and which of them are named -- so a later gate that respells it
# updates this and nothing else.

#: Two prefixes, not one -- `referenced by: none found` used to answer three
#: different questions with one sentence (nothing calls this / only tests call
#: this / this itself IS a test). Declared here, not imported from the
#: renderer, for the same reason as always: a check that reads its expected
#: text out of the code under test can only ever agree with it. The renderer
#: spells these sentences too, and the two must match byte for byte.
REFS_PROD_PREFIX = "referenced by (production): "
REFS_TEST_PREFIX = "referenced by (tests): "
REFS_PREFIXES = (REFS_PROD_PREFIX, REFS_TEST_PREFIX)
REFS_NONE = "none found"
REFS_SELF_ONLY = re.compile(r"^(\d+) sites, this module only$")
REFS_MODULES = re.compile(
    r"^(\d+) sites in (\d+) modules \(([^)]*)\)(?: \+ (\d+) in this module)?$")

REFS_LEGEND = ("counted: calls and reads that resolved to this symbol. "
               "not counted: its own definition, imports, inheritance, "
               "attribute writes, docstring mentions, unresolved references.")

#: What the production/test split is based on -- the renderer's own copy of
#: this sentence is what a reader actually sees; this one is what holds the
#: renderer to having printed it, byte for byte.
SPLIT_LEGEND = ("split: production vs test caller module, by pytest's "
                "default discovery convention -- test_*.py / *_test.py "
                "naming, or a tests package anywhere on the module path. "
                "a module matching neither is counted production.")

#: Shown on a test-defined entity's own page. Byte-for-byte copy of the
#: renderer's `TEST_NOTE`.
TEST_NOTE = ("this entity is defined in a test module (see split legend "
             "below): zero callers here is the normal, expected state, not "
             "a finding.")

#: sites: total inbound edges, the page's own module included. modules: how many
#: distinct modules they came from. named: the modules the line spells out --
#: the renderer omits the page's own module from that list. own: how many of
#: `sites` the line attributes to the page's own module, which is what lets a
#: reader account for the unnamed one instead of guessing.
Refs = collections.namedtuple("Refs", "sites modules named own")


def refs_prefix_of(line):
    """Which of the two inbound-line prefixes `line` uses, or None."""
    for prefix in REFS_PREFIXES:
        if line.startswith(prefix):
            return prefix
    return None


def parse_refs(line):
    """The rendered inbound line as numbers, or None when it is not one of the
    forms this map writes. Works for either bucket prefix -- the BODY grammar
    (the part after the prefix) is the same for both."""
    prefix = refs_prefix_of(line)
    if prefix is None:
        return None
    body = line[len(prefix):].strip()
    if body == REFS_NONE:
        return Refs(0, 0, (), 0)
    match = REFS_SELF_ONLY.match(body)
    if match:
        # every site is in the page's own module, and the line says so
        return Refs(int(match.group(1)), 1, (), int(match.group(1)))
    match = REFS_MODULES.match(body)
    if match:
        named = tuple(n.strip() for n in match.group(3).split(",") if n.strip())
        return Refs(int(match.group(1)), int(match.group(2)), named,
                    int(match.group(4) or 0))
    return None


def refs_lines(text):
    return [ln for ln in text.splitlines() if refs_prefix_of(ln) is not None]


def is_test_module(mod):
    """Second, independently hand-written reading of the SAME pytest-derived
    rule `render.is_test_module` applies -- see that function's docstring for
    the convention (`test_*.py` / `*_test.py` naming, or a `tests` package)
    and why it is derived rather than tuned. Written a second time rather than
    imported, same reason as `REFS_PROD_PREFIX`: importing a classification
    from the code under test can only ever agree with it. This is what lets
    `inbound_attribution` catch a renderer that classifies a caller module
    differently than this second reading does."""
    parts = mod.split(".")
    last = parts[-1]
    if last.startswith("test_") or last.endswith("_test"):
        return True
    return "tests" in parts


# ------------------------------------------------------------------ checks
# Each check takes a MapUnderCheck and returns a list of human-readable
# failures. An empty list is a pass. No check raises to signal a failure --
# a raise is a broken check, and `run` lets it through rather than swallowing
# it into a pass.


def no_empty_pages(m):
    """A page that exists and holds nothing is a page the map counts and a
    reader cannot use.

    `tc26`: the render report's `pages` is `rglob("*.md")`, which counts a file
    that was created and never written, so a zero-byte page is invisible in
    every number the report publishes. This is the check that sees it."""
    return [f"{m.rel(p)}: page has no content"
            for p in m.pages
            if not p.read_text(encoding="utf-8").strip()]


#: The one page in the tree that is neither a module index nor an entity: the
#: top index. A structural fact about the layout -- there is exactly one root --
#: not a remembered fact about this corpus. It stays 1 at any corpus size, which
#: is what keeps `page_accounting` an invariant rather than a baseline.
TOP_INDEX_PAGES = 1


def page_accounting(m):
    """Every page the map CLAIMS must be a page the map HAS.

    The tree is required to hold exactly one page per module index, one per
    entity, and one top index. Both sides are derived independently: the left is
    the files on disk, the right is the store. When they disagree the map is
    advertising something a reader cannot open.

    This is the check that sees a page silently overwriting another. Two entity
    names that differ only by case resolve to one filename on Windows and macOS,
    so the second write destroys the first and every count the render report
    publishes still looks right -- `pages` is an `rglob` of the tree, so it
    agrees with the tree by construction and cannot notice (that is `tc18`, and
    `tc24` rules that counting the tree a second time is NOT the fix).

    RED ON THIS REPO TODAY, by exactly one page: `scripts.run_skill_eval:Verdict`
    and `:verdict` land on one file. Gate `g2` owns the rename; `g1` only
    asserts it. See the `xfail(strict=True)` in tests/test_code_map.py.

    TWO ARMS, and the second is the durable one.

    - COVERAGE: every module and every entity the store declares must be the
      TITLE of some page. Shape-free -- it never says where a page lives or what
      it is called, so no later gate moves it -- and it is what names the loss.
    - COUNT: `pages == 1 + modules + entities`. This is the identity the render
      report contradicts, so it is the one that is red today, and it catches a
      loss that coverage cannot: a page duplicated, or a page in the tree the
      store never asked for.

    Coverage is asserted on its own rather than only as a diagnostic when the
    count is off. Attacking the count arm alone found the hole: delete one page
    and add one stray page and the arithmetic balances while a page the map
    advertises is gone.

    The count arm is the one a later gate can legitimately move: it assumes the
    tree holds exactly one index per module plus one top index. A gate that adds
    an index tier has to update the accounting -- deliberately, not silently,
    because the constant is named here and nowhere else.

    Both arms read the TITLE of every page that exists, never the renderer's
    filename expression -- a check that derives its expectation with the code
    under test's own expression can only ever agree with it."""
    titles = {m.title_key(p) for p in m.pages}
    failures = [f"{k}: an entity the map claims and does not have"
                for k in sorted(set(m.entities) - titles)]
    failures += [f"{k}: a module index the map claims and does not have"
                 for k in sorted(set(m.modules) - titles)]
    expected = TOP_INDEX_PAGES + len(m.modules) + len(m.entities)
    actual = len(m.pages)
    if actual != expected:
        failures.append(
            f"the tree holds {actual} pages; the store accounts for {expected} "
            f"({TOP_INDEX_PAGES} top index + {len(m.modules)} module indexes + "
            f"{len(m.entities)} entities)")
    return failures


def refs_line_self_consistent(m):
    """A page's inbound lines must agree with their own lists.

    PAGE-LOCAL: this reads the page and nothing else -- no store, no supplement.
    `inbound_attribution` is strictly stronger wherever the store can be read,
    and on a healthy map the two agree on every entity page. Two things keep
    this one from being dead weight:

    - it covers EVERY page in the tree, while `inbound_attribution` only covers
      pages whose title names a known entity. A page that lost its title, or
      that the store no longer knows about, is invisible to the store check and
      visible here.
    - it survives the store: a later gate that changes the schema breaks the
      second derivation, and this rule still holds.

    Split into PRODUCTION and TEST buckets (gate g5): a page carrying an
    inbound line must carry EXACTLY TWO, one per bucket, each named exactly
    once. The arithmetic within each bucket is the rule the single line always
    satisfied: you cannot name a module twice, you cannot name more modules
    than you counted, the counted modules you do not name must be EXACTLY the
    one the line accounts for with `+ N in this module` -- one when it does,
    none when it does not -- you cannot attribute more sites to your own
    module than you counted, the sites left over must cover the modules you
    named, you cannot draw N sites from more than N modules, and zero sites
    and zero modules must arrive together.

    The two inbound lines must be followed by `REFS_LEGEND` (what the count
    counted) then `SPLIT_LEGEND` (what the split was based on) -- a number a
    reader cannot interpret is the defect `g2` closed, and a split whose basis
    is not stated is the defect `g5` exists to close the same way.

    An entity's own module classification (page-local: derived from the
    TITLE's dotted name, the same string this function already reads, so no
    store lookup is needed) governs `TEST_NOTE`: it must be present when the
    page's own module is a test module, and absent otherwise -- a test-defined
    entity's near-universal none/none must not read as a bare, alarming line,
    and a production entity must not be told it is a test.

    What it does NOT prove: that the numbers are RIGHT. A line can be perfectly
    self-consistent and completely wrong -- that is `inbound_attribution`'s
    job."""
    failures = []
    for page in m.pages:
        where = m.rel(page)
        title = m.title_key(page) or ""
        own = title.split(":", 1)[0] if ":" in title else title
        lines = m.text(page).splitlines()
        refs_idx = [i for i, ln in enumerate(lines) if refs_prefix_of(ln) is not None]
        if not refs_idx:
            continue

        prefixes_seen = [refs_prefix_of(lines[i]) for i in refs_idx]
        if len(refs_idx) != 2 or set(prefixes_seen) != set(REFS_PREFIXES):
            failures.append(f"{where}: inbound lines are {prefixes_seen!r}, expected "
                            f"exactly one production and one tests line")

        last = refs_idx[-1]
        if lines[last + 1:last + 3] != [REFS_LEGEND, SPLIT_LEGEND]:
            failures.append(f"{where}: the inbound lines are not followed by the "
                            f"legend saying what the count counted and what the "
                            f"split was based on")

        has_note = TEST_NOTE in lines
        if own and is_test_module(own):
            if not has_note:
                failures.append(f"{where}: titled {title!r} in a test module but "
                                f"carries no test-defined note")
        elif has_note:
            failures.append(f"{where}: carries the test-defined note but {own!r} "
                            f"is not a test module")

        for i in refs_idx:
            line = lines[i]
            stated = parse_refs(line)
            if stated is None:
                failures.append(f"{where}: cannot read the inbound line: {line!r}")
                continue
            named = list(stated.named)
            if len(set(named)) != len(named):
                failures.append(f"{where}: names a module more than once: {named}")
            gap = stated.modules - len(named)
            if gap < 0:
                failures.append(f"{where}: names {len(named)} modules but counts only "
                                f"{stated.modules}")
            elif stated.own and gap != 1:
                failures.append(f"{where}: attributes {stated.own} sites to its own "
                                f"module, so exactly one counted module -- its own -- "
                                f"must go unnamed, but {gap} of {stated.modules} are")
            elif not stated.own and gap != 0:
                failures.append(f"{where}: counts {stated.modules} modules and names "
                                f"{len(named)}; a line that attributes no sites to its "
                                f"own module must name every module it counts")
            if stated.own > stated.sites:
                failures.append(f"{where}: attributes {stated.own} sites to its own "
                                f"module out of {stated.sites} counted")
            elif stated.sites - stated.own < len(named):
                failures.append(f"{where}: {stated.sites - stated.own} sites are left "
                                f"for the {len(named)} modules it names")
            if stated.sites < stated.modules:
                failures.append(f"{where}: {stated.sites} sites cannot come from "
                                f"{stated.modules} modules")
            if (stated.sites == 0) != (stated.modules == 0):
                failures.append(f"{where}: {stated.sites} sites and {stated.modules} "
                                f"modules disagree about whether anything references it")
            if own and own in named:
                failures.append(f"{where}: names its own module {own!r} in the caller "
                                f"list, which the count already accounts for")
    return failures


def entity_symbol_join(m):
    """A page's title must be what the SOURCE says is defined at its position.

    RE-BASED AT `g3`, and the reason is worth stating. This check used to
    compare two independent AST passes -- the extractor's symbol against a
    second pass's qualified key -- welded on (file, line). `g3` deleted that
    second pass. Left standing on one derivation the check would have compared
    the store symbol against a page title RENDERED FROM THAT SAME SYMBOL: a
    tautology that cannot fail, which is the exact defect this run exists to
    stamp out and would have arrived through a legitimate refactor.

    So the second derivation is `SourceScan`, here in the checks, deriving every
    definition's qualified name from the source text with no code path in common
    with `extract.py`. The comparison is now a stronger one than the old pair
    made: it is the map against the SOURCE, not one pass against another.

    Two arms, and they fail in opposite directions.

    - NAMING: for every entity page, the definition the source finds at the
      store's recorded position must have the page's own title as its qualified
      name. This catches a symbol that drops its enclosing chain, a symbol
      recorded at the wrong line, and a page titled after something that is not
      there at all.
    - COVERAGE: every definition the source scan finds must have a page. This is
      the arm that catches LOSS -- `tc34`, where the deleted second pass never
      descended into a `with` block, so definitions inside one had no page and
      nothing in the map said they were missing.

    What it does NOT prove: that the page's CONTENT is right. A page can be
    titled correctly and carry another entity's callers; that is
    `inbound_attribution`'s job."""
    failures = []
    titled = set()
    for page, key in m.entity_pages:
        where = m.rel(page)
        titled.add(key)
        position = m.position_of(key)
        if position is None:
            failures.append(f"{where}: {key} has no recorded position, so the page "
                            f"carries nothing the store knows about it")
            continue
        found = m.source.qualified_at.get(position)
        if found is None:
            failures.append(f"{where}: the store puts {key} at {position[0]} line "
                            f"{position[1]}, where the source defines nothing")
        elif found != key:
            failures.append(f"{where}: page is titled {key} but the source defines "
                            f"{found} at that position")
    for position, qualified in sorted(m.source.qualified_at.items()):
        if qualified not in titled:
            failures.append(f"{qualified}: defined at {position[0]} line "
                            f"{position[1]} and the map has no page for it")
    return failures


def page_location_matches_content(m):
    """A page's title must agree with the directory it was written into.

    `tc31`: nothing above ties a page's LOCATION to its CONTENT. Every check
    in this module reads a page by its TITLE -- `page_accounting` proves every
    title the store expects exists SOMEWHERE in the tree; `entity_symbol_join`
    and `inbound_attribution` both start from `m.entity_pages`, which finds a
    page by title too. None of them ask WHERE a page sits. Swap two pages'
    file contents, or move one into a sibling module's directory, and every
    title the store expects is still present somewhere -- COVERAGE holds,
    COUNT holds, naming and inbound arithmetic both hold, because all four are
    blind to location. `g4` adds a routing tier ON TOP of that same layout, so
    this is where the gap closes rather than doubling.

    The expected location comes out of each page's OWN title, never out of
    `page_file` or any renderer index -- a check that asks the code under test
    where its own output should live can only ever agree with it. A module
    page's title is the module's own dotted name and must sit at
    `<title>/INDEX.md`; an entity page's title is `<module>:<qualified name>`
    and must sit inside `<module>/`, whatever its filename -- the filename
    itself is `page_file`'s own case-fold disambiguation, which this check
    does not re-derive, so it stays independent of that scheme too.

    What it does NOT prove: that a MISNAMED page (right directory, wrong
    filename for its title) is caught -- only that the DIRECTORY is right.
    `no-empty-pages` and `page-accounting` together already constrain the
    filename indirectly (a page at the wrong filename either collides or goes
    missing); a dedicated filename-vs-title check is future work, not this
    gate's."""
    failures = []
    for page in m.pages:
        title = m.title_key(page)
        if title is None:
            continue
        where = m.rel(page)
        if title in m.modules:
            if page.parent.name != title or page.name != "INDEX.md":
                failures.append(f"{where}: titled module {title!r}, expected at "
                                f"{title}/INDEX.md")
        elif title in m.entities:
            expected_dir = title.split(":", 1)[0]
            if page.parent.name != expected_dir:
                failures.append(f"{where}: titled entity {title!r}, expected under "
                                f"{expected_dir}/, found under {page.parent.name}/")
    return failures


def inbound_attribution(m):
    """Every page's caller set must match an independent full scan of the
    store, split into the SAME two buckets the page renders.

    Four facts per bucket, both buckets, all compared against the second scan
    rather than against the renderer: how many inbound sites, how many
    distinct modules they came from, which modules those are (less the page's
    own, which the renderer accounts for with `+ N in this module` rather than
    naming), and how many sites that own-module clause claims. The bucket
    split itself uses `is_test_module` -- the SECOND, independently
    hand-written copy declared above, not the renderer's -- so a caller the
    renderer classifies wrongly is something this check can actually catch.

    This is the check that notices a map that lies about who uses what -- the
    single thing an agent reads the map FOR."""
    failures = []
    for page, key in m.entity_pages:
        where = m.rel(page)
        lines = refs_lines(m.text(page))
        if len(lines) != 2:
            failures.append(f"{where}: {len(lines)} inbound lines, expected exactly 2")
            continue
        by_prefix = {}
        broken = False
        for line in lines:
            stated = parse_refs(line)
            if stated is None:
                failures.append(f"{where}: cannot read the inbound line: {line!r}")
                broken = True
                continue
            by_prefix[refs_prefix_of(line)] = stated
        if broken or set(by_prefix) != set(REFS_PREFIXES):
            if not broken:
                failures.append(f"{where}: inbound lines are {sorted(by_prefix)!r}, "
                                f"expected one production and one tests line")
            continue

        truth = m.scan.inbound.get(key, {})
        own_module = key.split(":", 1)[0]
        truth_by_bucket = {
            REFS_PROD_PREFIX: {mm: n for mm, n in truth.items() if not is_test_module(mm)},
            REFS_TEST_PREFIX: {mm: n for mm, n in truth.items() if is_test_module(mm)},
        }

        for prefix, label in ((REFS_PROD_PREFIX, "production"), (REFS_TEST_PREFIX, "tests")):
            stated = by_prefix[prefix]
            bucket_truth = truth_by_bucket[prefix]
            expected_named = tuple(sorted(set(bucket_truth) - {own_module}))

            if stated.sites != sum(bucket_truth.values()):
                failures.append(f"{where}: page says {stated.sites} {label} inbound "
                                f"sites, the store has {sum(bucket_truth.values())}")
            if stated.modules != len(bucket_truth):
                failures.append(f"{where}: page says {stated.modules} {label} "
                                f"calling modules, the store has {len(bucket_truth)}")
            if tuple(sorted(stated.named)) != expected_named:
                failures.append(f"{where}: page names {list(stated.named)} as "
                                f"{label} callers, the store has {list(expected_named)}")
            if stated.own != bucket_truth.get(own_module, 0):
                failures.append(f"{where}: page attributes {stated.own} {label} "
                                f"sites to its own module, the store has "
                                f"{bucket_truth.get(own_module, 0)}")
    return failures


def _build_into(root, workdir, hash_seed, packages=()):
    """Build `root` into `workdir` in a FRESH PROCESS. Returns the page tree, or
    a failure string.

    A fresh process is the whole point. Set iteration order and dict rehashing
    vary with the interpreter's string hash seed, and a seed is fixed for the
    life of a process -- so two builds inside ONE process share it and a
    hash-ordered listing looks perfectly stable. The two seeds are pinned to
    different values rather than left to per-process randomization so the check
    exercises that difference every run instead of once in a while."""
    out = pathlib.Path(workdir) / "map"
    proc = subprocess.run(
        [sys.executable, "-m", "tools.code_map", "build", "--root", str(root),
         "--artifacts", str(pathlib.Path(workdir) / "artifacts"), "--out", str(out)]
        + ["--render-only=" + p for p in packages],
        cwd=str(PACKAGE_HOST), capture_output=True, text=True,
        env={**os.environ, "PYTHONHASHSEED": hash_seed},
    )
    if proc.returncode != 0:
        return None, (f"rebuild (PYTHONHASHSEED={hash_seed}) exited "
                      f"{proc.returncode}: {proc.stderr.strip()[-400:]}")
    return out, None


def _tree(root):
    """relative posix path -> bytes, for every page in a rendered tree."""
    root = pathlib.Path(root)
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in root.rglob("*") if p.is_file()}


def tree_diff(left, right):
    """Every path on which two rendered trees disagree. Empty list = identical.

    Not a boolean: the failure a reader needs is WHICH page moved."""
    a, b = _tree(left), _tree(right)
    out = []
    for path in sorted(set(a) - set(b)):
        out.append(f"{path}: in the first build only")
    for path in sorted(set(b) - set(a)):
        out.append(f"{path}: in the second build only")
    for path in sorted(set(a) & set(b)):
        if a[path] != b[path]:
            out.append(f"{path}: {len(a[path])} bytes vs {len(b[path])} bytes"
                       if len(a[path]) != len(b[path])
                       else f"{path}: same length, different bytes")
    return out


def deterministic_rebuild(m):
    """Two builds from unchanged source must produce BYTE-IDENTICAL page trees.

    Any non-empty diff is the failure. Nothing in a run report carries a
    timestamp or a duration precisely so this diff can cover the whole tree --
    do not add one.

    This does not touch the tree at `--out`: it builds twice into scratch and
    compares those two against each other, so it is a statement about the
    pipeline rather than about whether the committed tree happens to be
    fresh.

    Both rebuilds carry the render narrowing this check was given. They must:
    ignoring it would build the WHOLE corpus twice and report a determinism
    result about a pipeline nobody ran, while the narrowed tree at `--out` --
    the one every other check is reading -- went unexercised. The scratch path
    is the deliberate part of ignoring `--out`; the scope is not."""
    workdir = tempfile.mkdtemp(prefix="code-map-determinism-")
    try:
        first, err = _build_into(m.root, pathlib.Path(workdir) / "a", "0", m.packages)
        if err:
            return [err]
        second, err = _build_into(m.root, pathlib.Path(workdir) / "b", "1", m.packages)
        if err:
            return [err]
        return tree_diff(first, second)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


CHECKS = (
    ("no-empty-pages", no_empty_pages),
    ("page-accounting", page_accounting),
    ("refs-line-self-consistent", refs_line_self_consistent),
    ("entity-symbol-join", entity_symbol_join),
    ("page-location-matches-content", page_location_matches_content),
    ("inbound-attribution", inbound_attribution),
    ("deterministic-rebuild", deterministic_rebuild),
)


# ------------------------------------------------------------------- stage

def run(root, artifacts, out, packages=()):
    """Run every check over the built map. Returns 0 when all pass, 1 otherwise.

    A check stage that cannot look must not report success -- a missing page
    tree or a missing store is a failure, not a skip.

    `packages` is the render narrowing the tree at `out` was built with, and it
    has to be the same value: these checks join the store to the tree, and a
    store narrowed differently than the tree was rendered disagrees with it on
    every module in between. Getting it wrong is loud, not silent -- the join
    fails by hundreds."""
    m = MapUnderCheck(root, artifacts, out, packages)
    missing = [str(p) for p in (m.out, m.artifacts / STATEMENTS_NAME)
               if not p.exists()]
    if missing:
        print("FAIL cannot check: nothing built at " + ", ".join(missing)
              + " -- run `build` first")
        return 1

    failed = []
    for name, check in CHECKS:
        failures = check(m)
        if failures:
            failed.append(name)
            print(f"FAIL {name}: {len(failures)}")
            for line in failures[:MAX_REPORTED]:
                print("      " + line)
            if len(failures) > MAX_REPORTED:
                print(f"      ... and {len(failures) - MAX_REPORTED} more")
        else:
            print(f"ok   {name}")
    if failed:
        print(f"FAILED {len(failed)} of {len(CHECKS)} checks: " + ", ".join(failed))
        return 1
    print(f"passed {len(CHECKS)} checks")
    return 0
