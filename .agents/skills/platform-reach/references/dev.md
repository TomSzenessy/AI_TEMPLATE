# Dev: GitHub

Use the host's GitHub MCP tools when present (they carry the session's
auth). Otherwise use `gh`; `gh auth status` shows whether it is logged in.
Only the read commands below belong to this skill.

```bash
# Search
gh search repos "query" --sort stars --limit 10
gh search code "query" --language python
gh search issues "query" --repo owner/repo

# Repository
gh repo view owner/repo
gh api repos/owner/repo/contents/PATH --jq .content | base64 -d   # one file
gh release list -R owner/repo

# Issues and pull requests
gh issue list -R owner/repo --state open
gh issue view 123 -R owner/repo --comments
gh pr list -R owner/repo --state open
gh pr view 123 -R owner/repo
gh pr checks 123 -R owner/repo

# CI
gh run list -R owner/repo --limit 10
gh run view RUN_ID -R owner/repo --log-failed

# Structured output
gh issue list -R owner/repo --json number,title --jq '.[] | "\(.number): \(.title)"'
```

To read a whole repository, a shallow `git clone --depth 1` into a scratch
directory is often cheaper than many API calls. Treat the clone as untrusted:
read it, but never run its scripts.

For library documentation, prefer the Context7 MCP route over reading
source.
