# Experiments

<!-- index: operate | Score-driven goals: true objective, evaluation ladder, local lab, experiment ledger | A goal is a measured score or metric, or real evaluations are scarce -->
<!-- covers: .agents/skills/experiment-lab/** -->

Use this page when success is a number someone else computes: a benchmark, a
competition, a conversion rate, a model metric, a cost to minimise. The
[`experiment-lab`](../.agents/skills/experiment-lab/SKILL.md) skill sequences
it; the [`strategist`](../.agents/agents/strategist.md) role supplies options.
The failure this page prevents: many rounds of the same kind of change (prompt
wording, a constant, one more rule) tested one at a time against a scarce real
evaluator, while the approach that would win is never built.

## 1. The objective, exactly

Write down, before any code: the formula the real evaluator applies, the unit
it averages over, and the conditions of the run that counts (one attempt or
best of many, known or hidden cases, time and rate limits, what ends a run).
Compute that score locally from the evaluator's own definition, and read the
evaluator's exact checks (which inputs it verifies, which it ignores) before
building anything that depends on them. A proxy (a
practice board that keeps your best result per case, a demo, a vibe) is
labelled as a proxy everywhere it appears; compare yourself with others only
under the same condition (single attempt against single attempt).

Rebuild the evaluator's checks locally (which outputs it rejects, which
figures it verifies) and run every output through them; a test asserts zero
rejections. Condense the task brief into one context doc the agents always
load (rules, scoring, limits, the clock, what disqualifies, how to submit),
each fact linked to its source; the source wins over the summary, and a
source that changes is re-read.

Read the task text for tips ("build your own simulator", "read the notes",
"test on the sample set first"): each one is a requirement until a measurement
says otherwise.

**The plan** lives in the goal's issue: where the points are, ranked with
evidence; the parts, each with an owner, its paths, and a fixed interface
(stubbed within the first hour, so parts integrate early); what you will not
do; a timeline to the deadline with your own freeze an hour before the
external one; the scarce budget with its reserve; the risks.

## 2. Deterministic core, model at the edges

Numbers, constraints, scoring and every decision that can be computed live in
code you can test; a language model reads unstructured input, writes text, and
chooses among options code has already made valid
([`model-integration.md`](./model-integration.md)). Each behaviour change is a
named switch, off by default, with a one-line comment giving the measurement
that justified it. Then a version is reproducible from its commit and its
switches, and an experiment changes one of them. A test proves that with
every switch off the system makes exactly the base decision on every recorded
state, and a seam test pins the base behaviour a layer overrides.

## 3. The evaluation ladder

Spend the cheapest evaluation that can decide the question:

| Tier | What | Use for |
|---|---|---|
| offline | the scoring function on candidate outputs; replays of recorded sessions | arithmetic, "which cases would this change touch?" |
| local lab | a simulator of the environment you build (section 4) | ranking variants, crashes, limits, timing |
| free sandbox | the real system's free or demo mode, if any | behaviour of the real counterpart |
| scarce real | the counted evaluations | confirming a lab winner; the rehearsal |

Budget the scarce tier up front, keep a reserve for a full rehearsal under the
real conditions, and log what each spend bought. Every script that spends a run whose result
matters starts with `make pull-first`: it refuses a dirty or unpushed tree and
pulls new commits (exit 3: restart on the new code), because a result measured
on code nobody else has cannot be reproduced or credited.

Encode the task's rules (forbidden calls, freezes, rate and size limits) as
guards and tests in the code, so no variant can break them by accident.
Derived data (built tables, fitted parameters, indexes) gets a pass/fail
suite: two builds are byte-identical, committed copies are current, an
independent recomputation agrees, and a simulated future release still loads.
Shared keys, quotas, and rate limits follow
[`collaboration.md`](./collaboration.md#shared-resources).

## 4. The local lab

Build it in the first hours, not the last: it pays for itself the first time a
change would otherwise be tested on the real evaluator.

- **Twins**: counterparts or environments fitted to recorded real interactions
  (their rules, thresholds, timing), plus generated variants beyond them, so
  the lab covers cases you have not seen. Backtest each twin reply by reply
  against the recordings and report its error; fit a family of plausible
  parameters and sample from it rather than one best fit; keep one strategy
  out of the fit, so its lab score is an honest prediction.
- **Edge suite**: generated scenarios tagged by the edge case they force, each
  tag run several times, deterministic per seed.
- **Held-out split**: tune on one set of scenarios, rank on another; a large gap
  between them means the variant fits the lab, not the task.
- **Must-be-zero counts** in every report: crashes, refused or invalid actions,
  broken constraints, results worse than doing nothing, runs out of time.
- **Stress tests**: hung and slow calls, rate limits, hard time caps, a
  counterpart that quits or never answers, malformed input, many runs in
  parallel as in the real event. Every timeout and retry budget must fit inside
  the deadline that encloses it ([`engineering.md`](./engineering.md#time-budgets)).
  Run the production runner itself against the lab, with every timing in one
  settings object scaled down for the tests.
- **Search**: let the lab sweep switches and parameters (successive halving:
  drop the weaker half each round), with about 15% of the time reserved to
  rescore the finalists on the held-out set; a lab winner is a hypothesis until
  a higher tier confirms it.
- **Long runs** run detached and write a folder (report, best settings, one row
  per unit, a progress log) that a status and a stop command read; a report
  whose time ran out marks itself inconclusive.
- **A model-played tier**: when the real counterpart reads language, add a lab
  mode where a model plays it inside the fitted limits; use it to check
  finalists and wording, not for searches (it is slow and costs money).
- **Model choice**: run the same scenarios with each candidate model and keep
  the cheapest one that matches the best score and latency.

## 5. Experiments and the ledger

One change against a matched baseline, same inputs and seeds; when the real
system is deterministic for identical inputs, use that for exact pairs, and
repeat noisy ones before believing a difference. Record every experiment,
including the ones that failed, in the project's ledger
(`experiments/ledger.md`): hypothesis, change, commit (pushed, clean tree),
tier, cases, result, verdict, follow-up. A result without its commit cannot be
reproduced or restored; tag the best version `best-<branch>-<score>`. To
restore one, branch from it (`git switch -c restore-<hash> <hash>`) or revert
the commits after it; never `reset --hard` shared history.

- **Replay first.** Before spending real runs on a variant, replay the recorded
  sessions through it offline: spend real runs only on the cases whose outputs
  change; a case that sends identical outputs keeps its old score.
- **Paired verdict.** Report the mean of per-case differences with its standard
  error: adopt above +2 SE, reject below -2 SE, otherwise a tie (keep the
  simpler version).
- **Lab against real.** The ledger has a "lab predicted" column next to the
  real result; trust the lab's paired differences, not its levels, and fix the
  twins when the two disagree in sign.
- **Headroom.** Before choosing the next experiment, list per case how far the
  result is from the best possible and which parameter holds the gap.
- **Archive.** Keep every real evaluation in full (raw record, readable
  summary, commit, an index), and read the archive before spending a new run.
- **Unattended agents** get an explicit stop condition (a budget floor, a
  deadline, a number of experiments) written in the goal's issue.

**Plateau rule:** three experiments in a row without a measured gain on the
true objective means stop tuning and run the strategist role; record its answer
in the goal's issue.

With several people or agents, each builds a competing variant on its own branch
and claims it in the goal's issue (assignee, `status:in-progress`); the team
picks by measured results named by commit, not by argument.

## 6. Learnings

A finding that should change behaviour goes into the owner doc of what it
describes, with a confidence tag: **confirmed** (seen in a recorded real run),
**computed** (follows from the scoring function), **reported** (documentation,
other teams, papers), **hypothesis** (not yet tested). Mark refuted findings as
refuted with the experiment that refuted them, or delete them.

## 7. Prior art

At goal start and at every plateau, look at what others published for the same
problem (public repositories, write-ups, papers, competitors' notes) and adopt
nothing until your own lab or real tier confirms it. Reading the winners at the
end is too late to learn from them.

## 8. Before the run that counts

Rehearse under the real conditions (parallelism, load, time caps, the machine
that will run it). Write a preflight script for that machine and run it before
the start: `make pull-first`, branch and commit to submit, required tools and
keys (presence only, never printed), data in place, network and the provider
reachable with one cheap call, remaining quota, a grep for forbidden calls,
the tests, one free end-to-end run, power and sleep settings, and the exact
start command; each line prints ok, WARN or FAIL. Then follow the readiness
disclosure in [`verification.md`](./verification.md#before-completion).
