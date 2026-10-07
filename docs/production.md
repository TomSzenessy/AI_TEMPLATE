# Production readiness

<!-- index: operate | Production evidence and release boundary | A real project is being prepared for deployment or release. -->
<!-- covers: tools/kit/launch.py -->

The template is a production **governance kernel**, not a production product.
A copied project becomes production-ready only when its own facts and evidence
fill the gates below. No document, scanner, MCP response, or green test proves
universal reliability, security, privacy, accessibility, or legal compliance.

## Before implementation

Record the following in `VISION.md`, the stack decision, and the issue/WAL:

- users, outcome, non-goals, jurisdictions, and operating model;
- real product surfaces and their quality oracles;
- personal/sensitive data, providers, permissions, and security boundaries;
- deployment, cost, support, and irreversible decisions;
- the smallest capability/resource/skill that closes a named gap.

Run `make resources` before choosing an unfamiliar library, design pattern,
platform policy, or specialist skill. The registry is read-only and does not
install or authorize anything.

## Evidence required for a release

A release issue should link current evidence for each applicable row:

| Gate | Evidence |
|---|---|
| Build/reproducibility | Clean environment/bootstrap, lockfile or pinned inputs, deterministic artifact, exact revision |
| Functional quality | Focused tests, cross-surface checks, and the real user-visible artifact |
| Security | Threat model, authorization/negative tests, dependency review, secret scan, deployment permissions, vulnerability disposition |
| Privacy/data | Data inventory, retention/deletion/export behavior, provider/recipient facts, rights drill where applicable |
| Legal/platform | Final documents, counsel/provider evidence, store policy review, accessibility target where applicable |
| Reliability | Health checks, observability, SLO/alert owner, retry/idempotency behavior, capacity limits |
| Recovery | Backup/restore evidence, rollback procedure, incident owner, and communication path |
| Deployment | Staging and production-like validation, migration/rollback observation, live backend check |
| Independent review | Fresh critic, exact head/commit, unresolved trade-offs, and linked residual issues |

Each evidence row should identify:

```text
Owner:
Environment:
Date:
Revision / artifact:
Result:
Evidence type: source | test | deployed | provider | hardware | counsel
Link or local path:
```

Source/test evidence, deployed evidence, provider receipts, hardware results,
and counsel records are different evidence types; none silently substitutes for
another.

## Release sequence

1. Create or update the release issue before mutation; include acceptance and
   disclosure classification.
2. Build the smallest release candidate from pinned inputs.
3. Run `make verify` plus every active surface's real oracle.
4. Inspect the artifact and deployment state; do not stop at exit code zero.
5. Obtain an independent review and attach the exact head/artifact evidence.
6. Deploy through a protected, least-privilege environment; verify health,
   rollback, logs, metrics, and data state.
7. Publish an immutable release/digest and retain SBOM/provenance when a real
   release surface exists.
8. Reconcile the issue, manifest, resources, operations, legal/security records,
   and follow-up work.

The primary-source rationale for the MCP/resource and evidence boundary is in
[`research/mcp-production-boundaries-2026-09-25.md`](./research/mcp-production-boundaries-2026-09-25.md).

## Measure and learn

After launch, check the success metric from `VISION.md` with the
privacy-respecting measurement planned at kickoff, review error tracking and
performance against budgets, and read real user feedback (run `review-mining`
on your own product's reviews). Each confirmed problem or opportunity becomes an
issue; the slice order changes on evidence, not on opinion.

## Optional MCP and resource use

Context7-style documentation adapters, package registries, GitHub, official
platform documentation, security databases, and skill directories are optional
tools. The rules for choosing among them and trusting them — source precedence,
read-only and credential-free defaults, recorded provenance — are owned by
[`resources.md`](./resources.md).

## Definition of done

A project is ready to call itself production-ready only when its accountable
owner can show the evidence matrix, all applicable external gates are closed or
explicitly accepted, and residual risks are visible in the issue register. The
`repoctl readiness`/`make readiness` command now runs every blocking check the
registry knows (`run_checks(blocking_only=True)`), the release-gated skill
provenance check, and the public-launch prerequisites (split into one helper per
artifact — routes, `SECURITY.md`, threat model, security config, launch
evidence, data inventory — with the same rules as before); it deliberately does
**not** validate the whole matrix above. The template leaves those facts to the instantiated project.
From `phase = "private-preview"` on it also requires a fresh, passing UI
review for every web UI surface ([`building.md`](./building.md#ui-review)),
and a vision, stack decision, skill provenance, and critic evidence reviewed
within the last year; before that, their age is advice from `make garden`, never a failure.
