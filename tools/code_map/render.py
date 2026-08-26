"""Full-repo derived map -- one page per entity, agent-lean.

The module list and the entity tree are both DERIVED from the statement store
and from nothing else. The top INDEX groups modules by top-level package so it
stays a routing surface as the module count grows.

Importing this module has no side effects: the prototype loaded its stores at
import time, which made the module unimportable without a built store and
impossible to run twice against different roots. `load_stores()` now owns that.

ONE STORE (gate g3). There used to be a second AST pass whose entity keys the
renderer joined to the store's symbols on (file, line), because the statement
vocabulary could not say what a definition WAS. It can now, so the pass and the
join are both gone: a page is keyed by the store symbol itself.

That removal also closed `tc34`. The second pass descended `node.body` only, so
a definition inside a `with`, `if`, `try` or `for` block was not an entity at
all -- no page, no caller list, and no report saying it was missing. The
statement extractor is an `ast.NodeVisitor` and always reached those
definitions, so they get pages now.

D1 is FIXED (gate g3): the store declares its line base in every
`extraction-window` statement, and `source_line` reads that declaration instead
of compensating with an unexplained `+1`.
D2 is FIXED (gate g2): `extract.py` names every definition as its enclosing
scope's symbol plus its own name.

Output layout:
  map/INDEX.md                       top index, grouped by package
  map/<dotted.module>/INDEX.md       module doc, deps, constants, contents
  map/<dotted.module>/<Entity>.md    one page per class/function/method
  map/ids.jsonl                      id -> symbol-path lookup
"""
import collections
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys

from .extract import STATEMENTS_NAME, WINDOW

STDLIB = set(sys.stdlib_module_names)
REPORT_NAME = "render_report.json"

# Filenames written at the map ROOT (see render() below) -- named so
# scripts/map_orient.py's CODE_MAP_INDEX / CODE_MAP_IDS constants can be
# cross-checked against these instead of drifting apart on two hardcoded
# literals (#534). map_orient.py cannot import this module directly: it ships
# standalone into consuming repos that have no tools/code_map at all, so the
# two sides stay in sync via tests/test_map_orient.py::CodeMapCandidateAlignment
# instead of a live import.
TOP_INDEX_FILENAME = "INDEX.md"
IDS_FILENAME = "ids.jsonl"

HOLE = "HOLE: no docstring"


def in_render_scope(mod, packages):
    """True when a module belongs in a render narrowed to `packages`.

    `packages` is dotted package prefixes the CALLER passed; empty narrows
    nothing and every module renders. A module is in scope when it IS one of
    them or sits under one -- matched on dotted SEGMENTS, so `engine` takes
    `engine.run` and never `engine_helpers`.

    No package name is written down here, and none may be: a hardcoded
    `engine` would be one repository's directory tree compiled into a tool
    that is meant to run against any of them. The narrowing is an argument."""
    return not packages or any(mod == p or mod.startswith(p + ".") for p in packages)

# ---------------------------------------------------------------- store state
# Populated by load_stores(); module-level so the page builders below read them
# the way the prototype did, rather than threading one context object through
# every formatter.

entities = {}                                # store symbol -> definition facts
modules = {}                                 # module name -> module facts
docs = {}                                    # store symbol -> doc summary
params = collections.defaultdict(list)       # store symbol -> [(order, name)]
inherits = collections.defaultdict(list)     # store symbol -> [base symbol]
edges = collections.defaultdict(list)        # store symbol -> [(p, o, res, why)]
inbound = collections.defaultdict(collections.Counter)   # symbol -> {caller module: n}
imports_out = collections.defaultdict(list)  # "mod:" -> [(o, res)]
imported_by = collections.defaultdict(set)   # module -> {importing module}
children = collections.defaultdict(list)     # parent symbol -> [(line, child symbol)]
members_of = collections.defaultdict(list)   # module -> [store symbol]
page_file = {}                               # store symbol -> page filename
ids = collections.defaultdict(list)          # authored slug -> [store symbol]
tags = collections.defaultdict(list)         # gate g7: symbol -> [{"kind","text"}]
stale_tags = []                              # gate g6: [{"id","s","old_hash","new_hash"}]
MODULES = []
BY_PKG = collections.defaultdict(list)

