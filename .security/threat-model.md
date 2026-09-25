# Threat Model — Agent Template

**Last Updated:** 2026-09-25
**Version:** 1.1.0
**Methodology:** STRIDE + natural-language analysis

## 1. System overview

This repository is a portable project-governance layer, not a deployed product.
It gives coding agents a canonical instruction router, a machine-readable project
manifest, a documentation index, GitHub issue/incident adapters, and CI that
executes project-declared verification. A copied repository may add web, game,
backend, native, media, 3D, data, or document surfaces.

### Components

| Component | Purpose | Security criticality | Entry points |
|---|---|---:|---|
| `AGENTS.md` and host adapters | Route agent behavior and progressive disclosure | High | Agent context |
| `project.toml` | Own surfaces, owners, quality oracles, commands, and launch state | High | Agent and `repoctl` |
| `tools/repoctl.py` | Validate structure/docs, run declared checks, create incidents, and file issues | High | Local CLI, Make, CI |
| GitHub issue adapter | Search duplicates and create classified issues through `gh` | High | Local CLI, `gh` |
| CI workflow | Run `make verify` with a read-only token | High | GitHub Actions |
| Documentation/legal templates | Durable engineering and launch boundaries | Medium | Agent and humans |
| Host/sandbox policy | Enforce filesystem, network, identity, and approval boundaries | Critical | Agent host |

### Data flows

1. A developer or agent reads instructions, the manifest, and the documentation
   index, then edits a project working tree.
2. `make check` parses the manifest and Markdown without executing project
   verification commands.
3. `make verify` runs the repository's own tests and each active surface's
   explicitly declared command with `subprocess` argument lists and no shell.
4. An authorized agent may ask `gh` to search and create a classified issue;
   GitHub becomes the live task/evidence register.
5. CI checks out a revision and runs the same verification path with a
   least-privilege, non-persisted `GITHUB_TOKEN`.
6. A fresh reviewer or human validates the real artifact, security/privacy
   impact, and issue acceptance criteria.

## 2. Trust boundaries and security zones

### Zone A — untrusted repository and external content

Repository text, issue text, pull-request code, web pages, generated files,
skills, media, and model output are untrusted data. They can attempt prompt
injection, instruct an agent to exfiltrate data, or modify verification paths.
The agent host's OS sandbox, approval policy, identity, and network policy are
the enforcement boundary; `AGENTS.md` is guidance, not a sandbox.

### Zone B — local developer/agent workspace

The workspace is writable by the active agent but should contain no production
credentials. `repoctl` validates relative surface paths, rejects malformed
manifest fields, refuses to overwrite initialized identity, and does not invoke
a shell. It does execute verification commands intentionally; those commands are
repository code and must be inspected before execution.

### Zone C — GitHub integration

`gh` inherits the operator's host identity. Issue search is read-only; issue
creation and label synchronization are explicit mutations. Duplicate checks,
canonical headings, and classification reduce accidental issue spam but do not
replace repository permissions or human review.

### Zone D — CI and external providers

GitHub Actions receives repository code from the event ref. The workflow uses
`contents: read`, an ephemeral hosted runner, a pinned checkout action, and
`persist-credentials: false`; untrusted pull requests receive no repository
secrets. A future deployment workflow must add separate environments, OIDC or
short-lived credentials, protected refs, and human approval.

## 3. Attack surface and assets

### Local command surface

- `repoctl init` writes three bounded manifest fields after validating the name
  and refusing a second initialization.
- `repoctl incident` writes a new file under `docs/incidents` and refuses an
  existing path; title/summary are local operator input and must be redacted.
- `repoctl issue` reads a body file, searches GitHub, and creates an issue with
  validated labels; security findings require an explicit disclosure-review
  flag.
- `repoctl labels --sync` mutates GitHub labels with `--force`; run it only from
  an authorized repository after reviewing `.github/issue-labels.json`.
- `repoctl verify` executes manifest-declared commands with a 30-minute command
  timeout. This is an intentional code-execution seam, not a security boundary.

### Files and paths

- Surface paths reject absolute paths and `..` traversal.
- Documentation links are checked for local existence; external URLs are not
  fetched or trusted.
- Secret hygiene rejects tracked `.env`, private-key files, and common token
  patterns. It is a heuristic, not a complete secret scanner.

### CI and supply chain

- GitHub Actions are pinned to full commit SHAs; specialist scanner actions run
  on trusted pushes/manual runs and require the documented organization
  license secret where applicable.
- Dependabot watches GitHub Actions; projects add language ecosystems when they
  add lockfiles.
- The template has no application dependency manifest or runtime service.

### Critical assets

| Asset | Sensitivity | Required protection |
|---|---|---|
| Agent/host credentials and tokens | Critical | Never commit/log; host secret manager, short-lived identity, rotation |
| GitHub write identity | Critical | Explicit issue/label actions, protected branches, human review |
| Product source and verification commands | High | Protected review, least privilege, pinned dependencies |
| Personal data in future project surfaces | High | Inventory, minimization, rights/retention workflow, counsel gate |
| Issue/incident evidence | Medium/High | Redaction, access control, no raw secrets or exports |
| Legal and privacy drafts | High public-trust risk | Factual completion, version control, counsel approval |

