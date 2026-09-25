# Security policy

This repository is a template, not a hosted service. **Initialization gate:**
replace the contact and response expectations below before public launch.

- **Private security contact:** `[REQUIRED: monitored email or private channel]`
- **Private reporting route:** `[REQUIRED: platform private advisory URL or contact]`
- **Response owner:** `[REQUIRED: person/team]`

## Reporting a vulnerability

Do not open a public issue for an unpatched vulnerability, exposed secret,
personal-data incident, or exploitable dependency. Use the repository owner's
private security contact or the hosting platform's private vulnerability
reporting channel. If no private channel exists, ask the owner to establish one
before public launch.

Include a minimal description, affected version/commit, reproduction only in a
private channel, impact, and suggested mitigation. Do not include real secrets,
tokens, personal data, or destructive proof-of-concept instructions.

## Response expectations

The project owner is responsible for triage severity, containment, affected
versions, remediation, coordinated disclosure, and customer/regulatory
notification decisions. This file does not promise a response time or certify
compliance. Record verified remediation in the issue and regression suite; keep
the public issue free of exploit detail until disclosure is safe.

For a private fix's public pull request, use only the non-sensitive maintainer
attestation described in the PR template (`Security-Review:
maintainer-attested`, a named `Security-Owner`, and a maintainer-applied
`security-reviewed` label). The untrusted workflow does not query or prove
private advisory contents; keep the advisory and exploit details out of band.

## Agent and CI boundaries

Agents use least privilege and must not deploy, rotate production credentials,
delete data, or publish artifacts without explicit authorization. CI receives
read-only permissions by default; fork/untrusted changes do not receive secrets.
See [`docs/security.md`](./docs/security.md) for the engineering threat model.
