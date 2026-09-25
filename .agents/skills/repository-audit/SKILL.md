---
name: repository-audit
description: Use for whole-repository quality, dead-code, scalability, maintainability, security, or privacy audits that should produce prioritized issues instead of an unrequested rewrite.
---

# Repository audit

This skill is the host invocation adapter. Read the canonical procedure in
[`../../../docs/audit.md`](../../../docs/audit.md) and the repository inventory
before starting a broad review.

Keep the skill invocation short:

1. State scope, exclusions, and whether issue mutation is authorized.
2. Partition by surface/concern, reconcile coverage against the inventory, and
   reproduce claims before ranking them.
3. Stop at the report/issue register. Never silently implement the audit.
4. Keep active security, secrets, and personal data on the private route.

Do not copy the protocol here; [`docs/audit.md`](../../../docs/audit.md) is its
single source of truth.
