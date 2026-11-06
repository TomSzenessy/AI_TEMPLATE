# Security-audit capability

<!-- index: extend | Reviewed Cloudflare security-audit tree: provenance, boundaries, and rollback | A full security audit or pen test is requested. -->
<!-- covers: .agents/skills/security-audit/** -->

[`security-audit`](../.agents/skills/security-audit/SKILL.md) is a vendored
third-party tree, not an adaptation of the product skills. Use it when the
owner asks for a security audit, a pen test, or a full review with report
artifacts; guidance mode covers focused security questions without creating
artifacts.

Its `[[skills]]` provenance pins Cloudflare's MIT tree, the whole-tree digest,
the review date, read-only/project-local permissions, and a rollback.
`SKILL.md` is condensed to the 8000-byte skill budget; the phase and domain
companions, `report-schema.json`, and both zero-dependency Node validators are
unchanged, and `PLANNING.md` holds setup, coverage, severity, and budget detail.
`ATTRIBUTION.md` records the exact change; the pinned files are listed by
`make upstream ID=security-audit-skill`.