intern = sys.intern


def modof(symbol):
    return symbol.split(":", 1)[0] if ":" in symbol else symbol


def source_line(line, base):
    """A store line as the 1-based line the SOURCE FILE has.

    The renderer used to write a bare `+1` here with a comment naming the
    defect. That compensation was the proof the schema was silent: it was right
    only for as long as everyone remembered it. The store now declares its base
    in every `extraction-window` statement and this reads it."""
    return line + (1 - base)


def _case_tag(name):
    """A short, stable tag that tells two case-only spellings apart.

    `hashlib`, never the builtin `hash()`: `PYTHONHASHSEED` varies per process,
    so a `hash()`-derived filename would differ between two builds of the same
    source and the determinism check would -- correctly -- go red on it."""
    return hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]


def assign_page_filenames(keys):
    """store symbol -> page filename, for the symbols of ONE module.

    A page used to be named after its entity alone, so two entities in one
    module whose names differ only by case resolved to one file: on a
    case-insensitive filesystem the second write destroyed the first, and the
    map advertised a page a reader could not open.

    Names are grouped by their FOLDED spelling, and only a group with more than
    one member is disambiguated -- so the common case keeps the readable
    `<Entity>.md` and nothing else in the tree moves. `~` cannot occur in a
    Python qualified name, so a disambiguated filename can never collide with an
    undisambiguated one.

    Deliberately NOT handled: an entity literally named `INDEX`, which still
    lands on its module's own index page. Reserving that stem would make
    `page_accounting`'s only cross-platform falsifier unable to fail, and a
    check that cannot fail is the thing this gate exists to stamp out. Filed as
    a triage candidate instead."""
    groups = collections.defaultdict(list)
    for key in keys:
        groups[key.split(":", 1)[1].lower()].append(key)
    out = {}
    for group in groups.values():
        for key in group:
            name = key.split(":", 1)[1]
            out[key] = (f"{name}~{_case_tag(name)}.md" if len(group) > 1
                        else f"{name}.md")
    return out


