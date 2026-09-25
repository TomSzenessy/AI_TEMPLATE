# Engineering standard

The goal is compact, legible software with high leverage: a small interface
over a meaningful implementation, one owner for each changing fact, and tests
that cross the same seams as callers.

## Modularity

- Prefer a deep module over a thin pass-through wrapper. Apply the deletion test:
  if deleting a module makes complexity reappear in every caller, the module is
  earning its keep; if complexity disappears, remove it.
- Keep the interface small. Hide validation, retries, persistence, rendering,
  and provider quirks behind the seam that owns them.
- Introduce an adapter only when there are real alternatives or a test needs a
  controlled substitute. One implementation is not a reason for a framework.
- Keep domain language precise. `Surface`, `Module`, `Interface`, `Seam`, and
  `Source of truth` have the definitions in [`../CONTEXT.md`](../CONTEXT.md).
- Keep cross-surface payloads explicit and contract-tested in both directions.
  Put shared fixtures beside the contract, not in a consumer-only test.

## Single source of truth

Every value that two places could disagree about has one owner. Consumers import,
read, or generate it. When a fact must be duplicated for a human, link to the
owner and explain why the copy is not executable. Update all consumers and
migrations in the same change as the owner.

The root [`LICENSE`](../LICENSE) file is the authoritative license text.
`project.toml.license` is a human/tooling label for the selected SPDX-style
identifier; `repoctl` checks that both exist but does not infer that arbitrary
license text matches the label. Replace and review both files together; do not
claim a verified license from the manifest alone.

## Change discipline

- Make the smallest change that satisfies the issue; avoid opportunistic
  refactors, speculative abstractions, and broad formatting churn.
- Preserve public contracts unless the issue and ADR explicitly change them.
- Validate at boundaries; make invalid states fail early and clearly.
- Prefer structured logs/metrics with stable context; redact secrets and
  personal data before they reach durable logs.
- Comments explain why a non-obvious constraint exists. Code and names explain
  ordinary what.
- Delete dead code only after tracing callers, generated artifacts, deployment
  paths, and documentation. File residual cleanup as an issue when it is
  independent.

## Dependencies and change safety

A new dependency needs a recorded reason, license/provenance check, pinned
lockfile, update path, and a verification that proves the dependency's boundary
is actually needed. Prefer platform capabilities for small utilities. A new
tool or skill follows [`skills.md`](./skills.md).

## Review questions

- Is the new behavior at the right seam?
- Can a caller understand it without learning implementation details?
- Are failure modes, ordering, permissions, and observability explicit?
- Is there one authoritative owner for every new fact?
- Does the regression test fail before the fix and pass after it?
- Can the real artifact or state be inspected, not merely the return code?
