# AI_TEMPLATE
A portable GitHub repository for building a website, game, backend, native app,
Blender/3D scene, video, data product, document, or something new. It gives any
coding agent a small map, an issue-backed write-ahead record, safe defaults, and
a verification loop that keeps the repository lean as the product changes.

This is a **technical starting point**, not a promise of GDPR, legal, security,
accessibility, or performance compliance. Those claims require project-specific
facts, runtime evidence, and qualified review.

## Requirements

The governance CLI uses only the Python standard library but requires
**Python 3.11+** (`tomllib`). Node, language toolchains, Blender, FFmpeg, or
other project tools are declared by the individual project surface.

## Governance profile

The default `agent-first` profile is intentionally lean: `repoctl` owns
manifest/path safety, issue-backed intent, declared verification, and the local
review packet. Public-launch and regulated projects can set
`[governance].profile = "regulated"` to require the full issue and disclosure
record. Use native GitHub forms for human intake, Gitleaks/TruffleHog and
lychee for specialist CI, and pre-commit where the team wants local hooks.

## Start in five minutes

```bash
# In a copy of this repository:
git init
make init NAME=my-project KIND=web
# Then complete VISION.md and docs/STACK-DECISION.md, replace the license,
# owners, surfaces, and project-specific checks.
make inventory
make check
```

`make init` sets identity and phase only; it does not invent application folders
or choose a framework. The published `AI_TEMPLATE` can be reinitialized in a
copy; other already-initialized projects require an explicit manifest edit.
`make doctor` intentionally reports the license, owner, surface, and launch
gates that a real project must decide. Replace those gates in `project.toml`,
complete `VISION.md` and `docs/STACK-DECISION.md`, declare each real surface and
its verification, then rerun the doctor.

<!-- repoctl:project-readme -->
> Project initialized: **AI_TEMPLATE** (`template`). Keep this identity,
> launch state, and project-specific quick start current.

## The operating loop

```text
brief → issue-backed intent → inspect/reproduce → design seam
      → smallest implementation → declared checks → real artifact
      → fresh critic → reconcile issue/docs/manifest → close or link residual
```

`AGENTS.md` is the canonical agent contract. `CLAUDE.md`, `GEMINI.md`, and
`.github/copilot-instructions.md` are deliberately tiny host adapters that point
to it; they do not become competing instruction sources.

## Repository map

| Path | Owns |
|---|---|
| `AGENTS.md` | The short operating contract and trigger router. |
| `project.toml` | Machine-readable surfaces, quality oracles, checks, launch state, and reviewed skills. |
| `VISION.md` | Accepted product direction, constraints, success evidence, and intake questions. |
| `docs/STACK-DECISION.md` | Framework/toolchain decision and confirmation boundary. |
| `docs/README.md` | Human navigation index; every durable document is one hop away. |
| `docs/ISSUE_TEMPLATE.md` | Canonical GitHub Issue record. |
| `docs/audit.md` | Whole-repository audit and issue-filing protocol. |
| `docs/operations.md` | Reproduce → diagnose → repair → verify loop and error ledger. |
| `docs/verification.md` | Evidence ladder and independent quality loop. |
| `docs/security.md` / `SECURITY.md` | Engineering threat model and private vulnerability reporting. |
| `docs/privacy.md` / `docs/legal/` | Data inventory, rights workflow, and jurisdiction/counsel gate. |
| `docs/skills.md` | Safe skill discovery, inspection, pinning, and provenance. |
| `HANDOVER.template.md` | Concise local session-continuation record; copied to ignored `HANDOVER.md` when needed. |
| `docs/handoffs/` | Deliberate committed cross-session continuation records. |
| `.agents/skills/` | Small project-local handover, quality-loop, and audit workflows. |
| `tools/repoctl.py` | Zero-dependency structure checks, issue guard, incident creation, and review packets. |
| `.github/ISSUE_TEMPLATE/` | GitHub-native bug and improvement forms. |
| `.github/workflows/` | Least-privilege CI that runs the same verification path. |

## What “self-structuring” means here

The agent first discovers the real repository, declares only independently
owned and verifiable surfaces, and adds scoped instructions only where rules
actually differ. It keeps one owner for each changing fact, routes durable
knowledge through `docs/README.md`, and moves live tasks/status to GitHub
Issues. It can create a durable incident record when a failure needs a
regression artifact.

