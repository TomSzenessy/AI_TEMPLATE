# Full audit setup, coverage, and budget

Companion to [`SKILL.md`](SKILL.md), condensed from Cloudflare's
security-audit skill (MIT; see [`ATTRIBUTION.md`](ATTRIBUTION.md)). Read this
before a full audit. The write-isolation procedure itself is repeated verbatim
in [`HUNTING.md`](HUNTING.md) and
[`VALIDATION-AND-REPORTING.md`](VALIDATION-AND-REPORTING.md).

## Setup

Resolve the **skill directory** (the directory holding `SKILL.md`), **target**
repository root, stable **repo name**, **source ref** (reviewed commit, dirty or
clean), and an **output directory** outside the target, defaulting to
`~/security-audit-skill/<repo-name>/run-<N>`. Use a directory inside the
target only when the user explicitly selects it and it is wholly ignored by
version control.

The parent alone writes `run-metadata.json`, `architecture.md`,
`coverage-ledger.json`, `findings.json`, `REPORT.md`, `FINDINGS-DETAIL.md`, and
`NEEDS-VALIDATION.md`. Each hunter or verifier gets a unique lowercase
`<output-dir>/agents/<agent-id>/` with separate `scratch/` and `artifacts/`;
agents and target code may write only to `scratch/`. Retained `artifacts/` is
parent-owned and writable only by trusted parent-side promotion code. Never
use `/tmp` or the host home as a writable fallback.

Follow the descriptor-based, no-follow promotion procedure in
[`HUNTING.md`](HUNTING.md) and
[`VALIDATION-AND-REPORTING.md`](VALIDATION-AND-REPORTING.md). If any check
cannot be enforced, discard the scratch entry; if it is decisive evidence,
retain `needs_validation` with the exact promotion blocker.

Record the reproduction command, exact input, sandbox limits, and only
allowlisted environment variable names with safe non-secret values. Never
capture the ambient environment or credentials. `run-metadata.json` carries
`run_id`, `repo`, `target`, `source_ref`, `profile`, `scope_paths`, `budget`,
`execution_policy`, selected companions, prior-run paths, owners, and
`run_status`.

## Coverage and prior runs

No one pass is complete. Build a deterministic coverage plan before hunting,
update it after every result, and let the parent alone update the ledger;
units and critic waves are defined in [`RECONNAISSANCE.md`](RECONNAISSANCE.md)
and [`HUNTING.md`](HUNTING.md).

Read compatible prior ledgers and findings first. A prior ref is not proof a
path is unchanged: compare current source. Carry a prior `confirmed` record
only when its source and conditions are unchanged and its evidence still meets
this contract; link it to a current `planned` unit, keep its fingerprint,
exclude only that root cause from hunters, and re-verify it. Changed source
becomes a planned revalidation unit. Prior `needs_validation`, `deferred`,
`blocked`, and `out_of_scope` units are current work; a prior `rejected`
record suppresses only the unchanged failed claim. A `quick` or scoped prior
ledger contributes only its evidence and gaps.

## Profiles

`quick` coarsens units to surface × boundary × attack class (subsystem uses
`profile/quick/all-in-scope-subsystems`), runs one hunter wave and one final
coverage-critic pass, and uses one fresh verifier per candidate for validation
and final verification; accepted discoveries are `deferred`. `standard` is the
workflow as written. `deep` splits units per subsystem and lifecycle mode,
runs critic waves to a clean pass, keeps candidate validation and final
verification as separate fresh agents, and gives `prior_covered_same_source`
an independent second pass. A **scoped run** records everything outside the
named paths/subsystem/diff as `out_of_scope`, never `covered`, and presents
itself as partial.

## Severity anchors

Only `confirmed` records receive severity, and severity cannot exceed
demonstrated impact.

- **critical**: unauthenticated code execution, full data-store access, or
  takeover of arbitrary accounts.
- **high**: fully defeats an explicit control with real consequences
  (authentication bypass, cross-tenant read/write, stored script execution
  affecting other users, authenticated code execution, unauthenticated remote
  stop of a shared service).
- **medium**: a real boundary violation with limited blast radius, uncommon
  preconditions, or narrow resource scope.
- **low**: disclosure of non-secret internals, or minimal gain for sustained
  effort.
- **informational**: confirmed but minimal; useful as a prerequisite in a
  larger finding.

The high/medium discriminator: does the result fully defeat an explicit control
for an action with real consequences, or only weaken it? If you cannot state
the concrete damage, severity is lower than it feels.

## Cost budget

One unit is roughly one hunter assignment; a surviving candidate is one or two
verifier assignments. Record the user's maximum agent invocations. Before
reconnaissance, reserve the four baseline recon calls, the required post-wave
critic(s), and at least one verifier. If that minimum cannot be funded, launch
no agent: ask for a larger budget, narrower scope, or another profile; if
unchanged, set `run_status: "incomplete"` with
`budget_cannot_fund_reconnaissance_and_reserves` and report that no pass ran.

Reserve critics and validation before hunting; never assign hunters into a
reserve. If a later wave cannot cover them, launch no hunters, mark units
`deferred` with `budget_cannot_reserve_critics_and_validation`, and record the
gap with the retained final critic. If validation budget runs out, stop
hunting, validate in fingerprint order, set `incomplete` with
`validation_budget_exhausted`, keep unvalidated fingerprints linked to
`candidate` units, and never report complete.
