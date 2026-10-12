---
name: experiment-lab
description: "Experiment simulator and evaluation harness: reaches a measured goal by building a deterministic core and a local simulator first, then one-change experiments on a ledger; Use when success is a metric, benchmark, A/B result, latency or cost target, or leaderboard score, especially when real measurements are slow, costly, or limited"
---

# Experiment lab

Outcome: the goal's number improves through measured, reproducible steps, and
slow or costly real measurements are spent only to confirm what a cheap local
evaluation already ranked. Load this when success is a number (a model metric,
a benchmark, an A/B result, latency, cost, a leaderboard). The rules and their
reasons live in [`docs/experiments.md`](../../../docs/experiments.md); this
skill is the order of work. For a small goal, steps 1, 3, 5 and 6 are enough.

## Steps

1. **Objective.** Write the metric's formula, the averaging unit and the
   conditions of the measurement that matters into the goal's issue or context
   doc; implement it as a local function and check it against one real result.
   Rebuild any external evaluator's checks locally, and write the plan into the
   goal's issue (`docs/experiments.md` section 1).
2. **Options before code.** Run the [`strategist`](../../agents/strategist.md)
   role with the goal and constraints; ask `skill-scout` for the capabilities
   its top options need. Pick by expected gain per costly measurement, and
   record both answers in the goal's issue.
3. **Deterministic core.** Put numbers, constraints and decisions in tested
   code; give a model only reading, writing and choosing among valid options.
   Every behaviour change becomes a named switch, off by default.
4. **Lab, when real measurements are scarce.** Record real interactions, fit
   simulators of the environment and what it talks to, add generated variants,
   split train and held-out scenarios, and report the must-be-zero counts. Add
   the stress tests (hung calls, caps, a dependency that stops answering,
   parallel load) before the first tuning.
5. **Ledger.** Create `experiments/ledger.md`; each row names hypothesis,
   change, commit, tier, cases, lab prediction, result and verdict. A run whose
   result others will rely on starts with `make pull-first`.
6. **Loop.** One change per experiment, cheapest deciding tier first (offline
   replay, lab, sandbox, then costly real; real runs only on the cases the
   replay shows changing), judged by the paired verdict. Promote a switch only
   when the held-out lab and a real confirmation agree. After three experiments
   without a gain, stop and rerun step 2 with the results so far and prior art.
7. **Learnings.** Move each durable finding into its owner doc with a
   confidence tag (confirmed, computed, reported, hypothesis); mark refuted ones.
8. **Dry run.** Before a run that is hard to undo, run it once under the real
   conditions with the pre-run check of section 8, then make the readiness
   disclosure in `docs/verification.md`.

## Done when

- The local metric matches a real result, and the lab (if built) reports zero
  crashes, invalid actions, broken constraints and timeouts on held-out and
  stress scenarios.
- The ledger shows each promoted switch with its commit and its confirming
  measurement.
- Untested candidates and residual risks are issues the owner has seen.
