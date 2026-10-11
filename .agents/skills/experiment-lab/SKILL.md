---
name: experiment-lab
description: "Experiment simulator and evaluation harness: reaches a measured goal by building a deterministic core and a local simulator first, then one-change experiments on a ledger; Use when success is a score, metric, benchmark, competition, or optimisation against a scarce real evaluator"
---

# Experiment lab

Outcome: the goal's true score rises through measured, reproducible steps, and
scarce real evaluations are spent only to confirm what a free local evaluator
already ranked. Load this when success is a number computed by someone else, or
when real evaluations are limited, slow, or expensive. The rules and their
reasons live in [`docs/experiments.md`](../../../docs/experiments.md); this
skill is the order of work.

## Steps

1. **Objective.** Write the evaluator's formula, the averaging unit and the
   conditions of the run that counts into the project's context doc; implement
   it as a local function and check it against one real result. List every tip
   in the task text as a requirement.
2. **Options before code.** Run the [`strategist`](../../agents/strategist.md)
   role with the goal and constraints; ask `skill-scout` for the capabilities
   its top options need. Pick by expected gain per scarce evaluation.
3. **Deterministic core.** Put numbers, constraints and decisions in tested
   code; give the model only reading, writing and choosing among valid options.
   Every behaviour change becomes a named switch, off by default.
4. **Lab first.** Record a few real interactions, fit twins of the environment
   or counterparts to them, add generated variants, split train and held-out
   scenarios, and report the must-be-zero counts. Add the stress tests (hung
   calls, caps, quitting counterparts, parallel load) before the first tuning.
5. **Ledger.** Create `experiments/ledger.md`; each row names hypothesis,
   change, commit, tier, cases, result and verdict. Commit and push before a run
   whose result matters.
6. **Loop.** One change per experiment, cheapest deciding tier first (offline
   replay, lab, free sandbox, then scarce real). Promote a switch only when the
   held-out lab and a real confirmation agree. After three experiments without
   a gain, stop and rerun step 2 with the results so far, including what
   competitors or prior art published.
7. **Learnings.** Move each durable finding into its owner doc with a
   confidence tag (confirmed, computed, reported, hypothesis); mark refuted ones.
8. **Rehearse.** Run the full real conditions once from the machine and commit
   that will be used, then make the readiness disclosure in
   `docs/verification.md` before the irreversible run.

## Done when

- The local score function matches a real result, and the lab reports zero
  crashes, invalid moves, broken constraints and timeouts on held-out and
  stress scenarios.
- The ledger shows each promoted switch with its commit and its confirming
  measurement, and the rehearsal result is recorded.
- Untested candidates and residual risks are issues the owner has seen.
