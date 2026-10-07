# Handoffs

<!-- index: operate | Cross-session continuity rules | Work must be transferred or resumed. -->

Use a handoff only when a fresh human or agent must continue work across a
session, model, machine, or ownership boundary. It is a continuation record,
not a transcript or a second task register.

The one schema is [`TEMPLATE.md`](./TEMPLATE.md). For an active local session,
run `make handover`: it writes the ignored root `HANDOVER.md` from this
template with the time, branch, commit, uncommitted paths, and owed documents
already filled in, so only judgment (objective, decisions, next action) is left
to write. Hosts print it in the next session brief. For a handoff that must
survive the checkout, create
`docs/handoffs/YYYY-MM-DD-HHMM-<slug>.md` from [`TEMPLATE.md`](./TEMPLATE.md),
link it from [`../README.md`](../README.md), and reference the issue, commits,
ADRs, and tests rather than copying their content. Redact secrets and personal
data, state the sharing boundary, and delete or archive stale handoffs when the
work is complete.

A good handoff lets the next actor take one useful action without the original
conversation. A bad handoff restates the repository, assumes shared context, or
claims verification that was not run.
