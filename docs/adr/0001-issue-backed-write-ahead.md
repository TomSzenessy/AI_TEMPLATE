---
status: accepted
---

# Issue-backed write-ahead record

<!-- index: extend | Accepted write-ahead and documentation-boundary decision | You need the rationale for issue-backed continuity. -->

The repository uses a duplicate-checked GitHub Issue as the durable
write-ahead record for behavior, schema, security, privacy, and operational
changes: the rule and its mechanics are owned by
[`ISSUE_TEMPLATE.md`](../ISSUE_TEMPLATE.md). Durable documents own stable rationale,
runbooks, inventories, and navigation; they do not become a second task/status
board. This keeps cross-session continuity and auditability without an
append-only agent event log that would become repository sediment.

The issue (or the host's equivalent register in `minimal` profile) must exist
before such a mutation. When GitHub access is absent, the agent may perform
read-only discovery and stop at that gate.

GitHub issues are editable, so the issue body is coordination evidence only; a
project that needs temporal proof follows the receipt rules in
[`verification.md`](../verification.md#profile-aware-evidence).
