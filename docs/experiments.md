# Experiments

<!-- index: operate | Measured goals: true objective, evaluation ladder, local lab, experiment ledger | A goal is a measured score or metric, or real evaluations are slow, costly, or limited -->
<!-- covers: .agents/skills/experiment-lab/** -->

Use this page when success is a number: a model metric, a benchmark, a
latency or cost target, a conversion rate in an A/B test, a ranking on a
leaderboard. The [`experiment-lab`](../.agents/skills/experiment-lab/SKILL.md)
skill sequences it; the [`strategist`](../.agents/agents/strategist.md) role
supplies options. The failure this page prevents: many rounds of the same kind
of change (a prompt's wording, a constant, one more rule) tried one at a time
against a slow or expensive real measurement, while the approach that would
work is never built.

**Scale it to the goal.** A small one (tune a query, speed up a page) needs
sections 1, 2, and 5. Build the lab of section 4 when real measurements are
slow, costly, rate-limited, or risky; use section 8 before a run whose result
is hard to undo.

## 1. The objective, exactly

Write down, before any code: the formula that computes the number, the unit it
averages over, and the conditions of the measurement that matters (one attempt
or best of many, known or hidden cases, time and rate limits, what ends a run).
Compute it locally from its own definition, and read the evaluator's exact
checks (which inputs it verifies, which it ignores) before building anything
that depends on them. A proxy (a leaderboard that keeps your best submission, a
demo, a staging metric, a vibe) is labelled as a proxy wherever it appears;
compare results only under the same condition.

Where an external evaluator rejects outputs (a validator, an API's schema, a
grader), rebuild its checks locally, run every output through them, and keep a
test that asserts zero rejections. When the goal comes with a written brief
(a task statement, a spec, a client's requirements), condense it into one
context doc the agents load (rules, the metric, limits, deadlines, what is out
of bounds), each fact linked to its source; the source wins over the summary
and is re-read when it changes. Tips in the brief ("test on the sample set
first") are requirements until a measurement says otherwise.

**The plan** lives in the goal's issue: where the gains are, ranked with
evidence; the parts, each with an owner, its paths, and a fixed interface
(stubbed early, so parts integrate early); what you will not do; a timeline
with your own cut-off before any external deadline; the budget of real
measurements with a reserve; the risks.

## 2. Deterministic core, model at the edges

Numbers, constraints, scoring and every decision that can be computed live in
code you can test; a language model reads unstructured input, writes text, and
chooses among options code has already made valid
([`model-integration.md`](./model-integration.md)). Each behaviour change is a
named switch, off by default, with a one-line comment giving the measurement
that justified it. Then a version is reproducible from its commit and its
switches, and an experiment changes one of them. A test proves that with every
switch off the system makes exactly the base decision on every recorded input,
and a seam test pins the base behaviour a layer overrides.

## 3. The evaluation ladder

Spend the cheapest evaluation that can decide the question:

| Tier | What | Use for |
|---|---|---|
| offline | the scoring function on candidate outputs; replays of recorded inputs | arithmetic, "which cases would this change touch?" |
| local lab | a simulator or test harness of the environment (section 4) | ranking variants, crashes, limits, timing |
| free sandbox | the real system's free, staging, or demo mode, if any | behaviour of the real system |
| costly real | production traffic, paid API runs, official submissions | confirming a lab winner; the dry run |

Budget the costly tier up front, keep a reserve for a full dry run under the
real conditions, and log what each spend bought. A run whose result others will
rely on starts with `make pull-first` ([`collaboration.md`](./collaboration.md)):
a result measured on code nobody else has cannot be reproduced or credited.

Encode the goal's hard rules (forbidden calls, rate and size limits, freezes)
as guards and tests, so no variant breaks them by accident. Derived data
(built tables, fitted parameters, indexes) gets a pass/fail suite: two builds
are byte-identical, committed copies are current, an independent recomputation
agrees, and a simulated future input still loads.

## 4. The local lab

Build it early when real measurements are scarce: it pays for itself the first
time a change would otherwise be tried on the real system.

- **Simulators**: the environment and whatever it talks to (users, an API,
  another service or agent), fitted to recorded real interactions (their
  rules, thresholds, timing), plus generated variants beyond them. Backtest
  each against the recordings step by step and report its error; fit a family
  of plausible parameters and sample from it; keep one variant out of the fit,
  so its lab score is an honest prediction.
- **Held-out split**: tune on one set of scenarios, rank on another; a large gap
  means the variant fits the lab, not the goal.
- **Edge suite**: generated scenarios tagged by the edge case they force, each
  tag run several times, deterministic per seed.
- **Must-be-zero counts** in every report: crashes, invalid actions, broken
  constraints, results worse than doing nothing, timeouts.
- **Stress tests**: hung and slow calls, rate limits, hard time caps, a
  dependency that stops answering, malformed input, parallel load. Every
  timeout and retry budget fits inside its deadline
  ([`engineering.md`](./engineering.md#time-budgets)). Run the production code
  path itself against the lab, with every timing in one settings object scaled
  down for tests.
- **Search**: let the lab sweep switches and parameters (successive halving:
  drop the weaker half each round), with some time reserved to rescore the
  finalists on the held-out set; a lab winner is a hypothesis until a higher
  tier confirms it.
- **Long runs** run detached and write a folder (report, best settings, one row
  per unit, a progress log) that a status and a stop command read; a report
  whose time ran out marks itself inconclusive.
- **A model-played tier**: when the real system responds to language, add a
  lab mode where a model plays it within the fitted limits; use it to check
  finalists, not for searches (slow and paid). Choose the model by running the
  same scenarios with each candidate and keep the cheapest that matches.

## 5. Experiments and the ledger

One change against a matched baseline, same inputs and seeds; repeat noisy
measurements before believing a difference. Record every experiment, including
failures, in the project's ledger (`experiments/ledger.md`): hypothesis, change,
commit (pushed, clean tree), tier, cases, lab prediction, result, verdict,
follow-up. Tag the best version `best-<branch>-<score>`; restore one by
branching from it (`git switch -c restore-<hash> <hash>`) or reverting what came
after, never `reset --hard` on shared history.

- **Paired verdict.** Report the mean of per-case differences with its standard
  error: adopt above +2 SE, reject below -2 SE, otherwise a tie (keep the
  simpler version).
- **Replay first.** Before spending real runs on a variant, replay recorded
  inputs through it offline and spend real runs only on the cases whose outputs
  change.
- **Lab against real.** Trust the lab's paired differences, not its levels;
  fix the simulators when lab and real disagree in sign.
- **Headroom.** Before choosing the next experiment, list per case how far the
  result is from the best possible and what holds the gap.
- **Archive.** Keep every costly evaluation in full (raw record, summary,
  commit, an index) and read the archive before spending a new one.
- **Unattended agents** get an explicit stop condition (a budget floor, a
  deadline, a number of experiments) written in the goal's issue.

**Plateau rule:** three experiments in a row without a measured gain on the
true objective means stop tuning and run the strategist role; record its answer
in the goal's issue. With several people or agents, each builds a competing
variant on its own branch and claims it; pick by measured results named by
commit, not by argument.

## 6. Learnings

A finding that should change behaviour goes into the owner doc of what it
describes, with a confidence tag: **confirmed** (seen in a real measurement),
**computed** (follows from the scoring function), **reported** (documentation,
other people, papers), **hypothesis** (not yet tested). Mark refuted findings as
refuted with the experiment that refuted them, or delete them.

## 7. Prior art

At goal start and at every plateau, look at what others published for the same
problem (papers, public repositories, write-ups, benchmarks) and adopt nothing
until your own lab or real tier confirms it.

## 8. Before a run that is hard to undo

A release, a migration, a paid batch, an official submission, a demo: rehearse
under the real conditions (load, parallelism, time limits, the machine or
environment that will run it). For a recurring one, write a pre-run check that
prints ok, WARN or FAIL per line: `make pull-first`, the commit to run, required
tools and keys (presence only, never printed), data in place, the network and
providers reachable with one cheap call, remaining quota, the tests, one cheap
end-to-end run, and the exact start command. Then follow the readiness
disclosure in [`verification.md`](./verification.md#before-completion).
