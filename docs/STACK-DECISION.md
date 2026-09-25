# Stack decision record

Status: accepted for AI_TEMPLATE (no product framework)
Project: AI_TEMPLATE

## Decision

AI_TEMPLATE uses Python 3.11+ standard-library `repoctl` for its governance
core. It does not select a web, game, native, media, or data framework for a
future project. A copied project must make its own decision after vision intake.

## Decision criteria

- Fit the declared product outcome and constraints.
- Smallest dependency and operational surface that can prove the outcome.
- Ecosystem maturity, security/maintenance signals, and team/agent competence.
- Real artifact verification and a reversible migration seam.
- Provider/deployment fit and a clear rollback path.

## Options considered

For a website, compare the actual needs before choosing among static/Astro,
React/Next, and other options; do not select from popularity alone. For games,
native, media, and data, compare the domain toolchain and artifact oracle rather
than forcing the website matrix.

## Confirmation

Owner: TomSzenessy
Date: 2026-08-25
Human confirmation: the template should recommend, then confirm high-impact
choices.

## Rule

Record one decision per project in the issue-backed WAL and update this file (or
replace it in the project copy) before scaffolding. A copied project changes the
status to `pending` until its owner confirms a decision.
