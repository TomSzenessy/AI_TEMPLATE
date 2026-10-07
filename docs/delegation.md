# Delegation: orchestrator and subagents

<!-- index: operate | Orchestrator/subagent roles, brief, return, and critic verdict contract | Work is bounded enough to hand to a scout, implementer, critic, researcher, doc-gardener, or skill-scout. -->
<!-- covers: .agents/agents/** -->

Large projects outgrow one context window. The orchestrator keeps the goal,
the acceptance bar, and the decisions; bounded work goes to fresh subagents
whose short returns replace pages of raw reads. This document owns the brief
and return contract that every role in [`.agents/agents/`](../.agents/agents/)
follows. Hosts receive generated adapters (`make sync`); the role files are
the only copy of the instructions.

## When to delegate

**Delegate when the subtask needs context of its own or gains from
independence** (the critic is the case the independence matters most: a fresh
context cannot rationalize its own work). **Do it directly otherwise** — a
subagent costs a brief, a context, and a round trip, so a one-file change whose
brief would be longer than the change is a net loss.

Within that threshold, delegate work that is **bounded** (one question or one
deliverable), **separable** (needs no running conversation), and **checkable**
(has an observable result). Typical triggers:

<!-- repoctl:roles -->
| Role | Access, tier | Use it when |
|---|---|---|
| [`critic`](../.agents/agents/critic.md) | read-only, deep | Fresh, read-only reviewer that tries to falsify a completion claim against the original acceptance criteria, the diff, and the real artifact. Use before declaring high-risk or subjective work done; returns one verdict, blocker or ship-with-residuals. |
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

## The brief (orchestrator → subagent)

```text
Role: <scout | implementer | critic | researcher | doc-gardener | skill-scout>
Goal: <one sentence; the user-visible outcome this serves>
Question or deliverable: <exactly one>
Scope: <paths / systems allowed>; Out of scope: <explicit non-goals>
Context: <issue link, decisions already made, relevant file:line pointers>
Done when: <observable check: command, artifact, or answer shape>
Return: the role's block, within its word limit
```

Give the subagent pointers, not pasted files: it can read them itself.

Every role file opens its `## Brief` section by naming the fields **it** requires
and what it does when one is missing, so a brief can be filled in without
guessing and a missing field has a defined response (ask once, generate the
packet, or stop and report).

## The return (subagent → orchestrator)

Each role file fixes its own `## Return` block and word limit — a fixed shape,
not prose, so two runs of the same role are comparable. Shared rules: claims cite
`path:line`, commands, or URLs; unknowns are listed rather than guessed; no raw
dumps; residual work is named so the orchestrator can file it.

## The critic's verdict and its evidence

The critic returns exactly one of two words:

- `blocker` — the work is not done; it goes back for a fix and another pass.
- `ship-with-residuals` — done enough to ship; the named residuals follow.

There is no third option, because `accept`, `looks good`, or any other prose
means the same thing at different strengths and cannot be checked. Save the
critic's return block verbatim to `.agent/critic.md` (ignored, so it never rides
along in a commit) with `Commit:` set to the HEAD the critic read.

That record is the evidence the completion gate reads: on committed `high`-risk
paths, `make done` and the stop hook fail without it, fail when the verdict is
`blocker` or any word outside the vocabulary, and fail when `Commit:` is not the
current HEAD — so run the critic **after** the change is committed, then save the
return, then finish ([`self-healing.md`](./self-healing.md#critic-evidence-the-gate-can-read)).

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

Add a role only for a recurring task with a distinct trigger, tool boundary, and
return shape: `make new KIND=agent NAME=<name> DESC="<job; when to use>"`
refuses near-duplicates, writes valid frontmatter, and regenerates the host
adapters and the table above. Replace its `FILL-IN:` lines, give it the `## Brief`
and `## Return` sections every other role has, then `make done`.