def load_stores(artifacts, packages=()):
    """Read the statement store and build every index the page builders read.

    `packages` narrows the RENDER, never the walk -- see the comment below the
    read loop for what that distinction buys and why it is worth the two
    deletions it costs.

    ONE store. Every fact a page shows -- kind, signature, span, docstring body,
    values, decorators -- now rides the statement that names the thing, so the
    second AST pass this used to join against is gone, and with it the join.
    A page is keyed by the store symbol itself, because there is no longer a
    second spelling to translate to.

    Safe to call repeatedly: it resets state first."""
    artifacts = pathlib.Path(artifacts)
    for d in (docs, params, inherits, edges, inbound, imports_out, imported_by,
              children, members_of, page_file, BY_PKG, entities, modules, ids,
              tags, stale_tags):
        d.clear()
    MODULES.clear()

    with open(artifacts / STATEMENTS_NAME, encoding="utf-8") as f:
        for line in f:
            st = json.loads(line)
            p, s, o = st["p"], st["s"], st["o"]
            if p == WINDOW:
                d = st["d"]
                modules[modof(s)] = {"file": st["q"]["file"], "loc": d["loc"],
                                     "doc_body": d["doc_body"], "all": d["all"],
                                     "attrs": []}
                continue
            if p == "documents":
                docs[s] = o
                continue
            if p == "contains":
                d = st["d"]
                entities[intern(o)] = {"line": st["q"]["line"], "end": d["end"],
                                       "kind": d["kind"], "signature": d["signature"],
                                       "doc_body": d["doc_body"],
                                       "decorators": d["decorators"],
                                       "bases": d["bases"], "attrs": []}
                continue
            if p == "anchored":
                ids[o].append(s)
                continue
            if p == "tag":
                # Gate g7: must be intercepted explicitly, same as "anchored"
                # above -- an unhandled predicate falls through to the
                # edges/inbound catch-all below and would render as a bogus
                # cross-module bullet on some entity's page instead of
                # surfacing as the why-layer tag it is.
                d = st["d"]
                tags[s].append({"kind": o, "text": d["text"]})
                continue
            if p == "stale-anchor":
                # Gate g6: must be intercepted explicitly, same as "anchored"
                # above -- an unhandled predicate falls through to the
                # `edges`/`inbound` catch-all below and would render as a
                # bogus "stale-anchor cross-module" bullet on some entity's
                # page instead of surfacing as the staleness flag it is.
                d = st["d"]
                stale_tags.append({"id": o, "s": s,
                                   "old_hash": d["old_hash"], "new_hash": d["new_hash"]})
                continue
            if p == "stale-tag":
                # Gate g7 remediation fix 1: a REAL tag's own staleness --
                # the enclosing body changed while the tag text did not, with
                # no anchor involved at all. Lands in the SAME `stale_tags`
                # list/report field/ADVISORY channel g6 established above,
                # not a second reporting channel -- the review's explicit
                # requirement.
                d = st["d"]
                stale_tags.append({"id": o, "s": s,
                                   "old_hash": d["old_hash"], "new_hash": d["new_hash"]})
                continue
            if p == "declares":
                d = st["d"]
                owner = modules[modof(s)] if s.endswith(":") else entities[s]
                owner["attrs"].append({"name": o.split(":", 1)[1].rsplit(".", 1)[-1],
                                       "annotation": d["annotation"],
                                       "value": d["value"], "form": d["form"]})
                continue
            if p == "param-of":
                q = st["q"]
                params[o].append(((q["line"], q["col"]), s.rsplit(".", 1)[-1]))
                continue
            if p == "inherits":
                inherits[s].append(o)
                continue
            if p == "imports":
                imports_out[s].append((o, st.get("res")))
                if st.get("res") == "internal":
                    imported_by[modof(o)].add(modof(s))
                continue
            res = st.get("res")
            if res == "local":
                continue
            edges[intern(s)].append((intern(p), intern(o), intern(res or "?"),
                                     intern(st.get("why") or "")))
            if p in ("calls", "reads"):
                inbound[o][intern(modof(s))] += 1

    # Narrow the RENDER, never the walk. Everything above read the WHOLE store,
    # so an entity's inbound counts and a module's importer list still see
    # modules that get no page of their own -- "referenced by (tests): 12 sites"
    # is half of what makes a page answer a deletion question, and it goes to
    # zero the moment the walk itself narrows. What narrows is which modules get
    # pages. Every index built below is built from what SURVIVES this, so the
    # report's `entities` and `holes` describe the tree that was rendered rather
    # than the store behind it -- a count over the store would bury the rendered
    # subset's real holes under every hole in the corpus.
    for mod in [m for m in modules if not in_render_scope(m, packages)]:
        del modules[mod]
    for key in [k for k in entities if modof(k) not in modules]:
        del entities[key]

    # children: the parent is the symbol minus its last qualified part
    for key, e in entities.items():
        mod, name = key.split(":", 1)
        parent = mod + ":" + name.rsplit(".", 1)[0] if "." in name else mod + ":"
        children[parent].append((e["line"], key))
    for v in children.values():
        v.sort()

    MODULES.extend(sorted(modules))
    for m in MODULES:
        BY_PKG[m.split(".")[0]].append(m)
    for key in entities:
        members_of[modof(key)].append(key)
    for keys in members_of.values():
        page_file.update(assign_page_filenames(keys))


# ---------------------------------------------------------------- formatting


def ext_label(symbol):
    """stdlib vs third-party -- classified renderer-side; the store does not say."""
    top = symbol.split(":", 1)[0].split(".")[0]
    return "stdlib" if top in STDLIB or top == "builtins" else "third-party"


def tally(items):
    c = collections.Counter(items)
    return ", ".join(
        f"{k}" + (f" x{v}" if v > 1 else "")
        for k, v in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))
    )


def summary_of(key):
    """The docstring summary the store recorded for this symbol."""
    return docs.get(key)


def mod_summary_of(mod):
    return docs.get(mod + ":")


