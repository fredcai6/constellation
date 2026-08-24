# Understanding moves

Ways to convert an open question into evidence. Understanding and plan forms carry a mandatory
field: *name the spike or data view that would settle something now, or decline with a reason.*

- **Spike it.** Dispatch the prototyper: one named question, throwaway code, disposed. The
  prototype answers the question; it never becomes the implementation.
- **Picture it.** Build a data view that makes the problem visible — a table, a plot, a dump
  formatted so the anomaly has nowhere to hide.
- **Reproduce it.** Make the break happen on demand before reasoning about it. A break you
  cannot reproduce is an open question, not a fact.
- **Trace one case.** Follow a single concrete input through the system end to end and write
  down what actually happens at each hop.
- **Run the evidence loop.** For a break or an intent-vs-execution disconnect: reproduce it,
  then hypothesis → test until the cause is *shown*, never guessed. Each cycle names the
  hypothesis, the test that would falsify it, and what the test showed. The loop ends when the
  cause reproduces the break.

Questions are typed `fact` or `decision`. A fact is answerable from the code or by a move
above: resolve it yourself and record the evidence. A decision is a choice your principal
owns: never self-answer it — send it up and mark the field `unknown` until it returns.
