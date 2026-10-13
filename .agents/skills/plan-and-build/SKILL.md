---
name: plan-and-build
description: Takes a feature or change that spans several files from a vague idea to an approved design, a plan, and a reviewed, merged branch; Use when asked to build or change something non-trivial, requirements are unclear, or the user says "plan this", "let's build X", "brainstorm", "write a spec", or "execute the plan".
---

# Plan and build

Not for: fully specified small fixes (just do them), bugs
([`operations.md`](../../../docs/operations.md)), reviews, UI polish
([`ux-quality`](../ux-quality/SKILL.md)). A new product starts at `product-kickoff`.
If work outgrows its size mid-task, stop and say so.

## 1. Refine the idea (owner dialogue)

Find out what the owner actually wants and why before designing anything.

- Read first (`make where Q="<topic>"`, nearest `AGENTS.md`, issues); never ask
  what the repo can answer.
- Ask **one question per message**, one sentence, open before multiple
  choice ("walk me through the last time this bit you"); a guess they can
  correct often beats a question. Cover: who it is for, success, non-goals and anti-goals,
  prior art, current state, constraints, what would make them wince.
- Think wide privately, then show 2-3 genuinely different
  approaches with trade-offs and your pick (`strategist` role for large goals).
  A labeled throwaway spike is fine; keeping it goes through step 2.
- Surface assumptions as `ASSUMPTIONS: 1..n - correct me now`. Mark every
  guess as yours.
- Several independent capabilities: get a short capability map approved
  (id, responsibility, depends on, build order), then run steps 1-5 per module.
- Play back each understood part in ~250 words, ask what is wrong. Reframe
  vague asks as measurable criteria ("faster" becomes "LCP under 2.5 s").

## 2. Write the design and get it approved

The design is the write-ahead issue, not a new file ([`ISSUE_TEMPLATE.md`](../../../docs/ISSUE_TEMPLATE.md)):
search for duplicates, then `make issue` (a `Local-WAL` draft when there is no
remote). It carries intent and why, goals, non-goals, constraints, the decisions
the owner made (yours marked as yours), evidence-producing acceptance criteria,
risks, and a "Not doing" list. Run `make risk` for the ceremony level
and follow [`verification.md`](../../../docs/verification.md#the-quality-loop).

For a project-size design, have a fresh `critic` read it as the builder would;
sort its questions: already answered, minor (settle, mark as your call), theirs
(ask in ONE message).

**Hard gate:** no product code, scaffolding, or dependency installs until the
owner approves the posted design in a later message ("sounds good" to an idea
is not approval of a description you have not written). End the turn after
posting. Owner opts out of questions: state major how-it-is-made choices in one line, continue.

## 3. Write the plan

Map the files first (each with one responsibility; follow existing patterns).
Then cut tasks (template:
[`references/plan-template.md`](references/plan-template.md)):

- A task = the smallest unit with its own test cycle and review gate; fold
  setup and docs into the task that needs them. Vertical slices (schema + logic
  + surface for one behavior), not horizontal layers. XL (8+ files) is too big.
- Risky slice first; checkpoint (`make done` green) every 2-3 tasks.
- Every task lists exact files, Consumes/Produces signatures, the failing test
  first with real assertion values, and one verification command with its
  expected result. A step is done when exactly one reasonable thing can be
  written from it; "handle edge cases" or "TBD" decides nothing.
- Self-review against the design (checklist in the template); fix inline.

Store the plan as an issue comment (or in the `Local-WAL` draft), checkboxes
ticked as tasks land. Never a tracked backlog file; `make check` rejects those.
Owner confirms the plan.

## 4. Build

First a clean baseline: separate worktree per session
([`collaboration.md`](../../../docs/collaboration.md), never on the default
branch), `make start`, tests green. Tasks in plan order; **per task**:

1. Record `BASE=$(git rev-parse HEAD)`.
2. Dispatch a fresh `implementer` with the
   [brief](../../../docs/delegation.md#the-brief-orchestrator--subagent) fields:
   Goal, one Deliverable, Scope, Out of scope, Context (issue link, task text,
   interfaces earlier tasks produced), Done when (the verification command).
   Pointers, not pasted history. It spawns no subagents; it commits per slice.
3. Read its return block (`Done`/`Verified`/`Residuals`, see
   [`implementer.md`](../../agents/implementer.md)). Residuals touching
   correctness or scope: fix before review. It stopped for missing context:
   answer and redispatch. It could not finish: change something (context, deeper tier,
   smaller task, plan fix), never retry unchanged.
4. **Review in two passes on `git diff BASE..HEAD`**: (a) spec compliance
   against the task text, nothing missing or extra; (b) quality, incl.
   real assertions, simplicity, no weakened checks (`.skip`, loosened
   thresholds, suppressions). Tier scales with diff risk.
   Use the `critic`; at `high` risk its verdict is the final gate.
5. Findings loop: Critical/Important go back to the same implementer, then a
   scoped re-review of the fix diff only; 3 rounds, then a deeper-tier fresh
   implementer, then you rule. Minor ones go on the issue. Never fix in your
   own context or skip the re-review.
6. Tick the task on the issue with the commit range. After compaction trust
   the checklist and `git log`; never re-dispatch ticked tasks.

Small plans (a few mechanical tasks) may run inline: same TDD (watch the test
fail) and ticking, then one fresh `critic` over the whole branch.

**Parallel only if independent:** disjoint write scopes, no shared state or
interface still undefined. Define a shared contract first, then fan out, one worktree each; merge through you, then run `make done` once
on the combination. Related failures or unknown causes are not parallel work.

**Rulings, not stalls.** Decide plan defects and ambiguities yourself, the
design wins; record `Ruling: <what> - <why> - <cost if wrong>` on the issue.
Stop and ask only for: irreversible steps, security-sensitive actions, side
effects outside the worktree (merge, shared push, publish), or a plan so broken
every path is a guess.

## 5. Finish

1. `make done` on the exact tree you will integrate; a stale green does not
   count. Observe the real artifact; update docs you made stale. Failing: stop.
2. One whole-branch `critic` (deep tier) with the design, Rulings, deferred
   minors; one fix wave, one scoped re-check.
3. Confirm the base branch, then offer exactly: merge locally; push and open a
   PR (keep the worktree); keep as is. Integration is the owner's decision.
   Discard or force only on explicit request, after listing what is lost.
4. After merge or push: `make pull-first` before relying on the base,
   `make ci-status` until green. File residuals as issues. List every Ruling
   you made in the final message. Remove only worktrees you made, never `--force`.

## Red flags

| Thought | Reality |
|---|---|
| "Simple, skip the design" | Short is fine; unwritten is not. |
| "I'll offer options to save effort" | Options steer. Let them describe it first. |
| "The implementer self-reviewed" | It never replaces the fresh two-pass review. |
| "One more round" | After the cap the failure is structural; rule it. |
| "Plan is wrong here" | Rule against the design, record it, continue. |
| "Tests passed earlier" | Run them on the tree you integrate. |

Upstream depth: `make upstream ID=superpowers-workflow` lists pinned files (e.g. reviewer brief → code-reviewer.md); fetch only the one your step needs.