It does not blindly generate a framework, split a small product into
microservices, install an unverified skill, delete apparently unused code, or
publish legal text. Those are decisions with evidence and owner boundaries.

## What “self-healing” means here

The template cannot repair every unknown production problem autonomously. It
makes the repair loop observable and repeatable:

- `make check` detects manifest drift, missing docs/index entries, broken local
  links, and obvious tracked-secret hygiene failures.
- `make verify` runs the declared verification for every active surface.
- `make incident TITLE="..." SUMMARY="..."` creates a private incident draft;
  use `PUBLIC_SAFE=1` only after redaction/review to promote it to tracked docs.
- `make issue ...` validates an issue and refuses exact GitHub duplicates.
- `make review-packet ISSUE_FILE=...` gives a fresh critic an independent,
  bounded quality/spec review.
- CI repeats the checks with least privilege and pinned action revisions.

A green check never substitutes for observing the real rendered artifact,
persisted state, deployed provider, hardware, or counsel evidence.

## Independent quality loop

For substantial work, the agent may fan out bounded builder tasks by surface,
then give a fresh critic the original acceptance criteria and the real output.
This generalizes the useful Matt Shumer “fan out, harsh critic, iterate” pattern
without pretending that “perfect” is measurable. Visual work uses rendered
comparisons; games use play/performance traces; backends use real state and
failure paths; video/3D use reproducible renders and playback/frame checks.
After three focused iterations, unresolved trade-offs become an issue.

## Issues instead of documentation sprawl

GitHub Issues are the live task register, write-ahead record, priority queue,
and evidence log. Use [`docs/ISSUE_TEMPLATE.md`](./docs/ISSUE_TEMPLATE.md), and
file/update one issue per independent root cause. Durable docs explain the
product, architecture, runbook, legal/privacy facts, and decisions; they do not
become a second status board.

Before filing an issue, authenticate the GitHub CLI on the host and run
`make labels` once to create/update the repository taxonomy. If the checkout has
no trusted remote, set `repository.github = "owner/name"` in `project.toml`.
Search open/closed issues and the error ledger. The `repoctl issue` command then
searches exact-title and bounded topical/path duplicates and files a classified
issue with the canonical body. In `regulated` profile, public filing requires an explicit disclosure
review and a repository-relative `REVIEW_EVIDENCE` record; in `agent-first`, the
record is optional for ordinary public-safe work but recommended for sensitive
or release work. For example:

```bash
make issue BODY=.agent/issue.md TITLE="..." TYPE=bug PRIORITY=P1 \
  AREA=web TOPIC=example-topic STATUS=triage SURFACE=web \
  PUBLIC_REVIEWED=1 REVIEW_EVIDENCE=.agent/review.md
```

It is a guardrail, not a replacement for human judgment; the adapter refuses
active security findings and active vulnerabilities stay private.

## Non-code projects

The same structure supports creative work. Declare surfaces such as `scenes`,
`renders`, `footage`, `audio`, `assets`, or `documents`, give each a reproducible
quality oracle, and keep large source media in appropriate storage rather than
accidentally committing caches or temporary exports. The agent can discover a
missing skill for Blender, video, frontend, game, or another specialty, but it
must inspect and pin the source before use.

## Research and provenance

Primary-source findings and their boundaries are recorded in
[`docs/research/agentic-repository-baselines.md`](./docs/research/agentic-repository-baselines.md).
The template incorporates current guidance from OpenAI, Anthropic, GitHub,
NIST, SLSA, OpenSSF, OWASP, W3C, OpenTelemetry, the European Commission/EDPB,
EUR-Lex, and ICO where applicable. Those sources inform defaults; they do not
certify this repository or a future project.

## Before publishing

Select and add the project license, name accountable owners, configure GitHub
branch protection/review/secret scanning/Dependabot, replace legal placeholders
with verified facts, obtain counsel review where applicable, and attach runtime,
provider, deployment, hardware, or counsel evidence to the launch issue. See
[`docs/legal/README.md`](./docs/legal/README.md) and
[`docs/verification.md`](./docs/verification.md).
