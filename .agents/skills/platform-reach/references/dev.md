# GitHub and code

Distilled from Agent-Reach `references/dev.md` at the pin in `resources.toml`.
Read-only commands only: search, view, list, and API reads. Do not create,
fork, merge, comment, or change repository settings from this skill.

## Search

```bash
gh search repos "query" --sort stars --limit 10
gh search code "query" --language python
```

## Repository, issues, and pull requests

```bash
gh repo view owner/repo
gh issue list -R owner/repo --state open
gh issue view 123 -R owner/repo
gh pr list -R owner/repo --state open
gh pr view 123 -R owner/repo
gh pr checks 123 --repo owner/repo
```

## Actions and CI

```bash
gh run list --repo owner/repo --limit 10
gh run view <run-id> --repo owner/repo
gh run view <run-id> --repo owner/repo --log-failed
gh workflow list --repo owner/repo
```

## Releases and API reads

```bash
gh release list -R owner/repo
gh api /user
gh api repos/owner/repo
gh issue list --repo owner/repo --json number,title --jq '.[] | "\(.number): \(.title)"'
```

## Fallback

If `gh` is missing or unauthenticated, `curl -s "https://api.github.com/repos/owner/repo"`
works for public repository metadata (unauthenticated rate limits apply). Do
not ask the user for a token for a one-off public read; do not write a token to
a file or command history.

Success means the requested repository, issue, PR, or run content is present,
not merely that `gh` exited 0.