def loc(key, e):
    """file, N lines -- a page header carries no source position.

    The line number is deliberately absent. It churned: a 3-line edit near the
    top of a file shifts every entity below it, rewriting hundreds of unrelated
    pages. The file path stays because it is not a position -- it changes only
    when the file moves -- and the entity's own size stays because it changes
    only that entity's own page, which is a page changing when its own subject
    changed. `.code-map/statements.jsonl` already carries per-statement
    {file, line, col} and is gitignored, so the positions remain available to
    anything that needs them; they are simply not committed.

    The span is a DIFFERENCE of two store lines, so it is the same number in
    any line base -- the one number on this page the declared base cannot
    move."""
    head = modules[modof(key)]["file"]
    if e.get("end") is not None:
        head += f", {e['end'] - e['line'] + 1} lines"
    return head


def doc_block(summary, body):
    L = []
    if summary:
        L.append(summary)
        if body:
            L.append("")
            L.extend(body.split("\n"))
    else:
        L.append(HOLE)
    L.append("")
    return L


def tag_lines(key):
    """The entity or module's own why-layer: `Rationale:`/`Rejected:`/`See:`
    paragraphs the author wrote directly above it (gate g7), one line per
    tag in source order.

    ONE loop, no branch on kind, for every tag regardless of which of the
    three grammar words it carries -- this uniform treatment is itself the
    cull test's evidence (see `.agent-work/issue-456/cull-verdict.json`): a
    consumer that cannot tell `Assumption:`/`Constraint:`/`Rationale:` apart
    gives the vocabulary nothing to earn a fourth word, so the shipped
    grammar carries three."""
    ts = tags.get(key)
    if not ts:
        return []
    L = [f"{t['kind']}: {t['text']}" for t in ts]
    L.append("")
    return L


def attr_lines(attrs):
    """Constants / fields as code-shaped lines: NAME: annotation = value"""
    L = ["```python"]
    for a in attrs:
        if a["name"].startswith("__"):
            continue
        s = a["name"]
        if a.get("annotation"):
            s += f": {a['annotation']}"
        v = a.get("value")
        if v is not None:
            v = " ".join(v.split())
            if len(v) > 90:
                v = v[:87] + "..."
            s += f" = {v}"
        L.append(s)
    L.append("```")
    L.append("")
    return L


def uses_lines(key, mod):
    buckets = collections.defaultdict(list)
    unresolved = collections.Counter()
    ownparams = {f"{key}.{pn}" for _, pn in params.get(key, [])}
    for p, o, res, why in edges.get(key, []):
        if o in ownparams and p == "reads":
            continue
        if res == "unresolved":
            unresolved[(p, why or "?")] += 1
        elif res == "internal":
            tag = "internal" if modof(o) == mod else "cross-module"
            buckets[(p, tag)].append(
                o.split(":", 1)[1] if tag == "internal" and ":" in o else o)
        elif res == "external":
            lab = o[:-1] + " (module)" if o.endswith(":") else o.replace(":", ".")
            buckets[(p, ext_label(o))].append(lab)
    L = []
    for pred in ("calls", "reads", "writes"):
        for tag in ("internal", "cross-module", "stdlib", "third-party"):
            v = buckets.get((pred, tag))
            if v:
                L.append(f"{pred} {tag}: {tally(v)}")
    if unresolved:
        L.append("unresolved: " + ", ".join(
            f"{n} {p} ({why})" for (p, why), n in sorted(unresolved.items())))
    if L:
        L.append("")
    return L


#: What the inbound count counted, said on the page itself.
#:
#: A count without a definition is the defect: the page said 5, a reader's grep
#: said 7, and neither number told him which one was answering his question.
#: The wording tracks `load_stores`, which counts `calls` and `reads` and
#: nothing else -- `checks.py` declares this same sentence independently and
#: `RefsAccountingTests` pins it to that predicate test, so widening one
#: without the other goes red.
REFS_LEGEND = ("counted: calls and reads that resolved to this symbol. "
               "not counted: its own definition, imports, inheritance, "
               "attribute writes, docstring mentions, unresolved references.")

