---
name: quality-loop
description: Use for broad, subjective, security-sensitive, creative, or release work that needs bounded builder agents, an independent critic, and real-artifact evidence.
---

# Quality loop

Use this skill when “make it better” needs a measurable quality bar or when a
fresh perspective could catch a mistake the builder cannot see.

## Loop

1. Read the issue, `project.toml`, `AGENTS.md`, and the affected surface's
   quality oracle. Split independent deliverables and name their evidence.
2. Give each builder a disjoint scope, explicit constraints, and a command or
   artifact that proves completion. Do not let builders silently expand scope.
3. Run builders in parallel only when their seams do not conflict.
4. Give a fresh critic the original acceptance criteria, the actual diff/artifact,
   and the validation results. The critic must try to falsify the claim without
   editing first.
5. Fix confirmed blockers, rerun the real oracle, and record the evidence. Use at
   most three focused iterations; turn unresolved disagreement into an issue.

## Domain oracles

Use the repository's declared oracle: browser interaction and accessibility for
web, play/performance traces for games, rendered image/frame inspection for 3D
or video, real persisted state for backends/data, and citation/jurisdiction
review for legal or privacy work. A green command without artifact evidence is
not a quality result.
