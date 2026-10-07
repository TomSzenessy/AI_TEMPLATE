# MCP and production boundaries — 2026-09-25

**Research/access date:** 2026-09-25 UTC
**Scope:** optional MCP, documentation, and resource providers (especially Context7-style library-documentation retrieval), plus the evidence a generic production-readiness gate should require for web, native, backend, and media projects.
**Method:** current protocol specifications, official standards/guidance, and first-party provider/platform documentation. `[Fact]` means the cited source states the point. `[Template inference]` means this note recommends it for `AGENT_TEMPLATE`; it is not a universal standard or a product-specific finding.
**Repository snapshot:** the untracked local `AGENT_TEMPLATE` worktree observed during this research. Re-check the current files before implementation.

> **Boundary:** this is an engineering research note, not a security assessment, penetration test, legal opinion, accessibility audit, or certification. A provider response, green scanner, test, MCP Registry entry, or release checklist does not establish universal correctness, security, privacy, accessibility, SSDF, SLSA, WCAG, GDPR, store-policy, or other compliance. NIST SP 800-218 Rev. 1 is still a draft as accessed on 2026-09-25; the final SSDF publication is version 1.1.

## Findings

1. **An MCP route hint is not an install manifest, trust decision, or security boundary.** The host must choose whether a provider is admitted, which primitives are exposed, what data may leave, which credentials/processes/files/network destinations it may reach, and what happens on failure. This follows the MCP host role and consent requirements, and the official Registry's explicit separation of namespace authentication from code-security scanning ([MCP architecture](https://modelcontextprotocol.io/specification/2026-07-28/architecture), [MCP Registry](https://modelcontextprotocol.io/registry/about), both accessed 2026-09-25).
2. **The current MCP revision is `2026-07-28`.** It is stateless, carries protocol version and client capabilities on every request, and separates resources (application-driven), prompts (user-controlled use, server-authored content), and tools (model-controlled code execution). Roots and Sampling are deprecated; Roots is informational and not an access-control mechanism ([specification](https://modelcontextprotocol.io/specification/2026-07-28), [changelog](https://modelcontextprotocol.io/specification/2026-07-28/changelog), [deprecations](https://modelcontextprotocol.io/specification/2026-07-28/deprecated), [Roots](https://modelcontextprotocol.io/specification/2026-07-28/client/roots), accessed 2026-09-25).
3. **MCP itself cannot enforce all stated safety principles.** The host controls permissions, lifecycle, consent, authorization, and cross-server context; tool descriptions/annotations remain untrusted unless obtained from a trusted server, and returned results should be validated before entering model context ([MCP security and trust](https://modelcontextprotocol.io/specification/2026-07-28), [tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools), accessed 2026-09-25).
4. **Context7 is a useful documentation retrieval layer, not an authority layer.** Its first-party source documents `resolve-library-id` and `query-docs`, versioned IDs, direct source links, a remote MCP endpoint, and optional API keys. It also disclaims guaranteed accuracy, completeness, and security; its API backend, parser, and crawler are private. Its Data Safety page describes injection/malware detection, but that provider claim does not turn retrieved documentation into trusted instructions ([Context7 README](https://raw.githubusercontent.com/upstash/context7/master/README.md), [adding libraries](https://context7.com/docs/adding-libraries), [data safety](https://context7.com/docs/security/data-safety), accessed 2026-09-25).
5. **The production gate should be evidence-based and risk-tiered.** Source/test evidence, deployed observation, provider/hardware results, and counsel records are distinct. A release decision needs a named owner, exact source/artifact identity, environment, observation date, applicability decision, residual risk, and linked issue. `[Template inference]`
6. **Universal rows are evidence classes, not one-size-fits-all controls.** Web, native, backend, and media add conditional overlays. A row is `not applicable` only with a factual reason and owner; a high-risk or external gate cannot be hidden by a blank field. `[Template inference]`

## Current template fit

### Observed state

- `resources.toml` calls itself a read-only allowlist of starting points and assigns `mcp = "context7"` to several official library-documentation entries. It does not install or configure a server.
- `docs/resources.md` already says an MCP/documentation adapter is host-owned, should be read-only and credential-free by default, must record the consulted source/version, and must fall back to the linked official source.
- `docs/production.md` already separates build, quality, security, privacy, reliability, recovery, deployment, and independent-review evidence and states that local evidence does not replace deployed/provider/hardware/counsel evidence.
- `AGENTS.md` routes missing specialist capabilities through `make resources`, then the resource and skill policies.

### Remaining gap inferred from the research

`[Template inference]` The current `mcp = "context7"` field is useful for discovery, but a provider catalog should not also be the live host configuration or provider trust record. A concrete provider record needs, at minimum:

- purpose/trigger and owning team;
- transport and exact remote URL or local command;
- publisher/repository, package/container revision and content digest;
- negotiated MCP protocol version(s), not merely “MCP”;
- exposed primitive allowlist (`tools`, `resources`, `prompts`, extensions) and declared side effects;
- filesystem, process, environment, secret, and egress permissions enforced by the host;
- data classes allowed to leave, query minimization, retention/recipient facts, and credential class;
- timeout, response-size, rate, retry, cache, and circuit-breaker bounds;
- security/privacy review date, reviewer, update policy, rollback method, and tested fallback;
- an evidence link and expiry/freshness rule.

The catalog may remain vendor-neutral. The host should not turn the presence of a route hint into `enabled = true`, and should never accept a server description as proof of the permissions or behavior implemented by the server.

## 1. MCP facts that constrain safe routing

### 1.1 Control belongs to the host

**Facts.** MCP defines a host, a client connection to one server, and an independent server. The host manages client permissions and lifecycle, enforces policies and consent, handles authorization, and aggregates context. Servers expose resources, tools, and prompts; the protocol's design goal is that a server does not see the whole conversation or other servers. The host process is the isolation and policy boundary ([architecture](https://modelcontextprotocol.io/specification/2026-07-28/architecture), accessed 2026-09-25).

**Template inference.** A repository file or client configuration can name and constrain a provider, but it cannot grant the provider a sandbox. Filesystem, process, secret, and network permissions must be enforced by the host, CI runner, OS, container, or remote service boundary. This is also consistent with the template's existing instruction that skills and web content are untrusted data rather than authority.

### 1.2 Primitive routing must preserve the initiator model

| Primitive | Protocol fact | Safe template routing |
|---|---|---|
| **Resource** | Application-driven context selected/included by the host; identified by URI ([resources](https://modelcontextprotocol.io/specification/2026-07-28/server/resources)). | Use an explicit resource/context picker or a narrowly scoped automatic rule. Validate URI, MIME, size, and permissions. Do not confuse a resource with an executable tool. |
| **Prompt** | User-controlled use, but the **server defines the content** ([prompts](https://modelcontextprotocol.io/specification/2026-07-28/server/prompts)). | Expose as an explicit user action. Never auto-run a third-party prompt or let it rewrite host policy. Validate returned inputs/outputs. |
| **Tool** | Model-controlled code execution; the protocol does not mandate a specific interaction model ([tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)). | Place every tool in a separate permission/side-effect class. Show provider, tool, inputs, and destination; require confirmation for sensitive or mutating calls. A “read-only docs” route must not expose unrelated tools. |
| **Elicitation** | Server-initiated input requests; form mode must not request credentials/tokens, and URL mode must display the target domain and obtain consent ([elicitation](https://modelcontextprotocol.io/specification/2026-07-28/client/elicitation)). | A documentation provider should not need elicitation. If a vetted provider needs OAuth or another sensitive flow, use the provider's direct URL-mode flow and provider-specific credential store; do not collect a secret through a generic form. |
| **Roots** | Deprecated in `2026-07-28`; informational guidance, not access control ([Roots](https://modelcontextprotocol.io/specification/2026-07-28/client/roots)). | Do not use Roots as the permission boundary. Pass explicit paths/configuration and enforce them outside MCP. |
| **Sampling** | Deprecated in `2026-07-28`; new implementations should not adopt it ([Sampling](https://modelcontextprotocol.io/specification/2026-07-28/client/sampling), [deprecations](https://modelcontextprotocol.io/specification/2026-07-28/deprecated)). | Do not make a new documentation provider depend on server-initiated model sampling. Keep model/provider credentials and costs host-controlled. |

`[Template inference]` If a server exposes several primitives, admit and review them separately. A package name or Registry identity is not permission to use every tool it advertises.

### 1.3 Protocol metadata is discovery, not policy

**Facts.** Revision `2026-07-28` makes requests stateless; each request carries the protocol version and client capabilities, and clients may call `server/discover` to learn supported versions, identity, and capabilities ([changelog](https://modelcontextprotocol.io/specification/2026-07-28/changelog), [architecture](https://modelcontextprotocol.io/specification/2026-07-28/architecture), accessed 2026-09-25).

**Template inference.** Record the actual negotiated revision and server identity in provider evidence. Do not assume a vendor's “MCP” label means the latest revision, and do not silently downgrade a protected deployment without a documented compatibility decision.

### 1.4 Tool metadata is a hint, not enforcement

**Facts.** MCP says tool behavior annotations should be considered untrusted unless they come from a trusted server. Servers must validate tool inputs, enforce access control, rate-limit invocations, and sanitize outputs. Clients should show inputs, confirm sensitive operations, validate results, impose timeouts, and log tool usage ([MCP trust principles](https://modelcontextprotocol.io/specification/2026-07-28), [tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools), accessed 2026-09-25).

**Template inference.** Store a provider's declared `readOnly`/side-effect hints separately from the host's independently reviewed permission class. If a reviewed provider is trusted, its annotation can improve the UI, but it must never substitute for host authorization, sandboxing, or approval.

### 1.5 Authentication and token boundaries

**Facts.** MCP HTTP authorization is optional, but when implemented follows an OAuth 2.1-derived profile. Clients and servers use protected-resource metadata; clients include the resource indicator, servers validate audience binding, clients use PKCE, and MCP servers must not pass a client token through to an upstream API ([authorization overview](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization), [security considerations](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization/security-considerations), accessed 2026-09-25). The MCP security guide also addresses confused-deputy, SSRF, session/state-handle, local-server compromise, authorization-URL validation, and scope-minimization risks ([MCP security best practices](https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/security_best_practices), accessed 2026-09-25).

**Template inference.** A docs provider receives at most its own provider credential. Never forward a production, source-control, cloud, database, or user credential to retrieve public documentation. If authentication is needed, use a dedicated least-privilege credential, a host secret store, short lifetime where supported, rotation, and per-provider audit logs.

### 1.6 Registry presence is discovery metadata

**Facts.** The official MCP Registry is in preview. It authenticates namespaces through mechanisms such as GitHub, DNS, or HTTP ownership, but states that actual code-security scanning is delegated to package registries and downstream aggregators ([Registry overview](https://modelcontextprotocol.io/registry/about), accessed 2026-09-25).

**Template inference.** Registry publication, namespace ownership, a verified publisher, a high benchmark score, or popularity can aid discovery. None is sufficient admission evidence for a local package, remote endpoint, credential scope, retrieved content, or production action.

## 2. Context7 and Context7-style providers

### 2.1 What the first-party source establishes

**Facts.**

- Context7's current README describes two MCP documentation tools: `resolve-library-id` (name plus task query to an ID) and `query-docs` (Context7 library ID plus task query), and a remote endpoint at `https://mcp.context7.com/mcp` ([README](https://raw.githubusercontent.com/upstash/context7/master/README.md), accessed 2026-09-25).
- The CLI/API documentation exposes library IDs, version-specific IDs, source reputation/benchmark metadata, and a two-step resolve-then-query flow ([CLI](https://context7.com/docs/clients/cli), accessed 2026-09-25).
- The Search API returns snippets with the originating library and source-page link and accepts library/version/language hints ([Search API](https://context7.com/docs/search-api), accessed 2026-09-25).
- Public libraries may be submitted by anyone. Context7 indexes documentation files and, when documentation is sparse, can generate examples from source code. A verified badge and freshness mechanisms are trust/ranking/freshness signals, not proof that a snippet matches the consuming project's API or is safe to execute ([adding libraries](https://context7.com/docs/adding-libraries), [library owners](https://context7.com/docs/library-owners), [verification](https://context7.com/docs/howto/verification), [freshness](https://context7.com/docs/library-updates), accessed 2026-09-25).
- Context7 says the formulated query and library identifier—not the full prompt/code/conversation—are sent through MCP, and that queries are used for reranking/quality work and anonymously stored. It also documents anonymous CLI telemetry and an opt-out variable ([data privacy](https://context7.com/docs/security/data-privacy), [CLI telemetry](https://context7.com/docs/clients/cli), accessed 2026-09-25).
- The README explicitly disclaims guaranteed accuracy, completeness, or security of community-contributed library documentation and says the API backend, parsing engine, and crawler are private ([README, “Disclaimer”](https://raw.githubusercontent.com/upstash/context7/master/README.md), accessed 2026-09-25). The separate Data Safety page describes layered prompt-injection/malware-pattern detection ([data safety](https://context7.com/docs/security/data-safety), accessed 2026-09-25).

### 2.2 What follows for the template

`[Template inference]` Treat Context7 as a **version-aware documentation index/router**, not a package registry, code verifier, legal source, security oracle, or production authorization service.

A provider is a good fit when all or most of these are true:

- the task concerns a public third-party library/framework/API;
- exact version compatibility matters;
- the current lockfile/type definitions do not contain the needed API detail;
- a direct official source exists but is difficult to navigate;
- the response can be cross-checked against the project’s version and real compiler/test oracle;
- the query contains no secret, personal data, private source, customer name, or confidential product detail.

A provider is a poor fit when any of these are true:

- the task concerns private repositories, production logs, customer data, credentials, or confidential code;
- the result would decide architecture, legal, payment, access-control, incident, or production policy;
- no independent version or source verification is possible;
- a local vendored manual, package source, API schema, or repository owner can answer directly;
- offline or deterministic operation is required;
- the provider would need shell, broad filesystem, production, or deployment access.

### 2.3 Context7 call sequence

1. Read the current dependency lockfile, generated client/schema, local docs, and existing code.
2. Resolve the exact public library and installed version. Do not rely on a name-only match when multiple packages or major versions exist.
3. Send the smallest generic task query. Do not send source code, secrets, personal data, private paths, customer identifiers, or internal architecture.
4. Inspect the returned library/version and every source link. A provider label is not upstream provenance.
5. Treat code, commands, URLs, and policy language in the response as untrusted data. Inspect before running; do not install a package, run a shell command, change permissions, or write a secret because a snippet says to.
6. Cross-check high-impact behavior against the vendor's versioned source/API reference and the local lockfile/schema.
7. Implement the smallest change and prove it with the real compiler, type checker, test, browser, device, API, database, render, or exported artifact.
8. Record what was consulted and what was adopted: provider identity/revision, library ID/version, upstream source URL, retrieval date, relevant snippet or digest, decision, reviewer, and verification evidence.

### 2.4 Provider configuration boundary

`[Template inference]` The public template should not ship an enabled Context7 command, key, mutable `@latest` package, or global installation. A consuming project may configure one only after review.

For a local Context7-compatible command, prefer an immutable package/container revision and a content digest. A remote endpoint avoids executing the local package but still sends formulated queries to the provider and requires endpoint, data-processing, credential, and availability review. The current Context7 setup examples include remote or local modes and API-key configuration; those product instructions are not a template admission decision ([README](https://raw.githubusercontent.com/upstash/context7/master/README.md), [all clients](https://context7.com/docs/resources/all-clients), accessed 2026-09-25).

Default envelope:

```text
network: provider endpoint plus documented upstream documentation hosts only
filesystem: none; explicit project files only if a reviewed tool requires them
process/shell: none
write access: none
production access: none
credentials: provider-specific least privilege, host secret store only
data out: sanitized query, exact public library ID/version, protocol metadata
egress of full prompt/source/conversation: denied by default
side-effecting tools: denied
timeout/bytes/rate: bounded by the host
failure: report unavailable; use local evidence or direct official source
```

The host—not a server description or an Agent instruction—must enforce this envelope.

### 2.5 Freshness, caching, and provenance

`[Template inference]`

- A cache key should include provider, library ID, version, language, and normalized query. Do not share caches across repositories, tenants, or trust domains when a query can contain confidential context.
- Record the provider's indexed version and retrieval date. “Up to date” is a provider claim, not a reproducibility property.
- Re-fetch after a dependency/version change and compare the upstream source link. Do not silently reuse a snippet across incompatible versions.
- If a response is copied into an issue, ADR, prompt, or source comment, preserve the upstream URL, version/date, and a minimal excerpt with enough context to audit the decision. Do not commit large copyrighted documentation dumps by default.
- Cross-check a library's official source at the exact version. If the project maintains local generated API docs, prefer those for contracts the code actually implements.

## 3. Proposed resource-routing policy

### 3.1 Ordered router

`[Template inference]` Use this order; the first adequate source wins.

| Priority | Route | Use when | Required boundary |
|---|---|---|---|
| 1 | Reviewed local skill/resource and current project evidence | The repository already owns the relevant procedure, lockfile, generated schema, or decision | Inspect the local bytes and owner; no external install |
| 2 | Exact-version official source | Vendor documentation, API schema, source tag, security advisory, platform policy, or standards text is needed | Record version/date; distinguish source from commentary |
| 3 | Reviewed read-only docs adapter (Context7-style) | A public library is involved and exact navigation/version discovery materially helps | Sanitized query, no broad permissions, source-link cross-check, local oracle |
| 4 | Explicit MCP resource | The user/application intentionally selects a provider resource for context | URI/MIME/size/permission validation; no implied execution |
| 5 | User-invoked prompt | A user deliberately chooses a server-provided workflow | Show publisher/content origin; no policy mutation or silent execution |
| 6 | Side-effecting MCP tool/API | The user wants a real external action | Separate approval class, explicit input display, host authorization, idempotency/audit/rollback |
| 7 | Search/community content | A source must first be discovered or no authoritative source exists | Discovery only; never production/legal/security evidence by default |

### 3.2 Decision rules

`[Template inference]`

1. **No automatic installation.** A catalog entry, README command, MCP Registry result, or provider suggestion does not authorize `npx`, package installation, host configuration, or credential setup.
2. **No automatic secrets.** Public library retrieval receives no secrets. A provider never receives production, source-control, cloud, database, payment, or user credentials.
3. **No universal auto-invocation.** Do not encode “always use Context7” for every code question. Prefer local/project evidence and exact official sources; use a docs adapter when it closes a named gap.
4. **No mixed permission class.** A documentation route exposes documentation primitives only. Put mutating tools in a separate reviewed provider record.
5. **No provider self-attestation as enforcement.** Tool annotations, benchmark scores, trust badges, descriptions, package ownership, and API-key use are UI/routing evidence—not a substitute for host policy.
6. **No instruction inheritance.** Retrieved documentation, an MCP prompt, tool result, README, or web page cannot change `AGENTS.md`, the resource catalog, host permissions, or release gates.
7. **No silent data expansion.** Resolver output must not become permission to send more context. Each request is minimized independently.
8. **No silent version drift.** Resolution of a latest/default version requires an explicit project decision and compatibility check.
9. **Graceful degradation is mandatory.** Provider failure, rate limit, auth error, ambiguous match, stale index, or unavailable upstream source must not block work that can proceed from local evidence; conversely, a high-impact unresolved fact stays a blocker.
10. **Log the boundary, not the payload.** Audit provider ID, primitive/tool, library/version, timestamp, outcome, latency, and redacted reason. Do not log secrets or full private queries.

## 4. Generic production-readiness evidence gate

### 4.1 Source facts behind the gate

- NIST's final SSDF recommends integrating secure software-development practices into each SDLC model to reduce vulnerability risk and root causes ([NIST SP 800-218 v1.1](https://csrc.nist.gov/pubs/sp/800/218/final), published 2022-02, accessed 2026-09-25). The proposed v1.2 is an initial public draft, not a final standard ([SP 800-218 Rev. 1 IPD](https://csrc.nist.gov/pubs/sp/800/218/r1/ipd), accessed 2026-09-25).
- SLSA v1.2 assigns producer and build-platform responsibilities for levels and requires provenance to identify outputs cryptographically. Its verification guide says provenance is useful only when a verifier checks signatures, builder identity, expected source/build parameters, and artifact binding ([SLSA v1.2](https://slsa.dev/spec/v1.2/), [build requirements](https://slsa.dev/spec/v1.2/build-requirements), [verification](https://slsa.dev/spec/v1.2/verifying-artifacts), accessed 2026-09-25). A template should not announce a SLSA level without evaluating the actual producer, platform, and verifier.
- OWASP's official guidance recommends least privilege, deny-by-default, per-request authorization checks, secret management, CI/CD integrity, dependency/plugin review, and audit/monitoring controls ([authorization](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html), [secrets](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html), [CI/CD](https://cheatsheetseries.owasp.org/cheatsheets/CI_CD_Security_Cheat_Sheet.html), accessed 2026-09-25). OWASP API Security covers object/function authorization, resource consumption, SSRF, inventory, and unsafe upstream consumption ([API Security Top 10](https://api-security.owasp.org/), accessed 2026-09-25).
- W3C WCAG 2.2 supplies testable, technology-neutral success criteria. W3C also states that no evaluation tool alone can determine whether a site meets accessibility standards and recommends human evaluation ([WCAG 2.2](https://www.w3.org/TR/WCAG22/), [evaluation](https://www.w3.org/WAI/test-evaluate/), accessed 2026-09-25).
- Google SRE describes SLOs as reliability targets and monitoring as the basis for judging service health, diagnosing failures, and comparing behavior before/after a change ([SLOs](https://sre.google/workbook/implementing-slos/), [monitoring](https://sre.google/workbook/monitoring/), [canarying](https://sre.google/workbook/canarying-releases/), [incident response](https://sre.google/workbook/incident-response/), accessed 2026-09-25). These are engineering practices, not proof that every project needs the same SLO or canary design.
- OpenTelemetry defines traces, metrics, and logs as complementary signals for observable systems ([signals](https://opentelemetry.io/docs/concepts/signals/), accessed 2026-09-25). Instrument choice is not itself an operational gate.
- NIST SP 800-61 Rev. 3 provides incident-response recommendations integrated with CSF 2.0 ([SP 800-61r3](https://csrc.nist.gov/pubs/sp/800/61/r3/final), published 2025-04, accessed 2026-09-25). NIST SP 800-34 Rev. 1 Update 1 provides contingency-planning guidance and business-impact-analysis material ([SP 800-34r1 Update 1](https://csrc.nist.gov/pubs/sp/800/34/r1/upd1/final), accessed 2026-09-25).
- Platform-owner rules remain surface- and distribution-specific. Apple publishes App Review Guidelines, accessibility documentation, privacy manifests, and distribution guidance; Android publishes signing, testing, and Android vitals guidance ([Apple App Review](https://developer.apple.com/app-store/review/guidelines/), [Apple accessibility](https://developer.apple.com/documentation/accessibility), [Apple privacy manifests](https://developer.apple.com/documentation/bundleresources/privacy-manifest-files), [Android signing](https://developer.android.com/studio/publish/app-signing), [Android testing](https://developer.android.com/training/testing), [Android vitals](https://developer.android.com/google/play/vitals), accessed 2026-09-25).
- FFmpeg's generated online documentation tracks its newest revision, while local installed documentation should be used for an older version. FFmpeg publishes source, signatures, security advisories, and legal/licensing caveats; its protocol option documents that all protocols are allowed by default unless restricted ([documentation](https://ffmpeg.org/documentation.html), [download/source](https://ffmpeg.org/download.html), [security](https://ffmpeg.org/security.html), [legal](https://ffmpeg.org/legal.html), [protocols](https://ffmpeg.org/ffmpeg-protocols.html), accessed 2026-09-25).

### 4.2 Core evidence matrix

`[Template inference]` Every active release surface should link current evidence for each applicable row. The rows are release-governance requirements chosen for this template, not a certification checklist.

| Gate | Evidence required | Applicability/acceptance boundary |
|---|---|---|
| **Scope, owner, risk** | Named owner; users/outcome; environments; data classes; trust boundaries; critical journey; target SLO/capacity/security objectives; surface/risk classification | Required for every product. A template/bootstrap surface is not product evidence. |
| **Clean build and release identity** | Clean bootstrap/build from pinned toolchain and inputs; lockfiles or immutable inputs; exact source revision; artifact digest; documented build command/environment | Required when a buildable artifact exists. Record the evidence against the exact release candidate. |
| **Supply chain and licenses** | Dependency/action/package inventory; SBOM where the release surface warrants it; vulnerability and license results; accepted exceptions; update/rollback path | Applicable dependencies, generated binaries, containers, actions, codecs, fonts, models, and media tooling. A scanner result does not close unreviewed high-risk findings. |
| **Threat model and security review** | Current trust/data-flow diagram; abuse cases; authn/authz matrix; input/file/network boundaries; secret plan; abuse controls; security reviewer and residual issues | Required when the system handles accounts, files, external input, network services, production data, or side effects. Static documents can use a simpler threat model. |
| **Correctness and real artifact** | Type/parse/lint/static checks; focused tests; integration/contract tests; negative/failure tests; real user-visible artifact observation; cross-surface fixtures where applicable | Required for executable behavior. A green return code alone is not release evidence. |
| **Privacy and data lifecycle** | Data inventory; purposes/recipients/transfers; secrets/PII inventory; retention; export/deletion; access/deletion test; privacy/counsel gate when applicable | `N/A` only with a factual “no personal/sensitive/user data” reason. Vendor claims and policy text are not this project's evidence. |
| **Migrations and mutable state** | Forward migration; compatibility window; rollback/roll-forward procedure; representative state transition; backup before destructive change | Required for schema, stored content, queues, indexes, or persisted user state. |
| **Backup, restore, continuity** | Backup definition; restore drill in the target class; recovery time/point appropriate to impact; dependency/config restoration; owner and runbook | Required when loss/recovery matters. “Snapshots exist” is not a restore result. |
| **Reliability and capacity** | Health/readiness or equivalent; critical-path SLI/SLO; logs/metrics/traces with redaction; actionable alert owner; rate/quotas/timeouts/retry/idempotency/circuit-breaker behavior; load/capacity result | Required for hosted/shared/networked systems. A one-person local tool may record why a service SLO is not applicable while retaining deterministic artifact tests. |
| **Deployment and rollback** | Staging/production-like validation; protected least-privilege deploy identity; immutable release/digest; rollout/canary or justified alternative; health observation; tested rollback | Required for a deployed release. A canary is not universal; the evidence must match the actual distribution model. |
| **Incident and communications** | Detection path; named incident owner; severity/response procedure; user/provider/regulator communication path; postmortem learning; privacy/security disclosure route | Required for an operated/public service or team release. A template can have a runbook owner but not pretend an incident drill happened. |
| **Platform/legal/external gates** | Current platform-owner policy; final placeholder-free documents; store/provider/hardware/counsel evidence; accessibility target/evaluation where relevant | Conditional. Each external fact has its own receipt/date/environment. No derived universal claim. |
| **Independent review** | Fresh reviewer/critic; original acceptance criteria; exact source/artifact; security/privacy impact; unresolved trade-offs; linked residual issues | Required for a material production/release claim. The builder's summary is not independent evidence. |

### 4.3 Evidence record shape

`[Template inference]` A consuming project can use a small local/issue record with:

```text
gate_id
surface / release / environment
status: verified | pending | blocked | failed | not-applicable
owner / reviewer
source_revision
artifact_digest
evidence command, observation, receipt, or artifact link
observed_at
expires_at or freshness trigger
residual risk and issue
not-applicable reason and approver (when applicable)
```

Rules:

- `verified` means the evidence matches the named release candidate, environment, and observation date.
- A unit test does not satisfy a deployed, provider, hardware, or counsel gate.
- A staging observation does not silently become a production observation.
- `not-applicable` requires a reason and accountable approver; an empty cell is `pending`.
- An exception is a named, expiring risk decision with monitoring and rollback, not a compliance claim.
- A release is blocked when a required row is failed/unresolved, evidence is stale or bound to another artifact/environment, a destructive migration lacks recovery, or a critical residual has no owner.

### 4.4 Surface overlays

#### Web applications

`[Template inference]` Require:

- supported browser/runtime matrix and the critical user path observed in a real browser;
- responsive/rendering checks at declared viewports;
- no unhandled console/network failure on the critical path;
- keyboard, focus, screen-reader, contrast, zoom, and reduced-motion checks appropriate to the declared accessibility target;
- an explicit W3C evaluation record plus human review; a scanner is supporting evidence only;
- performance budgets measured on representative hardware/network;
- secure cookie/CORS/CSP/TLS/redirect/storage decisions, with third-party scripts and browser storage inventoried;
- backend failure, offline/retry, unauthorized, and degraded states observed;
- release/deployment, rollback, and CDN/cache invalidation tested when applicable.

Do not call the result “WCAG compliant” without a defined conformance target, complete evaluation scope, known limitations, and reviewer acceptance.

#### Native/mobile/desktop applications

`[Template inference]` Require:

- named supported OS/device/architecture matrix and evidence on the lowest and current target plus representative hardware;
- install, first run, upgrade, migration, uninstall/data-retention, offline, permission denial, and failure recovery where applicable;
- least-privilege permissions and a current purpose/feature mapping for each permission;
- platform accessibility and performance evidence on the real UI/runtime;
- current platform privacy/data declarations, manifests, and store disclosures;
- signed release artifacts and the platform's required notarization/installation/attestation steps;
- store/policy review and staged distribution evidence; the template cannot predict reviewer decisions;
- crash reporting/privacy, update failure, rollback/forward-fix, and support/incident ownership.

Apple and Android rules differ by target and distribution path. Cite the current platform owner; do not transplant one platform's checklist to another.

#### Backend/API/data services

`[Template inference]` Require:

- authentication and authorization matrix, including object/function/tenant negatives and server-side enforcement;
- bounded input, output encoding/serialization, file/protocol/SSRF controls, and dependency-safe parsing;
- current API/schema contract, compatibility/deprecation policy, and consumer contract tests;
- real database/queue/filesystem behavior, not a copied fake;
- transaction, concurrency, idempotency, retry, timeout, rate/quotas, and backpressure behavior;
- migrations, backup/restore, retention/deletion/export, and data reconciliation;
- host/provider limits, health/readiness, SLOs, capacity/load result, cost/resource limits, and alert ownership;
- upstream/downstream outage, partial failure, duplicate delivery, and rollback tests;
- inventory, version, documentation, and deprecation of every production endpoint/consumer where applicable.

#### Media/3D/audio/image/video pipelines

`[Template inference]` Treat source media, containers, metadata, fonts, models, decoders, filters, network protocols, and outputs as untrusted and rights-bearing inputs.

Require:

- source/asset provenance, licenses/attribution/permission, and consent/privacy facts;
- pinned renderer/encoder/decoder and exact build options, with a reproducible export recipe;
- isolated/bounded decoding/transcoding/rendering with file size, dimensions, frame count, duration, pixel, memory, CPU, time, and output limits;
- an explicit protocol/demuxer/filter allowlist when the tool supports it; never accept its permissive default implicitly;
- output container, codec, pixel/color, sample-rate/channel, duration, and metadata validation with representative media;
- actual playback/render observation plus frame, waveform, subtitle, or contact-sheet inspection;
- visual/audio quality and performance budgets for the target delivery resolution/device;
- captions, transcripts, audio description, alternative text, and localization evidence when part of the product claim;
- malicious/corrupt input and resource-exhaustion tests, with the pinned version's security advisories dispositioned;
- signed/published delivery, cache invalidation, rollback, and retention/cleanup where hosted.

FFmpeg's own legal page is explicitly not legal advice; codec/library, distribution, patent, and content rights require project-specific review. Never infer distribution rights from the ability to decode or encode a format.

## 5. Production decision logic

`[Template inference]`

1. **Classify** each release surface and its risk/data/side-effect boundaries.
2. **Fill** the core matrix and applicable overlays with evidence bound to the exact candidate.
3. **Run** local verification in a clean, least-privilege, credential-free context where possible.
4. **Observe** the real artifact and the production-like/deployed state separately.
5. **Review** independently; challenge the acceptance contract and artifact, not just the diff.
6. **Release** only when required evidence is current and residuals are owned. A limited launch can proceed only through an explicit, expiring risk decision with monitoring, user communication, and rollback.
7. **Reopen** the gate when source, dependency, configuration, data class, provider, platform policy, permission, architecture, or critical path changes.

A generic template should be able to say: “this release candidate has evidence for rows A–N in environments X/Y on date Z, with owner/reviewer R; external provider/counsel/hardware gate G remains blocked.” It should not say: “the project is compliant.”

## 6. Minimal implementation direction for the template

`[Template inference]` If the parent implementation proceeds, keep these boundaries small:

1. Keep `resources.toml` as a read-only catalog of official/community discovery sources. Preserve `mcp` only as a non-executing route hint, or replace it with a vendor-neutral `docs_provider` field.
2. Add a separate, consuming-project-owned provider/admission record for live MCP configuration. It must not be populated with secrets in the public template.
3. Add the provider fields listed in “Current template fit,” plus a `permissions`/evidence block; validate shape mechanically but do not attempt to infer safety from descriptions.
4. Route Context7-style lookup only for public library/API questions after local and official exact-version evidence; require source links, version capture, query minimization, and real project verification.
5. Keep resources, prompts, and tools in separate route/permission classes. Do not rely on deprecated Roots/Sampling for new designs.
6. Extend the production evidence matrix with the conditional web/native/backend/media overlays, or link a concise owned pack for each active surface. Do not make every project install all scanners/frameworks.
7. Add tests that prove the route does not install/execute a server, expose a secret, accept a mutable revision silently, omit a version/source, or use provider output as release evidence.
8. Recheck MCP `2026-07-28` compatibility before shipping a live config; the protocol and provider can evolve independently.

## Limitations and non-claims

- No package, MCP server, skill, browser, store, cloud account, or external provider was installed or executed for this note. This was source research plus local file inspection.
- Context7's open repository does not include its API backend, parser, or crawler. Its official web pages are first-party statements, not independent audits.
- The latest MCP revision was `2026-07-28` on the access date. A provider may negotiate an older compatible revision; record the actual result.
- Official source URLs, platform rules, pricing/limits, security advisories, and standards drafts change. Recheck them at implementation and release time.
- No source reviewed here establishes that any product, repository, provider, or template is universally secure, reliable, private, accessible, lawful, SSDF/SLSA-conformant, WCAG-conformant, or fit for a particular jurisdiction.
- This research note was intentionally the only file added. Navigation/manifest changes and implementation belong to the parent change and its own review.

## Direct source register

All URLs below were accessed **2026-09-25**. Protocol and standards version/publication dates are called out where the source exposes them.

| Area | Direct primary source |
|---|---|
| MCP current specification | [MCP specification 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28) |
| MCP architecture/trust | [Architecture](https://modelcontextprotocol.io/specification/2026-07-28/architecture), [security and trust](https://modelcontextprotocol.io/specification/2026-07-28), [tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools), [resources](https://modelcontextprotocol.io/specification/2026-07-28/server/resources), [prompts](https://modelcontextprotocol.io/specification/2026-07-28/server/prompts) |
| MCP input/security | [elicitation](https://modelcontextprotocol.io/specification/2026-07-28/client/elicitation), [authorization](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization), [authorization security](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization/security-considerations), [security best practices](https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/security_best_practices) |
| MCP lifecycle changes | [2026-07-28 changelog](https://modelcontextprotocol.io/specification/2026-07-28/changelog), [deprecated features](https://modelcontextprotocol.io/specification/2026-07-28/deprecated) |
| MCP discovery/Registry | [Official Registry overview](https://modelcontextprotocol.io/registry/about) |
| Context7 identity/tools/disclaimer | [Context7 repository README](https://raw.githubusercontent.com/upstash/context7/master/README.md) |
| Context7 retrieval model | [CLI](https://context7.com/docs/clients/cli), [Search API](https://context7.com/docs/search-api), [API guide](https://context7.com/docs/api-guide), [adding libraries](https://context7.com/docs/adding-libraries) |
| Context7 provenance/safety/privacy | [library owners](https://context7.com/docs/library-owners), [verification](https://context7.com/docs/howto/verification), [freshness](https://context7.com/docs/library-updates), [data safety](https://context7.com/docs/security/data-safety), [data privacy](https://context7.com/docs/security/data-privacy) |
| Secure SDLC | [NIST SP 800-218 v1.1 final](https://csrc.nist.gov/pubs/sp/800/218/final), [v1.2 initial public draft](https://csrc.nist.gov/pubs/sp/800/218/r1/ipd) |
| Supply-chain provenance | [SLSA v1.2](https://slsa.dev/spec/v1.2/), [build requirements](https://slsa.dev/spec/v1.2/build-requirements), [verification](https://slsa.dev/spec/v1.2/verifying-artifacts) |
| Application/API security | [OWASP Authorization](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html), [Secrets Management](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html), [CI/CD Security](https://cheatsheetseries.owasp.org/cheatsheets/CI_CD_Security_Cheat_Sheet.html), [API Security Top 10](https://api-security.owasp.org/) |
| Accessibility | [WCAG 2.2](https://www.w3.org/TR/WCAG22/), [W3C evaluation guidance](https://www.w3.org/WAI/test-evaluate/) |
| Reliability/operations | [Google SRE SLOs](https://sre.google/workbook/implementing-slos/), [monitoring](https://sre.google/workbook/monitoring/), [canarying](https://sre.google/workbook/canarying-releases/), [incident response](https://sre.google/workbook/incident-response/), [OpenTelemetry signals](https://opentelemetry.io/docs/concepts/signals/) |
| Recovery/incident | [NIST SP 800-61r3](https://csrc.nist.gov/pubs/sp/800/61/r3/final), [NIST SP 800-34r1 Update 1](https://csrc.nist.gov/pubs/sp/800/34/r1/upd1/final) |
| Native platforms | [Apple App Review](https://developer.apple.com/app-store/review/guidelines/), [Apple accessibility](https://developer.apple.com/documentation/accessibility), [Apple privacy manifests](https://developer.apple.com/documentation/bundleresources/privacy-manifest-files), [Android signing](https://developer.android.com/studio/publish/app-signing), [Android testing](https://developer.android.com/training/testing), [Android vitals](https://developer.android.com/google/play/vitals) |
| Media/FFmpeg | [documentation](https://ffmpeg.org/documentation.html), [download/source](https://ffmpeg.org/download.html), [security](https://ffmpeg.org/security.html), [legal](https://ffmpeg.org/legal.html), [protocols](https://ffmpeg.org/ffmpeg-protocols.html) |