#: `referenced by: none found` used to answer three different questions with
#: one sentence: nothing calls this, only tests call this, or this itself IS a
#: test (pytest, not another module, is what invokes it -- zero inbound there
#: is the expected state). A reader could not tell which without opening
#: another page. These two prefixes split the caller list so the split is
#: visible on the page itself; `checks.py` declares its own copies of both
#: (never imported), the same way it already does for `REFS_LEGEND`.
REFS_PROD_PREFIX = "referenced by (production): "
REFS_TEST_PREFIX = "referenced by (tests): "

#: Shown on a test-defined entity's own page, directly above its two caller
#: lines, so `none found` there reads as the normal state rather than a
#: dead-code alarm. `checks.py` declares its own copy, byte for byte.
TEST_NOTE = ("this entity is defined in a test module (see split legend "
             "below): zero callers here is the normal, expected state, not "
             "a finding.")

#: What the production/test split is based on, said on every page that
#: carries one -- the close criterion is that a reader who disagrees with the
#: split can see the rule that produced it without leaving the page. Derived
#: from pytest's own DOCUMENTED default discovery convention (the
#: `python_files` glob `test_*.py` / `*_test.py`, and the `tests` package
#: layout pytest's own docs recommend) rather than tuned to this repo's own
#: layout -- see `is_test_module`. A corpus whose tests follow neither
#: convention is classified production; that is a real degradation and this
#: sentence is where it is named, not hidden.
SPLIT_LEGEND = ("split: production vs test caller module, by pytest's "
                "default discovery convention -- test_*.py / *_test.py "
                "naming, or a tests package anywhere on the module path. "
                "a module matching neither is counted production.")


def is_test_module(mod):
    """True when `mod` is a pytest-discovered test module.

    Restated on the module's own DOTTED NAME rather than its file path: a
    module's last dotted segment is its file's basename with `.py` stripped
    (`extract.mod_of`), so the two agree by construction and no file lookup
    is needed here. Two independent halves of pytest's documented default
    `python_files` convention:

    - filename: `test_*.py` or `*_test.py` -- the last segment starts with
      `test_` or ends with `_test`.
    - layout: a `tests` package anywhere on the module's own dotted path --
      the other of the two standard layouts pytest's own docs describe.

    Derived, not tuned: nothing here reads this repo's own directory names.
    A corpus whose tests follow neither convention (a `run_tests` module
    alongside a `tests` package, for instance) classifies the outlier as
    production -- stated in `SPLIT_LEGEND`, not hidden. `checks.py` restates
    this same rule a second time, by hand, rather than importing it, so a
    divergence between the two is something a check can actually catch."""
    parts = mod.split(".")
    last = parts[-1]
    if last.startswith("test_") or last.endswith("_test"):
        return True
    return "tests" in parts


def _bucket_line(prefix, counter, mod):
    """One caller-list line for one bucket (production or test), in the same
    grammar the single combined line always used -- `none found` / `N sites,
    this module only` / `N sites in M modules (...) [+ K in this module]`.

    Shared by both buckets so there is exactly ONE `sorted(...)` call in this
    file governing caller-list order -- the anchor `tc32`'s falsifier mutates
    to prove nothing but that sort keeps the rendered order stable."""
    if not counter:
        return prefix + REFS_NONE
    n = sum(counter.values())
    ext = sorted(m for m in counter if m != mod)
    if ext:
        s = prefix + f"{n} sites in {len(counter)} modules (" + ", ".join(ext) + ")"
        own = counter.get(mod, 0)
        if own:
            s += f" + {own} in this module"
    else:
        s = prefix + f"{n} sites, this module only"
    return s


#: Matches `checks.REFS_NONE` byte for byte -- declared independently there.
REFS_NONE = "none found"


