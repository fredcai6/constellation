# Skill

A skill is one posture: who you are at this step and how you carry it. It makes the agent do
the same thing every run — predictability is the root virtue, and every criterion below serves
it. When a criterion is unclear, ask: does this make the next run more predictable, or less?

## The bar

- **One move.** A skill holds one posture. If it does two jobs, either state why they live
  together or split it.
- **Reads only its form.** A skill's procedure is: read the form `status` hands you, fill it,
  submit. A skill that requires other reading is carrying doctrine that belongs in a form
  field, an error message, or nowhere.
- **Word budget.** Each skill has one, forms included — a role costs everything its agent reads
  to hold that posture. These are alert thresholds, like the repo-wide caps in
  `docs/AGENT_GUIDE.md`: a crossing is a prompt to ask what the skill does not need, never a
  reason to trim guidance just to shrink the number. Checked with `wc`; only some are enforced
  by a test today.

  | Skill | Words |
  |---|---|
  | explorer | 2,500 |
  | epic-conductor | 1,500 |
  | issue-conductor | 1,500 |
  | issue-conductor-delegated | 500 |
  | interrogator | 800 |
  | spec-writer | 600 |
  | critic | 850 |
  | reviewer | 700 |
  | implementer | 800 |
  | gate-conductor | 800 |
  | excursion | 1,050 |
  | triage | 600 |
  | how-to-talk | 500 |
  | standards | 1,500 |
  | assemblies | 2,000 |
- **Leading words.** Open by telling the agent what to *do*, not by narrating background.
- **Completion is checkable.** "Done" is a state two agents cannot disagree on.
- **The no-op test.** Strip a sentence: if the run would go identically without it, it is
  sediment — cut it.
- **Negative space.** Say what NOT to do and where the skill does NOT apply, not only the
  happy path.
- **Prose per `standards/prose.md`;** names per `standards/glossary.md`.

An independent fresh-context reviewer judges the bar — never the author's self-grade.
