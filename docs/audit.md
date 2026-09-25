# Whole-repository audit protocol

Use this when the user asks for a broad health, quality, dead-code, scalability,
or improvement audit. The default deliverable is an **ephemeral,
evidence-backed report**; file/update GitHub Issues only when the user
explicitly authorizes that mutation. Do not turn a read-only audit into a
large unrequested refactor.

## Disclosure gate before filing

Before copying any finding into a public issue, classify it. An active
vulnerability, exposed credential, personal-data incident, or sensitive provider
detail stays in the private channel defined by [`../SECURITY.md`](../SECURITY.md)
with only the minimum redacted metadata. Do not run `make issue`, paste exploit
details, or ask a subagent to publish it. File publicly only after the owner
approves disclosure and the body has been checked for secrets, personal data,
and third-party confidential material.

## Coverage before conclusions

1. Read `AGENTS.md`, `project.toml`, this index, and all scoped instructions.
2. Inventory every tracked product/config/test/doc/creative file. Record the
   inventory scope and exclusions in the audit issue or ephemeral review packet.
3. Partition by surface and concern (behavior, security/privacy, architecture,
   tests, performance, docs, dependencies, operations). Use independent
   subagents when the host supports them; give each a disjoint scope and the
   same issue/evidence contract.
4. Reconcile the partitions against the inventory. Never claim “every line” or
   “no issue” without a coverage count and known blind spots.
5. Reproduce bugs and performance claims before ranking them. Mark hypotheses
   as hypotheses.

## Finding quality

Every finding names:

- concrete symptom and impact;
- exact paths, entry point, environment, and evidence;
- confirmed cause versus open question;
- smallest reproduction or measurement;
- proposed owner/surface and acceptance criteria with a regression/negative
  case;
- priority, confidence, and linked duplicate/parent issue.

Prefer one issue per root cause and acceptance boundary. Group repeated symptoms
under a parent issue when one owner and one fix remove the repetition. Keep style
preferences, speculative redesigns, and “could be nicer” observations out of the
queue unless they block a stated goal.

## Filing and sorting

Search existing issues and the error ledger before creating anything. In
report-only mode, stop at the evidence ledger and proposed issue titles. When
authorized to mutate the register, use the canonical
[`ISSUE_TEMPLATE.md`](./ISSUE_TEMPLATE.md) and `make issue`; update a matching
issue rather than copying it. Sort independent work by user/security impact,
then release blocker, reliability/data loss, performance/scalability,
maintainability, and cleanup. A P0/P1 label is not a substitute for evidence.

## Audit-to-implementation handoff

Do not silently implement a broad audit in the same pass. After the issues are
filed and prioritized, the issue selected for implementation becomes the
write-ahead record. Re-run its reproduction, make the smallest fix, and use the
independent quality loop in [`verification.md`](./verification.md).

For a large or subjective creative deliverable, use builder/critic agents and
real rendered evidence. For a code audit, use a fresh reviewer and focused
tests. In both cases, cap iterations, record residual disagreement, and avoid
claiming universal perfection.