def refs_line(key, mod):
    """The page's two inbound lines -- production callers, then test callers
    -- plus the legends that say what each counted and how the split was
    made.

    Splitting the SAME counted total (`REFS_LEGEND` is unchanged: still calls
    and reads, still nothing else) into two buckets by caller module is what
    turns `referenced by: none found` from one sentence doing three jobs into
    three lines that can each only mean one thing. A test-defined entity
    additionally gets `TEST_NOTE` first, so its own near-universal
    `none found` / `none found` does not read as a dead-code finding."""
    callers = inbound.get(key, {})
    prod = {m: n for m, n in callers.items() if not is_test_module(m)}
    test = {m: n for m, n in callers.items() if is_test_module(m)}
    L = []
    if is_test_module(mod):
        L.append(TEST_NOTE)
    L.append(_bucket_line(REFS_PROD_PREFIX, prod, mod))
    L.append(_bucket_line(REFS_TEST_PREFIX, test, mod))
    L.append(REFS_LEGEND)
    L.append(SPLIT_LEGEND)
    L.append("")
    return L


def entity_page(key, mod):
    name = key.split(":", 1)[1]
    e = entities[key]
    kind = e.get("kind", "?")
    L = [f"# {key}", f"{kind}, {loc(key, e)}", ""]

    sig = e.get("signature")
    decos = [d for d in e.get("decorators", [])
             if d not in ("property", "classmethod", "staticmethod")]
    if sig or kind == "class" or decos:
        L.append("```python")
        for d in decos:
            L.append(f"@{d}")
        if sig:
            L.append(f"{'async ' if kind.startswith('async') else ''}"
                     f"def {name.split('.')[-1]}{sig}")
        elif kind == "class":
            bases = ", ".join(b.split(":")[-1] for b in inherits.get(key, []))
            L.append(f"class {name.split('.')[-1]}({bases})" if bases
                     else f"class {name.split('.')[-1]}")
        L.append("```")
        L.append("")

    L.extend(doc_block(summary_of(key), e.get("doc_body")))
    L.extend(tag_lines(key))

    attrs = [a for a in (e.get("attrs") or []) if not a["name"].startswith("__")]
    if attrs:
        L.extend(attr_lines(attrs))

    kids = children.get(key, [])
    if kids:
        for _, k in kids:
            kn = k.split(":", 1)[1]
            ke = entities[k]
            L.append(f"- [{kn.split('.')[-1]}]({page_file[k]}) {ke.get('kind', '')}: "
                     + (summary_of(k) or HOLE))
        L.append("")

    L.extend(uses_lines(key, mod))
    L.extend(refs_line(key, mod))
    return "\n".join(L).rstrip() + "\n"


def module_index(mod):
    ms = modules[mod]
    members = members_of.get(mod, [])
    holes = sum(1 for k in members if not summary_of(k))
    L = [f"# {mod}",
         f"{ms['file']}, {ms['loc']} lines" + (f", {holes} holes" if holes else ""), ""]
    L.extend(doc_block(mod_summary_of(mod), ms.get("doc_body")))
    L.extend(tag_lines(mod + ":"))

    if ms.get("all"):
        L.append("__all__: " + ", ".join(str(x) for x in ms["all"]))
        L.append("")

    imps = imports_out.get(mod + ":", [])
    ext = sorted({o.rstrip(":").replace(":", ".") for o, res in imps if res == "external"})
    inte = sorted({o for o, res in imps if res == "internal"})
    std = [x for x in ext if ext_label(x) == "stdlib"]
    thi = [x for x in ext if ext_label(x) != "stdlib"]
    if std:
        L.append("imports stdlib: " + ", ".join(std))
    if thi:
        L.append("imports third-party: " + ", ".join(thi))
    if inte:
        L.append("imports internal: " + ", ".join(inte))
    importers = sorted(imported_by.get(mod, ()))
    if importers:
        L.append("imported by: " + ", ".join(importers))
    else:
        L.append("imported by: none found")
    L.append("")

    mattrs = [a for a in (ms.get("attrs") or []) if not a["name"].startswith("__")]
    if mattrs:
        L.extend(attr_lines(mattrs))

    def walk(key, depth):
        nm = key.split(":", 1)[1]
        e = entities[key]
        L.append("  " * depth + f"- [{nm}]({page_file[key]}) {e.get('kind', '')}: "
                 + (summary_of(key) or HOLE))
        for _, kid in children.get(key, []):
            walk(kid, depth + 1)

    for _, k in children.get(mod + ":", []):
        walk(k, 0)
    return "\n".join(L).rstrip() + "\n"


