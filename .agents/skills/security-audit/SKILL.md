---
name: security-audit
description: Security guidance and vulnerability review for codebases, APIs, services, CLIs, libraries, and daemons. Use for security questions, focused reviews, or vulnerability research. Run the full workflow only for an explicit codebase audit, pen-test, or comprehensive review, or when report artifacts are requested.
---

# Security audit

Find vulnerabilities that violate a real trust boundary, then give owners the
source evidence, safe reproduction, priority, and the smallest effective fix.
A candidate without a concrete affected principal, resource, or security
outcome is not confirmed.

Condensed from [Cloudflare's security-audit
skill](https://github.com/cloudflare/security-audit-skill) (MIT). Companions,
schema, and validators are vendored unchanged; see
[`ATTRIBUTION.md`](ATTRIBUTION.md).

## Operating modes

Guidance is the default; loading this skill does not authorize the full
workflow or file creation.

- **Guidance mode**: for a security question, focused review, methodology,
  triage, or one finding, use only the relevant parts. Do not run all six
  phases, create an output directory, or write audit artifacts. Focused agents
  may run and return results to the current task.
- **Full audit mode**: use all six phases and write the report files only when
  the user explicitly asks to audit or pen-test a codebase, asks for a full,
  comprehensive, or end-to-end review, or requests report artifacts.

If the request could mean either mode, ask one focused question first.
**Parent** coordinates and owns shared state; **Task tool** is the platform's
delegation mechanism; a **research agent** verifies source facts and a
**general agent** investigates broadly with bounded local execution.

## Universal execution safety

Source inspection is read-only. Run target-controlled builds, tests,
processes, browsers, emulators, fuzzers, and fixtures only in an OS-enforced
sandbox with: no external network (isolated loopback only); an empty,
allowlisted environment with scratch-local `HOME`, temp and caches; a
read-only target and toolchain with writes confined to assigned `scratch/`;
and explicit low CPU, memory, process, file-size, disk, and wall-clock limits.

Do not install dependencies or let builds fetch them. Use dummy principals,
fixtures, and secrets. Never probe deployed endpoints, shared infrastructure,
production identities, other users' data, or live control planes; never test
availability against a live service, publish artifacts, alter releases, spend
paid quota, or exceed the minimum effect needed to establish a defect. If every
control cannot be enforced, do not execute target code: report the missing
sandbox capability as a needs-validation blocker with a safe validation plan.
Never expose a retained output directory, another agent's directory, the host
home, credentials, sockets, or shared services to target code.

## Setup, planning, and budget

A full audit resolves the skill directory, target repository root, stable repo
name, source ref, and an output directory outside the target (default
`~/security-audit-skill/<repo-name>/run-<N>`). The parent alone writes the run
metadata, architecture map, coverage ledger, findings, and report; hunters and
verifiers work in isolated `agents/<id>/scratch/` directories. Read
[`PLANNING.md`](PLANNING.md) before starting for the write-isolation
procedure, coverage and prior-run rules, profiles (`quick`, `standard`,
`deep`), and the strict agent-invocation budget. The identical promotion block
is repeated in [`HUNTING.md`](HUNTING.md) and
[`VALIDATION-AND-REPORTING.md`](VALIDATION-AND-REPORTING.md). An unfunded
minimum, or a scoped/`quick` run, is recorded as incomplete or partial rather
than reported as full coverage.

## Core principles

**Boundary and result.** For every candidate, name the lower-trust principal,
accepted input or action, intended control, crossed boundary, affected
principal or resource, and a concrete observed or owner-observable result. Do
not elevate a missing best practice, guessed deployment behavior, generic
parser crash, or self-impact into a finding.

**Bounded local evidence.** Static analysis establishes the source path;
sandboxed local tests resolve behavior when all controls are available: a
minimal function harness, existing unit test, small parser fixture,
dummy-tenant integration test, locally rendered configuration, or bounded
isolated-loopback client. Stop at a wrong return value, unauthorized dummy
record, sanitizer finding, policy difference, or other minimum effect. Do not
produce persistence, post-fault, or concealment material.

**Source visibility.** Deployment controls, proxy behavior, provider settings,
browser headers, identity policy, broker ACLs, packaging, and topology are real
controls. If required and absent from the repository, do not assume presence or
absence: use `needs_validation` with the exact missing fact and a safe
owner-observed or local plan.

**Priority is not certainty.** Only `confirmed` records receive severity, and
severity cannot exceed demonstrated impact. `needs_validation` is a specific
source-grounded hypothesis blocked on a fact, not a low-confidence confirmed
vulnerability; it has no severity. The severity anchors and the high/medium
discriminator are in [`PLANNING.md`](PLANNING.md#severity-anchors).

**Smallest fix.** Name the invariant the code must enforce and the narrowest
source change at the last trusted decision point. Prefer repository-relative
changes and regression tests over generic hardening. The audit describes
fixes; it does not modify target source.

## Workflow

1. **Reconnaissance**: map source, trust boundaries, local build paths,
   companions, prior evidence, and the deterministic ledger
   ([`RECONNAISSANCE.md`](RECONNAISSANCE.md)).
2. **Coverage-led hunting**: assign isolated hunters from the ledger and
   collect structured candidates ([`HUNTING.md`](HUNTING.md),
   [`ATTACK-CLASSES.md`](ATTACK-CLASSES.md), and companions).
3. **Candidate validation**: consolidate fingerprints and give every candidate
   to a fresh source verifier
   ([`VALIDATION-AND-REPORTING.md`](VALIDATION-AND-REPORTING.md)).
4. **Structured output**: write `confirmed`, `needs_validation`, and `rejected`
   records to `findings.json`; validate with
   [`report-schema.json`](report-schema.json) and
   `node validate-findings.cjs`; validate coverage with
   `node validate-coverage-ledger.cjs`.
5. **Independent record verification**: fresh agents verify final source
   claims and reconcile corrections or state changes.
6. **Target-neutral report**: derive `REPORT.md`, `FINDINGS-DETAIL.md`, and
   `NEEDS-VALIDATION.md` from final records, with no live-probe instructions.

Stop only when all Phase 6 artifacts are written and both validators pass, or
when `run_status: "incomplete"` records the exact reason and the report
discloses the gap.

## Companion files

Read [`PLANNING.md`](PLANNING.md) first for setup, coverage, profiles, severity
anchors, and budget. The phase companions (`RECONNAISSANCE.md`, `HUNTING.md`,
`ATTACK-CLASSES.md`, `VALIDATION-AND-REPORTING.md`), the ten domain `.md`
files, `report-schema.json`, and the two validators sit beside this file; each
phase names the one it needs.

## Anti-patterns

Checklist deviations as vulnerabilities; defense-in-depth advice with no
reachable boundary violation; live or shared-environment testing where bounded
local evidence suffices; guessing provider, proxy, browser, identity, or
deployment behavior not in source; treating intended same-principal authority
or self-impact as a cross-boundary result; reporting a parser or runtime effect
stronger than observed; prose-only hunter results that cannot be deduplicated
or verified; re-reporting carried same-source confirmed records or using them
as hunt exemplars; assigning severity to `needs_validation`; writing the report
before independent verification or letting prose and JSON disagree.
