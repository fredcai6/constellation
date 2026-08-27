# Understanding moves

Ways to convert an open question into evidence. Understanding and plan forms carry a mandatory
field: *name the excursion that would settle something now, or decline with a reason.*

Three moves dispatch an **excursion** — a child run answering one named question, briefed on
the row or step that opens it, returning a scoped verdict and the command that regenerates it:

- **Ask the world.** Dispatch prior art: what the literature, the ecosystem, and this
  codebase's own history already say. Primary sources, a citation per claim.
- **Spike it.** Dispatch a prototype: throwaway code, disposed. The prototype answers the
  question; it never becomes the implementation.
- **Picture it.** Dispatch a picture: a table, a plot, a dump shaped so the anomaly has
  nowhere to hide — and a statement of what the view cannot show.

Three are worked in place:

- **Reproduce it.** Make the break happen on demand before reasoning about it. A break you
  cannot reproduce is an open question, not a fact.
- **Trace one case.** Follow a single concrete input through the system end to end and write
  down what actually happens at each hop.
- **Run the evidence loop.** For a break or an intent-vs-execution disconnect: reproduce it,
  then hypothesis → test until the cause is *shown*, never guessed. Each cycle names the
  hypothesis, the test that would falsify it, and what the test showed. The loop ends when the
  cause reproduces the break.

Questions are typed `fact`, `decision`, or `understanding`. A fact is answerable from the code
or by a move above: resolve it yourself and record the evidence. A decision is a choice your
principal owns: never self-answer it — send it up and mark the field `unknown` until it
returns. An understanding is the reading you are proceeding on: mirror it to your principal in
one sentence and record their confirmation or correction, verbatim.