def repo_name(root):
    """Name the map after the repository, not the directory it was built in: a
    git worktree's directory is named for the branch, so `<root>.name` would
    title the map after whatever scratch checkout happened to build it."""
    root = pathlib.Path(root).resolve()
    try:
        common = subprocess.run(["git", "rev-parse", "--git-common-dir"],
                                cwd=str(root), check=True,
                                capture_output=True, text=True).stdout.strip()
    except Exception:
        return root.name
    if not common:
        return root.name
    common = pathlib.Path(common)
    if not common.is_absolute():
        common = root / common
    parent = common.resolve().parent
    return parent.name or root.name


def module_group_key(mod):
    """The dotted-name prefix a module would share with a real subpackage: its
    first two segments, or the module itself when it has fewer than two.

    A property of the module's OWN name only -- no name, no directory
    convention (`src/`, `test_*`), no count. `top_index` groups a package's
    modules under this key wherever some OTHER module in the same package
    shares it as a genuine subpackage prefix (three or more segments); this
    function only says what that prefix WOULD be, for any module, so the
    caller can test every module against the same rule."""
    parts = mod.split(".")
    return ".".join(parts[:2])


def _module_line(mod):
    members = members_of.get(mod, [])
    h = sum(1 for k in members if not summary_of(k))
    d = mod_summary_of(mod)
    return (f"- [{mod}]({mod}/INDEX.md) ({len(members)} entities"
            + (f", {h} holes" if h else "") + "): " + (d or HOLE))


def top_index(title):
    """The map's one entry point, in TWO tiers.

    A flat list of every module is not a routing surface: a cold reader who
    reads only the first N lines learns nothing about the corpus's actual
    shape, because the buckets that happen to sort first eat the whole
    budget before the largest one ever appears. So tier 1 is every top-level
    package's own size, in full, before a single per-module bullet -- bounded
    by how many top-level packages the corpus has, never by how many modules
    or entities they hold. Tier 2, within each package's own section, groups
    a module under a real subpackage heading wherever the corpus actually
    nests one (derived from the module names' own segment counts -- critic
    F9: a rule keyed to `src/` or any other convention this repo happens to
    follow would look fine here and fail on the next corpus) and lists a
    module with no subpackage of its own directly, which is an honest report
    of a flat corpus, not a fallback."""
    L = [f"# {title} map", ""]
    if not BY_PKG:
        L.append("(no mappable modules found)")
        return "\n".join(L).rstrip() + "\n"

    L.append("## packages")
    for pkg in sorted(BY_PKG):
        mods = BY_PKG[pkg]
        nent = sum(len(members_of.get(m, [])) for m in mods)
        L.append(f"{pkg}: {len(mods)} modules, {nent} entities")
    L.append("")

    for pkg in sorted(BY_PKG):
        mods = BY_PKG[pkg]
        nent = sum(len(members_of.get(m, [])) for m in mods)
        L.append(f"## {pkg} ({len(mods)} modules, {nent} entities)")
        L.append("")

        subpkgs = {module_group_key(m) for m in mods if len(m.split(".")) >= 3}
        grouped = collections.defaultdict(list)
        loose = []
        for mod in mods:
            key = module_group_key(mod)
            (grouped[key] if key in subpkgs else loose).append(mod)

        for key in sorted(grouped):
            gmods = grouped[key]
            gent = sum(len(members_of.get(m, [])) for m in gmods)
            L.append(f"### {key} ({len(gmods)} modules, {gent} entities)")
            L.append("")
            for mod in gmods:
                L.append(_module_line(mod))
            L.append("")
        for mod in loose:
            L.append(_module_line(mod))
        if loose:
            L.append("")
    return "\n".join(L).rstrip() + "\n"


# ---------------------------------------------------------------- stage

