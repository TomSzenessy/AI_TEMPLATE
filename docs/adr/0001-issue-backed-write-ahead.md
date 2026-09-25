---
status: accepted
---

# Issue-backed write-ahead record

The repository uses a duplicate-checked GitHub Issue as the durable
write-ahead record for behavior, schema, security, privacy, and operational
changes: intent, scope, risks, and acceptance evidence exist before mutation and
are reconciled with the implementation. Durable documents own stable rationale,
runbooks, inventories, and navigation; they do not become a second task/status
board. This keeps cross-session continuity and auditability without an
append-only agent event log that would become repository sediment.

A `Local-WAL: <id>` packet may be used to assemble and validate intent while a
public issue is being prepared, but it is not authorization to implement. The
issue (or the host's equivalent register in `minimal` profile) must exist before
a behavior/schema/security/privacy/operational mutation. When GitHub access is
absent, the agent may perform read-only discovery and stop at that gate.

The issue body is mutable coordination evidence, not an immutable event log. A
project that needs temporal proof should add a redacted pre-change receipt and
bind review evidence to the exact implementation head.
