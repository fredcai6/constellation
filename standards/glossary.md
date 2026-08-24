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
- **interior / worklist** — a segment's mutable contents; grown, pruned, and reordered by
  amend; exhausted means the segment ends.
- **transition** — the step that ends a segment: looks back (what did we learn — does the plan
  hold?), decides, and mints the next interior. The OODA beat.
- **anchor** — a template step flagged so that amending it away is loud in the ledger and the
  parent's adjudication view. Still one journaled step to amend; never a refusal.
- **form** — one step's imperative, fields, and field notes; the unit that carries doctrine.
- **field kind** — how a field is satisfied: `check`, `evidence`, `artifact`, `decision`,
  `plan`; any field instead takes `waived: <reason>` or `unknown: <reason>`.
- **plan field** — a field whose submitted content is minted as steps: the next segment's
  interior, a gate's spec.
- **work id** — a run's address, `<kind><number>` (`issue712`); children by suffix
  (`issue712.g1`). Short and meaningless on purpose — the title holds the "what." Required on
  every call, never inferred.
- **quarters** — a run's work package, `.agent-work/<work-id>/`: journal, response forms, plan
  artifacts, notes; child runs nest inside. Derived from the id, visible to everyone.
- **journal** — the per-run append-only TOML record in its quarters; run state is a fold over
  it.
- **ledger** — the on-demand listing of open runs (bare `spine`): id, title, position, state;
  generated from journals, never stored.
- **model tier** — a logical dispatch weight (`light | standard | heavy`) named by assemblies
  and gate specs; the command palette maps it to a concrete runner.
- **conductor** — the one persistent agent of an assembly; pumps its interior mechanically,
  judges only at transitions.
- **gate** — a segment minted into an execute phase; runs as a child run (run-a-gate) with the
  gate executor conducting its implement–review loop.
- **prefill** — the parent's dispatch fields, stamped read-only into a child's opening. The
  order; contested by a blocked note up, never edited.
- **return** — the child's terminal fields, stamped into the parent's waiting step at close,
  including the child's amend summary.
- **authority block** — who your principal is, what you own, your latitude, where gaps go;
  derived at dispatch, never authored.
- **pivot criteria** — what changes the plan, not only what ends it.
- **command palette** — `constellation.toml`: the host repo's test/lint/build commands, which
  check fields reference instead of hardcoding, and the model-tier map.
