---
name: agent-handover
description: Start, resume, or conclude substantial cross-session work while preserving a concise, redacted handover and a concrete next action.
---

# Agent handover

Use this skill when work may cross a session, branch, machine, model, or owner.
For a short self-contained change, use the normal issue and verification loop.

## Start or resume

1. Check directly for root `HANDOVER.md`; read it completely if present.
2. Compare it with the current branch, working tree, manifest, and linked issue.
   Treat the working tree and current repository state as authoritative when
   they disagree.
3. Preserve unrelated uncommitted changes and secrets boundaries.

## While working

Keep the handover limited to state another actor cannot reconstruct from Git:
current goal, decisions, validation, blockers, and the next concrete action.
Reference issues, commits, specs, and ADRs instead of copying them.

## Conclude or pause

1. Copy [`../../../HANDOVER.template.md`](../../../HANDOVER.template.md) to root
   `HANDOVER.md` when a local continuation record is useful.
2. Update every section concisely and remove stale claims.
3. Use [`../../../docs/handoffs/TEMPLATE.md`](../../../docs/handoffs/TEMPLATE.md)
   for a committed cross-machine handoff, then add it to the docs index.
4. State in the final response whether the handover was updated and what remains.
