# Operations and incident loop

This repository treats an operational failure as evidence, not as an instruction
to patch the first suspicious line.

## Failure loop

1. **Observe:** capture UTC time, environment/version, exact symptom, affected
   surface, user impact, and redacted logs or traces. Stop secret/personal-data
   spreading.
2. **Search:** inspect [`ERROR_LOG.md`](./ERROR_LOG.md), open/closed issues, and
   recent changes for the same signature. Reuse the existing issue when the
   root cause and acceptance boundary match.
3. **Reproduce:** create the smallest deterministic repro or failing regression
   test. If local reproduction is impossible, file a `status:blocked` issue
   with the blocker, owner, and next experiment.
4. **Diagnose:** separate confirmed cause, contributing factors, and hypotheses.
   Instrument the boundary where the symptom is observable.
5. **Repair:** change one owner at a time, preserve a rollback, and keep the
   regression test.
6. **Verify:** run focused checks, `make verify`, and the real user path or
   artifact. Compare state before/after; a successful request is not proof of
   persistence or deletion.
7. **Reconcile:** add the permanent error-ledger entry, update the issue with
   evidence, and link the PR/commit. A significant failure gets a private
   incident draft through `make incident`; use `PUBLIC_SAFE=1` only after
   redacting and reviewing it for the tracked `docs/incidents/` register.

## Error ledger

[`ERROR_LOG.md`](./ERROR_LOG.md) is a compact, append-oriented record of solved
failure signatures: symptom, root cause, permanent fix, regression evidence, and
remaining operational action. It is not a task list. Do not copy an unresolved
finding there; keep that work in GitHub Issues.

## Safety during incidents

- Incident records are private drafts by default; promotion to tracked
  documentation requires an explicit public-safety review.
- Never paste credentials, access tokens, raw personal data, or full customer
  exports into issues, logs, or handoffs.
- Do not run destructive provider/database operations against production without
  an explicit scope, backup/rollback plan, and authorized operator.
- Treat restart, redeploy, and “clear cache” as hypotheses until the underlying
  state transition is observed.
- A green local test does not prove deployment, provider propagation, hardware,
  or counsel evidence; label evidence types separately.

## Handover during an incident

Use [`handoffs/TEMPLATE.md`](./handoffs/TEMPLATE.md) when the next actor needs
continuation. Include the current reproduction, commands already run, working
tree state, and the exact next diagnostic action—not a transcript.
