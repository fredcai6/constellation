# Glossary

One name for one thing. New terms enter through the key-terms field on understanding and plan
forms; coining a synonym for a term below is a defect.

- **run** — one instantiated pass through an assembly, addressed by its work id, recorded in
  its journal.
- **assembly** — a run template: a fixed skeleton of segments, each transition naming what its
  plan field may mint and which skill fills each step.
- **segment** — the engine's one structural concept: an ordered interior of items — steps or
  nested segments — ending in one transition. *Phase*, *gate*, and *wave* are segment names,
  not engine concepts.
- **interior** — a segment's mutable contents, one of two kinds: a **worklist** of steps
  (grown, pruned, and reordered by amend; exhausted means the segment ends) or a **board**.
- **board** — an expansive segment's interior as a living TOML document in the work location:
  seeded at entry, worked freely in place, validated by the engine at the transition. The
  understand board; the explore ideas board. Blocked is per-row, never per-run; a row
  resolves by prose evidence, an artifact, or a dispatched child's returns.
- **askable** — a board row workable right now: its own status is `open`, and no id in its
  `after` is `open` or `up`.
- **held** — a board row whose own status is `open` and one or more of whose `after` ids is
  `open` or `up`; those ids are what it is held by.
- **cluster** — an optional tag grouping board rows taken to the principal in one sitting. A
  cluster is ready when it has at least one open row and every open row in it is askable.
- **moot** — a board row settled by another row's answer rather than its own. The answer that
  mooted it is recorded as prose in its own `answer`; which row did the mooting is not
  recorded anywhere, and nothing needs it.
- **transition** — a segment's exit gate: fires when the interior drains, and each firing
  releases (advance, minting what comes next), refills the interior (rework, findings as
  prefill), or goes up (escalate). The OODA beat; cycling is re-firing.
- **verdict panel** — 0..n reviewers a transition dispatches, each cold and prefilled with
  focused criteria; verdicts return to the transition. Any revise refills, findings merged.
  Review never lives in an interior.
- **anchor** — one word, two senses. The rule above bars a second name for one thing; it does
  not bar one name for two, and these two never appear in the same reading. *In a run:* a
  template step flagged so that amending it away is loud in the ledger and the parent's
  adjudication view — still one journaled step to amend, never a refusal. *In the map:* an
  authored identity for a definition — a comment line holding only a bracketed kebab slug,
  `# [stable-id]`, directly above what it names. Minted on demand; the one fact about a
  definition the map stores instead of deriving.
- **form** — one step's imperative, fields, and field notes; the unit that carries doctrine.
- **field kind** — how a field is satisfied: `check`, `evidence`, `artifact`, `decision`,
  `plan`; any field instead takes `waived: <reason>` or `unknown: <reason>`.
- **plan field** — a field whose submitted content is minted as steps: the next segment's
  interior, a gate's spec.
- **work id** — a run's address: the tracker issue's number when one exists (`issue17`),
  `<kind><hash>` otherwise (`issue7c3f`); children by suffix (`issue17.g1`). The title holds
  the "what." Required on every call, never inferred.
- **work location** — a run's work package, `.agent-work/<work-id>/`: journal, response forms,
  plan artifacts, notes; child runs nest inside. Derived from the id, visible to everyone.
- **journal** — the per-run append-only TOML record in its work location; run state is a fold
  over it.
- **ledger** — the on-demand listing of open runs (bare `spine`): id, title, position, state;
  generated from journals, never stored.
- **model tier** — a logical dispatch weight (`light | standard | heavy`) named by assemblies
  and gate specs; the command palette maps it to a concrete runner.
- **conductor** — the one persistent agent of an assembly; pumps its interior mechanically,
  judges only at transitions.
- **gate** — a unit of execution minted by the plan; runs as a child run (run-a-gate) with the
  implementer working its interior and firing its review transition.
- **prefill** — the parent's dispatch fields, stamped read-only into a child's opening. The
  order; contested by a blocked note up, never edited.
- **return** — the child's terminal fields, stamped into the parent's waiting step at close,
  including the child's amend summary.
- **authority block** — who your principal is, what you own, your latitude, where gaps go;
  derived at dispatch, never authored.
- **pivot criteria** — what changes the plan, not only what ends it.
- **command palette** — `constellation.toml`: the host repo's test/lint/build commands, which
  check fields reference instead of hardcoding, and the model-tier table.
- **map** — the derived page tree under `map/`: one page per entity, a module index per module,
  one top index. Built by `tools/code_map` — the generator, and that is its only name — through
  `palette:map`; gitignored, regenerated at closeout, never committed. The artifact, not the act
  of making it.
- **entity** — a mapped definition: one function or class, named by its enclosing scope's symbol
  plus its own name. The unit the map gives a page to.
- **hole** — a mapped entity or module with no docstring, so the map has nothing to say about
  what it is for. Counted per module and repo-wide in the map's report.
- **corpus** — one word, two senses, on the same grounds as `anchor`. *The v2 corpus:* the
  authored artifacts an agent must read before it can work — skills, forms, standards,
  assemblies — measured in words against the 15,000 target (`docs/V2_DESIGN.md`, Measurable
  goals). Derived output is not in it. *The mappable corpus:* every tracked `.py` file the map
  is built from, which is the sense `tools/code_map` uses throughout its own docstrings.
