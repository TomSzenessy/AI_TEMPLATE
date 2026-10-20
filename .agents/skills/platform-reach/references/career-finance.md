# Career and finance: LinkedIn, jobs, Xueqiu

## LinkedIn

Upstream tries the MCP server first. Here the zero-install read comes first
because that server is not an approved route yet. Public pages only:

```bash
curl -s "https://r.jina.ai/https://www.linkedin.com/in/USERNAME"
curl -s "https://r.jina.ai/https://www.linkedin.com/company/NAME"
```

The full route is the LinkedIn MCP server
([stickerdaniel/linkedin-mcp-server](https://github.com/stickerdaniel/linkedin-mcp-server),
uvx `mcp-server-linkedin`), with a session the user creates once by hand:

```bash
mcporter call linkedin.get_person_profile linkedin_username="NAME" sections="experience,education"
mcporter call linkedin.get_company_profile company_name="NAME" sections="posts,jobs"
mcporter call linkedin.search_jobs keywords="software engineer" location="Remote" max_pages=2
mcporter call linkedin.search_people keywords="AI engineer" location="Berlin"
```

Upstream launches this server with `@latest`, which is unpinned. Add it
here only as a disabled, pinned route reviewed by the `skill-scout` role
([`docs/resources.md`](../../../../docs/resources.md#mcp-routes)).

People search returns personal data. Collect only what the user's purpose
needs, and keep it out of the repository (SKILL "Boundaries").

**Boss Zhipin** (Chinese job board) needs a dedicated, loopback-only Chrome
over CDP and a strict anti-bot runbook. That runbook is not reproduced here.
When the task needs it, fetch upstream `agent_reach/skill/references/career.md`
at the pin (`make upstream ID=agent-reach`), and follow its stop rules (`ENVIRONMENT_RISK`
or account-risk: stop, do not retry).

## Xueqiu (stock quotes and discussion)

Quotes may be delayed and are not investment advice.

```bash
opencli xueqiu whoami -f yaml          # checks the login session
opencli xueqiu search "NVIDIA" -f yaml
opencli xueqiu stock NVDA -f yaml      # live quote
opencli xueqiu hot -f yaml             # trending posts
opencli xueqiu hot-stock -f yaml       # trending tickers
```

Xueqiu needs a logged-in session, and HTTP 400 means the session or cookie
is the problem, not that the ticker is missing. If `whoami` works but
`stock` or `hot` fails, report an adapter or API problem, not a logout.
Success means a name, a ticker, a price or a non-empty list.