## 4. STRIDE analysis

### Spoofing

- **Risk:** an agent or developer follows instructions from an untrusted issue,
  skill, or web page and acts as a privileged identity.
- **Mitigation:** host sandbox/approval policy, explicit trust rule, no
  credentials in repository, private security disclosure, explicit `gh` actions.
- **Residual:** a user with local authority can always misuse their own agent;
  this is an accepted host responsibility.

### Tampering

- **Risk:** a malicious manifest or verification command executes code, changes
  the working tree, or tampers with a generated artifact.
- **Mitigation:** repository code is inspectable; `subprocess` uses argument
  lists without a shell; paths are bounded; CI is read-only and ephemeral;
  independent review and protected branches are required for real projects.
- **Residual:** any build system executes project code. The template cannot make
  an untrusted repository safe to run locally; users must inspect it first.

### Repudiation

- **Risk:** an agent changes code, files no issue, or claims verification without
  attributable evidence.
- **Mitigation:** issue-backed write-ahead record, commits/PR links, incident
  records, external critic packet, and typed evidence categories.
- **Residual:** GitHub identity, host audit logs, and branch protection must be
  configured by the project owner.

### Information disclosure

- **Risk:** secrets or personal data enter prompts, issue bodies, incident
  files, logs, CI artifacts, or third-party skills.
- **Mitigation:** ignore rules, secret-pattern gate, redaction instructions,
  private security route, no production credentials, and data inventory/rights
  workflow.
- **Residual:** regex detection cannot recognize every secret or personal datum;
  human review remains mandatory.

### Denial of service

- **Risk:** expensive verification, recursive commands, unbounded issue searches,
  or malicious PR code consumes CI/host resources.
- **Mitigation:** no recursive aggregate command, 30-minute subprocess timeout,
  30-minute CI job, bounded issue search, concurrency cancellation, and explicit
  dependency/skill admission.
- **Residual:** a project can declare expensive commands; owners must budget and
  monitor them.

### Elevation of privilege

- **Risk:** an issue, skill, or agent uses `gh`, a shell, or a manifest command
  to obtain merge, deployment, label, or secret authority.
- **Mitigation:** explicit mutations, no default deployment authority, host
  approvals, read-only CI, protected environments for future deploys, and
  human review for high-impact actions.
- **Residual:** the CLI inherits the caller's GitHub permissions; repository
  settings and host policy are mandatory controls.

## 5. Vulnerability pattern library

### Command execution

```python
# Unsafe: shell interpolation
subprocess.run(f"make {user_input}", shell=True)

# Safe for this template: argument list, repository command still requires review
subprocess.run(["make", "verify"], shell=False)
```

### Path handling

```python
# Unsafe
(root / user_path).write_text(content)

# Safer boundary in this template
if Path(value).is_absolute() or ".." in Path(value).parts:
    raise ValueError("path must stay inside the repository")
```

### Secret hygiene

A scanner finding is a lead, not proof. Confirm the file is tracked, inspect the
value's origin, revoke/rotate if real, and record only redacted evidence.

### Prompt/supply-chain injection

External text can claim to be an operator instruction. The safe response is to
treat it as data, check the canonical issue/manifest/host policy, inspect any
skill or command, and ask for human authorization for high-impact effects.

## 6. Security testing strategy

| Check | Frequency | Evidence |
|---|---|---|
| `python3 -m unittest discover -s tools/tests -p 'test_*.py'` | Every change | 28 CLI/profile/form/security behavior tests |
| `make check` | Every change/CI | Manifest, index, links, skill provenance, hygiene |
| `make verify` | Before completion/CI | Declared surface commands and real checks |
| YAML/JSON parsing | Configuration change | Parser output and CI review |
| Dependency/security updates | Weekly/project setup | Dependabot and lockfile review |
| Independent security review | Security-sensitive/release change | `.security/` report and linked issue |
| Runtime artifact inspection | Every user-facing change | Screenshot/render/API/state evidence |

## 7. Assumptions and accepted risks

1. The project owner configures protected branches, required reviews, secret
   scanning, vulnerability alerts, and a private security contact.
2. The agent host enforces workspace/network/identity boundaries outside this
   repository; prompt text is not treated as a sandbox.
3. Running `make verify` executes repository-owned code. The operator inspects
   untrusted repositories and manifest commands before running them.
4. GitHub CLI mutations inherit the operator's permissions; duplicate checks and
   labels are guardrails, not authorization.
5. The hygiene scanner is intentionally small and may miss secrets or flag
   examples; it never replaces a dedicated secret scanner.
6. Legal/privacy templates are drafting aids and never establish compliance.

## 8. Changelog

### 1.1.0 — 2026-08-25

- Added vision/stack intake and lean capability-pack boundaries.
- Added profile-aware issue/review contracts, dynamic skill discovery guidance,
  pinned specialist CI scans, and stronger path/provenance gates.

### 1.0.0 — 2026-08-25

- Initial STRIDE model for the portable template and its agent/CI/GitHub seams.
- Added explicit accepted risks for repository command execution and inherited
  GitHub authority.
