# Delegation: orchestrator and subagents

<!-- index: operate | Orchestrator/subagent roles, brief and report contract | Work is bounded enough to hand to a scout, implementer, critic, researcher, doc-gardener, or skill-scout. -->
<!-- covers: .agents/agents/** -->

Large projects outgrow one context window. The orchestrator keeps the goal,
the acceptance bar, and the decisions; bounded work goes to fresh subagents
whose short reports replace pages of raw reads. This document owns the brief
and report contract that every role in [`.agents/agents/`](../.agents/agents/)
follows. Hosts receive generated adapters (`make sync`); the role files are
the only copy of the instructions.

## When to delegate

Delegate when the work is **bounded** (one question or one deliverable),
**separable** (needs no running conversation), and **checkable** (has an
observable result). Typical triggers:

<!-- repoctl:roles -->
| Role | Access, tier | Use it when |
|---|---|---|
| [`critic`](../.agents/agents/critic.md) | read-only, deep | Fresh, read-only reviewer that tries to falsify a completion claim against the original acceptance criteria, the diff, and the real artifact. Use before declaring high-risk or subjective work done. |
| [`doc-gardener`](../.agents/agents/doc-gardener.md) | docs-only, fast | Docs-only maintainer. Fixes stale or dead doc bindings, broken command references, and navigation drift reported by make garden or the stop gate, so documentation keeps matching what the code actually does. |
| [`implementer`](../.agents/agents/implementer.md) | full, balanced | Builds one bounded deliverable from a brief - smallest coherent change, tests first for bugs, owning docs updated in the same change, verified with the declared commands. Use for disjoint, well-specified work packages. |
| [`researcher`](../.agents/agents/researcher.md) | web, balanced | Answers an external-knowledge question (current library APIs, platform rules, prior art, error messages) from primary sources using web search, docs MCP servers, and a browser, returning cited, version-specific findings. |
| [`scout`](../.agents/agents/scout.md) | read-only, fast | Read-only locator. Use before reading many files yourself - finds where something lives, who owns it, how it is wired, and what broke there before, then returns a short map with file:line evidence. |
| [`skill-scout`](../.agents/agents/skill-scout.md) | web, balanced | Finds and vets a missing capability (skill, MCP server, or tool) without installing it - checks overlap with existing skills first, inspects candidates for provenance and risk, and returns a ready-to-review provenance entry or a reuse recommendation. |
<!-- /repoctl:roles -->

The table is generated from each role's frontmatter by `make sync`, so a role
added with `make new KIND=agent` appears here automatically. Rules of thumb: a
scout replaces more than ~3 file reads with a 200-word map; implementers run in
parallel only on disjoint paths; a critic is mandatory at `high` risk because a
fresh context cannot rationalize its own work.

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
git worktrees. Merge results through the orchestrator, then run `make done`
once on the combined change.

## Adding or changing a role

Add a role only for a recurring task with a distinct trigger, tool boundary,
and report shape: `make new KIND=agent NAME=<name> DESC="<job; when to use>"`
refuses near-duplicates, writes valid frontmatter, and regenerates the host
adapters and the table above. Replace its `FILL-IN:` lines, then `make done`.
