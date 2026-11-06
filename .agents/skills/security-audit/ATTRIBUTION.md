# Attribution and review record

- **Upstream:** [cloudflare/security-audit-skill](https://github.com/cloudflare/security-audit-skill)
- **Pinned revision:** `c1c8a8c1471069fb0e188eeaff69b8e8db6564a8`
- **License:** MIT, Copyright (c) 2025-2026 Cloudflare, Inc. (full text in
  [`LICENSE`](LICENSE))
- **Reviewed:** 2026-11-05 for this kit
- **Local owner:** [`../../../docs/skills.md`](../../../docs/skills.md)
- **Provenance:** `project.toml [[skills]]`, `THIRD_PARTY_NOTICES.md`,
  `resources.toml` (`make upstream ID=security-audit-skill`)

## What changed

`SKILL.md` was condensed to this kit's 8000-byte skill budget: the operating
modes, universal execution safety, boundary/evidence principles, severity
rules, six-phase workflow, and anti-patterns are preserved; setup, coverage,
profiles, severity anchors, and the cost budget moved to `PLANNING.md`. The
phase companions, the ten domain companions, `report-schema.json`, both
validators, their tests, and the upstream license are vendored unchanged. No
upstream script runs automatically; the Node validators are invoked only
during a full audit.

## Boundaries

Read-only source work by default. Executing target code requires the
OS-enforced sandbox controls in `SKILL.md`; otherwise the result stays
`needs_validation`. The skill never probes live endpoints, installs
dependencies, or writes outside the run's output directory.

## Rollback

Remove `.agents/skills/security-audit/`, its `[[skills]]` entry, the
`security-audit-skill` resource record, and the notices row; then run
`make sync`.
