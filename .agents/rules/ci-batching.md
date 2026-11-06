---
name: ci-batching
description: Batch finished work into one verified change set; keep drafts cheap and never re-run a green result
scope: .github/** docs/collaboration.md
---

# CI batching

Four small PRs cost roughly three full CI runs each: every push, every merge to
the default branch, and every "behind" PR after a sibling merges (#152). Spend
one run on the exact tree that merges instead.

- One branch per coherent change set; keep the PR draft while iterating.
- Run `make done` locally, then `make ready` (default branch merged, one gate,
  one push, `gh pr ready`). It refuses a dirty tree or a failing gate.
- Several finished branches go through `make integrate BRANCHES="a b c"`; one
  integration branch, one gate, one PR carrying every `Fixes #N`.
- Never re-run CI that is already green, and never merge with a required check
  failed, pending, or skipped.
- A draft, a tree-hash reuse, or an unreachable-run classification may skip a
  heavy job; it never removes the check or hides a failed step.
- Prefer runtime secret fixtures over a commit-keyed `.gitleaksignore`
  fingerprint, which a squash merge orphans.
