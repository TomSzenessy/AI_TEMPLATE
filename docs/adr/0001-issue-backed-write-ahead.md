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
append-only agent event log that would become repository sediment. The tradeoff
is that issue creation/authentication is an operational prerequisite for those
changes; the agent stops at the write-ahead gate when GitHub access is absent.
