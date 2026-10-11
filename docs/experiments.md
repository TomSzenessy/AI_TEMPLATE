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
Compute that score locally from the evaluator's own definition. A proxy (a
practice board that keeps your best result per case, a demo, a vibe) is
labelled as a proxy everywhere it appears; compare yourself with others only
under the same condition (single attempt against single attempt).

Read the task text for tips ("build your own simulator", "read the notes",
"test on the sample set first"): each one is a requirement until a measurement
says otherwise.

## 2. Deterministic core, model at the edges

Numbers, constraints, scoring and every decision that can be computed live in
code you can test; a language model reads unstructured input, writes text, and
chooses among options code has already made valid. Each behaviour change is a
named switch, off by default, with a one-line comment giving the measurement
that justified it. Then a version is reproducible from its commit and its
switches, and an experiment changes one of them.

## 3. The evaluation ladder

Spend the cheapest evaluation that can decide the question:

| Tier | What | Use for |
|---|---|---|
| offline | the scoring function on candidate outputs; replays of recorded sessions | arithmetic, "which cases would this change touch?" |
| local lab | a simulator of the environment you build (section 4) | ranking variants, crashes, limits, timing |
| free sandbox | the real system's free or demo mode, if any | behaviour of the real counterpart |
| scarce real | the counted evaluations | confirming a lab winner; the rehearsal |

Budget the scarce tier up front, keep a reserve for a full rehearsal under the
real conditions, and log what each spend bought.

## 4. The local lab

Build it in the first hours, not the last: it pays for itself the first time a
change would otherwise be tested on the real evaluator.

- **Twins**: counterparts or environments fitted to recorded real interactions
  (their rules, thresholds, timing), plus generated variants beyond them, so
  the lab covers cases you have not seen.
- **Held-out split**: tune on one set of scenarios, rank on another; a large gap
  between them means the variant fits the lab, not the task.
- **Must-be-zero counts** in every report: crashes, refused or invalid actions,
  broken constraints, results worse than doing nothing, runs out of time.
- **Stress tests**: hung and slow calls, rate limits, hard time caps, a
  counterpart that quits or never answers, malformed input, many runs in
  parallel as in the real event. Every timeout and retry budget must fit inside
  the deadline that encloses it ([`engineering.md`](./engineering.md#time-budgets)).
- **Search**: let the lab sweep switches and parameters; a lab winner is a
  hypothesis until a higher tier confirms it.

## 5. Experiments and the ledger

One change against a matched baseline, same inputs and seeds; when the real
system is deterministic for identical inputs, use that for exact pairs, and
repeat noisy ones before believing a difference. Record every experiment,
including the ones that failed, in the project's ledger
(`experiments/ledger.md`): hypothesis, change, commit (pushed, clean tree),
tier, cases, result, verdict, follow-up. A result without its commit cannot be
reproduced or restored; tag the best version so it can be found.

**Plateau rule:** three experiments in a row without a measured gain on the
true objective means stop tuning and run the strategist role.

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
that will run it); then follow the readiness disclosure in
[`verification.md`](./verification.md#before-completion).
