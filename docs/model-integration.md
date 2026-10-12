# Model integration

<!-- index: design | Confining a language model inside a product: code decides, the model reads and writes, votes, grounding, shadow mode, measured confidence | code calls a model at runtime or model output reaches a decision -->

A language model inside a product is a fast, fluent component that is
sometimes confidently wrong, and wrong differently on every call. This page
owns how to give it a job whose errors code can catch. Timeouts and fallbacks
are in [`engineering.md`](./engineering.md#time-budgets); measuring a change
is in [`experiments.md`](./experiments.md).

## Division of labour

- **Code decides.** Numbers, limits, eligibility, and every decision that can
  be computed live in tested code. The model reads unstructured input, writes
  text, and chooses among options code has already made valid. It never
  produces a number that code then trusts; code computes it or checks it
  against the input.
- **Decisions are pure.** `decide(state)` depends only on the observable
  state, so a fresh process resumes where an old one stopped and a repeated
  call does not advance anything. Test both: call it twice, and once with a
  new instance on the same state.
- **Strict in tests, safe in production.** A switch makes an internal error
  raise under tests; in production the same error becomes a safe, counted
  default, shown in the run record
  ([no silent fallbacks](./engineering.md#no-silent-fallbacks)).

## Getting a trustworthy answer

- **Ground every claim.** A structured answer quotes the passage of its input
  each claim rests on; code checks the quote is really there and drops claims
  whose quote is missing.
- **Vote, do not ask for confidence.** For a judgement that matters, make N
  independent calls and act only when k agree; agreement is counted, not
  self-reported. Where the API exposes token probabilities, read confidence
  from them, never from the model's own statement.
- **Compare with a trivial baseline.** Score each classifier-like use against
  the dumbest rule ("always no", the majority class). A model that does not
  beat it is not used, however plausible its reasons read.
- **Fail empty.** A failed, timed-out, or unparsable call returns an empty
  result that code handles, never a guess, and it is not cached.
- **Each output kind earns its rule.** Before code acts on a new kind of model
  output, measure how often it is right and write the rule that uses it; one
  measured kind does not license another.

## Rolling out model influence

1. **Shadow.** The model's verdict is logged next to the decision code made,
   with a test proving shadow mode never changes a decision.
2. **Measure.** Read the trace: how often would the verdict have changed the
   decision, and was the change better on the real objective?
3. **Apply behind a switch**, off by default, named with the measurement that
   justified turning it on.

## Seeing what the model used

Log, per decision, which inputs and tools were actually read and which call
answered. A report then shows inputs nobody uses, lookups that failed and were
silently rescued, and calls that fell back. Check that no call fell back
before trusting a score.

## Running many at once

Parallel decisions must equal sequential ones on the same states: test it.
Warm shared caches before load, guard a shared connection with a lock, and
never queue a second call behind a hung one; give each decision its own
deadline and a safe fallback when it passes. Cache model calls by a hash of the
full prompt only in labs and tests, and check the cache is stable (cached and
fresh answers agree in kind).
