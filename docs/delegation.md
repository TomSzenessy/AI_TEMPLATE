# Delegation: orchestrator and subagents

<!-- covers: .agents/agents/** -->

Large projects outgrow one context window. The orchestrator keeps the goal,
the acceptance bar, and the decisions; bounded work goes to fresh subagents
whose short reports replace pages of raw reads. This document owns the brief
and report contract that every role in [`.agents/agents/`](../.agents/agents/)
follows. Hosts receive generated adapters (`make adapters`); the role files are
the only copy of the instructions.

## When to delegate

Delegate when the work is **bounded** (one question or one deliverable),
**separable** (needs no running conversation), and **checkable** (has an
observable result). Typical triggers:

| Situation | Role | Why it is cheaper |
|---|---|---|
| "Where/how does X work?" needs more than ~3 file reads | `scout` (fast tier) | A 200-word map replaces thousands of tokens of reads. |
| Two or more deliverables with disjoint paths | `implementer` per deliverable | Parallel work; each context holds one problem. |
| Completion claim on `high` risk or subjective work | `critic` (deep tier) | A fresh context cannot rationalize its own work. |
| Current API, platform rule, or unknown error message | `researcher` | Primary sources with versions, no memory guesses. |
| `make garden` or the stop gate reports doc drift | `doc-gardener` (fast tier) | Docs stay true without derailing the main task. |
| A capability seems missing | `skill-scout` | Overlap check and vetting before anything is added. |

Do the work yourself when it is a one-file change, needs the conversation's
nuance, or the brief would be longer than the work.

## The brief (orchestrator → subagent)

```text
Role: <scout | implementer | critic | researcher | doc-gardener | skill-scout>
Goal: <one sentence; the user-visible outcome this serves>
Question or deliverable: <exactly one>
Scope: <paths / systems allowed>; Out of scope: <explicit non-goals>
Context: <issue link, decisions already made, relevant file:line pointers>
Done when: <observable check: command, artifact, or answer shape>
Report: the role's format, within its word limit
```

Give the subagent pointers, not pasted files: it can read them itself.

## The report (subagent → orchestrator)

Each role file defines its exact format and word limit. Shared rules: claims
cite `path:line`, commands, or URLs; unknowns are listed rather than guessed;
no raw dumps; residual work is named so the orchestrator can file it.

## Model tiers and cost

Role frontmatter declares `tier: fast | balanced | deep | inherit` and
`access: read-only | docs-only | web | full`. Adapters map these to host
models and tool limits (for Claude Code: fast=haiku, balanced=sonnet,
deep=opus). Spend deep tiers on judgment (critique, architecture), fast tiers
on lookup and upkeep.

## Parallelism

Run subagents in parallel only when their write scopes are disjoint;
implementers that might touch the same files work sequentially or in separate
git worktrees. Merge results through the orchestrator, then run `make finish`
and `make verify` once on the combined change.

## Adding or changing a role

Add a role only for a recurring task with a distinct trigger, tool boundary,
and report shape; check `make skill-overlap TEXT="..."` first. Edit the
canonical file, run `make adapters`, and keep this table current.
