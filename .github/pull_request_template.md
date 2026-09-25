## Summary

<!-- What changed and why? Link the issue. -->

Fixes/Refs/Closes #<number>

For a private security fix, replace the public reference with a non-sensitive
`Security-Reference: GHSA-...` (or a GitHub advisory URL containing that GHSA
identifier) plus `Security-Owner: @team-or-owner`. The workflow verifies the
advisory through GitHub and checks the owner against its metadata. Do not paste
exploit details, secrets, or personal data here.

## Evidence

- [ ] Focused check:
- [ ] `make verify`
- [ ] Real artifact/state observed:
- [ ] Regression/negative case:

## Review

- [ ] Fresh critic/reviewer used for broad, subjective, security-sensitive, or release work.
- [ ] Durable docs and `project.toml` updated if behavior or structure changed.
- [ ] Secrets/personal data/provider-sensitive data redacted.
- [ ] External provider, deployment, hardware, and counsel gates are explicitly listed.