def run(root, artifacts, out, packages=()):
    """Render the page tree for `root` from `artifacts` into `out`. Returns an
    exit code.

    `packages` is the caller's render narrowing -- see `in_render_scope`."""
    load_stores(artifacts, packages)
    out = pathlib.Path(out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    sizes = []
    for mod in MODULES:
        d = out / mod
        d.mkdir(exist_ok=True)
        (d / "INDEX.md").write_text(module_index(mod), encoding="utf-8", newline="\n")

        def emit(key):
            page = entity_page(key, mod)
            (d / page_file[key]).write_text(
                page, encoding="utf-8", newline="\n")
            sizes.append((page.count("\n"), key))
            for _, kid in children.get(key, []):
                emit(kid)

        for _, k in children.get(mod + ":", []):
            emit(k)
    (out / TOP_INDEX_FILENAME).write_text(top_index(repo_name(root)),
                                           encoding="utf-8", newline="\n")
    # ids.jsonl: the mind map's one lookup. Sorted, so its git diff IS the
    # id-motion report, and `{id, s}` with NO position, so an edit anywhere else
    # in the file leaves it byte-identical. The symbol path is derived and
    # disposable; the authored slug is what the mind map stores.
    (out / IDS_FILENAME).write_text(
        "".join(json.dumps({"id": i, "s": ids[i][0]}) + "\n" for i in sorted(ids)),
        encoding="utf-8", newline="\n")
    duplicates = sorted(i for i in ids if len(ids[i]) > 1)

    # Count the tree, not the writes. A per-write counter reports what the
    # renderer TRIED to do, so two pages resolving to one path -- a name
    # colliding with the module's own INDEX.md, or two names differing only by
    # case on a case-insensitive filesystem -- reads as two pages while one
    # file exists. Counting the files makes the number incapable of disagreeing
    # with the tree it describes. Deduplicating resolved path strings would NOT
    # do: two strings differing only by case are distinct strings and the same
    # file.
    npages = sum(1 for _ in out.rglob("*.md"))

    holes = sum(1 for k in entities if not summary_of(k))
    sizes.sort(reverse=True)
    report = {
        "modules": len(MODULES),
        "entities": len(entities),
        "pages": npages,
        "entity_pages": len(sizes),
        "holes": holes,
        "ids": len(ids),
        "median_entity_page_lines": sizes[len(sizes) // 2][0] if sizes else 0,
        "largest_5": [[n, k] for n, k in sizes[:5]],
        # Gate g6 + g7 remediation fix 1: entries whose ENCLOSING body span
        # changed since the PREVIOUS build while the authored marker's own
        # identity did not -- an anchor's slug (g6), or a tag's (owner, text)
        # pair (g7, no anchor required). See extract.py's span_hash/run() for
        # what changed and what did not.
        "stale_tags": [t["id"] for t in stale_tags],
    }
    print(json.dumps(report, indent=1))
    for slug in duplicates:
        # An authored mistake, and the run report is where the ruling says it
        # surfaces. Keeping one silently would leave the mind map pointing at
        # whichever definition happened to win.
        print("FAIL duplicate id [%s] claimed by: %s"
              % (slug, ", ".join(sorted(ids[slug]))))
    for t in stale_tags:
        # ADVISORY, not a build failure (deliberately -- see the return code
        # below): a duplicate id is unambiguous data corruption, but a stale
        # tag might still be true. What a human does when this fires: open
        # the tag at `t['s']` and re-read it against the current code; update
        # or remove it if it no longer holds.
        print("ADVISORY stale tag [%s]: enclosing body changed, tag text did not -- "
              "review %s and update or remove the tag" % (t["id"], t["s"]))
    artifacts = os.fspath(artifacts)
    os.makedirs(artifacts, exist_ok=True)
    with open(os.path.join(artifacts, REPORT_NAME), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    # Stale tags do NOT fail the build: unlike a duplicate id, they are not
    # unambiguous corruption, so failing the build on one would be the same
    # twitchy tripwire `gb`'s ratio-over-count reasoning warns against --
    # `gb`'s own ruling scoped only its four ratio-based thresholds, not
    # this check's severity, but the underlying reasoning carries over.
    return 1 if duplicates else 0
