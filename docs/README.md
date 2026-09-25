# Documentation index

This is the navigation layer for humans and agents. It is intentionally small:
durable knowledge lives beside its owner; live work, status, and acceptance
tracking live in [GitHub Issues](https://github.com/), not in a second Markdown
backlog.

## Start and operate

| Read | Owns | Reach for it when |
|---|---|---|
| [`START-HERE.md`](./START-HERE.md) | First-run and session orientation | A new agent or maintainer needs the shortest safe route through the project. |
| [`../AGENTS.md`](../AGENTS.md) | Agent operating contract | Any change is requested. |
| [`../project.toml`](../project.toml) | Machine-readable structure, checks, launch state, skill provenance | Adding a surface, changing verification, or checking readiness. |
| [`../VISION.md`](../VISION.md) | Accepted product direction, constraints, and success evidence | Starting a new project or making a high-impact scope decision. |
| [`ADAPTATION.md`](./ADAPTATION.md) | Lean core and capability-pack selection | Turning the template into a project without generating unnecessary structure. |
| [`STACK-DECISION.md`](./STACK-DECISION.md) | Framework/toolchain decision and rationale | Choosing a project stack or replacing an assumed tool. |
| [`../HANDOVER.template.md`](../HANDOVER.template.md) | Local session-continuation scaffold | A substantial session may need an ignored root `HANDOVER.md`. |
| [`ISSUE_TEMPLATE.md`](./ISSUE_TEMPLATE.md) | Canonical issue shape | Filing or materially updating an issue. |
| [`audit.md`](./audit.md) | Whole-repository audit protocol | The request is to find, prioritize, and file improvements without implementing them. |
| [`operations.md`](./operations.md) | Error ledger and incident loop | A bug, outage, flaky test, or operational failure occurs. |
| [`ERROR_LOG.md`](./ERROR_LOG.md) | Solved failure signatures and permanent fixes | A recurring operational failure needs a durable regression/fix record. |
| [`verification.md`](./verification.md) | Definition of done and independent quality loop | A change is ready for review or a quality claim is made. |
| [`production.md`](./production.md) | Production evidence and release boundary | A real project is being prepared for deployment or release. |
| [`handoffs/README.md`](./handoffs/README.md) | Cross-session continuity | Work must be transferred or resumed. |
| [`handoffs/TEMPLATE.md`](./handoffs/TEMPLATE.md) | Handoff record scaffold | A fresh actor needs a focused continuation record. |
| [`incidents/README.md`](./incidents/README.md) | Reviewed public incident record boundary | A public incident is promoted or a regression artifact is reviewed. |

## Design and engineering

| Read | Owns | Reach for it when |
|---|---|---|
| [`architecture/README.md`](./architecture/README.md) | Current structure, seams, and decisions | Adding a surface, changing dependencies, or locating ownership. |
| [`../CONTEXT.md`](../CONTEXT.md) | Project vocabulary | A term is ambiguous or a domain model changes. |
| [`engineering.md`](./engineering.md) | Modular design, SSOT, dependency, and cleanup rules | Code is being changed, refactored, or reviewed. |
| [`../SECURITY.md`](../SECURITY.md) | Vulnerability disclosure and security contact | A vulnerability or security-sensitive change is involved. |
| [`../.security/threat-model.md`](../.security/threat-model.md) | STRIDE threat model and accepted trust boundaries | A security-sensitive tool, CI path, or agent permission is reviewed. |
| [`security.md`](./security.md) | Product threat model and secure implementation baseline | Auth, secrets, CI, dependencies, deployment, or untrusted input changes. |
| [`../CONTRIBUTING.md`](../CONTRIBUTING.md) | Human contribution and review flow | A person or agent prepares a branch or pull request. |

## Product, privacy, and launch

| Read | Owns | Reach for it when |
|---|---|---|
| [`privacy.md`](./privacy.md) | Privacy-by-design engineering and rights workflow | Personal data, telemetry, cookies, retention, or user rights exist. |
| [`legal/README.md`](./legal/README.md) | Jurisdiction and counsel gate | Public terms, privacy notice, Impressum, cookies, or launch copy is drafted. |
| [`legal/data-inventory.md`](./legal/data-inventory.md) | Factual data-flow inventory | A data field, vendor, retention period, or transfer is added. |
| [`legal/privacy-notice.template.md`](./legal/privacy-notice.template.md) | Draft notice scaffold | A public privacy notice is prepared for factual completion and review. |
| [`legal/terms.template.md`](./legal/terms.template.md) | Draft terms scaffold | Public terms are prepared for factual completion and review. |
| [`legal/impressum.template.md`](./legal/impressum.template.md) | Draft provider-information scaffold | A public operator notice is required. |
| [`legal/cookies.template.md`](./legal/cookies.template.md) | Browser-storage inventory scaffold | Cookies, local storage, pixels, or embeds are introduced. |

## Extensibility and evidence

| Read | Owns | Reach for it when |
|---|---|---|
| [`../resources.toml`](../resources.toml) | Machine-readable read-only resource/MCP routes | An agent needs validated current source or documentation starting points. |
| [`resources.md`](./resources.md) | Primary docs, examples, licenses, and platform/legal-risk routing | A task needs a capability, code style, example, or external gate not owned by the kernel. |
| [`skills.md`](./skills.md) | Safe skill discovery and provenance | A task needs a capability that the repository does not provide. |
| [`adr/README.md`](./adr/README.md) | Architecture decision records | A hard-to-reverse, surprising trade-off is made. |
| [`adr/0001-issue-backed-write-ahead.md`](./adr/0001-issue-backed-write-ahead.md) | Accepted WAL and documentation-boundary decision | The agent needs the rationale for issue-backed continuity. |
| [`research/agentic-repository-baselines.md`](./research/agentic-repository-baselines.md) | Primary-source research behind the template | Guidance, legal boundaries, or external references need provenance. |
| [`research/primary-source-hardening-2026-09-25.md`](./research/primary-source-hardening-2026-09-25.md) | Fresh hardening and adversarial pass | Reviewing new agent, CI, skill, privacy, or legal-risk controls. |
| [`research/mcp-production-boundaries-2026-09-25.md`](./research/mcp-production-boundaries-2026-09-25.md) | MCP/resource and generic production-evidence boundaries | Adding an optional documentation/resource provider or preparing a real release. |

## Durable knowledge versus live work

Keep these in GitHub Issues, with links to the durable artifacts they affect:

- bugs and reproducible defects;
- audit findings and prioritized improvements;
- planned features and refactors;
- privacy/security/compliance work until evidence closes it;
- deployment, provider, hardware, and counsel gates.

Keep only stable architecture, rationale, runbooks, legal/privacy inventories,
and reusable instructions in this tree. When a document becomes a status board,
move the status to an issue and reduce the document to its durable owner.

## Navigation recipes

- **“Where does this belong?”** Start at [`../project.toml`](../project.toml),
  then use this index and the nearest scoped `AGENTS.md`.
- **“What is broken?”** Read [`operations.md`](./operations.md), reproduce, and
  update or file an issue using [`ISSUE_TEMPLATE.md`](./ISSUE_TEMPLATE.md).
- **“Can this be removed?”** Prove callers/owners are gone, run the affected
  checks, and file an independent residual instead of deleting a live contract.
- **“Is it ready to ship?”** Read [`verification.md`](./verification.md) and
  [`production.md`](./production.md), run `make verify`, obtain a fresh-agent
  critique, and inspect the real artifact.

## Incident index

The CLI appends reviewed public incident records here; private drafts stay under
ignored `.agent/incidents/`.

<!-- repoctl:incidents -->
<!-- /repoctl:incidents -->
