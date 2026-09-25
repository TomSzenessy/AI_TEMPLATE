## Summary

<!-- What changed and why? Link the issue. -->

Fixes/Refs/Closes #<number>

For a private security fix, do not put a GHSA, private-advisory URL, exploit,
secret, or personal data in this public PR. Use the private reporting process
in [`SECURITY.md`](../SECURITY.md). A maintainer may add the non-sensitive
`security-reviewed` label and attest out of band with:
`Security-Review: maintainer-attested` and `Security-Owner: @team-or-owner`.
The workflow accepts that trusted label/association without querying private
advisory data; it does not verify exploit details.

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
