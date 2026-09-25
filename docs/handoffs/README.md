# Handoffs

Use a handoff only when a fresh human or agent must continue work across a
session, model, machine, or ownership boundary. It is a continuation record,
not a transcript or a second task register.

For an active local session, copy the root [`../../HANDOVER.template.md`](../../HANDOVER.template.md)
to the ignored root `HANDOVER.md`. For a handoff that must survive the checkout
or cross machines, create `docs/handoffs/YYYY-MM-DD-HHMM-<slug>.md` from
[`TEMPLATE.md`](./TEMPLATE.md), link it from [`../README.md`](../README.md), and
reference the issue, commits, ADRs, and tests rather than copying their content.
Redact secrets and personal data, state the sharing boundary, and delete or
archive stale handoffs when the work is complete.

A good handoff lets the next actor take one useful action without the original
conversation. A bad handoff restates the repository, assumes shared context, or
claims verification that was not run.
