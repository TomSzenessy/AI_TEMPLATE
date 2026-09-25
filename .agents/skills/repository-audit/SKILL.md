---
name: repository-audit
description: Use for whole-repository quality, dead-code, scalability, maintainability, security, or privacy audits that should produce prioritized issues instead of an unrequested rewrite.
---

# Repository audit

Use this skill for a broad review. Do not silently implement the audit while
discovering it.

## Procedure

1. Read `AGENTS.md`, `project.toml`, `docs/README.md`, the error ledger, and
   scoped instructions. Inventory tracked product, config, test, documentation,
   and creative files; record scope and exclusions.
2. Partition by surface and concern. Use independent agents for disjoint
   partitions when available, then reconcile coverage against the inventory.
3. Reproduce bugs and performance claims. Separate confirmed causes from
   hypotheses and mark inaccessible provider/deployment evidence as a gate.
4. Search existing issues and the error ledger. In the default **report-only**
   mode, return a prioritized coverage/evidence ledger without writing to
   GitHub. When the user explicitly authorizes issue mutation, create one issue
   per independent root cause/owner boundary with reproduction, impact, evidence,
   priority, and acceptance criteria; group repeated symptoms.
5. Keep active security, secret, and personal-data findings in the private route
   defined by `SECURITY.md`. Never make a public issue from an unpatched exploit.
6. Stop at the prioritized report/issue register. Select an issue for
   implementation separately, then use the normal smallest-change and
   quality-loop workflow.
