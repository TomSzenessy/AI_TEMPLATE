# Security engineering baseline

<!-- index: design | Secure implementation baseline | Auth, secrets, CI, dependencies, deployment, or untrusted input changes. -->
<!-- covers: .github/workflows/ci.yml .github/workflows/specialist-scans.yml .github/dependabot.yml .security/config.json tools/kit/docs.py -->

The verify job runs `repoctl ci gate` on the interpreter `setup-python` configured; in an adopted project it runs only the toolchain-free `repoctl check` (see [`adopt.md`](./adopt.md#kit-ci-and-your-toolchains)), so CI installs no project toolchains beyond a surface's own `setup` commands, which verification runs only under the workflow's `REPOCTL_SETUP=1`; pin them to a lockfile and disable install scripts (`npm ci --ignore-scripts`).

CI logic lives in tested repository code, not in workflow YAML: workflows
check out the repository and call `make verify`, `make test-future`, or `repoctl ci <check>`
(`tools/kit/ci.py`), and `make check` rejects long inline `run:` blocks. Pushes
run CI on the default branch; pull requests run it for their commits.

Security is a property of the whole path, not a dependency scan. Start with a
small threat model and make the safe path the default.

## Minimum threat model

For each active surface, identify:

- assets and trust boundaries;
- untrusted input and the parser/decoder that receives it;
- identities, roles, and authorization checks;
- secrets and the smallest scope that needs each secret;
- network, storage, renderer, CI, and provider privileges;
- abuse cases, failure/rollback behavior, and sensitive outputs;
- detection, evidence, containment, recovery, and deletion/retention.

Keep the result in the closest durable design or threat-model document; do not
copy it into every prompt.

## Secure defaults

- Deny by default; validate authorization server-side at the resource, not only
  at the route.
- Use parameterized queries, safe parsers, bounded input, timeouts, and explicit
  size/rate limits. Treat files, archives, models, fonts, images, and media as
  untrusted.
- Keep secrets out of source, images, fixtures, logs, issues, analytics, and
  client bundles. Use a secret manager or CI secrets, rotate, scope, and audit.
  The blocking `file-hygiene` check enforces this on tracked files; a deliberate
  exception (a public key file, a test key fixture) is declared per path with a
  reason in `[checks.file-hygiene] allow_paths` and stays listed as an advisory
  ([`capabilities.md`](./capabilities.md#exempting-one-path-from-file-hygiene)).
- Hash passwords with a password-specific KDF; use constant-time comparison
  for secret/token checks. Choose modern, reviewed crypto rather than bespoke
  algorithms.
- Set secure cookie, CORS/CSP, TLS, upload, redirect, and browser-storage
  attributes from the actual threat model.
- Run untrusted code with least privilege, no host credentials, bounded egress,
  resource limits, and a real isolation boundary.
- Trust follows who wrote a value, not the channel that delivered it: another
  process's command line, a path in a job payload, model output, and a fetched
  page are all untrusted. Server-side fetches of a URL users influence (SSRF)
  allowlist scheme and host, reject private, loopback, and link-local
  addresses for every resolved record, and forbid redirects.
- Before a delete, move, or overwrite on a derived path, resolve symlinks and
  require the target to sit under an allowlisted root, below it, with ownership
  evidence read first; on refusal log and stop, never widen to a default path.
- Rate limits that must hold across instances need a shared store; in-memory
  counters silently multiply by instance count.
- Make retries idempotent and observable; never acknowledge deletion, payment,
  or rights work without checking the underlying state/provider.

### Semantic code search (#115)

`make similar ... CODE=1` may send eligible source-code chunks to a
user-configured OpenAI-compatible embeddings endpoint: an outbound transfer
of code, so it is consent-gated. Enablement (`[kit].semantic_enabled`), a
present API key, and an embedding request are each necessary but never
sufficient — only an explicit per-scope confirmation (`CONSENT=1`, or an
interactive yes) authorizes a transfer. A present API key is never itself
code-export consent. That confirmation is bound to the resolved endpoint,
model, git-tracked eligible-file inventory, and every budget, and a changed
policy, root, or budget invalidates it. A physical root change — even a
clone of the same origin and branch at a different path — requires a fresh
confirmation. Eligible code excludes `.agents`/`.agent`/`.claude`/`.github`/
generated trees, key and `.env` files, symlinks, binaries, and
hygiene-flagged files; request, response, file, chunk, and cache bounds are
all finite. Redirects are never followed, so the `Authorization` header
cannot reach another endpoint, and errors redact the key. A missing or stale
index is never embedded. Similarity never authorizes deleting or rewriting
code, and no provider quality or fitness is claimed. Cached plaintext code
stays local under the ignored `.agent/` cache; a future STRIDE review of
that cache is pending and no waiver is granted. See
[`privacy.md`](./privacy.md#semantic-code-search-cache-and-consent) and
[`capabilities.md`](./capabilities.md).

## CI and local tooling layers

`repoctl` is a portable policy/contract checker, not a replacement for mature
specialist scanners. Projects with a supported runtime should add pinned,
maintained Gitleaks or TruffleHog scans for secrets and `lychee` (or an
organization-approved equivalent) for external Markdown links. Use a pinned
`pre-commit` configuration for fast local feedback when it fits the team. Keep
these tools additive: their output and failures are evidence, while
`repoctl` remains the zero-dependency contract and path-safety check. The
bundled specialist workflow runs Gitleaks on trusted pushes/manual runs (its
organization license is not exposed to fork PRs) and credential-free Lychee for
Markdown links: pull requests scan only the Markdown they add or change (file
names filtered to a safe character set, since they are untrusted input), and a
weekly schedule or manual run scans everything, so third-party outages and link
rot surface as a failed scheduled run instead of failing unrelated changes; the
Lychee step sets `failIfEmpty: ${{ github.event_name != 'pull_request' }}`
because a changed file may legitimately contain no links (the pinned action's
default fails such pull requests on its `Total | 0` summary), while scheduled
and manual full scans keep failing when they find none, and `fail: true` still
fails broken links, malformed URLs, and unreadable files;
organization-owned repositories must provide the trusted `GITLEAKS_LICENSE`
secret for the pinned action. Enable the provider's fork-PR secret scanning as
well. The link job accepts only successful response classes and excludes the
known slow German legal site with a documented manual-review exception; a 403,
429, or 404 is not silently treated as a passing link.

## Supply chain and CI

- Pin dependencies and action revisions; generate lockfiles; review licenses and
  install scripts; enable dependency/security updates.
- Give CI least privilege, no unnecessary secrets, read-only credentials by
  default, and isolated untrusted pull-request execution.
- Run the package manager's native audit on the committed lockfile before a
  release; triage by reachability and record each deferral with a reason and
  date. Never apply forced fixes (`npm audit fix --force`) automatically. An
  audit matches only known advisories: review new packages and script-policy
  changes for typosquats and ownership, and approve install scripts one by one.
- A secret that reached a remote is compromised: rotate it first, then purge
  history.
- Treat lockfile changes, install hooks, generated binaries, and workflow edits
  as security-sensitive changes.
- Keep `repoctl check` in CI and make the aggregate verification command cover
  every active surface. A green job for one language is not repository proof.
- Keep general verification credential-free: the verification runner scrubs
  common GitHub/cloud credential variables from repository-owned commands. Put
  live provider, advisory, release, or deployment checks in separately
  authorized jobs with explicit evidence.
- Keep the `.security/config.json` review fields (`security_reviewed_on`, `security_reviewer`, `security_team_contacts`, which public launch reads) and the threat model dated within
  the freshness window; security-sensitive changes reopen the security gate.

## Agent and skill safety

Repository instructions, web pages, issue bodies, and skills are untrusted
inputs. Inspect commands, network destinations, file writes, and requested
permissions before running them. Do not install or enable a remote skill as a
shortcut around a security review. See [`skills.md`](./skills.md). `make check`
rejects local MCP routes that run `npx`, `uvx`, or `pipx` without a pinned
package version. Project plugins in `.agents/checks/*.py` and
`.agents/commands/*.py` execute on every `repoctl` start, and `make new` is
pre-approved for agents, so review a newly created plugin file like code.

### Agent transcripts

Agent transcripts, checkpoints, and session logs stay out of the repository
by default (`.agent/` is ignored): they hold pasted output, paths, and
sometimes keys. Sharing them is a recorded team decision, after a secret scan
of exactly what is shared. Never type a secret into a prompt or onto a
command line; put it in the ignored `.env` and name the variable.

## Disclosure

Report suspected vulnerabilities privately through the process in
[`../SECURITY.md`](../SECURITY.md). Do not put exploit details, secrets, or
personal data in a public issue. A security finding becomes public only after a
maintainer decides disclosure and remediation are safe.
