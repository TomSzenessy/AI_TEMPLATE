# Contributing

## Before changing code

1. Read [`AGENTS.md`](./AGENTS.md), [`docs/README.md`](./docs/README.md), and the
   nearest scoped instructions.
2. Search GitHub Issues and [`docs/ERROR_LOG.md`](./docs/ERROR_LOG.md); create or
   update the issue-backed write-ahead record using
   [`docs/ISSUE_TEMPLATE.md`](./docs/ISSUE_TEMPLATE.md). In the `regulated`
   profile, public filing requires `PUBLIC_REVIEWED=1` and
   `REVIEW_EVIDENCE=<repo-relative record>`; `agent-first` and `minimal`
   follow their profile-specific rules in `AGENTS.md`.
3. Run the relevant existing check before editing so a new failure is not
   mistaken for a pre-existing one.

## Change and review

- Keep the change scoped to the issue; separate unrelated cleanup into issues.
- Add or update a regression/contract test and durable documentation in the
  same change.
- Run focused checks, `make verify`, and the real artifact check.
- Use a fresh reviewer for broad, subjective, security-sensitive, or release
  work. Address blockers; record residual uncertainty honestly.
- Link the issue (`Fixes #N` or `Refs #N`) and include commands, observed
  results, and remaining external gates in the PR.

## Commits and issues

Small, reviewable commits with a clear intent are preferred. GitHub Issues are
the live task/status register; do not recreate that register in Markdown.

Dependabot's automated PRs are reviewed as dependency changes and skip the
human issue-reference gate; the maintainer still reviews the diff and CI.
