# Privacy engineering

Privacy is a data-lifecycle property. This document starts the engineering
process; it is not legal advice or a GDPR conformity certificate.

## Data minimization by default

- Do not collect a field because it is convenient. Record purpose, source,
  subject, recipient, retention, access, and deletion path first.
- Keep anonymous, pseudonymous, and personal data distinct. A hash or opaque ID
  can still be personal data when linkable.
- Separate optional analytics/consent from necessary service operation. Never
  infer consent from account creation or bundle use.
- Minimize logs, traces, error payloads, uploads, backups, and support exports;
  redact at the boundary and bound retention.
- Treat free-form content, names, IDs, IP addresses, device data, payment
  metadata, and user-generated media as potentially sensitive.

## Rights and lifecycle

For every personal-data class, define a testable path for access/export,
correction, restriction, objection, consent withdrawal where applicable, and
erasure. Track the actual stores, replicas, backups, providers, and delayed jobs;
a database row deletion or HTTP success is not physical deletion evidence.
Record exceptions, owner, trigger, maximum period, and release condition.

## Cookies and browser storage

Inventory every cookie, local/session storage key, pixel, SDK, and third-party
embed by purpose, provider, duration, and whether it is strictly necessary.
Apply the applicable consent/terminal-device rule before optional access or
storage; provide a real withdrawal path. A source search does not prove runtime
behavior—test an authenticated production-like browser.

## Launch gate

Before public launch, the operator and qualified counsel must validate the
actual jurisdiction, controller/operator identity, lawful bases, notices,
provider roles and transfers, retention, rights process, age/minor policy,
cookie behavior, security measures, and any DPIA/DPO/imprint requirements. Mark
each as `pending`, `implemented`, `verified`, or `approved`; do not turn a
source-level default into a legal conclusion.

Use [`legal/data-inventory.md`](./legal/data-inventory.md) for factual inventory
and [`legal/README.md`](./legal/README.md) for the jurisdiction/counsel gate.
External research and source links live in
[`research/agentic-repository-baselines.md`](./research/agentic-repository-baselines.md).
